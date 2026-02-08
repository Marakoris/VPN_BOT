"""
YooKassa Webhook Handler for VPN Bot

Handles payment.succeeded events from YooKassa.
All actual payment processing (subscription extension, traffic reset,
notifications) is handled by the bot's KassaSmart polling flow.
This webhook only logs events for monitoring.
"""
import logging
from typing import Dict, Any
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Payments

log = logging.getLogger(__name__)


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


async def process_payment_webhook(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process YooKassa payment webhook.

    This function handles the payment.succeeded event from YooKassa.
    All actual payment processing (subscription, notifications) is done
    by the bot's KassaSmart polling flow. Webhook only logs for monitoring.

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

        # All payment processing handled by bot's KassaSmart flow:
        # - add_time_person (subscription extension)
        # - traffic reset
        # - user notification
        # - admin notification
        # Webhook only logs the event for monitoring

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
