"""
Subscription management module for VPN Bot

This module handles subscription activation, expiration, and token generation.
"""
import base64
import json
import hmac
import hashlib
import time
import logging
from typing import Optional, List, Dict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Servers
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

# Secret key for HMAC token generation
# Load from environment variable
import os
SECRET_KEY = os.getenv("SUBSCRIPTION_SECRET_KEY", "vpn-bot-subscription-secret-key-change-in-production")

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


# ==================== SUBSCRIPTION ACTIVATION ====================

async def activate_subscription(user_id: int, include_outline: bool = False) -> Optional[str]:
    """
    Activate subscription: create/enable keys on ALL servers

    This function:
    1. Gets all active servers (VLESS + Shadowsocks, optionally Outline)
    2. Creates new keys or enables existing ones on each server
    3. Sets subscription_active = true
    4. Generates/returns subscription token

    Args:
        user_id: User's telegram ID (tgid)
        include_outline: If True, also activate Outline keys (default: False)

    Returns:
        subscription_token or None if error
    """
    log.info(f"[Subscription] Activating for user {user_id} (include_outline={include_outline})")

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

            log.info(f"[Subscription] Found {len(servers)} servers for user {user_id}")

            # 3. Create/enable keys on each server
            success_count = 0
            error_count = 0

            for server in servers:
                try:
                    server_manager = ServerManager(server)
                    await server_manager.login()

                    # Check if key already exists on server
                    existing_client = await server_manager.get_user(user_id)

                    if not existing_client:
                        # Create new key
                        log.debug(f"[Subscription] Creating key for user {user_id} on server {server.id} ({server.name})")
                        result = await server_manager.add_client(user_id)

                        if result is not False:
                            success_count += 1
                            # Increment server space counter
                            server.space += 1
                        else:
                            error_count += 1
                            log.error(f"[Subscription] Failed to create key on server {server.id}")
                    else:
                        # Key exists, enable it
                        log.debug(f"[Subscription] Enabling key for user {user_id} on server {server.id} ({server.name})")
                        result = await server_manager.enable_client(user_id)

                        if result:
                            success_count += 1
                        else:
                            error_count += 1
                            log.error(f"[Subscription] Failed to enable key on server {server.id}")

                except Exception as e:
                    error_count += 1
                    log.error(f"[Subscription] Error on server {server.id}: {e}")
                    continue

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
                f"{success_count} success, {error_count} errors"
            )

            return token

        except Exception as e:
            log.error(f"[Subscription] Failed to activate for user {user_id}: {e}")
            await db.rollback()
            return None


# ==================== SUBSCRIPTION EXPIRATION ====================

async def expire_subscription(user_id: int) -> bool:
    """
    Expire subscription: disable keys on ALL servers

    This function:
    1. Gets all servers where user has keys
    2. Disables keys on each server (does NOT delete them)
    3. Sets subscription_active = false

    Args:
        user_id: User's telegram ID (tgid)

    Returns:
        True if successful, False if there were errors
    """
    log.info(f"[Subscription] Expiring for user {user_id}")

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

            # 3. Disable keys on each server
            success_count = 0
            error_count = 0

            for server in user_servers:
                try:
                    server_manager = ServerManager(server)
                    await server_manager.login()

                    result = await server_manager.disable_client(user_id)

                    if result:
                        success_count += 1
                        log.debug(f"[Subscription] Disabled key for user {user_id} on server {server.id}")
                    else:
                        error_count += 1
                        log.error(f"[Subscription] Failed to disable key on server {server.id}")

                except Exception as e:
                    error_count += 1
                    log.error(f"[Subscription] Error disabling on server {server.id}: {e}")
                    continue

            # 4. Set subscription_active = false (even if there were errors)
            user.subscription_active = False
            await db.commit()

            log.info(
                f"[Subscription] ✅ Expired for user {user_id}: "
                f"{success_count} success, {error_count} errors"
            )

            return error_count == 0

        except Exception as e:
            log.error(f"[Subscription] Failed to expire for user {user_id}: {e}")
            await db.rollback()
            return False


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
