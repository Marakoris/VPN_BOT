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
    now = datetime.utcnow()  # Use naive UTC datetime to match DB

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
        now_ts = int(datetime.utcnow().timestamp())
        today_start_ts = int(today_start.timestamp())
        week_ago = today_start - timedelta(days=7)
        week_ago_ts = int(week_ago.timestamp())

        # Active subscribers total
        active_with_traffic_today = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.subscription > now_ts,
                Persons.traffic_last_change >= today_start,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        active_with_traffic_today = active_with_traffic_today.scalar() or 0

        active_with_traffic_yesterday = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.subscription > now_ts,
                Persons.traffic_last_change >= yesterday_start,
                Persons.traffic_last_change < today_start,
                (Persons.banned == False) | (Persons.banned == None)
            )
        )
        active_with_traffic_yesterday = active_with_traffic_yesterday.scalar() or 0

        active_with_traffic_week = await db.execute(
            select(func.count()).select_from(Persons).filter(
                Persons.subscription > now_ts,
                Persons.traffic_last_change >= week_ago,
                (Persons.banned == False) | (Persons.banned == None)
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
        format_keys_status("SS", keys_health["ss"]),
        format_keys_status("Outline", keys_health["outline"])
    ])
    
    # Check if there are problems
    keys_has_problems = (
        keys_health["vless"]["missing"] > 0 or 
        keys_health["ss"]["missing"] > 0 or 
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
        "netherlands3": "NL Нидерланды-3",
        "spain": "ES Испания",
        "bypass_yc": "🇷🇺 RU-bypass (→NL)"
    }

    for server_key in ["germany", "netherlands", "netherlands2", "netherlands3", "bypass_yc"]:
        if server_key in speed_results.get("servers", {}):
            data = speed_results["servers"][server_key]
            download = data.get("download", 0)
            upload = data.get("upload", 0)
            name = server_names.get(server_key, server_key)

            # Get local speed on server
            local_key = f"{server_key}_local"
            local_download = speed_results.get("servers", {}).get(local_key, {}).get("download", 0)

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
                speed_lines.append(f"  ❓ {name}: нет данных")
        else:
            name = server_names.get(server_key, server_key)
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
    Save current traffic as daily_traffic_start_bytes for all users.
    Should run at midnight to capture traffic at the start of each day.
    """
    from sqlalchemy import text
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            text("""
                UPDATE users 
                SET daily_traffic_start_bytes = COALESCE(total_traffic_bytes, 0)
                WHERE subscription_active = true
            """)
        )
        await db.commit()
        log.info(f"[Traffic] Daily snapshot saved for {result.rowcount} users")
        return result.rowcount


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
        "ss": {"total": 0, "ok": 0, "missing": 0, "servers": 0},
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
            
            # Group servers by type
            vless_servers = [s for s in servers if s.type_vpn == 1]
            ss_servers = [s for s in servers if s.type_vpn == 2]
            outline_servers = [s for s in servers if s.type_vpn == 0]
            
            result["vless"]["servers"] = len(vless_servers)
            result["ss"]["servers"] = len(ss_servers)
            result["outline"]["servers"] = len(outline_servers)
            result["vless"]["total"] = len(active_tgids)
            result["ss"]["total"] = len(active_tgids)
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
            
            # Check SS
            ss_clients = set()
            for srv in ss_servers:
                try:
                    sm = ServerManager(srv)
                    await sm.login()
                    clients = await sm.get_all_user()
                    if clients:
                        for c in clients:
                            email = c.get("email", "")
                            if email.endswith("_ss"):
                                try:
                                    ss_clients.add(int(email[:-3]))
                                except:
                                    pass
                except:
                    pass
            result["ss"]["ok"] = len(active_tgids & ss_clients)
            result["ss"]["missing"] = len(active_tgids - ss_clients)
            
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
    except Exception as e:
        results["error"] = str(e)
    
    return results


# ==================== BYPASS SERVER TRAFFIC ====================

async def get_bypass_traffic(telegram_id: int) -> Dict:
    """
    Get user's traffic from bypass server (x-ui API).
    Returns: {'up': bytes, 'down': bytes, 'total': bytes, 'limit': bytes} or None
    """
    import aiohttp
    
    BYPASS_URL = "http://84.201.128.231:2053"
    BYPASS_LOGIN = "admin"
    BYPASS_PASSWORD = "AdminPass123"
    BYPASS_LIMIT_GB = 10  # 10 GB limit
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        # Use cookie jar for x-ui session cookies (required for auth)
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:
            # Login
            login_data = {"username": BYPASS_LOGIN, "password": BYPASS_PASSWORD}
            async with session.post(f"{BYPASS_URL}/login", data=login_data) as resp:
                if resp.status != 200:
                    log.warning(f"[bypass_traffic] Login failed for user {telegram_id}, status: {resp.status}")
                    return None
            
            # Get inbounds
            async with session.get(f"{BYPASS_URL}/panel/api/inbounds/list") as resp:
                if resp.status != 200:
                    log.warning(f"[bypass_traffic] Inbounds request failed for user {telegram_id}, status: {resp.status}")
                    return None
                data = await resp.json()
            
            if not data.get("success"):
                log.warning(f"[bypass_traffic] API returned success=false for user {telegram_id}")
                return None
            
            # Find user's traffic
            email = f"{telegram_id}_vless"
            for inbound in data.get("obj", []):
                for client in inbound.get("clientStats", []):
                    if client.get("email") == email:
                        up = client.get("up", 0)
                        down = client.get("down", 0)
                        return {
                            "up": up,
                            "down": down,
                            "total": up + down,
                            "limit": BYPASS_LIMIT_GB * 1024 * 1024 * 1024,
                            "total_formatted": format_bytes(up + down),
                            "limit_formatted": format_bytes(BYPASS_LIMIT_GB * 1024 * 1024 * 1024)
                        }
            
            # User not found on bypass server (this is normal for users without bypass key)
            return None
    except asyncio.TimeoutError:
        log.warning(f"[bypass_traffic] Timeout for user {telegram_id}")
        return None
    except Exception as e:
        log.error(f"[bypass_traffic] Error for user {telegram_id}: {type(e).__name__}: {e}")
        return None


# ==================== SERVER HEALTH MONITORING ====================

# Global dict to track server status (to detect changes)
_server_status: Dict[str, bool] = {}

# Bypass server config
BYPASS_SERVER = {
    "name": "🗽 Bypass (Yandex Cloud)",
    "url": "http://84.201.128.231:2053",
    "type": "x-ui"
}


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
                url = f"http://{ip}:{port}"
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
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


async def check_servers_health(bot) -> Dict[str, any]:
    """
    Check health of all VPN servers and send alerts on status changes.
    Returns statistics: {'checked': N, 'online': N, 'offline': N, 'alerts_sent': N}
    """
    global _server_status

    stats = {'checked': 0, 'online': 0, 'offline': 0, 'alerts_sent': 0}
    from bot.misc.util import CONFIG

    servers_to_check = []

    # Get all servers from database
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.work == True).order_by(Servers.id)
        result = await db.execute(stmt)
        db_servers = result.scalars().all()

        for srv in db_servers:
            servers_to_check.append({
                "id": f"db_{srv.id}",
                "name": srv.name,
                "server": srv,
                "type": "database"
            })

    # Add bypass server
    servers_to_check.append({
        "id": "bypass",
        "name": BYPASS_SERVER["name"],
        "server": BYPASS_SERVER,
        "type": "bypass"
    })

    # Check each server
    for srv_info in servers_to_check:
        stats['checked'] += 1
        server_id = srv_info["id"]
        server_name = srv_info["name"]
        server = srv_info["server"]

        # Check availability
        is_available = await check_server_available(server)

        # Get previous status (default to True = was online)
        prev_status = _server_status.get(server_id, True)

        # Update current status
        _server_status[server_id] = is_available

        if is_available:
            stats['online'] += 1

            # Server came back online
            if not prev_status:
                log.info(f"[HealthCheck] ✅ Server {server_name} is back ONLINE")
                # Send recovery alert
                for admin_id in CONFIG.admins_ids:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"✅ <b>Сервер снова онлайн!</b>\n\n"
                            f"🖥 {server_name}\n"
                            f"⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
                        )
                        stats['alerts_sent'] += 1
                    except Exception as e:
                        log.error(f"[HealthCheck] Failed to send recovery alert to {admin_id}: {e}")
        else:
            stats['offline'] += 1

            # Server went down
            if prev_status:
                log.warning(f"[HealthCheck] 🚨 Server {server_name} is DOWN!")
                # Send alert
                for admin_id in CONFIG.admins_ids:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"🚨 <b>СЕРВЕР НЕДОСТУПЕН!</b>\n\n"
                            f"🖥 {server_name}\n"
                            f"⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}\n\n"
                            f"⚠️ Проверьте сервер!"
                        )
                        stats['alerts_sent'] += 1
                    except Exception as e:
                        log.error(f"[HealthCheck] Failed to send alert to {admin_id}: {e}")
            else:
                # Still offline, log but don't spam
                log.debug(f"[HealthCheck] Server {server_name} still offline")

    log.info(f"[HealthCheck] Complete: {stats}")
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

    # Add bypass server
    bypass_online = _server_status.get("bypass", None)
    result.append({
        "id": "bypass",
        "name": BYPASS_SERVER["name"],
        "type": "🗽",
        "online": bypass_online,
        "status": "✅" if bypass_online else ("❌" if bypass_online is False else "❓")
    })

    return result
