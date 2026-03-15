"""
Async email sending service via Brevo SMTP.
"""

import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from subscription_api.dashboard.email_templates import (
    render_verification_email,
    render_password_reset_email,
    render_subscription_expiry_email,
    render_payment_success_email,
)

log = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@vpnnoborder.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "NoBorder VPN")


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        log.warning("[Email] SMTP credentials not configured, skipping send")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        log.info(f"[Email] Sent '{subject}' to {to}")
        return True
    except Exception as e:
        log.error(f"[Email] Failed to send to {to}: {e}")
        return False


async def send_verification_code(to: str, code: str) -> bool:
    """Send 6-digit verification code."""
    subject, html = render_verification_email(code)
    return await send_email(to, subject, html)


async def send_password_reset(to: str, token: str) -> bool:
    """Send password reset link."""
    reset_url = f"https://vpnnoborder.sytes.net/dashboard/reset-password?token={token}"
    subject, html = render_password_reset_email(reset_url)
    return await send_email(to, subject, html)


async def send_subscription_expiry(to: str, days_left: int, expiry_date: str) -> bool:
    """Send subscription expiry warning."""
    subject, html = render_subscription_expiry_email(days_left, expiry_date)
    return await send_email(to, subject, html)


async def send_payment_success(to: str, amount: float, days: int, expiry_date: str) -> bool:
    """Send payment confirmation."""
    subject, html = render_payment_success_email(amount, days, expiry_date)
    return await send_email(to, subject, html)
