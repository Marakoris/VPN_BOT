"""
Dashboard HTML page endpoints (/dashboard/*).
Uses Jinja2 templates with HTMX for dynamic content.
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons
from bot.misc.subscription import verify_subscription_token

from subscription_api.dashboard.auth import (
    verify_telegram_login,
    create_jwt_token,
    decode_jwt_token,
    hash_password,
    verify_password,
    COOKIE_NAME,
)
from subscription_api.dashboard.dependencies import get_current_user
from subscription_api.dashboard import services
from subscription_api.dashboard.services import log_dashboard_action
from subscription_api.dashboard.email_service import (
    send_verification_code,
    send_password_reset,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard Pages"])

# Templates directory
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

BOT_TOKEN = os.getenv("TG_TOKEN", "")
BOT_USERNAME = "NoBorderVPN_bot"
SUBSCRIPTION_API_URL = os.getenv("SUBSCRIPTION_API_URL", "https://vpnnoborder.sytes.net")


def _auth_redirect_response(token: str, redirect_url: str = "/dashboard/") -> HTMLResponse:
    """
    Return HTML page that sets cookie and redirects via JS.
    Telegram's in-app browser doesn't persist cookies on 302 redirects,
    so we return 200 + Set-Cookie + JS redirect instead.
    """
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Redirecting...</title></head>
<body style="background:#0f0f1a;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif">
<p>Загрузка...</p>
<script>window.location.replace("{redirect_url}");</script>
</body></html>"""
    response = HTMLResponse(html)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


# ==================== AUTH ROUTES ====================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page with Telegram Login Widget."""
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard/", status_code=302)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "bot_username": BOT_USERNAME,
    })


@router.post("/login")
async def login_email(request: Request, email: str = Form(""), password: str = Form("")):
    """Login via email + password."""
    if not email or not password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "bot_username": BOT_USERNAME,
            "email_error": "Введите email и пароль",
            "email_value": email,
        })

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.email == email.strip().lower())
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "bot_username": BOT_USERNAME,
            "email_error": "Неверный email или пароль",
            "email_value": email,
        })

    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "bot_username": BOT_USERNAME,
            "email_error": "Неверный email или пароль",
            "email_value": email,
        })

    token = create_jwt_token(user.id, user.tgid)
    log.info(f"[Dashboard] User {user.tgid} logged in via email")
    await log_dashboard_action("login_email", request, user)
    return _auth_redirect_response(token)


@router.get("/auth/telegram")
async def auth_telegram_callback(request: Request):
    """
    Telegram Login Widget callback.
    Telegram sends GET with query params: id, first_name, last_name, username, photo_url, auth_date, hash
    """
    params = dict(request.query_params)

    if not verify_telegram_login(params.copy()):
        return RedirectResponse("/dashboard/login?error=auth_failed", status_code=302)

    tgid = int(params.get("id", 0))
    if not tgid:
        return RedirectResponse("/dashboard/login?error=no_id", status_code=302)

    # Find user in DB
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.tgid == tgid)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        return RedirectResponse("/dashboard/login?error=not_found", status_code=302)

    # Create JWT and set cookie
    token = create_jwt_token(user.id, user.tgid)
    log.info(f"[Dashboard] User {tgid} logged in via Telegram Widget")
    await log_dashboard_action("login_telegram", request, user)
    return _auth_redirect_response(token)


@router.get("/auth/token")
async def auth_token(request: Request, t: str = "", next: str = ""):
    """
    Auth via subscription token from bot.
    Bot sends URL: /dashboard/auth/token?t={subscription_token}&next=/dashboard/referral
    """
    if not t:
        return RedirectResponse("/dashboard/login?error=no_token", status_code=302)

    user_id = verify_subscription_token(t)
    if not user_id:
        return RedirectResponse("/dashboard/login?error=invalid_token", status_code=302)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        return RedirectResponse("/dashboard/login?error=not_found", status_code=302)

    # Validate redirect URL — only allow local paths
    redirect_url = "/dashboard/"
    if next and next.startswith("/dashboard/"):
        redirect_url = next

    token = create_jwt_token(user.id, user.tgid)
    log.info(f"[Dashboard] User {user.tgid} logged in via subscription token")
    await log_dashboard_action("login_token", request, user)
    return _auth_redirect_response(token, redirect_url=redirect_url)


@router.get("/auth/jwt")
async def auth_jwt(request: Request, t: str = ""):
    """
    Auth via JWT token from landing page.
    Landing sends: /dashboard/auth/jwt?t={jwt_token}
    Sets cookie and redirects to dashboard.
    """
    if not t:
        return RedirectResponse("/dashboard/login?error=no_token", status_code=302)

    payload = decode_jwt_token(t)
    if not payload:
        return RedirectResponse("/dashboard/login?error=invalid_token", status_code=302)

    user_id = payload.get("user_id")
    if not user_id:
        return RedirectResponse("/dashboard/login?error=invalid_token", status_code=302)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        return RedirectResponse("/dashboard/login?error=not_found", status_code=302)

    log.info(f"[Dashboard] User id={user.id} logged in via JWT landing redirect")
    await log_dashboard_action("login_jwt", request, user)
    return _auth_redirect_response(t)


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    response = RedirectResponse("/dashboard/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ==================== PASSWORD RESET ====================

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Show forgot password form."""
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@router.post("/forgot-password")
async def forgot_password_submit(request: Request, email: str = Form("")):
    """Generate reset token and send email. Always shows success to prevent enumeration."""
    email = email.strip().lower()

    if email and "@" in email:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.email == email)
            result = await db.execute(stmt)
            db_user = result.scalar_one_or_none()

            if db_user:
                token = secrets.token_urlsafe(48)
                db_user.password_reset_token = token
                db_user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
                await db.commit()
                await send_password_reset(email, token)
                log.info(f"[Dashboard] Password reset requested for {email}")

    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "success": True,
    })


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    """Show reset password form if token is valid."""
    if not token:
        return RedirectResponse("/dashboard/forgot-password", status_code=302)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.password_reset_token == token)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()

        if not db_user or not db_user.password_reset_expires:
            return templates.TemplateResponse("reset_password.html", {
                "request": request, "error": "Ссылка недействительна или устарела.",
            })

        if db_user.password_reset_expires < datetime.now(timezone.utc):
            return templates.TemplateResponse("reset_password.html", {
                "request": request, "error": "Ссылка устарела. Запросите сброс пароля снова.",
            })

    return templates.TemplateResponse("reset_password.html", {
        "request": request, "token": token,
    })


@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    token: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    """Save new password."""
    if not token:
        return RedirectResponse("/dashboard/forgot-password", status_code=302)

    if len(password) < 6:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "token": token, "error": "Пароль должен быть не менее 6 символов",
        })
    if password != password_confirm:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "token": token, "error": "Пароли не совпадают",
        })

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.password_reset_token == token)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()

        if not db_user or not db_user.password_reset_expires:
            return templates.TemplateResponse("reset_password.html", {
                "request": request, "error": "Ссылка недействительна.",
            })

        if db_user.password_reset_expires < datetime.now(timezone.utc):
            return templates.TemplateResponse("reset_password.html", {
                "request": request, "error": "Ссылка устарела.",
            })

        db_user.password_hash = hash_password(password)
        db_user.password_reset_token = None
        db_user.password_reset_expires = None
        await db.commit()
        log.info(f"[Dashboard] Password reset completed for user id={db_user.id}")

    return templates.TemplateResponse("reset_password.html", {
        "request": request, "success": True,
    })


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page for web users."""
    user = await get_current_user(request)
    if user:
        return RedirectResponse("/dashboard/", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request})


# ==================== MAIN PAGES ====================

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Main dashboard page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_home", request, user)
    sub = await services.get_subscription_status(user)
    traffic = await services.get_traffic_data(user)
    bypass = await services.get_bypass_data(user)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "sub": sub,
        "traffic": traffic,
        "bypass": bypass,
        "page": "home",
    })


@router.get("/traffic", response_class=HTMLResponse)
async def traffic_page(request: Request):
    """Traffic details page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_traffic", request, user)
    traffic = await services.get_traffic_data(user)
    bypass = await services.get_bypass_data(user)

    return templates.TemplateResponse("traffic.html", {
        "request": request,
        "user": user,
        "traffic": traffic,
        "bypass": bypass,
        "page": "traffic",
    })


@router.get("/connection", response_class=HTMLResponse)
async def connection_page(request: Request):
    """Connection page with VPN link and QR code."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_connection", request, user)
    sub = await services.get_subscription_status(user)
    sub_url = ""
    connect_url = ""
    if sub.get("token"):
        sub_url = services.get_subscription_url(sub["token"])
        connect_url = services.get_connect_url(sub["token"])

    return templates.TemplateResponse("connection.html", {
        "request": request,
        "user": user,
        "sub": sub,
        "sub_url": sub_url,
        "connect_url": connect_url,
        "page": "connection",
    })


@router.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request):
    """Subscription plans page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_subscription", request, user)
    sub = await services.get_subscription_status(user)
    plans = services.get_plans()

    return templates.TemplateResponse("subscription.html", {
        "request": request,
        "user": user,
        "sub": sub,
        "plans": plans,
        "page": "subscription",
    })


@router.get("/payment", response_class=HTMLResponse)
async def payment_page(request: Request):
    """Payment methods page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_payment", request, user)
    plans = services.get_plans()
    payments = await services.get_payment_history(user.id)
    sub = await services.get_subscription_status(user)

    return templates.TemplateResponse("payment.html", {
        "request": request,
        "user": user,
        "plans": plans,
        "payments": payments,
        "sub": sub,
        "page": "payment",
    })


@router.get("/referral", response_class=HTMLResponse)
async def referral_page(request: Request):
    """Referral system page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_referral", request, user)
    referral = await services.get_referral_info(user)

    return templates.TemplateResponse("referral.html", {
        "request": request,
        "user": user,
        "referral": referral,
        "page": "referral",
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_settings", request, user)
    sub = await services.get_subscription_status(user)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "sub": sub,
        "page": "settings",
    })


@router.post("/settings/email")
async def settings_email(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    """Bind email + password: sends verification code instead of saving immediately."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    sub = await services.get_subscription_status(user)
    email = email.strip().lower()
    error = None
    is_password_change = bool(user.email) and email == user.email

    # Validate
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        error = "Введите корректный email"
    elif len(password) < 6:
        error = "Пароль должен быть не менее 6 символов"
    elif password != password_confirm:
        error = "Пароли не совпадают"

    if not error and not is_password_change:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.email == email, Persons.id != user.id)
            result = await db.execute(stmt)
            if result.scalar_one_or_none():
                error = "Этот email уже используется"

    if error:
        return templates.TemplateResponse("settings.html", {
            "request": request, "user": user, "sub": sub,
            "page": "settings", "email_error": error,
        })

    # If just changing password on already-verified email — save directly
    if is_password_change:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.id == user.id)
            result = await db.execute(stmt)
            db_user = result.scalar_one_or_none()
            if db_user:
                db_user.password_hash = hash_password(password)
                await db.commit()
        user = await get_current_user(request)
        sub = await services.get_subscription_status(user)
        return templates.TemplateResponse("settings.html", {
            "request": request, "user": user, "sub": sub,
            "page": "settings", "email_success": "Пароль обновлён",
        })

    # New email — generate verification code and send
    code = str(secrets.randbelow(900000) + 100000)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            db_user.email_pending = email
            db_user.email_verification_code = code
            db_user.email_verification_expires = expires
            db_user.password_hash = hash_password(password)
            await db.commit()

    await send_verification_code(email, code)
    log.info(f"[Dashboard] Verification code sent to {email} for user id={user.id}")

    user = await get_current_user(request)
    sub = await services.get_subscription_status(user)
    return templates.TemplateResponse("settings.html", {
        "request": request, "user": user, "sub": sub,
        "page": "settings",
        "verify_email": email,
        "email_success": "Код отправлен на " + email,
    })


@router.post("/settings/verify-email")
async def settings_verify_email(
    request: Request,
    code: str = Form(""),
):
    """Verify the 6-digit code and activate the email."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    sub = await services.get_subscription_status(user)
    code = code.strip()

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()

        if not db_user or not db_user.email_verification_code:
            return templates.TemplateResponse("settings.html", {
                "request": request, "user": user, "sub": sub,
                "page": "settings", "email_error": "Сначала запросите код",
            })

        now = datetime.now(timezone.utc)
        if db_user.email_verification_expires and db_user.email_verification_expires < now:
            return templates.TemplateResponse("settings.html", {
                "request": request, "user": user, "sub": sub,
                "page": "settings", "email_error": "Код истёк. Запросите новый.",
            })

        if db_user.email_verification_code != code:
            return templates.TemplateResponse("settings.html", {
                "request": request, "user": user, "sub": sub,
                "page": "settings",
                "verify_email": db_user.email_pending or "",
                "email_error": "Неверный код",
            })

        # Code is correct — activate email
        db_user.email = db_user.email_pending
        db_user.email_verified = True
        db_user.email_pending = None
        db_user.email_verification_code = None
        db_user.email_verification_expires = None
        await db.commit()
        log.info(f"[Dashboard] Email verified: {db_user.email} for user id={user.id}")
        await log_dashboard_action("email_verified", request, user, f"email={db_user.email}")

    user = await get_current_user(request)
    sub = await services.get_subscription_status(user)
    return templates.TemplateResponse("settings.html", {
        "request": request, "user": user, "sub": sub,
        "page": "settings", "email_success": "Email подтверждён!",
    })


@router.post("/settings/resend-code")
async def settings_resend_code(request: Request):
    """Resend verification code (rate limit: 1/min)."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    sub = await services.get_subscription_status(user)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()

        if not db_user or not db_user.email_pending:
            return templates.TemplateResponse("settings.html", {
                "request": request, "user": user, "sub": sub,
                "page": "settings", "email_error": "Нет ожидающего подтверждения email",
            })

        # Rate limit: check if code was sent less than 60s ago
        now = datetime.now(timezone.utc)
        if db_user.email_verification_expires:
            sent_at = db_user.email_verification_expires - timedelta(minutes=15)
            if (now - sent_at).total_seconds() < 60:
                return templates.TemplateResponse("settings.html", {
                    "request": request, "user": user, "sub": sub,
                    "page": "settings",
                    "verify_email": db_user.email_pending,
                    "email_error": "Подождите минуту перед повторной отправкой",
                })

        code = str(secrets.randbelow(900000) + 100000)
        expires = now + timedelta(minutes=15)
        db_user.email_verification_code = code
        db_user.email_verification_expires = expires
        await db.commit()

    await send_verification_code(db_user.email_pending, code)

    user = await get_current_user(request)
    sub = await services.get_subscription_status(user)
    return templates.TemplateResponse("settings.html", {
        "request": request, "user": user, "sub": sub,
        "page": "settings",
        "verify_email": db_user.email_pending,
        "email_success": "Код отправлен повторно",
    })


# ==================== HTMX PARTIALS ====================

@router.get("/partials/traffic-card", response_class=HTMLResponse)
async def partial_traffic_card(request: Request):
    """HTMX partial: traffic card."""
    user = await get_current_user(request)
    if not user:
        return HTMLResponse("", status_code=401)

    traffic = await services.get_traffic_data(user)
    bypass = await services.get_bypass_data(user)
    return templates.TemplateResponse("partials/_traffic_card.html", {
        "request": request,
        "traffic": traffic,
        "bypass": bypass,
    })


@router.get("/partials/subscription-card", response_class=HTMLResponse)
async def partial_subscription_card(request: Request):
    """HTMX partial: subscription card."""
    user = await get_current_user(request)
    if not user:
        return HTMLResponse("", status_code=401)

    sub = await services.get_subscription_status(user)
    return templates.TemplateResponse("partials/_subscription_card.html", {
        "request": request,
        "sub": sub,
    })


@router.get("/partials/balance-card", response_class=HTMLResponse)
async def partial_balance_card(request: Request):
    """HTMX partial: balance card."""
    user = await get_current_user(request)
    if not user:
        return HTMLResponse("", status_code=401)

    return templates.TemplateResponse("partials/_balance_card.html", {
        "request": request,
        "user": user,
    })
