"""
Traffic Monitoring Module
Collects and aggregates traffic usage from all VPN servers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Servers
from bot.misc.VPN.ServerManager import ServerManager

log = logging.getLogger(__name__)

# 500GB in bytes
DEFAULT_TRAFFIC_LIMIT = 500 * 1024 * 1024 * 1024  # 536870912000

# Количество дней до автоматического сброса трафика
TRAFFIC_RESET_DAYS = 30


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
    """
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
                    return {}

                result = {}
                bytes_by_id = metrics['bytesTransferredByUserId']

                for key in keys:
                    key_id = str(key.key_id)
                    telegram_id = key.name  # telegram_id is stored as key name
                    if key_id in bytes_by_id and telegram_id.isdigit():
                        # Use _outline suffix for consistency with _vless and _ss
                        result[f"{telegram_id}_outline"] = bytes_by_id[key_id]

                log.debug(f"[Traffic] Fetched {len(result)} clients from {server.name} (Outline)")
                return result

            except Exception as e:
                log.error(f"[Traffic] Error fetching Outline traffic from {server.name}: {e}")
                return {}

        # Get all client stats from server
        client_stats = await manager.get_all_user()
        if not client_stats:
            return {}

        result = {}
        for stat in client_stats:
            email = stat.get('email', '')
            up = stat.get('up', 0) or 0
            down = stat.get('down', 0) or 0
            result[email] = up + down

        log.debug(f"[Traffic] Fetched {len(result)} clients from {server.name}")
        return result

    except Exception as e:
        log.error(f"[Traffic] Error fetching from server {server.name}: {e}")
        return {}


async def update_all_users_traffic() -> Dict[str, int]:
    """
    Update traffic stats for ALL users with active subscriptions.
    OPTIMIZED: Fetches all data from servers first, then updates users.
    Returns statistics: {'updated': N, 'exceeded': N, 'errors': N, 'active': N}
    """
    import asyncio
    stats = {'updated': 0, 'exceeded': 0, 'errors': 0, 'blocked': 0, 'active': 0}
    now = datetime.now()

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all active servers
        stmt_servers = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([0, 1, 2])  # Outline, VLESS and Shadowsocks
        )
        result_servers = await db.execute(stmt_servers)
        servers = result_servers.scalars().all()

        # OPTIMIZATION: Fetch all traffic data from all servers in parallel
        log.info(f"[Traffic] Fetching data from {len(servers)} servers...")
        tasks = [fetch_all_traffic_from_server(server) for server in servers]
        server_data_list = await asyncio.gather(*tasks)

        # Merge all server data into one dict: {tgid: total_traffic}
        traffic_cache = {}  # {telegram_id: total_bytes}
        for server_data in server_data_list:
            for email, traffic in server_data.items():
                # Extract telegram_id from email (format: {tgid}_outline, {tgid}_vless or {tgid}_ss)
                tgid = email.split('_')[0] if '_' in email else email
                if tgid.isdigit():
                    tgid = int(tgid)
                    traffic_cache[tgid] = traffic_cache.get(tgid, 0) + traffic

        log.info(f"[Traffic] Cached traffic for {len(traffic_cache)} users from servers")

        # Get all users with active subscriptions
        stmt = select(Persons).filter(
            Persons.subscription_active == True
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        log.info(f"[Traffic] Updating {len(users)} active users")

        for user in users:
            try:
                # OPTIMIZATION: Get traffic from cache instead of querying servers
                total_traffic = traffic_cache.get(user.tgid, 0)

                # Check if traffic changed (user is actively using VPN)
                previous = user.previous_traffic_bytes or 0
                if total_traffic > previous:
                    # Traffic increased - user is active
                    user.traffic_last_change = now
                    stats['active'] += 1
                    log.debug(f"[Traffic] User {user.tgid} active: {format_bytes(previous)} -> {format_bytes(total_traffic)}")

                # Save current traffic as previous for next check
                user.previous_traffic_bytes = total_traffic
                user.total_traffic_bytes = total_traffic

                # Fix offset if it's greater than total (keys were recreated)
                if user.traffic_offset_bytes and user.traffic_offset_bytes > total_traffic:
                    log.warning(f"[Traffic] User {user.tgid} offset ({format_bytes(user.traffic_offset_bytes)}) > total ({format_bytes(total_traffic)}), resetting offset")
                    user.traffic_offset_bytes = total_traffic

                # Check if exceeded limit (using current = total - offset)
                limit = user.traffic_limit_bytes or DEFAULT_TRAFFIC_LIMIT
                offset = user.traffic_offset_bytes or 0
                current_traffic = max(0, total_traffic - offset)

                if current_traffic >= limit:
                    stats['exceeded'] += 1
                    log.warning(
                        f"[Traffic] User {user.tgid} EXCEEDED limit: "
                        f"{format_bytes(current_traffic)} / {format_bytes(limit)}"
                    )

                stats['updated'] += 1

            except Exception as e:
                log.error(f"[Traffic] Error updating traffic for user {user.tgid}: {e}")
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
                total = user.total_traffic_bytes or 0
                offset = user.traffic_offset_bytes or 0
                current = max(0, total - offset)
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
                user.traffic_reset_date = datetime.now()
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
    now = datetime.now()
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

                # Reset if: no reset date OR reset was more than 30 days ago
                if last_reset is None or last_reset < reset_threshold:
                    current_total = user.total_traffic_bytes or 0
                    user.traffic_offset_bytes = current_total
                    user.traffic_reset_date = now
                    user.traffic_warning_sent = False  # Сбрасываем флаг предупреждения
                    stats['reset'] += 1
                    log.info(
                        f"[Traffic] Monthly reset for user {user.tgid}: "
                        f"offset set to {format_bytes(current_total)}"
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

    now = datetime.now()

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
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.tgid == telegram_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        limit = user.traffic_limit_bytes or DEFAULT_TRAFFIC_LIMIT
        total = user.total_traffic_bytes or 0
        offset = user.traffic_offset_bytes or 0
        current = max(0, total - offset)  # Трафик с момента оплаты
        remaining = max(0, limit - current)
        percent_used = (current / limit * 100) if limit > 0 else 0

        days_until_reset = get_days_until_reset(user.traffic_reset_date)

        return {
            'used_bytes': current,  # Текущий период
            'used_formatted': format_bytes(current),
            'total_bytes': total,  # Всего за всё время
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
    Send setup reminder to users who paid but haven't used VPN for 2+ days.
    Called daily by scheduler.
    Returns statistics: {'checked': N, 'sent': N, 'errors': N}
    """
    from datetime import datetime, timedelta
    
    stats = {'checked': 0, 'sent': 0, 'errors': 0, 'blocked': 0}
    now = datetime.now()
    two_days_ago = now - timedelta(days=2)
    
    MESSAGE = '''Привет! 👋

У тебя активная подписка VPN, но мы заметили что ты ещё не подключался.

Может нужна помощь с настройкой? Это займёт всего пару минут:
• Поможем выбрать приложение для твоего устройства
• Настроим подключение
• Проверим что всё работает

Напиши в поддержку — разберёмся:
👉 @VPN_YouSupport_bot'''

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Find users:
        # - subscription_active = true
        # - total_traffic_bytes = 0 or NULL
        # - subscription_created_at < 2 days ago OR subscription (timestamp) was set > 2 days ago
        # - setup_reminder_sent = false
        # - bot_blocked = false
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            (Persons.total_traffic_bytes == 0) | (Persons.total_traffic_bytes == None),
            Persons.setup_reminder_sent == False,
            (Persons.bot_blocked == False) | (Persons.bot_blocked == None)
        )
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        for user in users:
            stats['checked'] += 1
            
            # Check if subscription is older than 2 days
            sub_date = user.subscription_created_at
            if sub_date is None:
                # Fallback: check subscription timestamp
                if user.subscription:
                    # subscription is end date, estimate start date based on subscription_months
                    months = user.subscription_months or 1
                    sub_start = datetime.fromtimestamp(user.subscription) - timedelta(days=months * 30)
                    if sub_start > two_days_ago:
                        continue  # Too recent
                else:
                    continue  # No subscription date
            else:
                # Handle timezone-aware datetime
                if sub_date.tzinfo is not None:
                    sub_date = sub_date.replace(tzinfo=None)
                if sub_date > two_days_ago:
                    continue  # Too recent
            
            # Send reminder
            try:
                await bot.send_message(user.tgid, MESSAGE)
                user.setup_reminder_sent = True
                stats['sent'] += 1
                log.info(f"[SetupReminder] Sent to user {user.tgid}")
            except Exception as e:
                error_msg = str(e).lower()
                if 'blocked' in error_msg or 'deactivated' in error_msg:
                    user.bot_blocked = True
                    user.setup_reminder_sent = True  # Don't retry
                    stats['blocked'] += 1
                    log.info(f"[SetupReminder] User {user.tgid} blocked bot")
                else:
                    stats['errors'] += 1
                    log.error(f"[SetupReminder] Error sending to {user.tgid}: {e}")
        
        await db.commit()
    
    log.info(f"[SetupReminder] Complete: {stats}")
    return stats
