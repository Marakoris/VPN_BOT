"""
Dashboard authentication module.
Supports two auth methods:
1. Telegram Login Widget (HMAC verification)
2. Subscription token link from bot
"""

import os
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError

log = logging.getLogger(__name__)

JWT_SECRET = os.getenv("DASHBOARD_JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
COOKIE_NAME = "dashboard_token"

BOT_TOKEN = os.getenv("TG_TOKEN", "")


def create_jwt_token(user_id: int, tgid: int) -> str:
    """Create JWT token for dashboard session."""
    expire = datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "user_id": user_id,
        "tgid": tgid,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[dict]:
    """Decode and verify JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def verify_telegram_login(data: dict) -> bool:
    """
    Verify Telegram Login Widget callback data using HMAC-SHA256.
    https://core.telegram.org/widgets/login#checking-authorization
    """
    check_hash = data.pop("hash", None)
    if not check_hash:
        return False

    # Build data-check-string
    items = sorted(data.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    # Secret key = SHA256(bot_token)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()

    # HMAC-SHA256
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, check_hash):
        log.warning("[Dashboard Auth] Telegram login HMAC verification failed")
        return False

    # Check auth_date is not too old (allow 1 day)
    auth_date = int(data.get("auth_date", 0))
    if datetime.utcnow().timestamp() - auth_date > 86400:
        log.warning("[Dashboard Auth] Telegram login auth_date too old")
        return False

    return True
