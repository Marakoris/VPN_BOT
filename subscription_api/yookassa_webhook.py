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


async def _is_payment_processed(user_id: int = None, amount: float = 0, payment_id: str = "", internal_user_id: int = None) -> bool:
    """
    Check if this payment has already been processed.
    Prevents duplicate processing when both polling and webhook succeed.
    Supports lookup by tgid (user_id) or by Persons.id (internal_user_id).
    """
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            if internal_user_id:
                stmt = select(Persons).filter(Persons.id == internal_user_id)
            else:
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
                log.info(f"[Webhook] Payment already processed for user tgid={user_id} internal_id={internal_user_id}, amount {amount}")
                return True

            return False

    except Exception as e:
        log.error(f"[Webhook] Error checking payment status: {e}")
        return False


async def _activate_dashboard_payment(user_id: int = None, days_count: int = 0, amount: float = 0, internal_user_id: int = None) -> Dict[str, Any]:
    """
    Process a dashboard-originated payment:
    - Add subscription time
    - Reset traffic
    - Record payment in DB
    - Activate subscription keys if needed
    - Send Telegram notifications

    Supports both bot users (user_id=tgid) and web users (internal_user_id=Persons.id).
    """
    from bot.database.methods.update import add_time_person, add_time_person_by_id, add_retention_person
    from bot.database.methods.insert import add_payment, add_payment_by_id, create_affiliate_statistics
    from bot.database.methods.update import add_referral_balance_person
    from bot.database.methods.get import get_person, get_person_by_id
    from bot.misc.traffic_monitor import reset_user_traffic, reset_bypass_traffic
    from bot.misc.subscription import activate_subscription

    # Determine if this is a web user (internal_user_id without tgid)
    is_web_user = internal_user_id is not None and not user_id

    try:
        # 1. Add subscription time
        seconds = days_count * COUNT_SECOND_DAY
        if is_web_user:
            await add_time_person_by_id(internal_user_id, seconds)
            log.info(f"[Webhook] Added {days_count} days to web user internal_id={internal_user_id}")
        else:
            await add_time_person(user_id, seconds)
            log.info(f"[Webhook] Added {days_count} days to user {user_id}")

        # 2. Reset traffic (only for users with tgid — web users have no keys yet)
        if user_id:
            await reset_user_traffic(user_id)
            await reset_bypass_traffic(user_id)

        # 3. Increment retention
        if user_id:
            await add_retention_person(user_id, 1)

        # 4. Record payment
        if is_web_user:
            await add_payment_by_id(internal_user_id, amount, "Dashboard YooKassa")
            log.info(f"[Webhook] Payment recorded for web user internal_id={internal_user_id}: {amount} RUB")
        else:
            await add_payment(user_id, amount, "Dashboard YooKassa")
            log.info(f"[Webhook] Payment recorded for user {user_id}: {amount} RUB")

        # 5. Activate subscription keys if not active
        if is_web_user:
            person = await get_person_by_id(internal_user_id)
        else:
            person = await get_person(user_id)

        if person and not person.subscription_active:
            try:
                if is_web_user:
                    await activate_subscription(internal_user_id=internal_user_id, include_outline=False)
                else:
                    await activate_subscription(user_id, include_outline=False)
                log.info(f"[Webhook] Activated subscription for user tgid={user_id} internal_id={internal_user_id}")
            except Exception as e:
                log.error(f"[Webhook] Error activating subscription for tgid={user_id} internal_id={internal_user_id}: {e}")

        # 6. Handle referral rewards
        if person and person.referral_user_tgid:
            try:
                referral_percent = int(os.getenv("REFERRAL_PERCENT", "50"))
                referral_balance = max(1, round(amount * (referral_percent * 0.01)))
                await add_referral_balance_person(referral_balance, person.referral_user_tgid)
                await create_affiliate_statistics(
                    person.fullname or "User",
                    user_id or internal_user_id,
                    person.referral_user_tgid,
                    amount,
                    referral_percent,
                    referral_balance,
                )
                log.info(f"[Webhook] Referral reward {referral_balance} RUB to {person.referral_user_tgid}")
            except Exception as e:
                log.error(f"[Webhook] Error processing referral: {e}")

        # 7. Send Telegram notifications (only for users with tgid)
        if user_id:
            await _send_telegram_notifications(user_id, days_count, amount)

        # 8. Send email notification
        try:
            # Re-fetch to get latest state
            if is_web_user:
                person = await get_person_by_id(internal_user_id)
            else:
                person = await get_person(user_id)

            if person and person.email and getattr(person, 'email_verified', False) and getattr(person, 'email_notifications', True):
                from subscription_api.dashboard.email_service import send_payment_success
                expiry_date = datetime.fromtimestamp(person.subscription).strftime('%d.%m.%Y') if person.subscription else "—"
                await send_payment_success(person.email, amount, days_count, expiry_date)
        except Exception as e:
            log.error(f"[Webhook] Error sending email notification: {e}")

        return {"status": "success", "user_id": user_id or internal_user_id, "days_added": days_count}

    except Exception as e:
        log.error(f"[Webhook] Error activating dashboard payment for tgid={user_id} internal_id={internal_user_id}: {e}")
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
        internal_user_id_str = metadata.get("internal_user_id")
        days_count_str = metadata.get("days_count")
        source = metadata.get("source", "unknown")

        if not days_count_str:
            log.warning(f"[Webhook] Missing days_count in payment {payment_id}: {metadata}")
            return {
                "status": "error",
                "reason": "missing_metadata",
                "payment_id": payment_id
            }

        # Parse user identifiers
        user_id = int(user_id_str) if user_id_str else None
        internal_user_id = int(internal_user_id_str) if internal_user_id_str else None
        days_count = int(days_count_str)

        # Must have at least one user identifier
        if not user_id and not internal_user_id:
            log.warning(f"[Webhook] No user identifier in payment {payment_id}: {metadata}")
            return {
                "status": "error",
                "reason": "missing_user_id",
                "payment_id": payment_id
            }

        log.info(
            f"[Webhook] Processing payment {payment_id}: "
            f"tgid={user_id}, internal_id={internal_user_id}, days={days_count}, amount={amount}, source={source}"
        )

        # Skip non-dashboard payments (autopay/manual handle their own notifications)
        if source != "dashboard":
            log.info(f"[Webhook] Skipping {source} payment {payment_id} (handled by {source} flow)")
            return {
                "status": "skipped",
                "reason": f"source={source}, handled by {source} flow",
                "payment_id": payment_id,
                "user_id": user_id or internal_user_id,
            }

        # Check for duplicate
        if await _is_payment_processed(user_id=user_id, amount=amount, payment_id=payment_id, internal_user_id=internal_user_id):
            log.info(f"[Webhook] Payment {payment_id} already processed, skipping")
            return {
                "status": "duplicate",
                "payment_id": payment_id,
                "user_id": user_id or internal_user_id
            }

        # Actually process the payment
        result = await _activate_dashboard_payment(
            user_id=user_id,
            days_count=days_count,
            amount=amount,
            internal_user_id=internal_user_id
        )
        result["payment_id"] = payment_id

        log.info(
            f"[Webhook] Payment {payment_id} processed: "
            f"tgid={user_id}, internal_id={internal_user_id}, +{days_count} days, {amount} RUB"
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
