"""
Dashboard business logic.
Reuses existing database methods and subscription/traffic modules.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from urllib.parse import quote

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import (
    Persons, Servers, Payments, PromoCode,
    AffiliateStatistics, WithdrawalRequests,
    message_button_association
)
from bot.misc.traffic_monitor import (
    get_user_traffic_info,
    get_user_bypass_info,
    format_bytes,
    DEFAULT_TRAFFIC_LIMIT,
    BYPASS_LIMIT_BYTES,
)
from bot.misc.subscription import verify_subscription_token

log = logging.getLogger(__name__)

SUBSCRIPTION_API_URL = os.getenv("SUBSCRIPTION_API_URL", "https://vpnnoborder.sytes.net")
MONTH_COSTS = os.getenv("MONTH_COST", "150,390,600,999").split(",")
DEPOSITS = os.getenv("DEPOSIT", "50,390,800,1600").split(",")
TRIAL_PERIOD = int(os.getenv("TRIAL_PERIOD", "259200"))
REFERRAL_PERCENT = int(os.getenv("REFERRAL_PERCENT", "50"))
MINIMUM_WITHDRAWAL = int(os.getenv("MINIMUM_WITHDRAWAL_AMOUNT", "2000"))
BOT_USERNAME = "NoBorderVPN_bot"


async def get_subscription_status(user: Persons) -> dict:
    """Get subscription status for a user."""
    now = datetime.now()
    active = bool(user.subscription_active)
    expired = bool(user.subscription_expired)
    expiry_ts = user.subscription
    expiry_date = None
    days_remaining = None

    if expiry_ts:
        expiry_dt = datetime.fromtimestamp(expiry_ts)
        expiry_date = expiry_dt.strftime("%d.%m.%Y")
        diff = expiry_dt - now
        days_remaining = max(0, diff.days)

    return {
        "active": active,
        "expired": expired,
        "expiry_timestamp": expiry_ts,
        "expiry_date": expiry_date,
        "days_remaining": days_remaining,
        "subscription_months": user.subscription_months,
        "subscription_price": user.subscription_price,
        "autopay_enabled": bool(user.payment_method_id),
        "free_trial_used": bool(user.free_trial_used),
        "token": user.subscription_token,
    }


async def get_traffic_data(tgid: int) -> dict:
    """Get traffic data for user."""
    info = await get_user_traffic_info(tgid)
    if not info:
        return {
            "used_bytes": 0,
            "used_formatted": "0 B",
            "limit_bytes": DEFAULT_TRAFFIC_LIMIT,
            "limit_formatted": format_bytes(DEFAULT_TRAFFIC_LIMIT),
            "remaining_bytes": DEFAULT_TRAFFIC_LIMIT,
            "remaining_formatted": format_bytes(DEFAULT_TRAFFIC_LIMIT),
            "percent_used": 0.0,
            "days_until_reset": 30,
            "exceeded": False,
        }
    return info


async def get_bypass_data(tgid: int) -> dict:
    """Get bypass traffic data."""
    info = await get_user_bypass_info(tgid)
    if not info:
        return {
            "total": 0,
            "total_formatted": "0 B",
            "limit": BYPASS_LIMIT_BYTES,
            "limit_formatted": format_bytes(BYPASS_LIMIT_BYTES),
            "remaining": BYPASS_LIMIT_BYTES,
            "remaining_formatted": format_bytes(BYPASS_LIMIT_BYTES),
            "percent": 0.0,
            "exceeded": False,
        }
    return info


async def get_payment_history(user_id: int) -> List[dict]:
    """Get payment history for user (by internal user id)."""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = (
            select(Payments)
            .filter(Payments.user == user_id)
            .order_by(Payments.data.desc())
            .limit(50)
        )
        result = await db.execute(stmt)
        payments = result.scalars().all()

        return [
            {
                "id": p.id,
                "amount": p.amount,
                "payment_system": p.payment_system or "Unknown",
                "date": p.data.strftime("%d.%m.%Y %H:%M") if p.data else None,
            }
            for p in payments
        ]


async def get_referral_info(user: Persons) -> dict:
    """Get referral statistics."""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Count invited users
        stmt_count = select(func.count()).select_from(Persons).filter(
            Persons.referral_user_tgid == user.tgid
        )
        result = await db.execute(stmt_count)
        total_invited = result.scalar() or 0

        # Total earned from referrals
        stmt_earned = select(func.coalesce(func.sum(AffiliateStatistics.reward_amount), 0)).filter(
            AffiliateStatistics.referral_tg_id == user.tgid
        )
        result = await db.execute(stmt_earned)
        total_earned = result.scalar() or 0

        # Detailed referral clients
        stmt_clients = (
            select(
                AffiliateStatistics.client_fullname,
                AffiliateStatistics.client_tg_id,
                AffiliateStatistics.attraction_date,
                AffiliateStatistics.payment_date,
                AffiliateStatistics.payment_amount,
                AffiliateStatistics.reward_percent,
                AffiliateStatistics.reward_amount,
            )
            .filter(AffiliateStatistics.referral_tg_id == user.tgid)
            .order_by(AffiliateStatistics.payment_date.desc())
        )
        result = await db.execute(stmt_clients)
        raw_clients = result.all()

        # Group by client
        clients_map: Dict[int, dict] = {}
        for row in raw_clients:
            tg_id = row.client_tg_id
            if tg_id not in clients_map:
                clients_map[tg_id] = {
                    "name": row.client_fullname or "Пользователь",
                    "tg_id": tg_id,
                    "first_payment_date": row.payment_date,
                    "total_paid": 0,
                    "total_reward": 0,
                    "payments_count": 0,
                }
            c = clients_map[tg_id]
            c["total_paid"] += row.payment_amount or 0
            c["total_reward"] += row.reward_amount or 0
            c["payments_count"] += 1
            # Track earliest payment
            if row.payment_date and (not c["first_payment_date"] or row.payment_date < c["first_payment_date"]):
                c["first_payment_date"] = row.payment_date

        clients = sorted(clients_map.values(), key=lambda x: x["first_payment_date"] or datetime.min, reverse=True)
        for c in clients:
            if c["first_payment_date"]:
                c["first_payment_date"] = c["first_payment_date"].strftime("%d.%m.%Y")

        # Recent reward history (individual payments)
        rewards = []
        for row in raw_clients[:20]:
            rewards.append({
                "client_name": row.client_fullname or "Пользователь",
                "date": row.payment_date.strftime("%d.%m.%Y") if row.payment_date else "-",
                "payment_amount": row.payment_amount or 0,
                "reward_amount": row.reward_amount or 0,
                "reward_percent": row.reward_percent or 0,
            })

    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref{user.tgid}"

    return {
        "referral_balance": user.referral_balance or 0,
        "total_invited": total_invited,
        "total_earned": total_earned,
        "referral_link": referral_link,
        "referral_percent": REFERRAL_PERCENT,
        "minimum_withdrawal": MINIMUM_WITHDRAWAL,
        "clients": clients,
        "rewards": rewards,
    }


def get_subscription_url(token: str) -> str:
    """Build the subscription URL for VPN clients."""
    return f"{SUBSCRIPTION_API_URL}/sub/{quote(token, safe='')}"


def get_connect_url(token: str) -> str:
    """Build the connect page URL."""
    return f"{SUBSCRIPTION_API_URL}/connect/{quote(token, safe='')}"


def get_plans() -> List[dict]:
    """Return available subscription plans."""
    plan_months = [1, 3, 6, 12]
    plan_days = [31, 93, 186, 365]

    plans = []
    for i, cost in enumerate(MONTH_COSTS):
        months = plan_months[i] if i < len(plan_months) else i + 1
        days = plan_days[i] if i < len(plan_days) else 31
        plans.append({
            "months": months,
            "days": days,
            "price": int(cost),
            "name": f"{months} months",
            "per_month": round(int(cost) / months),
        })
    return plans


def get_deposit_amounts() -> List[int]:
    """Return available deposit amounts."""
    return [int(d) for d in DEPOSITS]


async def apply_promo_code(user: Persons, code: str) -> dict:
    """Apply a promo code for the user."""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Find promo code
        stmt = select(PromoCode).filter(PromoCode.text == code)
        result = await db.execute(stmt)
        promo = result.scalar_one_or_none()

        if not promo:
            return {"success": False, "error": "Промокод не найден"}

        # Check expiry
        if promo.expires_at and promo.expires_at < datetime.now():
            return {"success": False, "error": "Промокод истек"}

        # Check if already used
        stmt_used = select(message_button_association).where(
            message_button_association.c.promocode_id == promo.id,
            message_button_association.c.users_id == user.id,
        )
        result = await db.execute(stmt_used)
        if result.first():
            return {"success": False, "error": "Вы уже использовали этот промокод"}

        # Apply promo
        from bot.database.methods.update import add_time_person, add_balance_person

        if promo.add_days > 0:
            await add_time_person(user.tgid, promo.add_days * 86400)
        if promo.add_balance:
            await add_balance_person(promo.add_balance, user.tgid)

        # Record usage
        from sqlalchemy import insert
        await db.execute(
            insert(message_button_association).values(
                promocode_id=promo.id,
                users_id=user.id
            )
        )
        await db.commit()

        msg = []
        if promo.add_days > 0:
            msg.append(f"+{promo.add_days} дней подписки")
        if promo.add_balance:
            msg.append(f"+{promo.add_balance}₽ на баланс")

        return {"success": True, "message": " и ".join(msg)}


async def activate_trial(user: Persons) -> dict:
    """Activate free trial for user."""
    if user.free_trial_used:
        return {"success": False, "error": "Пробный период уже использован"}

    if user.subscription_active:
        return {"success": False, "error": "У вас уже есть активная подписка"}

    from bot.database.methods.update import add_time_person
    from bot.misc.subscription import activate_subscription

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        person = result.scalar_one_or_none()

        if person:
            person.free_trial_used = True
            await db.commit()

    # Add trial period time
    await add_time_person(user.tgid, TRIAL_PERIOD)

    # Activate subscription keys
    try:
        await activate_subscription(user.tgid, include_outline=False)
    except Exception as e:
        log.error(f"[Dashboard] Error activating trial subscription for {user.tgid}: {e}")

    return {"success": True, "message": f"Пробный период активирован ({TRIAL_PERIOD // 86400} дня)"}


async def create_payment(user: Persons, amount: int, payment_system: str, months: int = None) -> dict:
    """
    Create a payment and return the payment URL.
    Uses direct API calls to payment providers (not aiogram handlers).
    """
    if payment_system == "kassa":
        return await _create_yookassa_payment(user, amount, months)
    elif payment_system == "cryptobot":
        return await _create_cryptobot_payment(user, amount)
    else:
        return {"success": False, "error": f"Платежная система '{payment_system}' не поддерживается"}


async def _create_yookassa_payment(user: Persons, amount: int, months: int = None) -> dict:
    """Create YooKassa payment via API."""
    import uuid
    try:
        from yookassa import Configuration, Payment

        shop_id = os.getenv("YOOKASSA_SHOP_ID")
        secret_key = os.getenv("YOOKASSA_SECRET_KEY")

        if not shop_id or not secret_key:
            return {"success": False, "error": "YooKassa not configured"}

        Configuration.account_id = int(shop_id)
        Configuration.secret_key = secret_key

        days_count = (months or 1) * 31

        payment = await Payment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "receipt": {
                "customer": {
                    "full_name": user.fullname or "User",
                    "email": "default@mail.ru",
                },
                "items": [{
                    "description": "VPN подписка NoBorder",
                    "quantity": 1,
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                }]
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"{SUBSCRIPTION_API_URL}/dashboard/"
            },
            "capture": True,
            "description": "VPN подписка NoBorder",
            "save_payment_method": True,
            "metadata": {
                "user_id": str(user.tgid),
                "days_count": str(days_count),
                "price_on_db": str(amount),
                "source": "dashboard"
            }
        }, str(uuid.uuid4()))

        return {
            "success": True,
            "payment_url": payment.confirmation.confirmation_url,
            "payment_id": payment.id,
        }
    except Exception as e:
        log.error(f"[Dashboard] YooKassa payment error: {e}")
        return {"success": False, "error": str(e)}


async def _create_cryptobot_payment(user: Persons, amount: int) -> dict:
    """Create CryptoBot payment via API."""
    import aiohttp

    api_key = os.getenv("CRYPTO_BOT_API")
    if not api_key:
        return {"success": False, "error": "CryptoBot not configured"}

    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                "https://pay.crypt.bot/api/createInvoice",
                headers={"Crypto-Pay-API-Token": api_key},
                json={
                    "asset": "USDT",
                    "amount": str(round(amount / 90, 2)),  # Approximate RUB to USDT
                    "description": f"VPN NoBorder - {user.tgid}",
                    "payload": f"dashboard_{user.tgid}_{amount}",
                }
            )
            data = await resp.json()

            if data.get("ok"):
                return {
                    "success": True,
                    "payment_url": data["result"]["pay_url"],
                    "payment_id": str(data["result"]["invoice_id"]),
                }
            else:
                return {"success": False, "error": data.get("error", {}).get("name", "Unknown error")}
    except Exception as e:
        log.error(f"[Dashboard] CryptoBot payment error: {e}")
        return {"success": False, "error": str(e)}


async def create_withdrawal(user: Persons, amount: int, payment_info: str, communication: str = None) -> dict:
    """Create a withdrawal request."""
    if (user.referral_balance or 0) < amount:
        return {"success": False, "error": "Недостаточно средств"}

    if amount < MINIMUM_WITHDRAWAL:
        return {"success": False, "error": f"Минимальная сумма вывода: {MINIMUM_WITHDRAWAL}₽"}

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Deduct from referral balance
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        person = result.scalar_one_or_none()

        if not person or (person.referral_balance or 0) < amount:
            return {"success": False, "error": "Недостаточно средств"}

        person.referral_balance = (person.referral_balance or 0) - amount

        # Create withdrawal request
        wr = WithdrawalRequests(
            amount=amount,
            payment_info=payment_info,
            communication=communication or "",
            user_tgid=person.tgid,
        )
        db.add(wr)
        await db.commit()

    return {"success": True, "message": "Заявка на вывод создана"}
