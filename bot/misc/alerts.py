"""
Admin Alerts Module
Sends technical alerts to a separate Telegram bot.
Payment alerts (autopay) still use the main bot.
"""
import aiohttp
import logging
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)


async def send_admin_alert(message: str, parse_mode: str = "HTML") -> bool:
    """
    Send alert to admin via separate alerts bot.
    Falls back to main bot admins if alerts bot is not configured.
    
    Args:
        message: Alert message text
        parse_mode: Telegram parse mode (HTML or Markdown)
    
    Returns:
        True if sent successfully, False otherwise
    """
    # Use alerts bot if configured, otherwise skip (don't use main bot for alerts)
    if not CONFIG.alerts_bot_token or not CONFIG.alerts_chat_id:
        log.warning("[Alerts] ALERTS_BOT_TOKEN or ALERTS_CHAT_ID not configured, skipping alert")
        return False
    
    url = f"https://api.telegram.org/bot{CONFIG.alerts_bot_token}/sendMessage"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": CONFIG.alerts_chat_id,
                "text": message,
                "parse_mode": parse_mode
            }) as response:
                if response.status == 200:
                    log.debug(f"[Alerts] Alert sent successfully")
                    return True
                else:
                    log.error(f"[Alerts] Failed to send alert: {response.status}")
                    return False
    except Exception as e:
        log.error(f"[Alerts] Error sending alert: {e}")
        return False
