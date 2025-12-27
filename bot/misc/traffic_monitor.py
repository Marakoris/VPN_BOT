"""
Traffic Monitoring Module
Collects and aggregates traffic usage from all VPN servers.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Servers
from bot.misc.VPN.ServerManager import ServerManager

log = logging.getLogger(__name__)

# 500GB in bytes
DEFAULT_TRAFFIC_LIMIT = 500 * 1024 * 1024 * 1024  # 536870912000


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


async def update_all_users_traffic() -> Dict[str, int]:
    """
    Update traffic stats for ALL users with active subscriptions.
    Also tracks traffic activity (when traffic last changed).
    Returns statistics: {'updated': N, 'exceeded': N, 'errors': N, 'active': N}
    """
    stats = {'updated': 0, 'exceeded': 0, 'errors': 0, 'blocked': 0, 'active': 0}
    now = datetime.now()

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all users with active subscriptions
        stmt = select(Persons).filter(
            Persons.subscription_active == True
        )
        result = await db.execute(stmt)
        users = result.scalars().all()

        log.info(f"[Traffic] Checking traffic for {len(users)} active users")

        for user in users:
            try:
                # Collect traffic from all servers
                total_traffic = await collect_user_traffic(user.tgid)

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

                # Check if exceeded limit
                limit = user.traffic_limit_bytes or DEFAULT_TRAFFIC_LIMIT

                if total_traffic >= limit:
                    stats['exceeded'] += 1
                    log.warning(
                        f"[Traffic] User {user.tgid} EXCEEDED limit: "
                        f"{format_bytes(total_traffic)} / {format_bytes(limit)}"
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
    Returns list of blocked user telegram IDs.
    """
    from bot.misc.subscription import expire_subscription
    from bot.misc.language import get_lang, Localization

    blocked_users = []

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get users who exceeded limit
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            Persons.total_traffic_bytes >= Persons.traffic_limit_bytes
        )
        result = await db.execute(stmt)
        exceeded_users = result.scalars().all()

        for user in exceeded_users:
            try:
                log.warning(
                    f"[Traffic] Blocking user {user.tgid}: "
                    f"{format_bytes(user.total_traffic_bytes)} >= {format_bytes(user.traffic_limit_bytes)}"
                )

                # Expire subscription (disable keys)
                await expire_subscription(user.tgid)

                # Notify user
                lang = await get_lang(user.tgid)
                try:
                    await bot.send_message(
                        user.tgid,
                        f"⚠️ Ваш лимит трафика исчерпан!\n\n"
                        f"📊 Использовано: {format_bytes(user.total_traffic_bytes)}\n"
                        f"📦 Лимит: {format_bytes(user.traffic_limit_bytes)}\n\n"
                        f"Для продолжения использования VPN, пожалуйста, продлите подписку."
                    )
                except Exception as e:
                    log.error(f"[Traffic] Could not notify user {user.tgid}: {e}")

                blocked_users.append(user.tgid)

            except Exception as e:
                log.error(f"[Traffic] Error blocking user {user.tgid}: {e}")

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
        used = user.total_traffic_bytes or 0
        remaining = max(0, limit - used)
        percent_used = (used / limit * 100) if limit > 0 else 0

        return {
            'used_bytes': used,
            'used_formatted': format_bytes(used),
            'limit_bytes': limit,
            'limit_formatted': format_bytes(limit),
            'remaining_bytes': remaining,
            'remaining_formatted': format_bytes(remaining),
            'percent_used': round(percent_used, 1),
            'reset_date': user.traffic_reset_date,
            'exceeded': used >= limit
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
