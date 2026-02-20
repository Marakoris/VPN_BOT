"""
HTML email templates for NoBorder VPN dashboard.
Dark theme, inline CSS, mobile-friendly.
"""

BRAND_COLOR = "#6c5ce7"
BG_COLOR = "#0f0f1a"
CARD_BG = "#1a1a2e"
TEXT_COLOR = "#e0e0e0"
TEXT_MUTED = "#888"
SUCCESS_COLOR = "#00ff88"
DANGER_COLOR = "#ff6b6b"
BORDER_COLOR = "#2a2a3e"

DASHBOARD_URL = "https://vpnnoborder.sytes.net/dashboard"


def _email_wrapper(content: str) -> str:
    """Common email wrapper with logo and footer."""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{BG_COLOR};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{BG_COLOR};padding:20px 0">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:0 auto">
  <!-- Header -->
  <tr><td style="text-align:center;padding:24px 20px 16px">
    <div style="font-size:32px;margin-bottom:8px">&#x1f6e1;</div>
    <div style="font-size:20px;font-weight:700;color:#fff">NoBorder VPN</div>
  </td></tr>
  <!-- Content card -->
  <tr><td style="padding:0 16px">
    <div style="background:{CARD_BG};border-radius:16px;border:1px solid {BORDER_COLOR};padding:28px 24px">
      {content}
    </div>
  </td></tr>
  <!-- Footer -->
  <tr><td style="text-align:center;padding:20px;color:{TEXT_MUTED};font-size:12px">
    <a href="{DASHBOARD_URL}" style="color:{BRAND_COLOR};text-decoration:none">vpnnoborder.com</a>
    <br>
    <span style="color:{TEXT_MUTED}">&#169; NoBorder VPN</span>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _button(text: str, url: str) -> str:
    """Styled CTA button."""
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0 8px">'
        f'<tr><td align="center">'
        f'<a href="{url}" style="display:inline-block;background:{BRAND_COLOR};color:#fff;'
        f'font-size:15px;font-weight:600;padding:14px 32px;border-radius:12px;'
        f'text-decoration:none;letter-spacing:0.3px">{text}</a>'
        f'</td></tr></table>'
    )


def render_verification_email(code: str) -> tuple[str, str]:
    """Verification code email. Returns (subject, html)."""
    subject = f"Код подтверждения: {code}"
    content = f"""
      <h2 style="color:#fff;font-size:18px;margin:0 0 12px;text-align:center">Подтверждение email</h2>
      <p style="color:{TEXT_COLOR};font-size:14px;line-height:1.5;margin:0 0 24px;text-align:center">
        Введите этот код в личном кабинете:
      </p>
      <div style="text-align:center;margin:0 0 24px">
        <div style="display:inline-block;background:{BG_COLOR};border:2px solid {BRAND_COLOR};
          border-radius:12px;padding:16px 32px;font-size:32px;font-weight:700;
          letter-spacing:8px;color:#fff;font-family:monospace">{code}</div>
      </div>
      <p style="color:{TEXT_MUTED};font-size:13px;text-align:center;margin:0">
        Код действителен 15 минут.<br>Если вы не запрашивали код — просто проигнорируйте письмо.
      </p>"""
    return subject, _email_wrapper(content)


def render_password_reset_email(reset_url: str) -> tuple[str, str]:
    """Password reset email. Returns (subject, html)."""
    subject = "Сброс пароля - NoBorder VPN"
    content = f"""
      <h2 style="color:#fff;font-size:18px;margin:0 0 12px;text-align:center">Сброс пароля</h2>
      <p style="color:{TEXT_COLOR};font-size:14px;line-height:1.5;margin:0 0 8px;text-align:center">
        Нажмите кнопку ниже, чтобы задать новый пароль:
      </p>
      {_button("Сбросить пароль", reset_url)}
      <p style="color:{TEXT_MUTED};font-size:13px;text-align:center;margin:16px 0 0">
        Ссылка действительна 1 час.<br>Если вы не запрашивали сброс — просто проигнорируйте письмо.
      </p>"""
    return subject, _email_wrapper(content)


def render_subscription_expiry_email(days_left: int, expiry_date: str) -> tuple[str, str]:
    """Subscription expiry warning. Returns (subject, html)."""
    if days_left <= 1:
        subject = "Подписка истекает сегодня!"
        urgency = f'<span style="color:{DANGER_COLOR};font-weight:600">сегодня</span>'
    else:
        subject = f"Подписка истекает через {days_left} дня"
        urgency = f'через <span style="color:#ffaa00;font-weight:600">{days_left} дня</span>'

    content = f"""
      <h2 style="color:#fff;font-size:18px;margin:0 0 12px;text-align:center">Подписка заканчивается</h2>
      <p style="color:{TEXT_COLOR};font-size:14px;line-height:1.5;margin:0 0 8px;text-align:center">
        Ваша подписка истекает {urgency}
        <br><span style="color:{TEXT_MUTED}">({expiry_date})</span>
      </p>
      {_button("Продлить подписку", DASHBOARD_URL + "/payment")}
      <p style="color:{TEXT_MUTED};font-size:13px;text-align:center;margin:8px 0 0">
        После истечения VPN перестанет работать.
      </p>"""
    return subject, _email_wrapper(content)


def render_payment_success_email(amount: float, days: int, expiry_date: str) -> tuple[str, str]:
    """Payment confirmation email. Returns (subject, html)."""
    subject = f"Оплата {amount:.0f} руб. прошла успешно"
    content = f"""
      <h2 style="color:#fff;font-size:18px;margin:0 0 16px;text-align:center">Оплата прошла успешно</h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px">
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid {BORDER_COLOR};color:{TEXT_MUTED};font-size:14px">Сумма</td>
          <td style="padding:10px 0;border-bottom:1px solid {BORDER_COLOR};color:#fff;font-size:14px;text-align:right;font-weight:600">{amount:.0f} &#8381;</td>
        </tr>
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid {BORDER_COLOR};color:{TEXT_MUTED};font-size:14px">Период</td>
          <td style="padding:10px 0;border-bottom:1px solid {BORDER_COLOR};color:#fff;font-size:14px;text-align:right">{days} дн.</td>
        </tr>
        <tr>
          <td style="padding:10px 0;color:{TEXT_MUTED};font-size:14px">Активна до</td>
          <td style="padding:10px 0;color:{SUCCESS_COLOR};font-size:14px;text-align:right;font-weight:600">{expiry_date}</td>
        </tr>
      </table>
      <p style="color:{TEXT_MUTED};font-size:13px;text-align:center;margin:0">
        Если VPN уже настроен &#8212; ничего делать не нужно.
      </p>"""
    return subject, _email_wrapper(content)
