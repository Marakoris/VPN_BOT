"""
Dashboard HTML page endpoints (/dashboard/*).
Uses Jinja2 templates with HTMX for dynamic content.
"""

import os
import logging
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


# ==================== MAIN PAGES ====================

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Main dashboard page."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    await log_dashboard_action("page_home", request, user)
    sub = await services.get_subscription_status(user)
    traffic = await services.get_traffic_data(user.tgid)
    bypass = await services.get_bypass_data(user.tgid)

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
    traffic = await services.get_traffic_data(user.tgid)
    bypass = await services.get_bypass_data(user.tgid)

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
    """Bind email + password to account, or change password."""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    sub = await services.get_subscription_status(user)
    email = email.strip().lower()
    error = None

    # Validate email format
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        error = "Введите корректный email"
    elif len(password) < 6:
        error = "Пароль должен быть не менее 6 символов"
    elif password != password_confirm:
        error = "Пароли не совпадают"

    if not error:
        # Check email uniqueness (skip if user already has this email)
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.email == email, Persons.id != user.id)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                error = "Этот email уже используется"

    if error:
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "user": user,
            "sub": sub,
            "page": "settings",
            "email_error": error,
        })

    # Save email + password hash
    had_email = bool(user.email)
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(Persons.id == user.id)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            db_user.email = email
            db_user.password_hash = hash_password(password)
            await db.commit()
            log.info(f"[Dashboard] User {user.tgid} bound email {email}")
            await log_dashboard_action("email_bind", request, user, f"email={email}")

    # Re-fetch user to get updated email
    user = await get_current_user(request)
    sub = await services.get_subscription_status(user)

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "sub": sub,
        "page": "settings",
        "email_success": "Пароль обновлён" if had_email else "Email привязан",
    })


# ==================== HTMX PARTIALS ====================

@router.get("/partials/traffic-card", response_class=HTMLResponse)
async def partial_traffic_card(request: Request):
    """HTMX partial: traffic card."""
    user = await get_current_user(request)
    if not user:
        return HTMLResponse("", status_code=401)

    traffic = await services.get_traffic_data(user.tgid)
    bypass = await services.get_bypass_data(user.tgid)
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
