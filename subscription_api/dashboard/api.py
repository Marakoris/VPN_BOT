"""
Dashboard JSON API endpoints (/api/v1/*).
"""

import re
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons
from subscription_api.dashboard.dependencies import require_user_api
from subscription_api.dashboard.auth import hash_password, verify_password, create_jwt_token
from subscription_api.dashboard import services
from subscription_api.dashboard.services import log_dashboard_action

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Dashboard API"])

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


# ==================== PUBLIC AUTH ENDPOINTS ====================

@router.post("/register")
async def api_register(request: Request):
    """Register a new user via email + password (public, no auth)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)

    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    password_confirm = body.get("password_confirm") or ""

    # Validation
    if not email or not EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "Введите корректный email"}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"ok": False, "error": "Пароль должен быть не менее 6 символов"}, status_code=400)
    if password != password_confirm:
        return JSONResponse({"ok": False, "error": "Пароли не совпадают"}, status_code=400)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Check email uniqueness
        stmt = select(Persons).filter(Persons.email == email)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            return JSONResponse({"ok": False, "error": "Этот email уже зарегистрирован"}, status_code=400)

        # Create new user
        new_user = Persons(
            tgid=None,
            email=email,
            password_hash=hash_password(password),
            subscription_active=False,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

    token = create_jwt_token(new_user.id, new_user.tgid)
    log.info(f"[Dashboard] New web user registered: {email} (id={new_user.id})")
    return {"ok": True, "token": token}


@router.post("/login")
async def api_login(request: Request):
    """Login via email + password (public, no auth)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)

    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return JSONResponse({"ok": False, "error": "Введите email и пароль"}, status_code=400)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.email == email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        return JSONResponse({"ok": False, "error": "Неверный email или пароль"}, status_code=400)

    if not verify_password(password, user.password_hash):
        return JSONResponse({"ok": False, "error": "Неверный email или пароль"}, status_code=400)

    token = create_jwt_token(user.id, user.tgid)
    log.info(f"[Dashboard] User {user.email} logged in via API")
    return {"ok": True, "token": token}


@router.get("/me")
async def api_me(user: Persons = Depends(require_user_api)):
    """Get current user profile."""
    return {
        "tgid": user.tgid,
        "username": user.username,
        "fullname": user.fullname,
        "balance": user.balance or 0,
        "referral_balance": user.referral_balance or 0,
        "lang": user.lang or "ru",
        "subscription_active": bool(user.subscription_active),
    }


@router.get("/subscription")
async def api_subscription(user: Persons = Depends(require_user_api)):
    """Get subscription status."""
    status = await services.get_subscription_status(user)
    return status


@router.get("/traffic")
async def api_traffic(user: Persons = Depends(require_user_api)):
    """Get traffic statistics."""
    traffic = await services.get_traffic_data(user)
    bypass = await services.get_bypass_data(user)
    return {
        "main": traffic,
        "bypass": bypass,
    }


@router.get("/payments")
async def api_payments(user: Persons = Depends(require_user_api)):
    """Get payment history."""
    payments = await services.get_payment_history(user.id)
    return {"payments": payments}


@router.post("/payment/create")
async def api_create_payment(request: Request, user: Persons = Depends(require_user_api)):
    """Create a payment."""
    body = await request.json()
    amount = body.get("amount")
    payment_system = body.get("payment_system", "kassa")
    months = body.get("months")

    if not amount or int(amount) < 1:
        return JSONResponse({"success": False, "error": "Invalid amount"}, status_code=400)

    result = await services.create_payment(user, int(amount), payment_system, months)
    if result.get("success"):
        await log_dashboard_action("payment_create", request, user, f"{payment_system} {amount}₽ {months}мес")
    return result


@router.post("/promo/apply")
async def api_apply_promo(request: Request, user: Persons = Depends(require_user_api)):
    """Apply a promo code."""
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        return JSONResponse({"success": False, "error": "Введите промокод"}, status_code=400)

    result = await services.apply_promo_code(user, code)
    if result.get("success"):
        await log_dashboard_action("promo_apply", request, user, f"code={code}")
    return result


@router.post("/trial/activate")
async def api_activate_trial(request: Request, user: Persons = Depends(require_user_api)):
    """Activate free trial."""
    result = await services.activate_trial(user)
    if result.get("success"):
        await log_dashboard_action("trial_activate", request, user)
    return result


@router.get("/referral")
async def api_referral(user: Persons = Depends(require_user_api)):
    """Get referral info."""
    info = await services.get_referral_info(user)
    return info


@router.post("/referral/withdraw")
async def api_withdraw(request: Request, user: Persons = Depends(require_user_api)):
    """Request referral withdrawal."""
    body = await request.json()
    amount = body.get("amount")
    payment_info = body.get("payment_info", "")
    communication = body.get("communication", "")

    if not amount or int(amount) < 1:
        return JSONResponse({"success": False, "error": "Invalid amount"}, status_code=400)
    if not payment_info:
        return JSONResponse({"success": False, "error": "Укажите реквизиты"}, status_code=400)

    result = await services.create_withdrawal(user, int(amount), payment_info, communication)
    if result.get("success"):
        await log_dashboard_action("withdrawal_create", request, user, f"{amount}₽")
    return result


@router.post("/autopay/disable")
async def api_disable_autopay(request: Request, user: Persons = Depends(require_user_api)):
    """Disable autopayment."""
    from bot.database.methods.update import delete_payment_method_id_person
    if await delete_payment_method_id_person(user.tgid):
        log.info(f"[Dashboard] User {user.tgid} disabled autopay")
        await log_dashboard_action("autopay_disable", request, user)
        return {"success": True, "message": "Автоплатёж отключён"}
    return JSONResponse({"success": False, "error": "Ошибка"}, status_code=500)


@router.get("/plans")
async def api_plans():
    """Get available subscription plans."""
    return {"plans": services.get_plans()}


@router.post("/referral/create-utm-link")
async def api_create_utm_link(request: Request, user: Persons = Depends(require_user_api)):
    """Generate a referral link with UTM tag and save description."""
    import re
    from base64 import urlsafe_b64encode
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from bot.database.main import engine
    from bot.database.models.main import ReferralUtmTag

    body = await request.json()
    tag = (body.get("tag") or "").strip()
    description = (body.get("description") or "").strip()[:100]

    if not tag or not re.match(r'^[a-zA-Z0-9_-]{1,30}$', tag):
        return JSONResponse(
            {"success": False, "error": "Метка должна содержать только латиницу, цифры, дефис и подчёркивание (1-30 символов)"},
            status_code=400,
        )

    # Save tag with description
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(ReferralUtmTag).filter(
            ReferralUtmTag.user_tgid == user.tgid,
            ReferralUtmTag.tag == tag,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            if description:
                existing.description = description
        else:
            db.add(ReferralUtmTag(user_tgid=user.tgid, tag=tag, description=description or None))
        await db.commit()

    payload = f"{user.tgid}_{tag}"
    encoded = urlsafe_b64encode(payload.encode()).decode().rstrip('=')
    bot_username = services.BOT_USERNAME
    link = f"https://t.me/{bot_username}?start={encoded}"

    await log_dashboard_action("utm_link_create", request, user, f"tag={tag}")
    return {"success": True, "link": link, "tag": tag, "description": description}


@router.get("/referral/export-excel")
async def api_referral_export_excel(request: Request, user: Persons = Depends(require_user_api)):
    """Export referral data as Excel file."""
    import pandas as pd
    from io import BytesIO
    from zoneinfo import ZoneInfo

    moscow_tz = ZoneInfo("Europe/Moscow")
    info = await services.get_referral_info(user)

    # Sheet 1: All referrals
    referrals_data = []
    for i, r in enumerate(info.get("all_referrals", [])):
        status_map = {"paid": "Оплатил", "trial": "Триал", "registered": "Регистрация"}
        referrals_data.append({
            "№": i + 1,
            "Имя": r["name"],
            "Telegram ID": r["tg_id"],
            "Статус": status_map.get(r["status"], r["status"]),
            "UTM-метка": r.get("referral_utm") or "—",
            "Дата регистрации": r.get("first_interaction") or "—",
            "Кол-во оплат": r.get("payments_count", 0),
            "Сумма оплат, ₽": r.get("total_paid", 0),
            "Вознаграждение, ₽": r.get("total_reward", 0),
        })
    df_referrals = pd.DataFrame(referrals_data) if referrals_data else pd.DataFrame()

    # Sheet 2: Rewards (recent)
    rewards_data = []
    for i, rw in enumerate(info.get("rewards", [])):
        rewards_data.append({
            "№": i + 1,
            "Клиент": rw["client_name"],
            "Дата оплаты": rw["date"],
            "Сумма оплаты, ₽": rw["payment_amount"],
            "Процент": f"{rw['reward_percent']}%",
            "Вознаграждение, ₽": rw["reward_amount"],
        })
    df_rewards = pd.DataFrame(rewards_data) if rewards_data else pd.DataFrame()

    # Sheet 3: UTM funnel stats
    utm_data = []
    for tag, f in info.get("utm_funnels", {}).items():
        utm_data.append({
            "UTM-метка": "Без метки" if tag == "__none__" else tag,
            "Регистрации": f["registered"],
            "Триал": f["trial_activated"],
            "Оплаты": f["paid"],
            "Конверсия, %": f.get("conversion", 0),
        })
    df_utm = pd.DataFrame(utm_data) if utm_data else pd.DataFrame()

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        if not df_referrals.empty:
            df_referrals.to_excel(writer, sheet_name="Рефералы", index=False)
            _format_excel_sheet(writer, df_referrals, "Рефералы")
        if not df_rewards.empty:
            df_rewards.to_excel(writer, sheet_name="Начисления", index=False)
            _format_excel_sheet(writer, df_rewards, "Начисления")
        if not df_utm.empty:
            df_utm.to_excel(writer, sheet_name="UTM-источники", index=False)
            _format_excel_sheet(writer, df_utm, "UTM-источники")

    buffer.seek(0)
    filename = f"referrals_{user.tgid}.xlsx"
    await log_dashboard_action("referral_export_excel", request, user)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _format_excel_sheet(writer, df, sheet_name: str):
    """Apply formatting to an Excel sheet."""
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    header_fmt = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "border": 1})
    currency_fmt = workbook.add_format({"num_format": "#,##0 ₽", "align": "right"})

    for col_num, col in enumerate(df.columns):
        max_len = max(df[col].astype(str).map(len).max(), len(col)) + 4
        if "₽" in col:
            worksheet.set_column(col_num, col_num, max_len, currency_fmt)
        else:
            worksheet.set_column(col_num, col_num, max_len)
        worksheet.write(0, col_num, col, header_fmt)
