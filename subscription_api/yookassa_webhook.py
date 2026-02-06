"""
YooKassa Webhook Handler for VPN Bot

Handles delayed payments that weren't caught by polling.
When a payment is completed after the 30-minute polling window,
YooKassa sends a webhook notification that this handler processes.
"""
import os
import logging
import aiohttp
from typing import Dict, Optional, Any
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Payments
from bot.database.methods.update import add_time_person
from bot.database.methods.insert import add_payment
from bot.misc.traffic_monitor import reset_user_traffic, reset_bypass_traffic
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

# Telegram Bot token for sending notifications
TG_TOKEN = os.getenv("TG_TOKEN")
ADMINS_IDS = os.getenv("ADMINS_IDS", "")


async def _is_payment_processed(user_id: int, amount: float, payment_id: str) -> bool:
    """
    Check if this payment has already been processed.

    Prevents duplicate processing when both polling and webhook succeed.

    Args:
        user_id: Telegram user ID
        amount: Payment amount in RUB
        payment_id: YooKassa payment ID

    Returns:
        True if payment already exists, False otherwise
    """
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            # Get user by telegram ID
            stmt = select(Persons).filter(Persons.tgid == user_id)
            result = await db.execute(stmt)
            person = result.scalar_one_or_none()

            if not person:
                return False

            # Check for recent payment with same amount (within last hour)
            # This is a simple deduplication - payment_id could be stored for exact match
            from datetime import timedelta
            one_hour_ago = datetime.now() - timedelta(hours=1)

            stmt = select(Payments).filter(
                Payments.user == person.id,
                Payments.amount == amount,
                Payments.data >= one_hour_ago
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                log.info(f"[Webhook] Payment already processed for user {user_id}, amount {amount}")
                return True

            return False

    except Exception as e:
        log.error(f"[Webhook] Error checking payment status: {e}")
        return False


async def _send_user_notification(user_id: int, days: int, amount: float) -> bool:
    """
    Send Telegram notification to user about successful payment.

    Args:
        user_id: Telegram user ID
        days: Number of days added
        amount: Payment amount

    Returns:
        True if notification sent successfully
    """
    if not TG_TOKEN:
        log.error("[Webhook] TG_TOKEN not set, cannot send notification")
        return False

    try:
        # Get user to show subscription end date
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.tgid == user_id)
            result = await db.execute(stmt)
            person = result.scalar_one_or_none()

            if not person:
                log.error(f"[Webhook] User {user_id} not found for notification")
                return False

            subscription_end = datetime.fromtimestamp(person.subscription).strftime('%d.%m.%Y')

        message = (
            f"<b>Платёж обработан!</b>\n\n"
            f"Сумма: {amount:.0f} руб.\n"
            f"Подписка продлена на {days} дн.\n\n"
            f"Подписка активна до: <b>{subscription_end}</b>\n\n"
            f"Если VPN уже настроен — ничего делать не нужно, всё работает"
        )

        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

        async with aiohttp.ClientSession() as session:
            resp = await session.post(url, json={
                "chat_id": user_id,
                "text": message,
                "parse_mode": "HTML"
            })
            data = await resp.json()

            if data.get("ok"):
                log.info(f"[Webhook] Notification sent to user {user_id}")
                return True
            else:
                log.error(f"[Webhook] Failed to send notification: {data}")
                return False

    except Exception as e:
        log.error(f"[Webhook] Error sending user notification: {e}")
        return False


async def _send_admin_notifications(user_id: int, days: int, amount: float, payment_id: str) -> None:
    """
    Send Telegram notifications to admins about webhook payment.

    Args:
        user_id: Telegram user ID
        days: Number of days added
        amount: Payment amount
        payment_id: YooKassa payment ID
    """
    if not TG_TOKEN or not ADMINS_IDS:
        return

    try:
        admin_ids = [int(x.strip()) for x in ADMINS_IDS.split(",") if x.strip()]

        message = (
            f"<b>Webhook платёж обработан</b>\n\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Сумма: {amount:.0f} руб.\n"
            f"Дней: {days}\n"
            f"Payment ID: <code>{payment_id}</code>\n\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

        async with aiohttp.ClientSession() as session:
            for admin_id in admin_ids:
                try:
                    await session.post(url, json={
                        "chat_id": admin_id,
                        "text": message,
                        "parse_mode": "HTML"
                    })
                except Exception as e:
                    log.error(f"[Webhook] Failed to notify admin {admin_id}: {e}")

        log.info(f"[Webhook] Admin notifications sent for payment {payment_id}")

    except Exception as e:
        log.error(f"[Webhook] Error sending admin notifications: {e}")


async def process_payment_webhook(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process YooKassa payment webhook.

    This function handles the payment.succeeded event from YooKassa.
    It activates the user's subscription and sends notifications.

    Args:
        webhook_data: Parsed JSON from YooKassa webhook

    Returns:
        Dict with processing result
    """
    try:
        event_type = webhook_data.get("event")
        payment_obj = webhook_data.get("object", {})

        # Only process payment.succeeded events
        if event_type != "payment.succeeded":
            log.info(f"[Webhook] Ignoring event type: {event_type}")
            return {"status": "ignored", "reason": f"event_type={event_type}"}

        # Extract payment info
        payment_id = payment_obj.get("id")
        status = payment_obj.get("status")
        amount_obj = payment_obj.get("amount", {})
        amount = float(amount_obj.get("value", 0))
        metadata = payment_obj.get("metadata", {})

        # Get user info from metadata
        user_id_str = metadata.get("user_id")
        days_count_str = metadata.get("days_count")
        source = metadata.get("source", "unknown")

        if not user_id_str or not days_count_str:
            log.warning(f"[Webhook] Missing metadata in payment {payment_id}: {metadata}")
            return {
                "status": "error",
                "reason": "missing_metadata",
                "payment_id": payment_id
            }

        user_id = int(user_id_str)
        days_count = int(days_count_str)

        log.info(
            f"[Webhook] Processing payment {payment_id}: "
            f"user={user_id}, days={days_count}, amount={amount}, source={source}"
        )

        # Check for duplicate (polling may have already processed this)
        if await _is_payment_processed(user_id, amount, payment_id):
            log.info(f"[Webhook] Payment {payment_id} already processed, skipping")
            return {
                "status": "duplicate",
                "payment_id": payment_id,
                "user_id": user_id
            }

        # Activate subscription
        seconds_to_add = days_count * CONFIG.COUNT_SECOND_DAY

        success = await add_time_person(user_id, seconds_to_add)
        if not success:
            log.error(f"[Webhook] Failed to add time for user {user_id}")
            return {
                "status": "error",
                "reason": "add_time_failed",
                "user_id": user_id
            }

        # Reset traffic counters
        await reset_user_traffic(user_id)
        await reset_bypass_traffic(user_id)

        # Record payment in database
        try:
            await add_payment(user_id, amount, "YooKassa_Webhook")
        except Exception as e:
            log.error(f"[Webhook] Failed to record payment: {e}")
            # Don't fail the whole process - subscription is already activated

        # Send notifications
        await _send_user_notification(user_id, days_count, amount)
        await _send_admin_notifications(user_id, days_count, amount, payment_id)

        log.info(
            f"[Webhook] Successfully processed payment {payment_id}: "
            f"user={user_id}, +{days_count} days"
        )

        return {
            "status": "success",
            "payment_id": payment_id,
            "user_id": user_id,
            "days_added": days_count,
            "amount": amount
        }

    except Exception as e:
        log.error(f"[Webhook] Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "reason": str(e)
        }
