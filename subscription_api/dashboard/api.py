"""
Dashboard JSON API endpoints (/api/v1/*).
"""

import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from bot.database.models.main import Persons
from subscription_api.dashboard.dependencies import require_user_api
from subscription_api.dashboard import services

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Dashboard API"])


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
    traffic = await services.get_traffic_data(user.tgid)
    bypass = await services.get_bypass_data(user.tgid)
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
    return result


@router.post("/promo/apply")
async def api_apply_promo(request: Request, user: Persons = Depends(require_user_api)):
    """Apply a promo code."""
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        return JSONResponse({"success": False, "error": "Введите промокод"}, status_code=400)

    result = await services.apply_promo_code(user, code)
    return result


@router.post("/trial/activate")
async def api_activate_trial(user: Persons = Depends(require_user_api)):
    """Activate free trial."""
    result = await services.activate_trial(user)
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
    return result


@router.get("/plans")
async def api_plans():
    """Get available subscription plans."""
    return {"plans": services.get_plans(), "deposits": services.get_deposit_amounts()}
