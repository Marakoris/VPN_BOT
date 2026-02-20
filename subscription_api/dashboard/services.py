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
    DashboardLogs, message_button_association
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


async def get_traffic_data(user) -> dict:
    """Get traffic data for user. Accepts Persons object or tgid (int) for backward compat."""
    default = {
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
    tgid = user.tgid if hasattr(user, 'tgid') else user
    if tgid is None:
        return default
    info = await get_user_traffic_info(tgid)
    if not info:
        return default
    return info


async def get_bypass_data(user) -> dict:
    """Get bypass traffic data. Accepts Persons object or tgid (int) for backward compat."""
    default = {
        "total": 0,
        "total_formatted": "0 B",
        "limit": BYPASS_LIMIT_BYTES,
        "limit_formatted": format_bytes(BYPASS_LIMIT_BYTES),
        "remaining": BYPASS_LIMIT_BYTES,
        "remaining_formatted": format_bytes(BYPASS_LIMIT_BYTES),
        "percent": 0.0,
        "exceeded": False,
    }
    tgid = user.tgid if hasattr(user, 'tgid') else user
    if tgid is None:
        return default
    info = await get_user_bypass_info(tgid)
    if not info:
        return default
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
    """Get referral statistics with funnel and UTM breakdown."""
    import time as _time
    current_time = int(_time.time())

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all referrals from users table
        stmt_referrals = select(Persons).filter(Persons.referral_user_tgid == user.tgid)
        result = await db.execute(stmt_referrals)
        all_referrals_db = result.scalars().all()

        total_invited = len(all_referrals_db)

        # Total earned from referrals
        stmt_earned = select(func.coalesce(func.sum(AffiliateStatistics.reward_amount), 0)).filter(
            AffiliateStatistics.referral_tg_id == user.tgid
        )
        result = await db.execute(stmt_earned)
        total_earned = result.scalar() or 0

        # Detailed referral clients (from affiliate_statistics — payment data)
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

        # Group payment data by client
        clients_map: Dict[int, dict] = {}
        for row in raw_clients:
            tg_id = row.client_tg_id
            if tg_id not in clients_map:
                clients_map[tg_id] = {
                    "total_paid": 0,
                    "total_reward": 0,
                    "payments_count": 0,
                    "first_payment_date": row.payment_date,
                }
            c = clients_map[tg_id]
            c["total_paid"] += row.payment_amount or 0
            c["total_reward"] += row.reward_amount or 0
            c["payments_count"] += 1
            if row.payment_date and (not c["first_payment_date"] or row.payment_date < c["first_payment_date"]):
                c["first_payment_date"] = row.payment_date

        # Build funnel data and all_referrals list
        funnel = {'registered': 0, 'trial_activated': 0, 'paid': 0}
        utm_funnels: Dict[Optional[str], dict] = {}
        all_referrals = []

        for r in all_referrals_db:
            # Determine status
            if r.retention and r.retention > 0:
                status = 'paid'
            elif r.free_trial_used:
                status = 'trial'
            else:
                status = 'registered'

            utm = r.referral_utm

            # Overall funnel
            funnel['registered'] += 1
            if status in ('trial', 'paid'):
                funnel['trial_activated'] += 1
            if status == 'paid':
                funnel['paid'] += 1

            # UTM funnel
            if utm not in utm_funnels:
                utm_funnels[utm] = {'registered': 0, 'trial_activated': 0, 'paid': 0}
            utm_funnels[utm]['registered'] += 1
            if status in ('trial', 'paid'):
                utm_funnels[utm]['trial_activated'] += 1
            if status == 'paid':
                utm_funnels[utm]['paid'] += 1

            payment_data = clients_map.get(r.tgid, {})

            all_referrals.append({
                "name": r.fullname or "Пользователь",
                "tg_id": r.tgid,
                "status": status,
                "referral_utm": utm,
                "first_interaction": r.first_interaction.strftime("%d.%m.%Y") if r.first_interaction else None,
                "total_paid": payment_data.get("total_paid", 0),
                "total_reward": payment_data.get("total_reward", 0),
                "payments_count": payment_data.get("payments_count", 0),
                "first_payment_date": payment_data.get("first_payment_date", "").strftime("%d.%m.%Y") if payment_data.get("first_payment_date") else None,
            })

        # Sort: paid first, then trial, then registered
        status_order = {'paid': 0, 'trial': 1, 'registered': 2}
        all_referrals.sort(key=lambda x: status_order.get(x['status'], 3))

        # Build legacy clients list (only those who paid)
        clients = []
        for ref in all_referrals:
            if ref['payments_count'] > 0:
                clients.append({
                    "name": ref["name"],
                    "tg_id": ref["tg_id"],
                    "first_payment_date": ref["first_payment_date"],
                    "total_paid": ref["total_paid"],
                    "total_reward": ref["total_reward"],
                    "payments_count": ref["payments_count"],
                })

        # Reward history (all individual payments)
        rewards = []
        for row in raw_clients:
            rewards.append({
                "client_name": row.client_fullname or "Пользователь",
                "client_tg_id": row.client_tg_id,
                "date": row.payment_date.strftime("%d.%m.%Y") if row.payment_date else "-",
                "payment_amount": row.payment_amount or 0,
                "reward_amount": row.reward_amount or 0,
                "reward_percent": row.reward_percent or 0,
            })

        # Load withdrawal history
        stmt_withdrawals = (
            select(WithdrawalRequests)
            .filter(WithdrawalRequests.user_tgid == user.tgid)
            .order_by(WithdrawalRequests.request_date.desc())
        )
        result = await db.execute(stmt_withdrawals)
        withdrawal_rows = result.scalars().all()

        withdrawals = []
        for w in withdrawal_rows:
            withdrawals.append({
                "amount": w.amount,
                "payment_info": w.payment_info or "",
                "status": "paid" if w.check_payment else "pending",
                "request_date": w.request_date.strftime("%d.%m.%Y") if w.request_date else "",
                "payment_date": w.payment_date.strftime("%d.%m.%Y") if w.payment_date else "",
            })

        # Load UTM tag descriptions
        from bot.database.models.main import ReferralUtmTag
        stmt_tags = select(ReferralUtmTag).filter(ReferralUtmTag.user_tgid == user.tgid)
        result = await db.execute(stmt_tags)
        utm_tag_rows = result.scalars().all()
        utm_descriptions = {t.tag: t.description for t in utm_tag_rows if t.description}

        # Format UTM funnels for template (convert None key to string)
        utm_funnels_formatted = {}
        for k, v in utm_funnels.items():
            conv = round(v['paid'] / v['registered'] * 100) if v['registered'] > 0 else 0
            v['conversion'] = conv
            v['description'] = utm_descriptions.get(k, '') if k else ''
            utm_funnels_formatted[k if k is not None else '__none__'] = v

    from base64 import urlsafe_b64encode
    encoded = urlsafe_b64encode(str(user.tgid).encode()).decode().rstrip('=')
    referral_link = f"https://t.me/{BOT_USERNAME}?start={encoded}"

    # Build list of all created UTM links
    utm_links = []
    for t in utm_tag_rows:
        tag_payload = f"{user.tgid}_{t.tag}"
        tag_encoded = urlsafe_b64encode(tag_payload.encode()).decode().rstrip('=')
        utm_links.append({
            "tag": t.tag,
            "description": t.description or t.tag,
            "link": f"https://t.me/{BOT_USERNAME}?start={tag_encoded}",
            "created_at": t.created_at.strftime("%d.%m.%Y") if t.created_at else "",
        })

    return {
        "referral_balance": user.referral_balance or 0,
        "total_invited": total_invited,
        "total_earned": total_earned,
        "referral_link": referral_link,
        "referral_percent": REFERRAL_PERCENT,
        "minimum_withdrawal": MINIMUM_WITHDRAWAL,
        "clients": clients,
        "rewards": rewards,
        "all_referrals": all_referrals,
        "funnel": funnel,
        "utm_funnels": utm_funnels_formatted,
        "utm_links": utm_links,
        "withdrawals": withdrawals,
        "total_withdrawn": sum(w["amount"] for w in withdrawals if w["status"] == "paid"),
        "user_tgid": user.tgid,
        "bot_username": BOT_USERNAME,
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
    """Activate free trial for user. Supports both bot users (tgid) and web users (tgid=NULL)."""
    if user.free_trial_used:
        return {"success": False, "error": "Пробный период уже использован"}

    if user.subscription_active:
        return {"success": False, "error": "У вас уже есть активная подписка"}

    from bot.database.methods.update import add_time_person, add_time_person_by_id
    from bot.misc.subscription import activate_subscription

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        person = result.scalar_one_or_none()

        if person:
            person.free_trial_used = True
            await db.commit()

    # Add trial period time and activate subscription
    if user.tgid is not None:
        # Bot user — use existing tgid-based functions
        await add_time_person(user.tgid, TRIAL_PERIOD)
        try:
            await activate_subscription(user.tgid, include_outline=False)
        except Exception as e:
            log.error(f"[Dashboard] Error activating trial subscription for tgid={user.tgid}: {e}")
    else:
        # Web user (tgid=NULL) — use id-based functions
        await add_time_person_by_id(user.id, TRIAL_PERIOD)
        try:
            await activate_subscription(internal_user_id=user.id, include_outline=False)
        except Exception as e:
            log.error(f"[Dashboard] Error activating trial subscription for user_id={user.id}: {e}")

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
                "return_url": f"{SUBSCRIPTION_API_URL}/dashboard/connection"
            },
            "capture": True,
            "description": "VPN подписка NoBorder",
            "save_payment_method": True,
            "metadata": {
                "user_id": str(user.tgid) if user.tgid else "",
                "internal_user_id": str(user.id),
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
                    "description": f"VPN NoBorder - {user.tgid or user.id}",
                    "payload": f"dashboard_{user.tgid or user.id}_{amount}",
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


async def log_dashboard_action(
    action: str,
    request=None,
    user: Persons = None,
    details: str = None,
):
    """Log a dashboard action for analytics."""
    try:
        ip = None
        ua = None
        if request:
            ip = request.headers.get("x-real-ip") or request.client.host
            ua = (request.headers.get("user-agent") or "")[:500]

        async with AsyncSession(autoflush=False, bind=engine()) as db:
            entry = DashboardLogs(
                user_id=user.id if user else None,
                tgid=user.tgid if user else None,
                action=action,
                details=details,
                ip_address=ip,
                user_agent=ua,
            )
            db.add(entry)
            await db.commit()
    except Exception as e:
        log.error(f"[DashboardLog] Error logging {action}: {e}")
