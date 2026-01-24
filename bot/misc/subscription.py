"""
Subscription management module for VPN Bot

This module handles subscription activation, expiration, and token generation.
"""
import asyncio
import base64
import json
import hmac
import hashlib
import time
import logging
import aiohttp
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Servers
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

# Retry settings for disable operations
DISABLE_MAX_RETRIES = 3
DISABLE_RETRY_DELAY = 5  # seconds

# Secret key for HMAC token generation
# Load from environment variable
import os
SECRET_KEY = os.getenv("SUBSCRIPTION_SECRET_KEY", "vpn-bot-subscription-secret-key-change-in-production")

# ==================== LOCK MANAGEMENT ====================

# User-level locks to prevent race conditions when activating/expiring subscriptions
# Key: user_id (telegram ID), Value: asyncio.Lock
_user_locks: Dict[int, asyncio.Lock] = {}
_user_locks_lock = asyncio.Lock()  # Lock for accessing _user_locks dict


async def _get_user_lock(user_id: int) -> asyncio.Lock:
    """
    Get or create a lock for a specific user.
    Thread-safe access to user locks dictionary.
    """
    async with _user_locks_lock:
        if user_id not in _user_locks:
            _user_locks[user_id] = asyncio.Lock()
        return _user_locks[user_id]


async def _notify_admins_disable_failed(user_id: int, failed_servers: List[Tuple[int, str]]) -> None:
    """
    Send Telegram notification to admins about failed disable operations.

    Args:
        user_id: User's telegram ID
        failed_servers: List of (server_id, server_name) tuples that failed
    """
    try:
        bot_token = os.getenv("TG_TOKEN")
        admin_ids_str = os.getenv("ADMINS_IDS", "")

        if not bot_token or not admin_ids_str:
            log.error("[Subscription] Cannot notify admins: TG_TOKEN or ADMINS_IDS not set")
            return

        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

        # Format message
        servers_list = "\n".join([f"   • {name} (ID={sid})" for sid, name in failed_servers])
        message = (
            f"⚠️ <b>Неполная блокировка пользователя!</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"❌ Не удалось отключить ({len(failed_servers)} серверов):\n"
            f"{servers_list}\n\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🔧 Требуется ручная проверка!"
        )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        async with aiohttp.ClientSession() as session:
            for admin_id in admin_ids:
                try:
                    await session.post(url, json={
                        "chat_id": admin_id,
                        "text": message,
                        "parse_mode": "HTML"
                    })
                except Exception as e:
                    log.error(f"[Subscription] Failed to notify admin {admin_id}: {e}")

        log.info(f"[Subscription] Notified admins about failed disable for user {user_id}")

    except Exception as e:
        log.error(f"[Subscription] Error sending admin notification: {e}")


async def _cleanup_user_lock(user_id: int):
    """
    Remove user lock from dictionary to prevent memory leaks.
    Called after operation completes and lock is released.
    """
    async with _user_locks_lock:
        if user_id in _user_locks and not _user_locks[user_id].locked():
            del _user_locks[user_id]

# Maximum users per server (from config)
MAX_PEOPLE_SERVER = CONFIG.max_people_server if hasattr(CONFIG, 'max_people_server') else 100


# ==================== TOKEN GENERATION ====================

def generate_subscription_token(user_id: int) -> str:
    """
    Generate HMAC-signed subscription token

    Token format: base64(json_payload + "|" + hmac_signature)

    Args:
        user_id: User's internal database ID

    Returns:
        Base64-encoded token string
    """
    # Token data
    data = {
        "user_id": user_id,
        "expire": int(time.time()) + (365 * 24 * 60 * 60),  # 1 year
        "created": int(time.time())
    }

    # JSON string
    payload = json.dumps(data)

    # HMAC signature (SHA256, first 16 characters)
    signature = hmac.new(
        SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:16]

    # Combine payload and signature
    token_data = f"{payload}|{signature}"

    # Base64 encode
    token = base64.urlsafe_b64encode(token_data.encode()).decode()

    log.debug(f"[Subscription] Generated token for user {user_id}")
    return token


def verify_subscription_token(token: str) -> Optional[int]:
    """
    Verify subscription token and return user_id

    Args:
        token: Base64-encoded token string

    Returns:
        user_id if token is valid, None otherwise
    """
    try:
        # Base64 decode
        decoded = base64.urlsafe_b64decode(token.encode()).decode()

        # Split payload and signature
        payload, signature = decoded.split('|')

        # Verify signature
        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:16]

        if signature != expected_signature:
            log.warning(f"[Subscription] Invalid token signature")
            return None

        # Parse data
        data = json.loads(payload)

        # Check expiration
        if time.time() > data['expire']:
            log.info(f"[Subscription] Token expired for user {data['user_id']}")
            return None

        return data['user_id']

    except Exception as e:
        log.error(f"[Subscription] Token verification failed: {e}")
        return None


# ==================== ACTIVATION ALERTS ====================

async def _send_activation_alert(user_id: int, username: str, success_count: int, error_count: int, servers, results):
    """Send alert to admins when subscription activation has errors.

    Args:
        servers: List of dicts with 'id' and 'name' keys (NOT SQLAlchemy objects!)
    """
    try:
        from aiogram import Bot
        from bot.misc.util import CONFIG

        # Build error details
        failed_servers = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                server_name = servers[i]['name'] if i < len(servers) else f"Server #{i}"
                failed_servers.append(f"❌ {server_name}: {str(res)[:50]}")
            elif not res[1]:  # success = False
                srv = next((s for s in servers if s['id'] == res[0]), None)
                if srv:
                    failed_servers.append(f"❌ {srv['name']}: Failed")
        
        username_str = f"@{username}" if username else "без username"
        
        message = f"""⚠️ Ошибка создания ключей

👤 Пользователь: {username_str}
🆔 ID: {user_id}

📊 Результат: {success_count} ✅ / {error_count} ❌

Проблемные серверы:
""" + "\n".join(failed_servers[:10])
        
        if len(failed_servers) > 10:
            message += f"\n... и ещё {len(failed_servers) - 10}"
        
        bot = Bot(token=CONFIG.tg_token)
        try:
            for admin_id in CONFIG.admins_ids:
                try:
                    await bot.send_message(admin_id, message)
                except Exception as e:
                    log.error(f"[Subscription Alert] Failed to send to admin {admin_id}: {e}")
        finally:
            await bot.session.close()
            
    except Exception as e:
        log.error(f"[Subscription Alert] Error sending alert: {e}")


async def _send_server_limit_alert(server_name: str, server_id: int, current_space: int, max_limit: int):
    """Send alert to admins when server reaches its key limit.

    Args:
        server_name: Name of the server
        server_id: Server ID in database
        current_space: Current number of keys on server
        max_limit: Maximum allowed keys
    """
    try:
        from aiogram import Bot
        from bot.misc.util import CONFIG

        message = f"""🚨 Сервер достиг лимита ключей!

🖥️ Сервер: {server_name}
🆔 ID: {server_id}

📊 Заполненность: {current_space}/{max_limit} ({round(current_space/max_limit*100)}%)

⚠️ Новые пользователи НЕ смогут получить ключи на этом сервере.

💡 Рекомендации:
• Добавить новый сервер
• Увеличить лимит MAX_PEOPLE_SERVER в .env
• Очистить неактивных пользователей"""

        bot = Bot(token=CONFIG.tg_token)
        try:
            for admin_id in CONFIG.admins_ids:
                try:
                    await bot.send_message(admin_id, message)
                except Exception as e:
                    log.error(f"[Server Limit Alert] Failed to send to admin {admin_id}: {e}")
        finally:
            await bot.session.close()

        log.warning(f"[Server Limit] Server {server_name} (id={server_id}) reached limit: {current_space}/{max_limit}")

    except Exception as e:
        log.error(f"[Server Limit Alert] Error sending alert: {e}")


# ==================== SUBSCRIPTION ACTIVATION ====================

async def _activate_on_server(server, user_id: int) -> tuple:
    """
    Helper function to activate subscription on a single server.
    Returns: (server_id, success: bool, is_new_key: bool)
    """
    try:
        server_manager = ServerManager(server)
        await server_manager.login()

        # Try to delete old key (without suffix) if exists
        # This cleans up legacy keys from old system
        try:
            await server_manager.client.xui.delete_client(
                inbound_id=server_manager.client.inbound_id,
                email=str(user_id)  # Old format without suffix
            )
            log.debug(f"[Subscription] Deleted old key for user {user_id} on server {server.id}")
        except Exception:
            pass  # Old key doesn't exist, that's fine

        # Check if key already exists on server (new format with suffix)
        existing_client = await server_manager.get_user(user_id)

        if not existing_client:
            # Create new key
            log.debug(f"[Subscription] Creating key for user {user_id} on server {server.id} ({server.name})")
            result = await server_manager.add_client(user_id)

            if result is not False:
                return (server.id, True, True)  # success, new key created
            else:
                log.error(f"[Subscription] Failed to create key on server {server.id}")
                return (server.id, False, False)
        else:
            # Key exists, enable it
            log.debug(f"[Subscription] Enabling key for user {user_id} on server {server.id} ({server.name})")
            result = await server_manager.enable_client(user_id)

            if result:
                return (server.id, True, False)  # success, existing key enabled
            else:
                log.error(f"[Subscription] Failed to enable key on server {server.id}")
                return (server.id, False, False)

    except Exception as e:
        log.error(f"[Subscription] Error on server {server.id}: {e}")
        return (server.id, False, False)


async def activate_subscription(user_id: int, include_outline: bool = False) -> Optional[str]:
    """
    Activate subscription: create/enable keys on ALL servers IN PARALLEL

    This function:
    1. Gets all active servers (VLESS + Shadowsocks, optionally Outline)
    2. Creates new keys or enables existing ones on each server (PARALLEL)
    3. Sets subscription_active = true
    4. Generates/returns subscription token

    Uses user-level locking to prevent race conditions when user clicks
    activation button multiple times rapidly.

    Args:
        user_id: User's telegram ID (tgid)
        include_outline: If True, also activate Outline keys (default: False)

    Returns:
        subscription_token or None if error
    """
    # Get user-specific lock to prevent race conditions
    user_lock = await _get_user_lock(user_id)

    # Try to acquire lock without waiting
    if user_lock.locked():
        log.warning(f"[Subscription] Activation already in progress for user {user_id}, skipping duplicate request")
        return None

    async with user_lock:
        log.info(f"[Subscription] Activating for user {user_id} (include_outline={include_outline})")

        try:
            async with AsyncSession(autoflush=False, bind=engine()) as db:
                try:
                    # 1. Get user from database
                    statement = select(Persons).filter(Persons.tgid == user_id)
                    result = await db.execute(statement)
                    user = result.scalar_one_or_none()

                    if not user:
                        log.error(f"[Subscription] User {user_id} not found")
                        return None

                    # 2. Get ALL active servers (VLESS + Shadowsocks, optionally Outline)
                    # NOTE: Outline (type_vpn=0) is normally handled separately via "🔑 Outline VPN" button
                    # But admin panel can force include_outline=True to activate all protocols
                    if include_outline:
                        vpn_types = [0, 1, 2]  # Outline, VLESS and Shadowsocks
                    else:
                        vpn_types = [1, 2]  # VLESS and Shadowsocks only

                    statement = select(Servers).filter(
                        Servers.work == True,
                        Servers.type_vpn.in_(vpn_types),
                        Servers.space < MAX_PEOPLE_SERVER
                    ).order_by(Servers.id)

                    result = await db.execute(statement)
                    servers = result.scalars().all()

                    if not servers:
                        log.warning(f"[Subscription] No available servers found")
                        return None

                    log.info(f"[Subscription] Found {len(servers)} servers for user {user_id}, activating in parallel...")

                    # 3. Create/enable keys on ALL servers IN PARALLEL
                    tasks = [_activate_on_server(server, user_id) for server in servers]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Process results
                    success_count = 0
                    error_count = 0
                    new_keys_server_ids = []

                    for res in results:
                        if isinstance(res, Exception):
                            error_count += 1
                            log.error(f"[Subscription] Parallel task exception: {res}")
                        else:
                            server_id, success, is_new_key = res
                            if success:
                                success_count += 1
                                if is_new_key:
                                    new_keys_server_ids.append(server_id)
                            else:
                                error_count += 1

                    # Update server.space for servers where new keys were created
                    # and check if any server reached its limit
                    servers_at_limit = []
                    if new_keys_server_ids:
                        for server in servers:
                            if server.id in new_keys_server_ids:
                                server.space += 1
                                # Check if server reached limit
                                if server.space >= MAX_PEOPLE_SERVER:
                                    servers_at_limit.append({
                                        'name': server.name,
                                        'id': server.id,
                                        'space': server.space
                                    })

                    # 4. Set subscription_active = true and commit all changes
                    user.subscription_active = True

                    # 5. Create/get subscription token
                    if not user.subscription_token:
                        # Generate new token using internal user.id (not tgid!)
                        token = generate_subscription_token(user.id)

                        user.subscription_token = token
                        user.subscription_created_at = datetime.now()
                        await db.commit()
                    else:
                        token = user.subscription_token
                        user.subscription_updated_at = datetime.now()
                        await db.commit()

                    log.info(
                        f"[Subscription] ✅ Activated for user {user_id}: "
                        f"{success_count} success, {error_count} errors (parallel)"
                    )

                    # Copy data for alert BEFORE leaving session context
                    alert_data = None
                    if error_count > 0:
                        alert_data = {
                            'user_id': user_id,
                            'username': str(user.username) if user.username else None,
                            'success_count': success_count,
                            'error_count': error_count,
                            'servers': [{'id': s.id, 'name': s.name} for s in servers],
                            'results': list(results)
                        }

                    # Commit and close session before creating background task
                    await db.commit()

                    # Fire-and-forget alert AFTER session is closed
                    if alert_data:
                        asyncio.create_task(_send_activation_alert(**alert_data))

                    # Send alerts for servers that reached their limit
                    for srv in servers_at_limit:
                        asyncio.create_task(_send_server_limit_alert(
                            server_name=srv['name'],
                            server_id=srv['id'],
                            current_space=srv['space'],
                            max_limit=MAX_PEOPLE_SERVER
                        ))

                    return token

                except Exception as e:
                    log.error(f"[Subscription] Failed to activate for user {user_id}: {e}")
                    await db.rollback()
                    return None
        finally:
            # Cleanup lock from dictionary to prevent memory leaks
            await _cleanup_user_lock(user_id)


# ==================== SUBSCRIPTION SYNC ====================

async def sync_subscription_keys(user_id: int) -> dict:
    """
    Sync subscription keys: create missing keys on new servers

    This function checks all active servers and creates keys
    where they don't exist yet. Used when user requests subscription URL.

    Args:
        user_id: User's telegram ID (tgid)

    Returns:
        dict with 'created' count and 'errors' count
    """
    result = {'created': 0, 'errors': 0, 'checked': 0}

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        try:
            # Get user
            statement = select(Persons).filter(Persons.tgid == user_id)
            user_result = await db.execute(statement)
            user = user_result.scalar_one_or_none()

            if not user or not user.subscription_active:
                return result

            # Get all active servers (VLESS + Shadowsocks)
            statement = select(Servers).filter(
                Servers.work == True,
                Servers.type_vpn.in_([1, 2]),
                Servers.space < MAX_PEOPLE_SERVER
            ).order_by(Servers.id)

            server_result = await db.execute(statement)
            servers = server_result.scalars().all()

            for server in servers:
                result['checked'] += 1
                try:
                    server_manager = ServerManager(server)
                    await server_manager.login()

                    # Check if key exists
                    existing_client = await server_manager.get_user(user_id)

                    if not existing_client:
                        # Create missing key
                        log.info(f"[Subscription Sync] Creating missing key for {user_id} on {server.name}")
                        create_result = await server_manager.add_client(user_id)

                        if create_result is not False:
                            result['created'] += 1
                            server.space += 1
                        else:
                            result['errors'] += 1

                except Exception as e:
                    log.error(f"[Subscription Sync] Error on server {server.id}: {e}")
                    result['errors'] += 1
                    continue

            if result['created'] > 0:
                await db.commit()
                log.info(f"[Subscription Sync] User {user_id}: created {result['created']} keys")

            return result

        except Exception as e:
            log.error(f"[Subscription Sync] Failed for user {user_id}: {e}")
            return result


# ==================== SUBSCRIPTION EXPIRATION ====================

async def expire_subscription(user_id: int) -> bool:
    """
    Expire subscription: disable keys on ALL servers

    This function:
    1. Gets all servers where user has keys
    2. Disables keys on each server (does NOT delete them)
    3. Sets subscription_active = false

    Uses user-level locking to prevent race conditions.

    Args:
        user_id: User's telegram ID (tgid)

    Returns:
        True if successful, False if there were errors
    """
    # Get user-specific lock to prevent race conditions
    user_lock = await _get_user_lock(user_id)

    # Try to acquire lock without waiting
    if user_lock.locked():
        log.warning(f"[Subscription] Expiration already in progress for user {user_id}, skipping duplicate request")
        return False

    async with user_lock:
        log.info(f"[Subscription] Expiring for user {user_id}")

        try:
            async with AsyncSession(autoflush=False, bind=engine()) as db:
                try:
                    # 1. Get user from database
                    statement = select(Persons).filter(Persons.tgid == user_id)
                    result = await db.execute(statement)
                    user = result.scalar_one_or_none()

                    if not user:
                        log.error(f"[Subscription] User {user_id} not found")
                        return False

                    # 2. Get all active servers (we'll check which ones have keys via API)
                    # NOTE: Include Outline (type_vpn=0) here for DISABLE security
                    # Outline is NOT created during activate_subscription (on-demand only)
                    # BUT must be disabled during expire for security
                    statement = select(Servers).filter(
                        Servers.work == True,
                        Servers.type_vpn.in_([0, 1, 2])  # Outline, VLESS and Shadowsocks
                    ).order_by(Servers.id)

                    result = await db.execute(statement)
                    all_servers = result.scalars().all()

                    # Filter servers where user actually has keys
                    user_servers = []
                    for server in all_servers:
                        try:
                            server_manager = ServerManager(server)
                            await server_manager.login()
                            existing_client = await server_manager.get_user(user_id)
                            if existing_client:
                                user_servers.append(server)
                        except Exception as e:
                            log.debug(f"[Subscription] Error checking server {server.id}: {e}")
                            continue

                    if not user_servers:
                        log.warning(f"[Subscription] No servers found for user {user_id}")
                        # Still set subscription_active = false
                        user.subscription_active = False
                        await db.commit()
                        return True

                    log.info(f"[Subscription] Found {len(user_servers)} servers with keys for user {user_id}")

                    # 3. Disable keys on each server with retry logic
                    success_count = 0
                    failed_servers: List[Tuple[int, str]] = []  # (server_id, server_name)

                    for server in user_servers:
                        disabled = False

                        # Try up to DISABLE_MAX_RETRIES times
                        for attempt in range(1, DISABLE_MAX_RETRIES + 1):
                            try:
                                server_manager = ServerManager(server)
                                await server_manager.login()
                                result = await server_manager.disable_client(user_id)

                                if result:
                                    disabled = True
                                    success_count += 1
                                    log.debug(f"[Subscription] Disabled key for user {user_id} on server {server.id}")
                                    break
                                else:
                                    log.warning(
                                        f"[Subscription] Disable attempt {attempt}/{DISABLE_MAX_RETRIES} "
                                        f"failed on server {server.id} ({server.name})"
                                    )

                            except Exception as e:
                                log.warning(
                                    f"[Subscription] Disable attempt {attempt}/{DISABLE_MAX_RETRIES} "
                                    f"error on server {server.id}: {e}"
                                )

                            # Wait before retry (except on last attempt)
                            if attempt < DISABLE_MAX_RETRIES:
                                await asyncio.sleep(DISABLE_RETRY_DELAY)

                        if not disabled:
                            failed_servers.append((server.id, server.name))
                            log.error(
                                f"[Subscription] Failed to disable key on server {server.id} "
                                f"({server.name}) after {DISABLE_MAX_RETRIES} attempts"
                            )

                    # 4. Set subscription_active = false (even if there were errors)
                    user.subscription_active = False
                    await db.commit()

                    log.info(
                        f"[Subscription] ✅ Expired for user {user_id}: "
                        f"{success_count} success, {len(failed_servers)} errors"
                    )

                    # 5. Notify admins if there were failures
                    if failed_servers:
                        await _notify_admins_disable_failed(user_id, failed_servers)

                    return len(failed_servers) == 0

                except Exception as e:
                    log.error(f"[Subscription] Failed to expire for user {user_id}: {e}")
                    await db.rollback()
                    return False
        finally:
            # Cleanup lock from dictionary to prevent memory leaks
            await _cleanup_user_lock(user_id)


# ==================== UTILITY FUNCTIONS ====================

async def get_user_subscription_status(user_id: int) -> Dict:
    """
    Get subscription status for user

    Args:
        user_id: User's telegram ID (tgid)

    Returns:
        Dictionary with subscription info
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        try:
            statement = select(Persons).filter(Persons.tgid == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()

            if not user:
                return {"error": "User not found"}

            return {
                "active": user.subscription_active if hasattr(user, 'subscription_active') else False,
                "token": user.subscription_token if hasattr(user, 'subscription_token') else None,
                "created_at": user.subscription_created_at if hasattr(user, 'subscription_created_at') else None,
                "updated_at": user.subscription_updated_at if hasattr(user, 'subscription_updated_at') else None,
            }

        except Exception as e:
            log.error(f"[Subscription] Failed to get status for user {user_id}: {e}")
            return {"error": str(e)}



# ==================== NEW SERVER INTEGRATION (Stage 7) ====================

async def create_keys_for_active_subscriptions_on_new_server(server_id: int) -> Dict:
    """
    Create VPN keys for all users with active subscriptions on a new server
    
    This function is called when a new server is added to automatically
    provision keys for existing subscription users.
    
    Stage 7: New Servers Integration
    
    Args:
        server_id: ID of the newly added server
        
    Returns:
        Dictionary with statistics:
        {
            "total_users": int,
            "success_count": int,
            "error_count": int,
            "errors": List[str]
        }
    """
    log.info(f"[Stage 7] Creating keys for active subscriptions on server {server_id}")
    
    stats = {
        "total_users": 0,
        "success_count": 0,
        "error_count": 0,
        "errors": []
    }
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        try:
            # 1. Get the new server
            statement = select(Servers).filter(Servers.id == server_id)
            result = await db.execute(statement)
            server = result.scalar_one_or_none()
            
            if not server:
                log.error(f"[Stage 7] Server {server_id} not found")
                stats["errors"].append(f"Server {server_id} not found")
                return stats
            
            # Only process VLESS and Shadowsocks servers
            # NOTE: Outline handled separately via "🔑 Outline VPN" button
            if server.type_vpn not in [1, 2]:
                log.info(f"[Stage 7] Server {server_id} is not VLESS/Shadowsocks (type={server.type_vpn}), skipping")
                return stats
            
            log.info(f"[Stage 7] Server: {server.name} (type={server.type_vpn})")
            
            # 2. Get all users with active subscriptions
            statement = select(Persons).filter(Persons.subscription_active == True)
            result = await db.execute(statement)
            active_users = result.scalars().all()
            
            stats["total_users"] = len(active_users)
            
            if not active_users:
                log.info(f"[Stage 7] No active subscriptions found")
                return stats
            
            log.info(f"[Stage 7] Found {len(active_users)} users with active subscriptions")
            
            # 3. Initialize server manager
            try:
                server_manager = ServerManager(server)
                await server_manager.login()
            except Exception as e:
                error_msg = f"Failed to connect to server {server_id}: {e}"
                log.error(f"[Stage 7] {error_msg}")
                stats["errors"].append(error_msg)
                stats["error_count"] = stats["total_users"]
                return stats
            
            # 4. Create keys for each user
            for user in active_users:
                try:
                    # Check if user already has a key on this server
                    existing_client = await server_manager.get_user(user.tgid)
                    
                    if existing_client:
                        log.debug(f"[Stage 7] User {user.tgid} already has key on server {server_id}, skipping")
                        stats["success_count"] += 1
                        continue
                    
                    # Create new key
                    result = await server_manager.add_client(user.tgid)
                    
                    if result is not False:
                        stats["success_count"] += 1
                        log.debug(f"[Stage 7] ✅ Created key for user {user.tgid} on server {server_id}")
                    else:
                        stats["error_count"] += 1
                        error_msg = f"Failed to create key for user {user.tgid}"
                        log.warning(f"[Stage 7] {error_msg}")
                        stats["errors"].append(error_msg)
                        
                except Exception as e:
                    stats["error_count"] += 1
                    error_msg = f"Error creating key for user {user.tgid}: {e}"
                    log.error(f"[Stage 7] {error_msg}")
                    stats["errors"].append(error_msg)
                    continue
            
            # 5. Update server space count
            try:
                all_clients = await server_manager.get_all_user()
                new_space = len(all_clients) if all_clients else 0
                server.space = new_space
                await db.commit()
                log.info(f"[Stage 7] Updated server {server_id} space to {new_space}")

                # Check if server reached limit after creating keys
                if new_space >= MAX_PEOPLE_SERVER:
                    asyncio.create_task(_send_server_limit_alert(
                        server_name=server.name,
                        server_id=server.id,
                        current_space=new_space,
                        max_limit=MAX_PEOPLE_SERVER
                    ))
            except Exception as e:
                log.warning(f"[Stage 7] Failed to update server space: {e}")
            
            log.info(
                f"[Stage 7] ✅ Completed for server {server_id}: "
                f"{stats['success_count']}/{stats['total_users']} success, "
                f"{stats['error_count']} errors"
            )
            
            return stats
            
        except Exception as e:
            log.error(f"[Stage 7] Unexpected error: {e}")
            stats["errors"].append(f"Unexpected error: {e}")
            return stats
