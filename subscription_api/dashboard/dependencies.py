"""
FastAPI dependencies for dashboard authentication.
"""

import logging
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons
from subscription_api.dashboard.auth import decode_jwt_token, COOKIE_NAME

log = logging.getLogger(__name__)


async def get_current_user(request: Request) -> Optional[Persons]:
    """
    Get current authenticated user from JWT cookie or Authorization header.
    Returns Persons ORM object or None.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        # Fallback: check Authorization header (for API calls from register flow)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None

    payload = decode_jwt_token(token)
    if not payload:
        return None

    user_id = payload.get("user_id")
    if not user_id:
        return None

    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Persons).filter(Persons.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            return user
    except Exception as e:
        log.error(f"[Dashboard] Error fetching user {user_id}: {e}")
        return None


async def require_user(request: Request) -> Persons:
    """
    Require authenticated user. Redirects to login if not authenticated.
    For use in HTML page endpoints.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/dashboard/login"})
    return user


async def require_user_api(request: Request) -> Persons:
    """
    Require authenticated user for API endpoints. Returns 401 JSON.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
