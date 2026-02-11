"""
YooKassa Webhook Handler for VPN Bot

Handles payment.succeeded events from YooKassa.
For bot-originated payments: polling handles them first, webhook is backup.
For dashboard-originated payments: webhook is the primary handler.
"""
import os
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Payments

log = logging.getLogger(__name__)

COUNT_SECOND_DAY = 86400


async def _is_payment_processed(user_id: int, amount: float, payment_id: str) -> bool:
    """
    Check if this payment has already been processed.
    Prevents duplicate processing when both polling and webhook succeed.
    """
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.tgid == user_id)
            result = await db.execute(stmt)
            person = result.scalar_one_or_none()

            if not person:
                return False

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


async def _activate_dashboard_payment(user_id: int, days_count: int, amount: float) -> Dict[str, Any]:
    """
    Process a dashboard-originated payment:
    - Add subscription time
    - Reset traffic
    - Record payment in DB
    - Activate subscription keys if needed
    - Send Telegram notifications
    """
    from bot.database.methods.update import add_time_person, add_retention_person
    from bot.database.methods.insert import add_payment, create_affiliate_statistics
    from bot.database.methods.update import add_referral_balance_person
    from bot.database.methods.get import get_person
    from bot.misc.traffic_monitor import reset_user_traffic, reset_bypass_traffic
    from bot.misc.subscription import activate_subscription

    try:
        # 1. Add subscription time
        seconds = days_count * COUNT_SECOND_DAY
        await add_time_person(user_id, seconds)
        log.info(f"[Webhook] Added {days_count} days to user {user_id}")

        # 2. Reset traffic
        await reset_user_traffic(user_id)
        await reset_bypass_traffic(user_id)

        # 3. Increment retention
        await add_retention_person(user_id, 1)

        # 4. Record payment
        await add_payment(user_id, amount, "Dashboard YooKassa")
        log.info(f"[Webhook] Payment recorded for user {user_id}: {amount} RUB")

        # 5. Activate subscription keys if not active
        person = await get_person(user_id)
        if person and not person.subscription_active:
            try:
                await activate_subscription(user_id, include_outline=False)
                log.info(f"[Webhook] Activated subscription for user {user_id}")
            except Exception as e:
                log.error(f"[Webhook] Error activating subscription for {user_id}: {e}")

        # 6. Handle referral rewards
        if person and person.referral_user_tgid:
            try:
                referral_percent = int(os.getenv("REFERRAL_PERCENT", "50"))
                referral_balance = max(1, round(amount * (referral_percent * 0.01)))
                await add_referral_balance_person(referral_balance, person.referral_user_tgid)
                await create_affiliate_statistics(
                    person.fullname or "User",
                    user_id,
                    person.referral_user_tgid,
                    amount,
                    referral_percent,
                    referral_balance,
                )
                log.info(f"[Webhook] Referral reward {referral_balance} RUB to {person.referral_user_tgid}")
            except Exception as e:
                log.error(f"[Webhook] Error processing referral for {user_id}: {e}")

        # 7. Send Telegram notifications
        await _send_telegram_notifications(user_id, days_count, amount)

        return {"status": "success", "user_id": user_id, "days_added": days_count}

    except Exception as e:
        log.error(f"[Webhook] Error activating dashboard payment for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "reason": str(e)}


async def _send_telegram_notifications(user_id: int, days_count: int, amount: float):
    """Send Telegram notifications about successful payment."""
    from aiogram import Bot
    from bot.database.methods.get import get_person

    bot_token = os.getenv("TG_TOKEN", "")
    if not bot_token:
        log.error("[Webhook] TG_TOKEN not set, can't send notifications")
        return

    bot = Bot(token=bot_token)
    try:
        person = await get_person(user_id)
        if not person:
            return

        # User notification
        subscription_end = datetime.fromtimestamp(person.subscription).strftime('%d.%m.%Y')
        user_msg = (
            f"✅ Оплата {amount:.0f}₽ прошла успешно!\n\n"
            f"📅 Подписка активна до: <b>{subscription_end}</b>\n"
            f"ℹ️ Если VPN уже настроен — ничего делать не нужно, всё работает"
        )
        try:
            await bot.send_message(user_id, user_msg, parse_mode="HTML")
        except Exception as e:
            log.error(f"[Webhook] Can't send user notification to {user_id}: {e}")

        # Admin notifications
        admins = os.getenv("ADMINS_IDS", "").split(",")
        for admin_id_str in admins:
            admin_id = int(admin_id_str.strip()) if admin_id_str.strip() else None
            if not admin_id:
                continue
            admin_msg = (
                f"💰 Оплата через Dashboard\n"
                f"👤 {person.fullname or 'User'} (ID: {user_id})\n"
                f"💵 {amount:.0f}₽ за {days_count} дней\n"
                f"📅 Подписка до: {subscription_end}"
            )
            try:
                await bot.send_message(admin_id, admin_msg)
            except Exception as e:
                log.error(f"[Webhook] Can't send admin notification to {admin_id}: {e}")

    finally:
        await bot.session.close()


async def process_payment_webhook(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process YooKassa payment webhook.
    For dashboard payments: activates subscription, records payment, sends notifications.
    For bot payments: checks if already processed by polling, activates if not.
    """
    try:
        event_type = webhook_data.get("event")
        payment_obj = webhook_data.get("object", {})

        if event_type != "payment.succeeded":
            log.info(f"[Webhook] Ignoring event type: {event_type}")
            return {"status": "ignored", "reason": f"event_type={event_type}"}

        payment_id = payment_obj.get("id")
        status = payment_obj.get("status")
        amount_obj = payment_obj.get("amount", {})
        amount = float(amount_obj.get("value", 0))
        metadata = payment_obj.get("metadata", {})

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

        # Check for duplicate
        if await _is_payment_processed(user_id, amount, payment_id):
            log.info(f"[Webhook] Payment {payment_id} already processed, skipping")
            return {
                "status": "duplicate",
                "payment_id": payment_id,
                "user_id": user_id
            }

        # Actually process the payment
        result = await _activate_dashboard_payment(user_id, days_count, amount)
        result["payment_id"] = payment_id

        log.info(
            f"[Webhook] Payment {payment_id} processed: "
            f"user={user_id}, +{days_count} days, {amount} RUB"
        )

        return result

    except Exception as e:
        log.error(f"[Webhook] Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "reason": str(e)
        }
