"""
Traffic Monitoring Module
Collects and aggregates traffic usage from all VPN servers.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, update, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Servers, DailyTrafficLog
from bot.misc.VPN.ServerManager import ServerManager

log = logging.getLogger(__name__)

# 500GB in bytes
DEFAULT_TRAFFIC_LIMIT = 500 * 1024 * 1024 * 1024  # 536870912000

# Количество дней до автоматического сброса трафика
TRAFFIC_RESET_DAYS = 30

# Cache for server traffic data
# Key: server_id, Value: {email: bytes}
# Used when server is temporarily unavailable to preserve last known values
_server_traffic_cache: Dict[int, Dict[str, int]] = {}
_server_cache_updated: Dict[int, datetime] = {}  # Last update time per server
SERVER_CACHE_MAX_AGE_HOURS = 24  # Don't use cache older than 24 hours


async def get_user_traffic_from_log(telegram_id: int, db: AsyncSession, reset_date: datetime = None) -> int:
    """
    Get user's traffic from daily_traffic_log since their reset date.
    This is more reliable than real-time server data because it doesn't
    get lost when servers are reinstalled/disabled.

    Args:
        telegram_id: User's telegram ID
        db: Database session
        reset_date: Date to start counting from (usually traffic_reset_date)

    Returns:
        Total traffic in bytes since reset_date
    """
    from sqlalchemy import func

    query = select(func.coalesce(func.sum(DailyTrafficLog.traffic_bytes), 0)).where(
        DailyTrafficLog.user_id == telegram_id
    )

    if reset_date:
        # Convert to date only (daily_traffic_log uses Date, not datetime)
        if hasattr(reset_date, 'date'):
            reset_date = reset_date.date()
        query = query.where(DailyTrafficLog.date >= reset_date)

    result = await db.execute(query)
    total = result.scalar() or 0

    return total


async def get_user_traffic_from_server(server: Servers, telegram_id: int) -> int:
    """
    Get traffic usage for a specific user from a server.
    Returns total bytes (upload + download).
    """
    try:
        manager = ServerManager(server)
        await manager.login()

        if server.type_vpn == 0:  # Outline
            # Use get_user_traffic method which calls metrics endpoint
            used = await manager.client.get_user_traffic(telegram_id)
            log.debug(f"[Traffic] User {telegram_id} on {server.name} (Outline): {used} bytes")
            return used

        elif server.type_vpn == 1:  # VLESS
            email = f"{telegram_id}_vless"
        elif server.type_vpn == 2:  # Shadowsocks
            email = f"{telegram_id}_ss"
        else:
            return 0

        # Get all client stats from server using ServerManager method (for VLESS/SS)
        client_stats = await manager.get_all_user()

        if not client_stats:
            return 0

        # Find our user in stats
        for stat in client_stats:
            if stat.get('email') == email:
                up = stat.get('up', 0) or 0
                down = stat.get('down', 0) or 0
                total = up + down
                log.debug(f"[Traffic] User {telegram_id} on {server.name}: up={up}, down={down}, total={total}")
                return total

        return 0

    except Exception as e:
        log.error(f"[Traffic] Error getting traffic for user {telegram_id} from server {server.name}: {e}")
        return 0


async def collect_user_traffic(telegram_id: int) -> int:
    """
    Collect total traffic for a user across ALL servers.
    Returns total bytes used.
    """
    total_traffic = 0

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all active servers (Outline, VLESS, Shadowsocks)
        stmt = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([0, 1, 2])  # Outline, VLESS and Shadowsocks
        )
        result = await db.execute(stmt)
        servers = result.scalars().all()

        for server in servers:
            traffic = await get_user_traffic_from_server(server, telegram_id)
            total_traffic += traffic

    log.info(f"[Traffic] User {telegram_id} total traffic: {format_bytes(total_traffic)}")
    return total_traffic


async def fetch_all_traffic_from_server(server) -> Dict[str, int]:
    """
    Fetch all client traffic data from a single server.
    Returns dict: {email: total_bytes}

    Uses caching: if server is unavailable, returns last known values
    (up to SERVER_CACHE_MAX_AGE_HOURS old).
    """
    global _server_traffic_cache, _server_cache_updated

    def _get_cached_data() -> Dict[str, int]:
        """Return cached data if available and not too old."""
        if server.id not in _server_traffic_cache:
            return {}

        last_update = _server_cache_updated.get(server.id)
        if last_update:
            age = datetime.utcnow() - last_update
            if age.total_seconds() > SERVER_CACHE_MAX_AGE_HOURS * 3600:
                log.warning(f"[Traffic] Cache for {server.name} is too old ({age}), ignoring")
                return {}

        cached = _server_traffic_cache[server.id]
        log.warning(f"[Traffic] Using cached data for {server.name}: {len(cached)} clients")
        return cached

    def _update_cache(data: Dict[str, int]):
        """Update cache with fresh data."""
        _server_traffic_cache[server.id] = data.copy()
        _server_cache_updated[server.id] = datetime.utcnow()

    try:
        from bot.misc.VPN.ServerManager import ServerManager
        manager = ServerManager(server)
        await manager.login()

        if server.type_vpn == 0:  # Outline
            try:
                # Get all keys from Outline server
                keys = await manager.client.client_outline.get_keys()
                # Get traffic metrics
                metrics = await manager.client.client_outline.get_transferred_data()

                if not metrics or 'bytesTransferredByUserId' not in metrics:
                    log.debug(f"[Traffic] No metrics from Outline server {server.name}")
                    return _get_cached_data()

                result = {}
                bytes_by_id = metrics['bytesTransferredByUserId']

                for key in keys:
                    key_id = str(key.key_id)
                    telegram_id = key.name  # telegram_id is stored as key name
                    if key_id in bytes_by_id and telegram_id.isdigit():
                        # Use _outline suffix for consistency with _vless and _ss
                        result[f"{telegram_id}_outline"] = bytes_by_id[key_id]

                log.debug(f"[Traffic] Fetched {len(result)} clients from {server.name} (Outline)")
                _update_cache(result)
                return result

            except Exception as e:
                log.error(f"[Traffic] Error fetching Outline traffic from {server.name}: {e}")
                return _get_cached_data()

        # Get all client stats from server
        client_stats = await manager.get_all_user()
        if not client_stats:
            log.warning(f"[Traffic] No data from {server.name}, using cache")
            return _get_cached_data()

        result = {}
        for stat in client_stats:
            email = stat.get('email', '')
            up = stat.get('up', 0) or 0
            down = stat.get('down', 0) or 0
            result[email] = up + down

        log.debug(f"[Traffic] Fetched {len(result)} clients from {server.name}")
        _update_cache(result)
        return result

    except Exception as e:
        log.error(f"[Traffic] Error fetching from server {server.name}: {e}")
        return _get_cached_data()


async def update_all_users_traffic(bot=None) -> Dict[str, int]:
    """
    UNIFIED traffic update for ALL users with active subscriptions.
    Fetches data from ALL servers (main + bypass), updates both traffic types,
    and sends bypass notifications if thresholds are reached.

    Returns statistics: {
        'updated': N, 'exceeded': N, 'errors': N, 'active': N,
        'bypass_notified_50': N, 'bypass_notified_70': N, 'bypass_notified_90': N, 'bypass_blocked': N
    }
    """
    import asyncio
    stats = {
        'updated': 0, 'exceeded': 0, 'errors': 0, 'blocked': 0, 'active': 0,
        'bypass_notified_50': 0, 'bypass_notified_70': 0, 'bypass_notified_90': 0, 'bypass_blocked': 0
    }
    now = datetime.utcnow()

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all active servers
        stmt_servers = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([0, 1, 2])
        )
        result_servers = await db.execute(stmt_servers)
        servers = result_servers.scalars().all()

        # Separate main and bypass servers
        main_servers = [s for s in servers if not s.is_bypass]
        bypass_servers = [s for s in servers if s.is_bypass]

        log.info(f"[Traffic] Fetching from {len(main_servers)} main + {len(bypass_servers)} bypass servers...")

        # Fetch all traffic data in parallel
        all_tasks = [fetch_all_traffic_from_server(server) for server in servers]
        server_data_list = await asyncio.gather(*all_tasks)

        # Build separate caches for main and bypass traffic
        main_cache = {}  # {tgid: bytes}
        bypass_cache = {}  # {tgid: bytes}

        for server, server_data in zip(servers, server_data_list):
            target_cache = bypass_cache if server.is_bypass else main_cache
            for email, traffic in server_data.items():
                tgid = email.split('_')[0] if '_' in email else email
                if tgid.isdigit():
                    tgid = int(tgid)
                    target_cache[tgid] = target_cache.get(tgid, 0) + traffic

        log.info(f"[Traffic] Main: {len(main_cache)} users, Bypass: {len(bypass_cache)} users")

        # Get all users with active subscriptions
        stmt = select(Persons).filter(Persons.subscription_active == True)
        result = await db.execute(stmt)
        users = result.scalars().all()

        log.info(f"[Traffic] Updating {len(users)} active users")

        for user in users:
            try:
                # === MAIN TRAFFIC ===
                main_traffic = main_cache.get(user.tgid, 0)

                # Check activity
                previous = user.previous_traffic_bytes or 0
                if main_traffic > previous:
                    user.traffic_last_change = now
                    stats['active'] += 1

                user.previous_traffic_bytes = main_traffic
                user.total_traffic_bytes = main_traffic

                # NOTE: Don't reset offset if offset > main_traffic
                # This can happen when servers are temporarily unavailable
                # and main_traffic is incomplete. Resetting offset breaks accounting.
                if user.traffic_offset_bytes and user.traffic_offset_bytes > main_traffic:
                    log.debug(
                        f"[Traffic] User {user.tgid} offset ({format_bytes(user.traffic_offset_bytes)}) > "
                        f"total ({format_bytes(main_traffic)}), keeping offset (server may be unavailable)"
                    )

                # Check main limit
                limit = user.traffic_limit_bytes or DEFAULT_TRAFFIC_LIMIT
                offset = user.traffic_offset_bytes or 0
                current_main = max(0, main_traffic - offset)

                if current_main >= limit:
                    stats['exceeded'] += 1

                # === BYPASS TRAFFIC ===
                bypass_traffic = bypass_cache.get(user.tgid, 0)
                user.bypass_traffic_bytes = bypass_traffic

                # NOTE: Don't reset bypass offset either (same reason as main traffic)
                if user.bypass_offset_bytes and user.bypass_offset_bytes > bypass_traffic:
                    log.debug(
                        f"[Traffic] User {user.tgid} bypass offset > total, keeping offset"
                    )

                # Calculate bypass usage
                bypass_offset = user.bypass_offset_bytes or 0
                current_bypass = max(0, bypass_traffic - bypass_offset)
                bypass_percent = (current_bypass / BYPASS_LIMIT_BYTES * 100) if BYPASS_LIMIT_BYTES > 0 else 0

                # Days until bypass reset
                days_until_reset = BYPASS_RESET_DAYS
                if user.bypass_reset_date:
                    reset_date = user.bypass_reset_date
                    if reset_date.tzinfo is not None:
                        reset_date = reset_date.replace(tzinfo=None)
                    next_reset = reset_date + timedelta(days=BYPASS_RESET_DAYS)
                    delta = next_reset - now
                    days_until_reset = max(0, delta.days)

                remaining_bypass = max(0, BYPASS_LIMIT_BYTES - current_bypass)

                # === BYPASS NOTIFICATIONS (if bot provided) ===
                if bot and bypass_traffic > 0:
                    try:
                        # 100% - blocked
                        if bypass_percent >= 100:
                            log.warning(f"[Traffic] User {user.tgid} bypass 100%: {format_bytes(current_bypass)}")
                            await bot.send_message(
                                user.tgid,
                                f"🚫 <b>Лимит трафика на сервере Обхода исчерпан!</b>\n\n"
                                f"Использовано: {format_bytes(current_bypass)} / {format_bytes(BYPASS_LIMIT_BYTES)} (100%)\n\n"
                                f"Доступ к серверу Обхода отключён.\n\n"
                                f"✅ <b>Основные VPN серверы — продолжают работать!</b>\n\n"
                                f"💡 Оплатите подписку чтобы сбросить лимит."
                            )
                            stats['bypass_blocked'] += 1

                        # 90% warning
                        elif bypass_percent >= 90 and not user.bypass_warning_90_sent:
                            await bot.send_message(
                                user.tgid,
                                f"🚨 <b>Критично! Лимит почти исчерпан</b>\n\n"
                                f"Использовано: {format_bytes(current_bypass)} / {format_bytes(BYPASS_LIMIT_BYTES)} ({bypass_percent:.0f}%)\n"
                                f"Осталось: {format_bytes(remaining_bypass)}\n\n"
                                f"При исчерпании лимита сервер Обхода будет отключён.\n\n"
                                f"💡 Оплатите подписку или подождите {days_until_reset} дней."
                            )
                            user.bypass_warning_90_sent = True
                            stats['bypass_notified_90'] += 1

                        # 70% warning
                        elif bypass_percent >= 70 and not user.bypass_warning_70_sent:
                            await bot.send_message(
                                user.tgid,
                                f"⚠️ <b>Внимание! Лимит почти израсходован</b>\n\n"
                                f"Использовано: {format_bytes(current_bypass)} / {format_bytes(BYPASS_LIMIT_BYTES)} ({bypass_percent:.0f}%)\n"
                                f"Осталось: {format_bytes(remaining_bypass)}\n\n"
                                f"Основные VPN серверы — без ограничений.\n\n"
                                f"Сброс через {days_until_reset} дней или при оплате."
                            )
                            user.bypass_warning_70_sent = True
                            stats['bypass_notified_70'] += 1

                        # 50% warning
                        elif bypass_percent >= 50 and not user.bypass_warning_50_sent:
                            await bot.send_message(
                                user.tgid,
                                f"📊 <b>Лимит трафика на сервере Обхода</b>\n\n"
                                f"Использовано: {format_bytes(current_bypass)} / {format_bytes(BYPASS_LIMIT_BYTES)} ({bypass_percent:.0f}%)\n\n"
                                f"Основные серверы VPN — без ограничений.\n\n"
                                f"Сброс через {days_until_reset} дней или при оплате."
                            )
                            user.bypass_warning_50_sent = True
                            stats['bypass_notified_50'] += 1

                    except Exception as e:
                        log.error(f"[Traffic] Bypass notification error for {user.tgid}: {e}")

                stats['updated'] += 1

            except Exception as e:
                log.error(f"[Traffic] Error updating user {user.tgid}: {e}")
                stats['errors'] += 1

        await db.commit()

    log.info(f"[Traffic] Update complete: {stats}")
    return stats


async def check_and_block_exceeded_users(bot) -> List[int]:
    """
    Check all users and block those who exceeded their traffic limit.
    Also sends 90% warning to users approaching the limit.
    Returns list of blocked user telegram IDs.
    """
    from bot.misc.subscription import expire_subscription
    from bot.misc.language import get_lang, Localization
    from bot.keyboards.inline.user_inline import renew
    from bot.misc.util import CONFIG
    from bot.misc.callbackData import MainMenuAction
    from aiogram.types import InlineKeyboardButton

    blocked_users = []
    warned_users = []

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all active users to check both 90% and 100% thresholds
        stmt = select(Persons).filter(
            Persons.subscription_active == True
        )
        result = await db.execute(stmt)
        all_users = result.scalars().all()

        for user in all_users:
            try:
                limit = user.traffic_limit_bytes or DEFAULT_TRAFFIC_LIMIT

                # Use daily_traffic_log instead of real-time data (more reliable)
                # Traffic from log doesn't get lost when servers are reinstalled
                current = await get_user_traffic_from_log(user.tgid, db, user.traffic_reset_date)
                percent = (current / limit * 100) if limit > 0 else 0

                # Check if 100% exceeded - block user
                if current >= limit:
                    log.warning(
                        f"[Traffic] Blocking user {user.tgid}: "
                        f"{format_bytes(current)} >= {format_bytes(limit)}"
                    )

                    # Expire subscription (disable keys)
                    await expire_subscription(user.tgid)

                    # Build payment keyboard with main menu button
                    lang = user.lang or 'ru'
                    kb = await renew(CONFIG, lang, user.tgid, user.payment_method_id)
                    # Add main menu button
                    kb.inline_keyboard.append([
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data=MainMenuAction(action='back_to_menu').pack()
                        )
                    ])

                    # Notify user
                    try:
                        await bot.send_message(
                            user.tgid,
                            f"🚫 <b>Лимит трафика исчерпан!</b>\n\n"
                            f"📊 Использовано: {format_bytes(current)}\n"
                            f"📦 Лимит: {format_bytes(limit)}\n\n"
                            f"VPN отключен. Для продолжения использования продлите подписку 👇",
                            reply_markup=kb
                        )
                    except Exception as e:
                        log.error(f"[Traffic] Could not notify user {user.tgid}: {e}")

                    blocked_users.append(user.tgid)

                # Check if 90% reached and warning not yet sent
                elif percent >= 90 and not user.traffic_warning_sent:
                    log.info(f"[Traffic] Sending 90% warning to user {user.tgid}: {percent:.1f}%")

                    # Build payment keyboard with main menu button
                    lang = user.lang or 'ru'
                    kb = await renew(CONFIG, lang, user.tgid, user.payment_method_id)
                    # Add main menu button
                    kb.inline_keyboard.append([
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data=MainMenuAction(action='back_to_menu').pack()
                        )
                    ])

                    # Send warning
                    try:
                        await bot.send_message(
                            user.tgid,
                            f"⚠️ <b>Внимание! Лимит трафика почти исчерпан</b>\n\n"
                            f"📊 Использовано: {format_bytes(current)} / {format_bytes(limit)} ({percent:.0f}%)\n"
                            f"📦 Осталось: {format_bytes(limit - current)}\n\n"
                            f"При исчерпании лимита VPN будет отключен.\n"
                            f"💡 Лимит сбрасывается раз в 30 дней или при оплате.\n\n"
                            f"Продлите подписку, чтобы сбросить лимит 👇",
                            reply_markup=kb
                        )
                        # Mark warning as sent
                        user.traffic_warning_sent = True
                        warned_users.append(user.tgid)
                    except Exception as e:
                        log.error(f"[Traffic] Could not send 90% warning to user {user.tgid}: {e}")

            except Exception as e:
                log.error(f"[Traffic] Error checking user {user.tgid}: {e}")

        await db.commit()

    if warned_users:
        log.info(f"[Traffic] Sent 90% warnings to {len(warned_users)} users")

    return blocked_users


async def reset_user_traffic(telegram_id: int) -> bool:
    """
    Reset traffic counter for a user (called after payment).
    Sets offset to current total, so "current traffic" starts from 0.
    """
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            # Сначала получаем текущий total_traffic
            stmt = select(Persons).where(Persons.tgid == telegram_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                current_total = user.total_traffic_bytes or 0
                # Устанавливаем offset = текущий total, чтобы "текущий трафик" стал 0
                user.traffic_offset_bytes = current_total
                user.traffic_reset_date = datetime.now(timezone.utc)
                user.traffic_warning_sent = False  # Сбрасываем флаг предупреждения
                await db.commit()

                log.info(f"[Traffic] Reset traffic for user {telegram_id}: offset set to {format_bytes(current_total)}")
                return True
            else:
                log.warning(f"[Traffic] User {telegram_id} not found for traffic reset")
                return False

    except Exception as e:
        log.error(f"[Traffic] Error resetting traffic for user {telegram_id}: {e}")
        return False


async def reset_traffic_on_servers(telegram_id: int) -> bool:
    """
    Reset traffic counters on all VPN servers for a user.
    Note: 3X-UI panel doesn't have a direct reset method,
    traffic resets when client is recreated or manually in panel.
    """
    # В 3X-UI панели нет API для сброса трафика отдельного клиента
    # Трафик сбрасывается только при пересоздании клиента или вручную
    # Поэтому просто логируем и возвращаем True
    log.info(f"[Traffic] Traffic reset requested for user {telegram_id} (DB only, panel stats preserved)")
    return True


async def reset_monthly_traffic() -> Dict[str, int]:
    """
    Reset traffic for users whose last reset was more than 30 days ago.
    Called daily by scheduler.
    Returns statistics: {'checked': N, 'reset': N, 'errors': N}
    """
    stats = {'checked': 0, 'reset': 0, 'errors': 0}
    now = datetime.utcnow()  # Use naive UTC datetime to match DB
    reset_threshold = now - timedelta(days=TRAFFIC_RESET_DAYS)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all users with active subscriptions
        stmt = select(Persons).filter(
            Persons.subscription_active == True
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        for user in users:
            stats['checked'] += 1
            try:
                # Check if reset is needed
                last_reset = user.traffic_reset_date

                # Normalize timezone for comparison (remove tzinfo if present)
                if last_reset is not None and last_reset.tzinfo is not None:
                    last_reset = last_reset.replace(tzinfo=None)

                # Reset if: no reset date OR reset was more than 30 days ago
                if last_reset is None or last_reset < reset_threshold:
                    current_total = user.total_traffic_bytes or 0
                    user.traffic_offset_bytes = current_total
                    user.traffic_reset_date = now
                    user.traffic_warning_sent = False  # Сбрасываем флаг предупреждения

                    # Синхронно сбрасываем bypass трафик
                    bypass_total = user.bypass_traffic_bytes or 0
                    user.bypass_offset_bytes = bypass_total
                    user.bypass_reset_date = now
                    user.bypass_warning_50_sent = False
                    user.bypass_warning_70_sent = False
                    user.bypass_warning_90_sent = False

                    stats['reset'] += 1
                    log.info(
                        f"[Traffic] Monthly reset for user {user.tgid}: "
                        f"traffic offset={format_bytes(current_total)}, bypass offset={format_bytes(bypass_total)}"
                    )

            except Exception as e:
                log.error(f"[Traffic] Error in monthly reset for user {user.tgid}: {e}")
                stats['errors'] += 1

        await db.commit()

    log.info(f"[Traffic] Monthly reset complete: {stats}")
    return stats


def get_days_until_reset(reset_date: Optional[datetime]) -> int:
    """
    Calculate days until next traffic reset.
    Returns 0-30 days.
    """
    if reset_date is None:
        return 0  # Will be reset on next check

    now = datetime.utcnow()  # Use naive UTC datetime to match DB

    # Handle timezone-aware datetimes
    if reset_date.tzinfo is not None:
        reset_date = reset_date.replace(tzinfo=None)

    next_reset = reset_date + timedelta(days=TRAFFIC_RESET_DAYS)
    delta = next_reset - now

    if delta.days <= 0:
        return 0
    return min(delta.days, TRAFFIC_RESET_DAYS)


async def get_user_traffic_info(telegram_id: int) -> Dict:
    """
    Get traffic info for a user to display.
    Uses daily_traffic_log for accurate counting (doesn't lose data on server reinstall).
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.tgid == telegram_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        limit = user.traffic_limit_bytes or DEFAULT_TRAFFIC_LIMIT
        total = user.total_traffic_bytes or 0  # Raw total from servers (for reference)

        # Use daily_traffic_log for current period (more reliable)
        current = await get_user_traffic_from_log(telegram_id, db, user.traffic_reset_date)
        remaining = max(0, limit - current)
        percent_used = (current / limit * 100) if limit > 0 else 0

        days_until_reset = get_days_until_reset(user.traffic_reset_date)

        return {
            'used_bytes': current,  # Текущий период (из лога)
            'used_formatted': format_bytes(current),
            'total_bytes': total,  # Всего за всё время (raw)
            'total_formatted': format_bytes(total),
            'limit_bytes': limit,
            'limit_formatted': format_bytes(limit),
            'remaining_bytes': remaining,
            'remaining_formatted': format_bytes(remaining),
            'percent_used': round(percent_used, 1),
            'reset_date': user.traffic_reset_date,
            'days_until_reset': days_until_reset,
            'exceeded': current >= limit
        }


async def get_user_bypass_info(telegram_id: int) -> Optional[Dict]:
    """
    Get bypass traffic info from DB (not real-time from servers).
    Used for displaying in user menu.
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.tgid == telegram_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        total = user.bypass_traffic_bytes or 0
        offset = user.bypass_offset_bytes or 0
        current = max(0, total - offset)
        limit = BYPASS_LIMIT_BYTES
        remaining = max(0, limit - current)
        percent_used = (current / limit * 100) if limit > 0 else 0

        return {
            'total': current,
            'total_formatted': format_bytes(current),
            'limit': limit,
            'limit_formatted': format_bytes(limit),
            'remaining': remaining,
            'remaining_formatted': format_bytes(remaining),
            'percent': round(percent_used, 1),
            'exceeded': current >= limit
        }


def format_bytes(bytes_value: int) -> str:
    """
    Format bytes to human readable string.
    """
    if bytes_value is None:
        return "0 B"

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(bytes_value) < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0

    return f"{bytes_value:.1f} PB"


async def send_setup_reminders(bot) -> Dict[str, int]:
    """
    Send setup reminder to users who paid but haven't used VPN.
    - First reminder: 2 days after payment
    - Second reminder: 3 days after first reminder
    Called daily by scheduler.
    Returns statistics: {'checked': N, 'sent': N, 'errors': N}
    """
    from datetime import datetime, timedelta, timezone

    stats = {'checked': 0, 'sent_first': 0, 'sent_second': 0, 'errors': 0, 'blocked': 0}
    now = datetime.utcnow()  # Use naive UTC datetime to match DB
    two_days_ago = now - timedelta(days=2)
    three_days_ago = now - timedelta(days=3)

    MESSAGE_FIRST = '''Привет! 👋

У тебя активная подписка VPN, но мы заметили что ты ещё не подключался.

Может нужна помощь с настройкой? Это займёт всего пару минут:
• Поможем выбрать приложение для твоего устройства
• Настроим подключение
• Проверим что всё работает

Напиши в поддержку — разберёмся:
👉 @VPN_YouSupport_bot'''

    MESSAGE_SECOND = '''Привет! Это повторное напоминание 📱

Ты оплатил подписку VPN, но похоже так и не настроил.

Не хочется чтобы деньги пропали! Давай поможем:
• Пришли модель телефона — подберём инструкцию
• Или просто напиши «помогите» — разберёмся вместе

Поддержка онлайн:
👉 @VPN_YouSupport_bot'''

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Find users who need reminder:
        # - subscription_active = true
        # - total_traffic_bytes = 0 or NULL
        # - setup_reminder_count < 2 (max 2 reminders)
        # - bot_blocked = false
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            (Persons.total_traffic_bytes == 0) | (Persons.total_traffic_bytes == None),
            (Persons.setup_reminder_count < 2) | (Persons.setup_reminder_count == None),
            (Persons.bot_blocked == False) | (Persons.bot_blocked == None)
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        for user in users:
            stats['checked'] += 1
            reminder_count = user.setup_reminder_count or 0

            if reminder_count == 0:
                # First reminder: check if subscription is older than 2 days
                sub_date = user.subscription_created_at
                if sub_date is None:
                    if user.subscription:
                        months = user.subscription_months or 1
                        sub_start = datetime.fromtimestamp(user.subscription) - timedelta(days=months * 30)
                        if sub_start > two_days_ago:
                            continue  # Too recent
                    else:
                        continue
                else:
                    if sub_date.tzinfo is not None:
                        sub_date = sub_date.replace(tzinfo=None)
                    if sub_date > two_days_ago:
                        continue  # Too recent

                message = MESSAGE_FIRST
                stat_key = 'sent_first'

            elif reminder_count == 1:
                # Second reminder: check if 3 days passed since first reminder
                last_sent = user.setup_reminder_last_sent
                if last_sent is None:
                    continue  # No record of first reminder
                if last_sent.tzinfo is not None:
                    last_sent = last_sent.replace(tzinfo=None)
                if last_sent > three_days_ago:
                    continue  # Not enough time passed

                message = MESSAGE_SECOND
                stat_key = 'sent_second'
            else:
                continue  # Already sent 2 reminders

            # Send reminder
            try:
                await bot.send_message(user.tgid, message)
                user.setup_reminder_count = reminder_count + 1
                user.setup_reminder_last_sent = now
                user.setup_reminder_sent = True  # Keep for backwards compatibility
                stats[stat_key] += 1
                log.info(f"[SetupReminder] Sent reminder #{reminder_count + 1} to user {user.tgid}")
            except Exception as e:
                error_msg = str(e).lower()
                if 'blocked' in error_msg or 'deactivated' in error_msg:
                    user.bot_blocked = True
                    user.bot_blocked_at = datetime.now(timezone.utc)
                    user.setup_reminder_count = 2  # Don't retry
                    stats['blocked'] += 1
                    log.info(f"[SetupReminder] User {user.tgid} blocked bot")
                else:
                    stats['errors'] += 1
                    log.error(f"[SetupReminder] Error sending to {user.tgid}: {e}")

        await db.commit()

    log.info(f"[SetupReminder] Complete: {stats}")
    return stats


async def send_reengagement_reminders(bot) -> Dict[str, int]:
    """
    Send re-engagement reminder to users who used VPN before but stopped.
    Conditions:
    - subscription_active = true
    - total_traffic_bytes > 0 (they used it before)
    - traffic_last_change > 7 days ago (stopped using)
    - reengagement_reminder_sent = false
    Only sends ONE reminder per user.
    """
    from datetime import datetime, timedelta

    stats = {'checked': 0, 'sent': 0, 'errors': 0, 'blocked': 0}
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    MESSAGE = '''Привет! 👋

Заметили, что ты давно не пользовался VPN.

Всё в порядке? Может возникли какие-то проблемы?

• Если VPN перестал работать — напиши, поможем
• Если забыл как подключиться — пришлём инструкцию
• Если нужна помощь — мы на связи!

Напиши нам:
👉 @VPN_YouSupport_bot'''

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            Persons.total_traffic_bytes > 0,  # Used VPN before
            Persons.traffic_last_change < week_ago,  # Stopped using > 7 days
            (Persons.reengagement_reminder_sent == False) | (Persons.reengagement_reminder_sent == None),
            (Persons.bot_blocked == False) | (Persons.bot_blocked == None)
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        for user in users:
            stats['checked'] += 1

            try:
                await bot.send_message(user.tgid, MESSAGE)
                user.reengagement_reminder_sent = True
                stats['sent'] += 1
                log.info(f"[Reengagement] Sent reminder to user {user.tgid}")
            except Exception as e:
                error_msg = str(e).lower()
                if 'blocked' in error_msg or 'deactivated' in error_msg:
                    user.bot_blocked = True
                    user.bot_blocked_at = datetime.now(timezone.utc)
                    user.reengagement_reminder_sent = True  # Don't retry
                    stats['blocked'] += 1
                    log.info(f"[Reengagement] User {user.tgid} blocked bot")
                else:
                    stats['errors'] += 1
                    log.error(f"[Reengagement] Error sending to {user.tgid}: {e}")

        await db.commit()

    log.info(f"[Reengagement] Complete: {stats}")
    return stats


async def send_daily_stats(bot) -> None:
    """
    Send daily statistics to admins every morning.
    Includes: total users, funnel (new->trial->paid), UTM breakdown, payments, revenue.
    """
    from datetime import datetime, timedelta, timezone
    from bot.misc.util import CONFIG

    now = datetime.utcnow()  # Use naive UTC datetime to match DB
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = yesterday_end  # Midnight today UTC

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Total users
        total_users = await db.execute(
            select(func.count()).select_from(Persons).filter(
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        total_users = total_users.scalar() or 0

        # === FUNNEL: New users yesterday ===
        new_users = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.first_interaction >= yesterday_start,
                Persons.first_interaction < yesterday_end,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        new_users = new_users.scalar() or 0

        # Funnel: got trial yesterday (from new users)
        new_trial = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.first_interaction >= yesterday_start,
                Persons.first_interaction < yesterday_end,
                Persons.free_trial_used == True,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        new_trial = new_trial.scalar() or 0

        # Funnel: paid yesterday (from new users)
        new_paid = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.first_interaction >= yesterday_start,
                Persons.first_interaction < yesterday_end,
                Persons.retention > 0,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        new_paid = new_paid.scalar() or 0

        # === NEW: Activation of new users (used VPN) ===
        # New users who got trial yesterday AND have traffic
        new_used_vpn = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.first_interaction >= yesterday_start,
                Persons.first_interaction < yesterday_end,
                Persons.free_trial_used == True,
                Persons.total_traffic_bytes > 0,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        new_used_vpn = new_used_vpn.scalar() or 0
        new_not_used = new_trial - new_used_vpn

        # === NEW: Activity stats ===
        from bot.database.models.main import DailyTrafficLog

        now_ts = int(datetime.utcnow().timestamp())
        week_ago = today_start - timedelta(days=7)

        # Сегодня: по traffic_last_change (накопительное за текущий день)
        active_with_traffic_today = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.traffic_last_change >= today_start,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        active_with_traffic_today = active_with_traffic_today.scalar() or 0

        # Вчера: из таблицы daily_traffic_log (записано в полночь)
        yesterday_date = (today_start - timedelta(days=1)).date()
        active_with_traffic_yesterday = await db.execute(
            select(func.count()).select_from(DailyTrafficLog).filter(
                DailyTrafficLog.date == yesterday_date
            )
        )
        active_with_traffic_yesterday = active_with_traffic_yesterday.scalar() or 0

        # За неделю: уникальные пользователи из daily_traffic_log за 7 дней
        week_ago_date = (today_start - timedelta(days=7)).date()
        active_with_traffic_week = await db.execute(
            select(func.count(func.distinct(DailyTrafficLog.user_id))).filter(
                DailyTrafficLog.date >= week_ago_date
            )
        )
        active_with_traffic_week = active_with_traffic_week.scalar() or 0

        # === NEW: Sleeping users (paid but no traffic > 7 days) ===
        sleeping_users = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.subscription > now_ts,
                Persons.retention > 0,  # paid users
                or_(
                    Persons.traffic_last_change < week_ago,
                    Persons.traffic_last_change == None
                ),
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        sleeping_users = sleeping_users.scalar() or 0

        # === UTM breakdown for new users ===
        utm_stats = await db.execute(
            select(
                Persons.client_id,
                func.count()
            ).filter(
                Persons.first_interaction >= yesterday_start,
                Persons.first_interaction < yesterday_end,
                (Persons.banned == False) | (Persons.banned == None)
            ).group_by(Persons.client_id).order_by(func.count().desc())
        )
        utm_data = utm_stats.all()

        # === Traffic source from survey (for users without UTM) ===
        # Note: traffic_source field may not exist in older DB schemas
        try:
            traffic_source_stats = await db.execute(
                select(
                    Persons.traffic_source,
                    func.count()
                ).filter(
                    Persons.first_interaction >= yesterday_start,
                    Persons.first_interaction < yesterday_end,
                    Persons.traffic_source != None,
                    (Persons.banned == False) | (Persons.banned == None)
                ).group_by(Persons.traffic_source).order_by(func.count().desc())
            )
            traffic_source_data = traffic_source_stats.all()
        except Exception as e:
            log.warning(f"[DailyStats] traffic_source query failed (field may not exist): {e}")
            traffic_source_data = []

        # Active subscriptions
        active_subs = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.subscription_active == True,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        active_subs = active_subs.scalar() or 0

        # Users on trial (active, free_trial_used = true, retention = 0)
        trial_users = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.free_trial_used == True,
                Persons.retention == 0,
                Persons.subscription_active == True,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        trial_users = trial_users.scalar() or 0

        # Payments yesterday
        try:
            from bot.database.models.main import Payments
            payments_yesterday = await db.execute(
                select(func.count(), func.sum(Payments.amount)).select_from(Payments).filter(
                    Payments.data >= yesterday_start,
                    Payments.data < yesterday_end
                )
            )
            row = payments_yesterday.one()
            payments_count = row[0] or 0
            revenue = row[1] or 0
        except Exception as e:
            import logging
            logging.error(f'[DailyStats] Failed to get payments: {e}')
            payments_count = 0
            revenue = 0

        # Users with traffic vs without
        with_traffic = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.subscription_active == True,
                Persons.total_traffic_bytes > 0,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        with_traffic = with_traffic.scalar() or 0
        without_traffic = active_subs - with_traffic

        # Traffic stats: total and daily
        # Note: daily_traffic_start_bytes may not exist in older DB schemas
        try:
            traffic_result = await db.execute(
                select(
                    func.sum(Persons.total_traffic_bytes - Persons.traffic_offset_bytes),
                    func.sum(Persons.total_traffic_bytes - Persons.daily_traffic_start_bytes)
                ).filter(
                    Persons.subscription_active == True
                )
            )
            traffic_row = traffic_result.one()
            total_active_traffic = int(max(0, traffic_row[0] or 0))
            daily_traffic_bytes = int(max(0, traffic_row[1] or 0))
        except Exception as e:
            log.warning(f"[DailyStats] Traffic stats query failed: {e}")
            # Fallback: just get total traffic
            try:
                traffic_result = await db.execute(
                    select(
                        func.sum(Persons.total_traffic_bytes - Persons.traffic_offset_bytes)
                    ).filter(
                        Persons.subscription_active == True
                    )
                )
                total_active_traffic = int(max(0, traffic_result.scalar() or 0))
            except:
                total_active_traffic = 0
            daily_traffic_bytes = 0

    # Check subscription keys health
    keys_health = await check_subscription_keys_health()
    
    # Format keys health section
    def format_keys_status(name, data):
        if data["total"] == 0:
            return f"  • {name}: нет подписчиков"
        ok = data["ok"]
        total = data["total"]
        servers = data["servers"]
        missing = data["missing"]
        if missing == 0:
            return f"  ✅ {name}: {ok}/{total} на {servers} серверах"
        else:
            return f"  ❌ {name}: {ok}/{total} (не хватает {missing}!)"
    
    keys_section = "\n".join([
        format_keys_status("VLESS", keys_health["vless"]),
        format_keys_status("Outline", keys_health["outline"])
    ])

    # Check if there are problems
    keys_has_problems = (
        keys_health["vless"]["missing"] > 0 or
        keys_health["outline"]["missing"] > 0
    )
    keys_header = "⚠️ Ключи подписки:" if keys_has_problems else "🔑 Ключи подписки:"

    # Get speed test results from Pushgateway
    speed_results = await get_speed_test_results()
    speed_lines = []
    speed_threshold = 30  # Mbps
    speed_has_problems = False

    server_names = {
        "germany": "DE Германия",
        "netherlands": "NL Нидерланды",
        "netherlands2": "NL Нидерланды-2",
        "spain": "ES Испания",
        "usa": "US США",
        "bypass_yc": "🇷🇺 RU-bypass (→NL)"
    }

    for server_key in ["germany", "netherlands", "netherlands2", "spain", "usa", "bypass_yc"]:
        if server_key in speed_results.get("servers", {}):
            data = speed_results["servers"][server_key]
            download = data.get("download", 0)
            upload = data.get("upload", 0)
            name = server_names.get(server_key, server_key)

            # Get local speed on server
            local_key = f"{server_key}_local"
            local_download = speed_results.get("servers", {}).get(local_key, {}).get("download", 0)
            # Also check for local speed stored directly in the server data (e.g., USA)
            if local_download == 0 and data.get("local", 0) > 0:
                local_download = data.get("local", 0)

            # Special handling for bypass - show chain: bypass→NL→internet
            if server_key == "bypass_yc":
                to_nl = data.get("to_nl", 0)
                if to_nl > 0 and download > 0:
                    status = "✅" if download >= speed_threshold else "⚠️"
                    if download < speed_threshold:
                        speed_has_problems = True
                    speed_lines.append(f"  {status} {name}: {to_nl:.0f}→NL / {download:.0f} Mbps")
                elif download > 0:
                    status = "✅" if download >= speed_threshold else "⚠️"
                    if download < speed_threshold:
                        speed_has_problems = True
                    speed_lines.append(f"  {status} {name}: {download:.0f} Mbps")
                else:
                    speed_lines.append(f"  ❓ {name}: нет данных")
                continue

            if download > 0:
                status = "✅" if download >= speed_threshold else "⚠️"
                if download < speed_threshold:
                    speed_has_problems = True
                if local_download > 0:
                    speed_lines.append(f"  {status} {name}: {download:.0f} / {local_download:.0f} Mbps")
                else:
                    speed_lines.append(f"  {status} {name}: {download:.0f} Mbps")
            else:
                # No iperf3 data, but check if local data exists
                if local_download > 0:
                    status = "✅" if local_download >= speed_threshold else "⚠️"
                    if local_download < speed_threshold:
                        speed_has_problems = True
                    speed_lines.append(f"  {status} {name}: — / {local_download:.0f} Mbps")
                else:
                    speed_lines.append(f"  ❓ {name}: нет данных")
        else:
            # No iperf3 data - check if local data exists
            name = server_names.get(server_key, server_key)
            local_key = f"{server_key}_local"
            local_download = speed_results.get("servers", {}).get(local_key, {}).get("download", 0)
            if local_download > 0:
                status = "✅" if local_download >= speed_threshold else "⚠️"
                if local_download < speed_threshold:
                    speed_has_problems = True
                speed_lines.append(f"  {status} {name}: — / {local_download:.0f} Mbps")
            else:
                speed_lines.append(f"  ❓ {name}: нет данных")

    speed_section = "\n".join(speed_lines) if speed_lines else "  нет данных"
    speed_header = "⚠️ Скорость (→RU / интернет):" if speed_has_problems else "🚀 Скорость (→RU / интернет):"


    # Format UTM section
    utm_lines = []
    for client_id, count in utm_data:
        source = client_id if client_id else "органика"
        # Shorten utm_source_ prefix
        if source.startswith("utm_source_"):
            source = source.replace("utm_source_", "")
        utm_lines.append(f"  • {source}: {count}")
    utm_section = "\n".join(utm_lines) if utm_lines else "  • нет данных"

    # Format traffic source section (from survey)
    source_names = {
        'telegram_search': '🔍 Поиск в TG',
        'friend': '👥 От друга',
        'forum': '📱 Форум',
        'website': '🌐 Сайт',
        'ads': '📢 Реклама',
        'other': '🤷 Не помню'
    }
    traffic_lines = []
    for source, count in traffic_source_data:
        name = source_names.get(source, source)
        traffic_lines.append(f"  • {name}: {count}")
    traffic_section = "\n".join(traffic_lines) if traffic_lines else "  • нет данных"

    # Format message
    date_str = (now - timedelta(days=1)).strftime('%d.%m.%Y')
    message = f'''📊 Статистика за {date_str}

👥 Всего пользователей: {total_users:,}

📈 Воронка вчера:
  → Пришли: {new_users}
  → Пробный период: {new_trial}
  → Оплатили: {new_paid}

🎯 Активация новых:
  ✅ Использовали VPN: {new_used_vpn} ({int(new_used_vpn/new_trial*100) if new_trial > 0 else 0}%)
  ❌ Не использовали: {new_not_used}

🔗 UTM-метки ({new_users}):
{utm_section}

📋 Опрос (откуда узнали):
{traffic_section}

📱 Активные подписки: {active_subs}
├ На пробном: {trial_users}
├ С трафиком: {with_traffic}
└ Без трафика: {without_traffic}

📊 Активность (использовали):
  Сегодня: {active_with_traffic_today}
  Вчера: {active_with_traffic_yesterday}
  За неделю: {active_with_traffic_week} ({int(active_with_traffic_week/active_subs*100) if active_subs > 0 else 0}%)

😴 Спящие (платят, не юзают >7д): {sleeping_users}

💰 Оплат вчера: {payments_count}
💵 Выручка: {revenue:,.0f}₽

📶 Трафик всего: {format_bytes(total_active_traffic)}
📊 За сутки: {format_bytes(daily_traffic_bytes)}

{keys_header}
{keys_section}

{speed_header}
{speed_section}'''

    # Send to admins
    for admin_id in CONFIG.admins_ids:
        try:
            await bot.send_message(admin_id, message)
            log.info(f"[DailyStats] Sent to admin {admin_id}")
        except Exception as e:
            log.error(f"[DailyStats] Error sending to {admin_id}: {e}")


async def snapshot_daily_traffic():
    """
    Save daily traffic log for all users, broken down by server.
    Should run at midnight to capture traffic at the end of each day.
    Records absolute traffic value per server - delta can be calculated from previous day.
    Also resets daily_traffic_start_bytes for daily stats calculation.
    """
    from datetime import date, datetime
    from bot.database.models.main import DailyTrafficLog
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    today = date.today()
    stats = {'servers': 0, 'records': 0, 'users': set(), 'daily_reset': 0}

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Reset daily_traffic_start_bytes for all users (for daily stats)
        reset_stmt = update(Persons).values(
            daily_traffic_start_bytes=Persons.total_traffic_bytes
        ).where(
            Persons.subscription_active == True
        )
        result = await db.execute(reset_stmt)
        stats['daily_reset'] = result.rowcount
        log.info(f"[Traffic] Reset daily_traffic_start_bytes for {stats['daily_reset']} users")
        # Get all active servers
        stmt_servers = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([0, 1, 2])  # Outline, VLESS and Shadowsocks
        )
        result_servers = await db.execute(stmt_servers)
        servers = result_servers.scalars().all()

        # Fetch traffic from each server
        for server in servers:
            stats['servers'] += 1
            try:
                server_traffic = await fetch_all_traffic_from_server(server)

                if not server_traffic:
                    continue

                # Record traffic for each user on this server
                for email, traffic_bytes in server_traffic.items():
                    # Extract telegram_id from email (format: {tgid}_outline, {tgid}_vless or {tgid}_ss)
                    tgid_str = email.split('_')[0] if '_' in email else email
                    if not tgid_str.isdigit():
                        continue

                    tgid = int(tgid_str)

                    if traffic_bytes <= 0:
                        continue  # Skip users with no traffic

                    try:
                        # UPSERT: insert or update if exists
                        stmt = pg_insert(DailyTrafficLog).values(
                            user_id=tgid,
                            date=today,
                            server_id=server.id,
                            traffic_bytes=traffic_bytes
                        ).on_conflict_do_update(
                            constraint='uq_user_date_server',
                            set_={'traffic_bytes': traffic_bytes}
                        )
                        await db.execute(stmt)
                        stats['records'] += 1
                        stats['users'].add(tgid)
                    except Exception as e:
                        log.debug(f"[Traffic] Error recording for user {tgid} on server {server.name}: {e}")

            except Exception as e:
                log.warning(f"[Traffic] Error fetching from server {server.name}: {e}")

        await db.commit()

    log.info(f"[Traffic] Daily traffic log: {stats['records']} records for {len(stats['users'])} users across {stats['servers']} servers for {today}")
    return stats['records']


async def get_user_traffic_history(telegram_id: int, days: int = 7) -> Dict:
    """
    Get traffic history for a user broken down by server and protocol.

    Returns:
    {
        'total': 12345678,  # Total bytes for period
        'by_date': {
            '2026-01-14': {'total': 1234, 'servers': {...}},
            '2026-01-13': {'total': 5678, 'servers': {...}},
        },
        'by_server': {
            'Germany VLESS': {'total': 1000, 'type': 1},
            'Russia SS': {'total': 500, 'type': 2},
        },
        'by_protocol': {
            'VLESS': 5000,
            'Shadowsocks': 3000,
            'Outline': 2000,
        }
    }
    """
    from datetime import date, timedelta
    from bot.database.models.main import DailyTrafficLog

    result = {
        'total': 0,
        'by_date': {},
        'by_server': {},
        'by_protocol': {'VLESS': 0, 'Shadowsocks': 0, 'Outline': 0}
    }

    start_date = date.today() - timedelta(days=days)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get traffic logs with server info
        stmt = select(
            DailyTrafficLog.date,
            DailyTrafficLog.server_id,
            DailyTrafficLog.traffic_bytes,
            Servers.name,
            Servers.type_vpn
        ).join(
            Servers, DailyTrafficLog.server_id == Servers.id
        ).filter(
            DailyTrafficLog.user_id == telegram_id,
            DailyTrafficLog.date >= start_date
        ).order_by(DailyTrafficLog.date.desc())

        rows = await db.execute(stmt)
        data = rows.all()

        # Also get previous day's data to calculate daily delta
        prev_date = start_date - timedelta(days=1)
        prev_stmt = select(
            DailyTrafficLog.server_id,
            DailyTrafficLog.traffic_bytes
        ).filter(
            DailyTrafficLog.user_id == telegram_id,
            DailyTrafficLog.date == prev_date
        )
        prev_rows = await db.execute(prev_stmt)
        prev_data = {row[0]: row[1] for row in prev_rows.all()}

        # Process data
        dates_seen = {}  # {(date, server_id): traffic}

        for row in data:
            log_date, server_id, traffic, server_name, type_vpn = row
            date_str = log_date.strftime('%Y-%m-%d')

            # Determine protocol name
            if type_vpn == 0:
                protocol = 'Outline'
            elif type_vpn == 1:
                protocol = 'VLESS'
            else:
                protocol = 'Shadowsocks'

            # By date
            if date_str not in result['by_date']:
                result['by_date'][date_str] = {'total': 0, 'servers': {}}

            # Calculate daily delta (current - previous day)
            # For now, store absolute values - delta calculation needs consecutive days
            result['by_date'][date_str]['servers'][server_name] = traffic
            dates_seen[(log_date, server_id)] = traffic

            # By server (cumulative)
            if server_name not in result['by_server']:
                result['by_server'][server_name] = {'total': 0, 'type': type_vpn}

        # Calculate totals and deltas
        # Sort dates to process in order
        sorted_dates = sorted(result['by_date'].keys(), reverse=True)

        for i, date_str in enumerate(sorted_dates):
            day_data = result['by_date'][date_str]
            day_total = 0

            for server_name, traffic in day_data['servers'].items():
                # For now, just use the absolute traffic value
                # Daily delta would need yesterday's data for that server
                day_total += traffic

                # Update server total (use latest/max value)
                if server_name in result['by_server']:
                    result['by_server'][server_name]['total'] = max(
                        result['by_server'][server_name]['total'],
                        traffic
                    )

            day_data['total'] = day_total

        # Calculate totals by protocol
        for server_name, server_data in result['by_server'].items():
            type_vpn = server_data['type']
            traffic = server_data['total']

            if type_vpn == 0:
                result['by_protocol']['Outline'] += traffic
            elif type_vpn == 1:
                result['by_protocol']['VLESS'] += traffic
            else:
                result['by_protocol']['Shadowsocks'] += traffic

        result['total'] = sum(result['by_protocol'].values())

    return result


async def check_subscription_keys_health():
    """
    Check if all active users with subscription have keys on all servers.
    Returns dict with stats for VLESS, SS, Outline.
    """
    import time
    from bot.database.models.main import Servers
    from bot.misc.VPN.ServerManager import ServerManager
    
    result = {
        "vless": {"total": 0, "ok": 0, "missing": 0, "servers": 0},
        "outline": {"total": 0, "ok": 0, "missing": 0, "servers": 0},
    }
    
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            # Get active users with subscription_token
            now = int(time.time())
            users_result = await db.execute(
                select(Persons.tgid).filter(
                    Persons.subscription > now,
                    Persons.banned == False,
                    Persons.subscription_token != None
                )
            )
            active_tgids = set(row[0] for row in users_result.fetchall())
            
            if not active_tgids:
                return result
            
            # Get all active servers by type
            servers_result = await db.execute(
                select(Servers).filter(Servers.work == True).order_by(Servers.id)
            )
            servers = list(servers_result.scalars().all())
            
            # Group servers by type (SS disabled)
            vless_servers = [s for s in servers if s.type_vpn == 1]
            outline_servers = [s for s in servers if s.type_vpn == 0]

            result["vless"]["servers"] = len(vless_servers)
            result["outline"]["servers"] = len(outline_servers)
            result["vless"]["total"] = len(active_tgids)
            result["outline"]["total"] = len(active_tgids)
            
            # Check VLESS
            vless_clients = set()
            for srv in vless_servers:
                try:
                    sm = ServerManager(srv)
                    await sm.login()
                    clients = await sm.get_all_user()
                    if clients:
                        for c in clients:
                            email = c.get("email", "")
                            if email.endswith("_vless"):
                                try:
                                    vless_clients.add(int(email[:-6]))
                                except:
                                    pass
                except:
                    pass
            result["vless"]["ok"] = len(active_tgids & vless_clients)
            result["vless"]["missing"] = len(active_tgids - vless_clients)

            # Check Outline
            outline_clients = set()
            for srv in outline_servers:
                try:
                    sm = ServerManager(srv)
                    await sm.login()
                    clients = await sm.get_all_user()
                    if clients:
                        for c in clients:
                            name = c.name if hasattr(c, "name") else str(c)
                            try:
                                outline_clients.add(int(name))
                            except:
                                pass
                except:
                    pass
            result["outline"]["ok"] = len(active_tgids & outline_clients)
            result["outline"]["missing"] = len(active_tgids - outline_clients)
            
    except Exception as e:
        log.error(f"[KeysHealth] Error: {e}")
    
    return result


async def get_speed_test_results():
    """
    Fetch speed test results from Pushgateway.
    Returns dict with download/upload speeds for each server.
    """
    import aiohttp
    
    PUSHGATEWAY_URL = "http://130.49.146.140:9091/metrics"
    
    results = {
        "servers": {},  # server_name -> {download, upload, ping}
        "timestamp": None,
        "error": None
    }
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(PUSHGATEWAY_URL) as response:
                if response.status == 200:
                    text = await response.text()
                    
                    # Parse metrics
                    for line in text.split("\n"):
                        if line.startswith("#") or not line.strip():
                            continue
                        
                        # speedtest_download_mbps{instance="russia",job="speedtest",target="germany"} 18.42
                        if "speedtest_download_mbps" in line and 'target="' in line:
                            try:
                                target = line.split('target="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                if target not in results["servers"]:
                                    results["servers"][target] = {}
                                results["servers"][target]["download"] = value
                            except:
                                pass
                        
                        elif "speedtest_upload_mbps" in line and 'target="' in line:
                            try:
                                target = line.split('target="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                if target not in results["servers"]:
                                    results["servers"][target] = {}
                                results["servers"][target]["upload"] = value
                            except:
                                pass
                        
                        elif "speedtest_ping_ms" in line and 'target="' in line:
                            try:
                                target = line.split('target="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                if target not in results["servers"]:
                                    results["servers"][target] = {}
                                results["servers"][target]["ping"] = value
                            except:
                                pass
                        
                        # internet_download_mbps{...server="germany"} 68.45
                        elif "internet_download_mbps" in line and 'server="' in line:
                            try:
                                server = line.split('server="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                key = f"{server}_local"
                                if key not in results["servers"]:
                                    results["servers"][key] = {}
                                results["servers"][key]["download"] = value
                            except:
                                pass
                        
                        elif "internet_upload_mbps" in line and 'server="' in line:
                            try:
                                server = line.split('server="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                key = f"{server}_local"
                                if key not in results["servers"]:
                                    results["servers"][key] = {}
                                results["servers"][key]["upload"] = value
                            except:
                                pass
                        # vpn_download_mbps - internet speed from bypass server
                        elif "vpn_download_mbps" in line and 'server="' in line:
                            try:
                                server = line.split('server="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                if server not in results["servers"]:
                                    results["servers"][server] = {}
                                results["servers"][server]["download"] = value
                            except:
                                pass

                        # vpn_to_nl_mbps - speed from bypass to NL
                        elif "vpn_to_nl_mbps" in line and 'server="' in line:
                            try:
                                server = line.split('server="')[1].split('"')[0]
                                value = float(line.split()[-1])
                                if server not in results["servers"]:
                                    results["servers"][server] = {}
                                results["servers"][server]["to_nl"] = value
                            except:
                                pass

                        # speedtest_nl_usa_download_mbps - USA speed tested from Netherlands (via tunnel)
                        elif "speedtest_nl_usa_download_mbps" in line:
                            try:
                                value = float(line.split()[-1])
                                if "usa" not in results["servers"]:
                                    results["servers"]["usa"] = {}
                                results["servers"]["usa"]["download"] = value
                            except:
                                pass

                        # speedtest_nl_usa_ping_ms - USA ping from Netherlands
                        elif "speedtest_nl_usa_ping_ms" in line:
                            try:
                                value = float(line.split()[-1])
                                if "usa" not in results["servers"]:
                                    results["servers"]["usa"] = {}
                                results["servers"]["usa"]["ping"] = value
                            except:
                                pass

                        # speedtest_local_mbps{target="usa"} - USA local speed (not via tunnel)
                        elif "speedtest_local_mbps" in line and 'target="usa"' in line:
                            try:
                                value = float(line.split()[-1])
                                if "usa" not in results["servers"]:
                                    results["servers"]["usa"] = {}
                                results["servers"]["usa"]["local"] = value
                            except:
                                pass
    except Exception as e:
        results["error"] = str(e)
    
    return results


# ==================== BYPASS SERVER TRAFFIC ====================

async def get_bypass_traffic(telegram_id: int) -> Dict:
    """
    Get user's traffic from ALL bypass servers (x-ui API).
    Traffic is SUMMED across all bypass servers.
    Returns: {'up': bytes, 'down': bytes, 'total': bytes, 'limit': bytes} or None
    """
    from bot.misc.VPN.ServerManager import ServerManager

    total_up = 0
    total_down = 0
    found_on_any_server = False

    try:
        # Get bypass servers from DB
        bypass_servers = await get_bypass_servers()

        if not bypass_servers:
            log.warning(f"[bypass_traffic] No bypass servers found in database")
            return None

        email = f"{telegram_id}_vless"

        for server in bypass_servers:
            try:
                # Use ServerManager for proper connection handling
                manager = ServerManager(server)
                await manager.login()

                # Get inbound info with client stats
                xui = manager.client.xui
                inbounds_response = await xui.get_inbounds()

                if not inbounds_response.get("success"):
                    log.warning(f"[bypass_traffic] Failed to get inbounds from {server.name} for user {telegram_id}")
                    continue

                # Find user's traffic on this server
                for inbound in inbounds_response.get("obj", []):
                    for client in inbound.get("clientStats", []):
                        if client.get("email") == email:
                            up = client.get("up", 0) or 0
                            down = client.get("down", 0) or 0
                            total_up += up
                            total_down += down
                            found_on_any_server = True
                            log.debug(f"[bypass_traffic] User {telegram_id} on {server.name}: up={up}, down={down}")
                            break

            except Exception as e:
                log.error(f"[bypass_traffic] Error getting traffic from {server.name} for user {telegram_id}: {e}")
                continue

        if not found_on_any_server:
            # User not found on any bypass server (this is normal for users without bypass key)
            return None

        return {
            "up": total_up,
            "down": total_down,
            "total": total_up + total_down,
            "limit": BYPASS_LIMIT_BYTES,
            "total_formatted": format_bytes(total_up + total_down),
            "limit_formatted": format_bytes(BYPASS_LIMIT_BYTES)
        }

    except Exception as e:
        log.error(f"[bypass_traffic] Error for user {telegram_id}: {type(e).__name__}: {e}")
        return None




# Bypass server constants (module level for notifications)
# Bypass servers are now loaded from DB (servers with traffic_limit IS NOT NULL)
BYPASS_LIMIT_GB = 10  # 10 GB limit (sum across all bypass servers)
BYPASS_LIMIT_BYTES = BYPASS_LIMIT_GB * 1024 * 1024 * 1024  # 10737418240 bytes
BYPASS_RESET_DAYS = 30  # Reset every 30 days


async def get_bypass_servers() -> List[Servers]:
    """
    Get all bypass servers from database.
    Bypass servers are identified by is_bypass = True.
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(
            Servers.work == True,
            Servers.is_bypass == True
        )
        result = await db.execute(stmt)
        return result.scalars().all()


async def get_all_bypass_traffic() -> Dict[int, int]:
    """
    Get traffic for ALL users from ALL bypass servers.
    Traffic is SUMMED across all bypass servers.
    Returns: {telegram_id: total_bytes}
    """
    result = {}

    try:
        # Get bypass servers from DB
        bypass_servers = await get_bypass_servers()

        if not bypass_servers:
            log.warning("[bypass_traffic] No bypass servers found in database")
            return result

        log.info(f"[bypass_traffic] Found {len(bypass_servers)} bypass servers")

        for server in bypass_servers:
            try:
                # Use ServerManager for proper connection handling
                manager = ServerManager(server)
                await manager.login()

                # Get inbound info with client stats
                xui = manager.client.xui
                inbounds_response = await xui.get_inbounds()

                if not inbounds_response.get("success"):
                    log.warning(f"[bypass_traffic] Failed to get inbounds from {server.name}")
                    continue

                # Collect traffic from this server
                for inbound in inbounds_response.get("obj", []):
                    for client in inbound.get("clientStats", []):
                        email = client.get("email", "")
                        if email.endswith("_vless"):
                            try:
                                tgid = int(email.replace("_vless", ""))
                                up = client.get("up", 0) or 0
                                down = client.get("down", 0) or 0
                                # SUM traffic from all bypass servers
                                result[tgid] = result.get(tgid, 0) + up + down
                            except ValueError:
                                pass

                log.debug(f"[bypass_traffic] Collected traffic from {server.name}")

            except Exception as e:
                log.error(f"[bypass_traffic] Error getting traffic from {server.name}: {e}")
                continue

        log.info(f"[bypass_traffic] Fetched traffic for {len(result)} users from {len(bypass_servers)} servers")
        return result

    except Exception as e:
        log.error(f"[bypass_traffic] Error fetching all traffic: {e}")
        return result


async def check_and_notify_bypass_traffic(bot) -> Dict[str, int]:
    """
    Check bypass traffic for all users and send notifications at 50%, 70%, 90%, 100%.
    Called by scheduler every hour.
    Returns statistics.
    """
    from bot.misc.util import CONFIG

    stats = {'checked': 0, 'notified_50': 0, 'notified_70': 0, 'notified_90': 0, 'blocked': 0, 'errors': 0}
    now = datetime.utcnow()

    # Get all bypass traffic at once
    bypass_traffic = await get_all_bypass_traffic()

    if not bypass_traffic:
        log.info("[bypass_traffic] No bypass traffic data or no users")
        return stats

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all active users
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            Persons.tgid.in_(bypass_traffic.keys())
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        for user in users:
            stats['checked'] += 1

            try:
                total = bypass_traffic.get(user.tgid, 0)
                offset = user.bypass_offset_bytes or 0
                current = max(0, total - offset)
                percent = (current / BYPASS_LIMIT_BYTES * 100) if BYPASS_LIMIT_BYTES > 0 else 0

                # Update traffic in DB
                user.bypass_traffic_bytes = total

                # Calculate days until reset
                days_until_reset = BYPASS_RESET_DAYS
                if user.bypass_reset_date:
                    reset_date = user.bypass_reset_date
                    if reset_date.tzinfo is not None:
                        reset_date = reset_date.replace(tzinfo=None)
                    next_reset = reset_date + timedelta(days=BYPASS_RESET_DAYS)
                    delta = next_reset - now
                    days_until_reset = max(0, delta.days)

                remaining = max(0, BYPASS_LIMIT_BYTES - current)

                # Check thresholds and send notifications
                # 100% - block
                if percent >= 100:
                    if not getattr(user, '_bypass_blocked_notified', False):
                        log.warning(f"[bypass_traffic] User {user.tgid} exceeded 100%: {format_bytes(current)}")
                        try:
                            await bot.send_message(
                                user.tgid,
                                f"🚫 <b>Лимит трафика на сервере Обхода исчерпан!</b>\n\n"
                                f"Использовано: {format_bytes(current)} / {format_bytes(BYPASS_LIMIT_BYTES)} (100%)\n\n"
                                f"Доступ к серверу Обхода отключён.\n\n"
                                f"✅ <b>Основные VPN серверы (Германия, Нидерланды) — продолжают работать!</b>\n\n"
                                f"💡 Оплатите подписку чтобы сбросить лимит и восстановить доступ."
                            )
                            stats['blocked'] += 1
                        except Exception as e:
                            log.error(f"[bypass_traffic] Failed to notify user {user.tgid} about 100%: {e}")

                # 90% warning
                elif percent >= 90 and not user.bypass_warning_90_sent:
                    log.info(f"[bypass_traffic] Sending 90% warning to user {user.tgid}")
                    try:
                        await bot.send_message(
                            user.tgid,
                            f"🚨 <b>Критично! Лимит почти исчерпан</b>\n\n"
                            f"Использовано: {format_bytes(current)} / {format_bytes(BYPASS_LIMIT_BYTES)} (90%)\n"
                            f"Осталось: {format_bytes(remaining)}\n\n"
                            f"При исчерпании лимита сервер Обхода будет отключён.\n\n"
                            f"💡 Оплатите подписку чтобы сбросить лимит.\n"
                            f"Или подождите {days_until_reset} дней до автоматического сброса."
                        )
                        user.bypass_warning_90_sent = True
                        stats['notified_90'] += 1
                    except Exception as e:
                        log.error(f"[bypass_traffic] Failed to send 90% warning to {user.tgid}: {e}")

                # 70% warning
                elif percent >= 70 and not user.bypass_warning_70_sent:
                    log.info(f"[bypass_traffic] Sending 70% warning to user {user.tgid}")
                    try:
                        await bot.send_message(
                            user.tgid,
                            f"⚠️ <b>Внимание! Лимит почти израсходован</b>\n\n"
                            f"Использовано: {format_bytes(current)} / {format_bytes(BYPASS_LIMIT_BYTES)} (70%)\n"
                            f"Осталось: {format_bytes(remaining)}\n\n"
                            f"ℹ️ Это лимит сервера Обхода (для белых списков РФ).\n"
                            f"При исчерпании — сервер Обхода будет недоступен.\n"
                            f"Основные VPN серверы продолжат работать без ограничений.\n\n"
                            f"Сброс через {days_until_reset} дней или при оплате подписки."
                        )
                        user.bypass_warning_70_sent = True
                        stats['notified_70'] += 1
                    except Exception as e:
                        log.error(f"[bypass_traffic] Failed to send 70% warning to {user.tgid}: {e}")

                # 50% warning
                elif percent >= 50 and not user.bypass_warning_50_sent:
                    log.info(f"[bypass_traffic] Sending 50% warning to user {user.tgid}")
                    try:
                        await bot.send_message(
                            user.tgid,
                            f"📊 <b>Лимит трафика на сервере Обхода</b>\n\n"
                            f"Использовано: {format_bytes(current)} / {format_bytes(BYPASS_LIMIT_BYTES)} (50%)\n\n"
                            f"ℹ️ Это лимит для сервера, который работает внутри России.\n"
                            f"Основные серверы VPN (Германия, Нидерланды) — без ограничений.\n\n"
                            f"Лимит сбрасывается через {days_until_reset} дней или при оплате подписки."
                        )
                        user.bypass_warning_50_sent = True
                        stats['notified_50'] += 1
                    except Exception as e:
                        log.error(f"[bypass_traffic] Failed to send 50% warning to {user.tgid}: {e}")

            except Exception as e:
                log.error(f"[bypass_traffic] Error processing user {user.tgid}: {e}")
                stats['errors'] += 1

        await db.commit()

    log.info(f"[bypass_traffic] Check complete: {stats}")
    return stats


async def reset_bypass_traffic(telegram_id: int) -> bool:
    """
    Reset bypass traffic counter for a user (called after payment).
    Sets offset to current total, so "current traffic" starts from 0.
    """
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).where(Persons.tgid == telegram_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if user:
                current_total = user.bypass_traffic_bytes or 0
                user.bypass_offset_bytes = current_total
                user.bypass_reset_date = datetime.now(timezone.utc)
                # Reset warning flags
                user.bypass_warning_50_sent = False
                user.bypass_warning_70_sent = False
                user.bypass_warning_90_sent = False
                await db.commit()

                log.info(f"[bypass_traffic] Reset for user {telegram_id}: offset set to {format_bytes(current_total)}")
                return True
            else:
                log.warning(f"[bypass_traffic] User {telegram_id} not found for reset")
                return False

    except Exception as e:
        log.error(f"[bypass_traffic] Error resetting for user {telegram_id}: {e}")
        return False


async def reset_monthly_bypass_traffic() -> Dict[str, int]:
    """
    Reset bypass traffic for users whose last reset was more than 30 days ago.
    Called daily by scheduler.
    """
    stats = {'checked': 0, 'reset': 0, 'errors': 0}
    now = datetime.utcnow()
    reset_threshold = now - timedelta(days=BYPASS_RESET_DAYS)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all users with active subscriptions and bypass traffic
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            Persons.bypass_traffic_bytes > 0
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        for user in users:
            stats['checked'] += 1
            try:
                last_reset = user.bypass_reset_date

                # Reset if: no reset date OR reset was more than 30 days ago
                if last_reset is None or (last_reset.replace(tzinfo=None) if last_reset.tzinfo else last_reset) < reset_threshold:
                    current_total = user.bypass_traffic_bytes or 0
                    user.bypass_offset_bytes = current_total
                    user.bypass_reset_date = now
                    # Reset warning flags
                    user.bypass_warning_50_sent = False
                    user.bypass_warning_70_sent = False
                    user.bypass_warning_90_sent = False
                    stats['reset'] += 1
                    log.info(f"[bypass_traffic] Monthly reset for user {user.tgid}: offset set to {format_bytes(current_total)}")

            except Exception as e:
                log.error(f"[bypass_traffic] Error in monthly reset for user {user.tgid}: {e}")
                stats['errors'] += 1

        await db.commit()

    log.info(f"[bypass_traffic] Monthly reset complete: {stats}")
    return stats

# ==================== SERVER HEALTH MONITORING ====================

# Global dict to track server status (to detect changes)
_server_status: Dict[str, bool] = {}

# Global dict to track speed status for alerts (server_key -> True if OK, False if problem)
_speed_status: Dict[str, bool] = {}


async def check_server_available(server) -> bool:
    """
    Check if a VPN server is reachable.
    Returns True if available, False otherwise.
    """
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=10)

        if hasattr(server, 'type_vpn'):
            # Database server object
            if server.type_vpn == 0:  # Outline
                # Parse outline_link JSON to get apiUrl
                import json
                try:
                    if not server.outline_link:
                        log.warning(f"[HealthCheck] No outline_link for {server.name}")
                        return False
                    outline_config = json.loads(server.outline_link)
                    url = outline_config.get('apiUrl', '')
                    if not url:
                        log.warning(f"[HealthCheck] No apiUrl in outline_link for {server.name}")
                        return False
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url, ssl=False) as resp:
                            # Any response means server is up
                            return resp.status in [200, 401, 403, 404, 500]
                except json.JSONDecodeError:
                    log.warning(f"[HealthCheck] Invalid outline_link JSON for {server.name}")
                    return False
            else:
                # VLESS/Shadowsocks - check x-ui panel
                # Extract IP without port if present
                ip = server.ip.split(':')[0] if ':' in server.ip else server.ip
                port = server.ip.split(':')[1] if ':' in server.ip else '2053'
                # Use HTTPS if connection_method is True
                protocol = "https" if server.connection_method else "http"
                url = f"{protocol}://{ip}:{port}"
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, ssl=False) as resp:
                        return resp.status == 200
        else:
            # Dict-based server (bypass)
            url = server.get("url", "")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    return resp.status == 200

    except asyncio.TimeoutError:
        server_name = server.name if hasattr(server, 'name') else server.get('name', 'unknown')
        log.warning(f"[HealthCheck] Timeout checking server: {server_name}")
        return False
    except Exception as e:
        server_name = server.name if hasattr(server, 'name') else (server.get('name', 'unknown') if isinstance(server, dict) else 'unknown')
        log.warning(f"[HealthCheck] Error checking server {server_name}: {e}")
        return False


async def check_server_with_retries(server, max_retries: int = 3, retry_delay: int = 10) -> bool:
    """
    Check server availability with retries to avoid false positives.
    Only returns False if ALL retry attempts fail.
    """
    server_name = server.name if hasattr(server, 'name') else server.get('name', 'unknown')
    
    for attempt in range(max_retries):
        is_available = await check_server_available(server)
        
        if is_available:
            if attempt > 0:
                log.info(f"[HealthCheck] Server {server_name} responded on attempt {attempt + 1}")
            return True
        
        # If not last attempt, wait and retry
        if attempt < max_retries - 1:
            log.info(f"[HealthCheck] Server {server_name} not responding, retry {attempt + 2}/{max_retries} in {retry_delay}s")
            await asyncio.sleep(retry_delay)
    
    # All retries failed
    log.warning(f"[HealthCheck] Server {server_name} failed all {max_retries} checks")
    return False


async def check_servers_health(bot) -> Dict[str, any]:
    """
    Check health of all VPN servers and send alerts on status changes.
    Groups servers by IP - one notification per physical server.
    Returns statistics: {'checked': N, 'online': N, 'offline': N, 'alerts_sent': N}
    """
    global _server_status

    stats = {'checked': 0, 'online': 0, 'offline': 0, 'alerts_sent': 0}
    from bot.misc.util import CONFIG

    # Get all servers from database
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.work == True).order_by(Servers.id)
        result = await db.execute(stmt)
        db_servers = result.scalars().all()

    # Group servers by base IP (without port)
    servers_by_ip = {}
    for srv in db_servers:
        # Extract base IP (remove port if present)
        base_ip = srv.ip.split(':')[0] if srv.ip else "unknown"
        if base_ip not in servers_by_ip:
            servers_by_ip[base_ip] = []
        servers_by_ip[base_ip].append(srv)

    # Check each physical server (by IP)
    for base_ip, servers in servers_by_ip.items():
        stats['checked'] += 1

        # Check if ANY server on this IP is available
        is_available = False
        server_names = []

        for srv in servers:
            server_names.append(srv.name)
            if await check_server_with_retries(srv):
                is_available = True
                break  # One successful check is enough

        # Use IP as unique identifier for status tracking
        server_id = f"ip_{base_ip}"

        # Get previous status (default to True = was online)
        prev_status = _server_status.get(server_id, True)

        # Update current status
        _server_status[server_id] = is_available

        # Format server names for notification
        if len(server_names) == 1:
            display_name = server_names[0]
        else:
            display_name = server_names[0]  # Main name
            # Add note about other services
            other_count = len(server_names) - 1
            display_name += f" (+{other_count} сервис{'а' if other_count < 5 else 'ов'})"

        if is_available:
            stats['online'] += 1

            # Server came back online
            if not prev_status:
                log.info(f"[HealthCheck] ✅ Server {base_ip} is back ONLINE")
                # Send recovery alert via alerts bot
                from bot.misc.alerts import send_admin_alert
                await send_admin_alert(
                    f"✅ <b>Сервер снова онлайн!</b>\n\n"
                    f"🖥 {display_name}\n"
                    f"🌐 {base_ip}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
                )
                stats['alerts_sent'] += 1
        else:
            stats['offline'] += 1

            # Server went down
            if prev_status:
                log.warning(f"[HealthCheck] 🚨 Server {base_ip} is DOWN!")
                # Send alert via alerts bot
                from bot.misc.alerts import send_admin_alert
                await send_admin_alert(
                    f"🚨 <b>СЕРВЕР НЕДОСТУПЕН!</b>\n\n"
                    f"🖥 {display_name}\n"
                    f"🌐 {base_ip}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}\n\n"
                    f"⚠️ Проверьте сервер!"
                )
                stats['alerts_sent'] += 1
            else:
                # Still offline, log but don't spam
                log.debug(f"[HealthCheck] Server {base_ip} still offline")

    log.info(f"[HealthCheck] Complete: {stats}")
    return stats


async def check_servers_speed(bot) -> Dict[str, any]:
    """
    Check speed of all VPN servers from Pushgateway metrics and send alerts on status changes.
    Uses centralized alerts bot configuration from .env.
    Returns statistics: {'checked': N, 'ok': N, 'slow': N, 'alerts_sent': N}
    """
    global _speed_status

    stats = {'checked': 0, 'ok': 0, 'slow': 0, 'no_data': 0, 'alerts_sent': 0}
    SPEED_THRESHOLD_RU = 30    # Mbps - порог для скорости из России
    SPEED_THRESHOLD_LOCAL = 50  # Mbps - порог для локальной скорости сервера

    # Mapping of Pushgateway server keys to display names
    # Format: pushgateway_key -> (display_name, use_local_key)
    # use_local_key: if True, also check {key}_local for local speed
    SERVER_MAPPING = {
        "germany": ("🇩🇪 Германия", True),
        "netherlands": ("🇳🇱 Нидерланды", True),
        "netherlands2": ("🇳🇱 Нидерланды-2", True),
        "netherlands3": ("🇳🇱 Нидерланды-3", True),
        "spain": ("🇪🇸 Испания", True),
        "usa": ("🇺🇸 США", True),
        "bypass_yc": ("🇷🇺 RU-bypass", False),
    }

    # Get speed results from Pushgateway
    speed_results = await get_speed_test_results()

    if speed_results.get("error"):
        log.warning(f"[SpeedCheck] Failed to get Pushgateway metrics: {speed_results['error']}")
        return stats

    servers_data = speed_results.get("servers", {})

    for server_key, (display_name, use_local) in SERVER_MAPPING.items():
        # Get download speed
        download = None  # Speed from Russia to VPN server
        local_download = None  # Server's local internet speed

        # Main speed (from Russia to VPN server)
        if server_key in servers_data:
            download = servers_data[server_key].get("download")

        # Local speed (server's own internet)
        local_key = f"{server_key}_local"
        if use_local and local_key in servers_data:
            local_download = servers_data[local_key].get("download")

        # Skip if no data at all
        if download is None and local_download is None:
            stats['no_data'] += 1
            continue

        stats['checked'] += 1

        # Check each metric against its threshold
        ru_ok = download is None or download >= SPEED_THRESHOLD_RU
        local_ok = local_download is None or local_download >= SPEED_THRESHOLD_LOCAL
        is_ok = ru_ok and local_ok

        # Get previous status (default to True = was OK)
        prev_status = _speed_status.get(server_key, True)

        # Update current status
        _speed_status[server_key] = is_ok

        # Build speed info string showing both metrics with their thresholds
        def format_speed_info():
            lines = []
            if download is not None:
                status = "✅" if download >= SPEED_THRESHOLD_RU else "⚠️"
                lines.append(f"   {status} →RU: {download:.1f} Mbps (порог {SPEED_THRESHOLD_RU})")
            if local_download is not None:
                status = "✅" if local_download >= SPEED_THRESHOLD_LOCAL else "⚠️"
                lines.append(f"   {status} Локальная: {local_download:.1f} Mbps (порог {SPEED_THRESHOLD_LOCAL})")
            return "\n".join(lines)

        if is_ok:
            stats['ok'] += 1

            # Speed recovered
            if not prev_status:
                log.info(f"[SpeedCheck] ✅ Speed recovered on {server_key}")
                from bot.misc.alerts import send_admin_alert

                msg = f"✅ <b>Скорость восстановлена</b>\n\n"
                msg += f"🖥 {display_name}\n"
                msg += f"📊 Скорость:\n{format_speed_info()}\n"
                msg += f"⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"

                await send_admin_alert(msg)
                stats['alerts_sent'] += 1
        else:
            stats['slow'] += 1

            # Speed dropped below threshold
            if prev_status:
                log.warning(f"[SpeedCheck] 🚨 Slow speed on {server_key}")
                from bot.misc.alerts import send_admin_alert

                msg = f"🚨 <b>Проблема со скоростью</b>\n\n"
                msg += f"🖥 {display_name}\n"
                msg += f"📊 Скорость:\n{format_speed_info()}\n"
                msg += f"⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"

                await send_admin_alert(msg)
                stats['alerts_sent'] += 1
            else:
                # Still slow, don't spam
                log.debug(f"[SpeedCheck] Server {server_key} still slow")

    log.info(f"[SpeedCheck] Complete: {stats}")
    return stats


async def get_servers_status() -> List[Dict]:
    """
    Get current status of all servers (for admin panel).
    Returns list of server status dicts.
    """
    global _server_status

    result = []

    # Get all servers from database
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.work == True).order_by(Servers.id)
        db_result = await db.execute(stmt)
        db_servers = db_result.scalars().all()

        for srv in db_servers:
            server_id = f"db_{srv.id}"
            is_online = _server_status.get(server_id, None)

            # Determine server type emoji
            if srv.type_vpn == 0:
                type_emoji = "🪐"  # Outline
            elif srv.type_vpn == 1:
                type_emoji = "🐊"  # VLESS
            else:
                type_emoji = "🦈"  # Shadowsocks

            result.append({
                "id": server_id,
                "name": srv.name,
                "type": type_emoji,
                "online": is_online,
                "status": "✅" if is_online else ("❌" if is_online is False else "❓")
            })

    return result
