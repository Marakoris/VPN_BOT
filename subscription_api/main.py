"""
Subscription API - main application

This FastAPI application provides subscription endpoints for VPN clients.
"""
import sys
import os
import logging
import asyncio
import base64
import time
from typing import Optional, Dict, Tuple
from datetime import datetime

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot.misc.subscription import verify_subscription_token
from bot.database.methods.get import get_person
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.main import engine
from bot.database.models.main import Persons, Servers, SubscriptionLogs
from bot.misc.VPN.ServerManager import ServerManager
from subscription_api.config_generators import generate_config
from subscription_api.security import (
    check_rate_limit,
    record_failed_attempt,
    check_suspicious_activity,
    get_security_stats,
    unban_ip,
    security_manager,
    is_yookassa_ip
)
from subscription_api.yookassa_webhook import process_payment_webhook

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Subscription cache: {user_id: (content, timestamp, headers)}
# Cache TTL: 5 minutes (300 seconds)
SUBSCRIPTION_CACHE: Dict[int, Tuple[str, float, dict]] = {}
CACHE_TTL = 300  # 5 minutes

def get_cached_subscription(user_id: int) -> Optional[Tuple[str, dict]]:
    """Get cached subscription if valid"""
    if user_id in SUBSCRIPTION_CACHE:
        content, timestamp, headers = SUBSCRIPTION_CACHE[user_id]
        if time.time() - timestamp < CACHE_TTL:
            return content, headers
        else:
            del SUBSCRIPTION_CACHE[user_id]
    return None

def cache_subscription(user_id: int, content: str, headers: dict):
    """Cache subscription content"""
    SUBSCRIPTION_CACHE[user_id] = (content, time.time(), headers)
    log.info(f"[Cache] Cached subscription for user {user_id}")

# Create FastAPI app
app = FastAPI(
    title="VPN Subscription API",
    description="Subscription-based VPN access API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for Happ and other VPN clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DASHBOARD ROUTERS ====================
from subscription_api.dashboard.router import router as dashboard_router
from subscription_api.dashboard.api import router as dashboard_api_router

app.include_router(dashboard_router)
app.include_router(dashboard_api_router)

# Mount static files directory (must be AFTER router includes)
static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    log.info("🚀 Starting Subscription API...")
    log.info("📡 Database connection ready")
    log.info("🔒 Security manager initialized")
    log.info(f"   - Rate limit: {security_manager.config.RATE_LIMIT_REQUESTS} req/{security_manager.config.RATE_LIMIT_WINDOW}s")
    log.info(f"   - Brute-force protection: {security_manager.config.BRUTE_FORCE_THRESHOLD} attempts")
    log.info(f"   - Ban duration: {security_manager.config.BRUTE_FORCE_BAN_DURATION}s")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    log.info("🛑 Shutting down Subscription API...")


# ==================== HEALTH CHECK ENDPOINTS ====================

@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint - basic health check

    Returns simple status message
    """
    return {
        "status": "ok",
        "service": "VPN Subscription API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Detailed health check

    Checks:
    - API status
    - Database connection
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Check database connection
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            result = await db.execute(select(Persons).limit(1))
            user = result.scalar_one_or_none()
            health_status["checks"]["database"] = "ok"
    except Exception as e:
        log.error(f"Health check - database error: {e}")
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/ping", tags=["Health"])
async def ping():
    """Simple ping endpoint"""
    return {"ping": "pong"}


# ==================== SUBSCRIPTION ENDPOINT ====================

async def log_subscription_access(
    user_id: int,
    ip_address: str,
    user_agent: str,
    servers_count: int
):
    """Log subscription access to database"""
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            log_entry = SubscriptionLogs(
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                servers_count=servers_count
            )
            db.add(log_entry)
            await db.commit()
    except Exception as e:
        log.error(f"Failed to log subscription access: {e}")


@app.get("/sub/{token}", response_class=PlainTextResponse, tags=["Subscription"])
async def get_subscription(token: str, request: Request):
    """
    Get subscription configuration

    Returns a list of VPN server configurations for the user.
    This endpoint will return actual VLESS/Shadowsocks configs in Stage 3.

    For now, it returns a simple text list of available servers.

    Args:
        token: Subscription token (HMAC-signed)
        request: FastAPI request object (for IP and user-agent)

    Returns:
        PlainTextResponse with server configurations or empty string
    """
    client_ip = request.client.host

    try:
        # SECURITY: Check rate limit
        allowed, error_msg = check_rate_limit(client_ip)
        if not allowed:
            log.warning(f"[Security] Rate limit blocked: {client_ip} - {error_msg}")
            return PlainTextResponse(
                content="# Rate limit exceeded\n",
                status_code=429,
                headers={"profile-title": "NoBorder VPN"}
            )

        # SECURITY: Check suspicious activity
        if check_suspicious_activity(client_ip):
            log.warning(f"[Security] Suspicious activity detected: {client_ip}")
            # Don't block, just log for now

        # 1. Verify token
        user_id = verify_subscription_token(token)
        if not user_id:
            # SECURITY: Record failed attempt for brute-force protection
            record_failed_attempt(client_ip, reason="invalid_token")
            log.warning(f"[Subscription API] Invalid token from {client_ip}")
            return PlainTextResponse(
                content="# Invalid subscription token\n",
                status_code=401,
                headers={"profile-title": "NoBorder VPN"}
            )

        # 1.5 Check cache first (for fast response)
        cached = get_cached_subscription(user_id)
        if cached:
            content, headers = cached
            log.info(f"[Subscription API] ⚡ Returning cached subscription for user_id {user_id}")
            return PlainTextResponse(content=content, headers=headers)

        # 2. Get user from database (using internal user_id)
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            statement = select(Persons).filter(Persons.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()

            if not user:
                log.warning(f"[Subscription API] User {user_id} not found")
                return ""

            # 3. Check subscription status
            if not user.subscription_active:
                log.info(f"[Subscription API] Inactive subscription for user {user.tgid}")
                raise HTTPException(
                    status_code=403,
                    detail="Subscription not active"
                )

            # 4. Get all active servers (VLESS + Shadowsocks)
            statement = select(Servers).filter(
                Servers.work == True,
                Servers.type_vpn.in_([1, 2])  # VLESS and Shadowsocks
            ).order_by(Servers.id)

            result = await db.execute(statement)
            all_servers = result.scalars().all()

            if not all_servers:
                log.warning(f"[Subscription API] No servers found")
                return ""

            # 5. Check which servers have keys for this user (PARALLEL with early return)
            SERVER_TIMEOUT = 15  # seconds per server (increased for high-latency servers like USA)
            TOTAL_TIMEOUT = 45    # max total time for all servers

            async def check_server(server):
                """Check if user has key on server and generate config"""
                try:
                    server_manager = ServerManager(server)
                    await server_manager.login()
                    existing_client = await server_manager.get_user(user.tgid)

                    if existing_client:
                        config_url = await generate_config(server, user.tgid)
                        return config_url
                    return None
                except Exception as e:
                    log.debug(f"[Subscription API] Error with server {server.id}: {e}")
                    return None

            async def check_server_with_timeout(server):
                """Wrap check_server with per-server timeout, return (server_id, is_bypass, result) for sorting"""
                try:
                    result = await asyncio.wait_for(check_server(server), timeout=SERVER_TIMEOUT)
                    return (server.id, server.is_bypass, result, server.name)
                except asyncio.TimeoutError:
                    log.warning(f"[Subscription API] Timeout for server {server.id} ({server.name})")
                    return (server.id, server.is_bypass, None, server.name)

            # Run all server checks with TOTAL timeout - return what we get
            tasks = [asyncio.create_task(check_server_with_timeout(server)) for server in all_servers]

            try:
                # Wait for all tasks but with total timeout
                done, pending = await asyncio.wait(tasks, timeout=TOTAL_TIMEOUT)

                # Cancel any still pending tasks
                for task in pending:
                    task.cancel()
                    log.warning(f"[Subscription API] Cancelled slow task")

                # Get results from completed tasks (format: (server_id, is_bypass, config))
                results_with_ids = []
                for task in done:
                    try:
                        server_id, is_bypass, result, server_name = task.result()
                        if result:
                            results_with_ids.append((server_id, is_bypass, result, server_name))
                    except Exception:
                        pass
                # Sort: regular servers first (is_bypass=False), then bypass servers, by server_id within each group
                results_with_ids.sort(key=lambda x: (x[1], x[3]))  # (is_bypass, server_id)
                results = [r[2] for r in results_with_ids]

            except asyncio.TimeoutError:
                # Total timeout - get what we have
                log.warning(f"[Subscription API] Total timeout reached, returning partial results")
                results_with_ids = []
                for task in tasks:
                    if task.done() and not task.cancelled():
                        try:
                            server_id, is_bypass, result, server_name = task.result()
                            if result:
                                results_with_ids.append((server_id, is_bypass, result, server_name))
                        except Exception:
                            pass
                # Sort: regular servers first (is_bypass=False), then bypass servers, by server_id within each group
                results_with_ids.sort(key=lambda x: (x[1], x[3]))  # (is_bypass, server_id)
                results = [r[2] for r in results_with_ids]

            # Use results directly (already filtered)
            config_lines = results
            # Reality bypass for Beeline whitelist user
            if user.tgid in [870499087, 464180877]:
                # Bypass servers with tunnel.vk-apps.com SNI (Beeline whitelist)
                log.info(f"[Subscription API] Added 3 Reality bypass servers for user {user.tgid}")

            if not config_lines:
                log.warning(f"[Subscription API] No keys found for user {user.tgid}")
                return ""

            # 7. Log access
            await log_subscription_access(
                user_id=user.id,
                ip_address=request.client.host,
                user_agent=request.headers.get("user-agent", "unknown"),
                servers_count=len(config_lines)
            )

            log.info(
                f"[Subscription API] ✅ Served subscription for user {user.tgid}: "
                f"{len(config_lines)} servers from {request.client.host}"
            )

            # Prepare response with custom headers for subscription title
            content = "\n".join(config_lines)

            # Add headers for readable subscription name in VPN clients
            # Including headers that Happ and other clients expect
            profile_title_b64 = base64.b64encode("NoBorder VPN 🔐".encode()).decode()
            headers = {
                "content-disposition": 'attachment; filename="NoBorder VPN.txt"',
                "profile-title": f"base64:{profile_title_b64}",
                "profile-update-interval": "2",
                "support-url": "https://t.me/NoBorderVPN_bot",
                "subscription-userinfo": f"upload=0; download=0; expire={int(user.subscription)}",
                "access-control-allow-origin": "*",
            }

            # Cache the result for fast subsequent requests
            cache_subscription(user_id, content, headers)

            return PlainTextResponse(content=content, headers=headers)

    except HTTPException:
        raise  # Re-raise HTTPException so FastAPI handles it properly
    except Exception as e:
        log.error(f"[Subscription API] Error in subscription endpoint: {e}")
        import traceback
        traceback.print_exc()
        return ""


# ==================== ADMIN ENDPOINTS (Optional) ====================

@app.get("/stats", tags=["Admin"])
async def get_stats():
    """
    Get subscription API statistics

    Returns statistics about subscription usage
    """
    try:
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            # Count active subscriptions
            result = await db.execute(
                select(Persons).filter(Persons.subscription_active == True)
            )
            active_count = len(result.scalars().all())

            # Count total subscription logs
            result = await db.execute(
                select(SubscriptionLogs)
            )
            total_accesses = len(result.scalars().all())

            return {
                "active_subscriptions": active_count,
                "total_accesses": total_accesses,
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        log.error(f"Stats endpoint error: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.get("/security/stats", tags=["Security"])
async def get_security_statistics(ip: Optional[str] = None):
    """
    Get security statistics

    Args:
        ip: Optional - get stats for specific IP

    Returns:
        Security statistics (rate limits, banned IPs, etc.)
    """
    try:
        stats = get_security_stats(ip)
        return JSONResponse(content=stats)
    except Exception as e:
        log.error(f"Security stats error: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.post("/security/unban/{ip}", tags=["Security"])
async def unban_ip_endpoint(ip: str):
    """
    Unban an IP address

    Args:
        ip: IP address to unban

    Returns:
        Success or error message
    """
    try:
        result = unban_ip(ip)
        if result:
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"IP {ip} has been unbanned",
                    "ip": ip
                }
            )
        else:
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"IP {ip} was not banned or not found",
                    "ip": ip
                },
                status_code=404
            )
    except Exception as e:
        log.error(f"Unban IP error: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


# ==================== YOOKASSA WEBHOOK ====================

def get_real_ip(request: Request) -> str:
    """Get real client IP from X-Real-IP or X-Forwarded-For headers."""
    # Try X-Real-IP first (set by nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # Try X-Forwarded-For (first IP in the chain)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    # Fallback to direct connection IP
    return request.client.host

@app.post("/webhooks/yookassa", tags=["Webhooks"])
async def yookassa_webhook(request: Request):
    """
    YooKassa payment webhook endpoint.

    Handles payment.succeeded events for delayed payments
    that weren't caught by the 30-minute polling window.

    Security:
    - Verifies request IP is from YooKassa whitelist
    - Processes payment and activates subscription
    - Sends notifications to user and admins
    """
    client_ip = get_real_ip(request)

    # Verify IP is from YooKassa
    if not is_yookassa_ip(client_ip):
        log.warning(f"[Webhook] Rejected request from non-YooKassa IP: {client_ip}")
        return JSONResponse(
            status_code=403,
            content={"error": "Forbidden"}
        )

    try:
        # Parse webhook data
        webhook_data = await request.json()
        log.info(f"[Webhook] Received webhook from {client_ip}: event={webhook_data.get('event')}")

        # Process the webhook
        result = await process_payment_webhook(webhook_data)

        log.info(f"[Webhook] Processing result: {result}")

        # Always return 200 OK to YooKassa (they will retry on non-2xx)
        return JSONResponse(content={"status": "ok", "result": result})

    except Exception as e:
        log.error(f"[Webhook] Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        # Still return 200 to prevent YooKassa retries on our errors
        return JSONResponse(content={"status": "error", "message": str(e)})


@app.get("/webhooks/yookassa/test", tags=["Webhooks"])
async def yookassa_webhook_test(request: Request):
    """
    Test endpoint to verify webhook is accessible.
    Returns client IP and whether it would be allowed.
    """
    client_ip = get_real_ip(request)
    is_allowed = is_yookassa_ip(client_ip)

    return JSONResponse(content={
        "status": "ok",
        "endpoint": "/webhooks/yookassa",
        "client_ip": client_ip,
        "is_yookassa_ip": is_allowed,
        "message": "Webhook endpoint is active. POST payment.succeeded events here."
    })


# ==================== HELPER FUNCTIONS ====================

def get_error_page(title: str, message: str) -> str:
    """Generate error page HTML"""
    return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - NoBorder VPN</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            text-align: center;
            max-width: 400px;
        }}
        .icon {{ font-size: 64px; margin-bottom: 20px; }}
        h1 {{ color: #ff6b6b; margin-bottom: 15px; font-size: 24px; }}
        p {{ color: #888; line-height: 1.6; }}
        .btn {{
            display: inline-block;
            margin-top: 20px;
            padding: 14px 28px;
            background: linear-gradient(135deg, #00d9ff 0%, #00ff88 100%);
            color: #000;
            text-decoration: none;
            border-radius: 12px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">⚠️</div>
        <h1>{title}</h1>
        <p>{message}</p>
        <a href="https://t.me/VPN_NB_test_bot" class="btn">Открыть бота</a>
    </div>
</body>
</html>
"""


# ==================== DEEP LINK ENDPOINT ====================

@app.get("/add/{token}", response_class=HTMLResponse, tags=["Subscription"])
async def add_subscription_deeplink(token: str, request: Request):
    """
    Beautiful landing page for adding subscription to VPN apps.
    Similar to Alius VPN style page.
    """
    client_ip = request.client.host
    import urllib.parse
    from datetime import datetime

    try:
        # Verify token first
        user_id = verify_subscription_token(token)
        if not user_id:
            record_failed_attempt(client_ip, reason="invalid_token")
            return HTMLResponse(content=get_error_page("Неверная ссылка", "Ссылка на подписку недействительна или истекла.<br>Получите новую ссылку в боте."), status_code=401)

        # Get user info for displaying subscription expiry
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            statement = select(Persons).filter(Persons.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()

        # Calculate subscription expiry
        expiry_text = "Неизвестно"
        if user and user.subscription:
            from datetime import datetime
            expiry_date = datetime.fromtimestamp(user.subscription)
            now = datetime.now()
            diff = expiry_date - now
            if diff.days > 30:
                months = diff.days // 30
                expiry_text = f"Истекает через {months} мес."
            elif diff.days > 0:
                expiry_text = f"Истекает через {diff.days} дн."
            elif diff.days == 0:
                expiry_text = "Истекает сегодня"
            else:
                expiry_text = "Подписка истекла"

        user_display = f"_{user.tgid}" if user else "Пользователь"

        # Build URLs
        encoded_token = urllib.parse.quote(token, safe='')
        subscription_url = f"https://vpnnoborder.sytes.net/sub/{encoded_token}"
        # For deep links use raw token (without URL encoding) - Happ handles it better
        raw_subscription_url = f"https://vpnnoborder.sytes.net/sub/{token}"
        deep_link_happ = f"happ://add/{raw_subscription_url}"
        deep_link_v2raytun = f"v2raytun://import/{raw_subscription_url}"

        log.info(f"[Deep Link] User {user_id} accessing add link from {client_ip}")

        html_content = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔷</text></svg>">
    <title>NoBorder VPN</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 500px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 0;
            margin-bottom: 20px;
        }}
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #ff8c00, #ffb347);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}
        .brand-name {{
            font-size: 18px;
            font-weight: 600;
        }}
        .header-icons {{
            display: flex;
            gap: 10px;
        }}
        .header-icon {{
            width: 36px;
            height: 36px;
            background: rgba(255,255,255,0.1);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            text-decoration: none;
            color: #fff;
            transition: background 0.2s;
        }}
        .header-icon:hover {{
            background: rgba(255,255,255,0.2);
        }}

        /* User Card */
        .user-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 16px 20px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .user-check {{
            width: 24px;
            height: 24px;
            background: #00d9ff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #000;
            font-size: 14px;
        }}
        .user-info {{
            flex: 1;
        }}
        .user-name {{
            font-weight: 600;
            font-size: 16px;
        }}
        .user-expiry {{
            font-size: 13px;
            color: #888;
            margin-top: 2px;
        }}
        .user-arrow {{
            color: #666;
            font-size: 20px;
        }}

        /* Section Title */
        .section-title {{
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
        }}

        /* Platform Tabs */
        .platform-tabs {{
            display: flex;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 4px;
            margin-bottom: 25px;
        }}
        .platform-tab {{
            flex: 1;
            padding: 12px 16px;
            border-radius: 10px;
            border: none;
            background: transparent;
            color: #888;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}
        .platform-tab.active {{
            background: rgba(255,255,255,0.1);
            color: #fff;
        }}
        .platform-tab:hover {{
            color: #fff;
        }}

        /* App Tabs */
        .app-tabs {{
            display: flex;
            gap: 10px;
            margin-bottom: 25px;
        }}
        .app-tab {{
            flex: 1;
            padding: 14px;
            border-radius: 25px;
            border: 2px solid transparent;
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}
        .app-tab.active {{
            border-color: #00d9ff;
            background: rgba(0, 217, 255, 0.1);
        }}
        .app-tab:hover {{
            background: rgba(255,255,255,0.1);
        }}
        .app-tab-icon {{
            font-size: 16px;
        }}

        /* Steps */
        .steps {{
            position: relative;
            padding-left: 40px;
        }}
        .steps::before {{
            content: '';
            position: absolute;
            left: 12px;
            top: 30px;
            bottom: 30px;
            width: 2px;
            background: linear-gradient(180deg, #00d9ff 0%, #00ff88 100%);
        }}
        .step {{
            position: relative;
            margin-bottom: 30px;
        }}
        .step:last-child {{
            margin-bottom: 0;
        }}
        .step-icon {{
            position: absolute;
            left: -40px;
            width: 26px;
            height: 26px;
            background: #0f0f1a;
            border: 2px solid #00d9ff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: #00d9ff;
        }}
        .step.completed .step-icon {{
            background: #00d9ff;
            color: #000;
        }}
        .step-title {{
            font-weight: 600;
            font-size: 16px;
            margin-bottom: 6px;
        }}
        .step-desc {{
            font-size: 14px;
            color: #888;
            margin-bottom: 12px;
        }}

        /* Buttons */
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 14px 24px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
        }}
        .btn-outline {{
            background: transparent;
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
        }}
        .btn-outline:hover {{
            background: rgba(255,255,255,0.1);
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #00d9ff 0%, #00ff88 100%);
            color: #000;
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 217, 255, 0.3);
        }}

        /* Tips */
        .tips {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 20px;
            margin-top: 30px;
            font-size: 13px;
            color: #888;
            line-height: 1.8;
        }}
        .tips-title {{
            color: #fff;
            font-weight: 500;
            margin-bottom: 10px;
        }}
        .tips code {{
            background: rgba(255,255,255,0.1);
            padding: 2px 6px;
            border-radius: 4px;
            color: #00d9ff;
        }}

        /* Hidden content */
        .platform-content {{
            display: none;
        }}
        .platform-content.active {{
            display: block;
        }}
        .app-content {{
            display: none;
        }}
        .app-content.active {{
            display: block;
        }}

        /* Copy notification */
        .copy-toast {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: #00d9ff;
            color: #000;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 500;
            opacity: 0;
            transition: all 0.3s;
        }}
        .copy-toast.show {{
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }}

        /* Navigation buttons */
        .nav-buttons {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 30px;
        }}
        .nav-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 14px 24px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            text-decoration: none;
            transition: all 0.2s;
            cursor: pointer;
            border: none;
        }}
        .nav-btn-primary {{
            background: linear-gradient(135deg, #00d9ff, #0099ff);
            color: #000;
        }}
        .nav-btn-primary:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(0, 217, 255, 0.3);
        }}
        .nav-btn-outline {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
        }}
        .nav-btn-outline:hover {{
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.3);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-section">
                <div class="logo">🌐</div>
                <span class="brand-name">NoBorder VPN</span>
            </div>
            <div class="header-icons">
                <a href="https://t.me/VPN_NB_test_bot" class="header-icon" title="Открыть бота">✈️</a>
            </div>
        </div>

        <!-- User Card -->
        <div class="user-card">
            <div class="user-check">✓</div>
            <div class="user-info">
                <div class="user-name">{user_display}</div>
                <div class="user-expiry">{expiry_text}</div>
            </div>
            <div class="user-arrow">›</div>
        </div>

        <!-- Installation Section -->
        <div class="section-title">Установка</div>

        <!-- Platform Tabs -->
        <div class="platform-tabs">
            <button class="platform-tab active" onclick="switchPlatform('android')">📱 Android</button>
            <button class="platform-tab" onclick="switchPlatform('ios')">🍎 iPhone</button>
            <button class="platform-tab" onclick="switchPlatform('macos')">🍏 macOS</button>
            <button class="platform-tab" onclick="switchPlatform('windows')">🖥 Windows</button>
            <button class="platform-tab" onclick="switchPlatform('tv')">📺 TV</button>
        </div>

        <!-- Android Content -->
        <div id="android-content" class="platform-content active">
            <div class="app-tabs">
                <button class="app-tab active" onclick="switchApp('android', 'happ')">⭐ Happ</button>
                <button class="app-tab" onclick="switchApp('android', 'v2raytun')">V2RayTun</button>
            </div>

            <div id="android-happ" class="app-content active">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте Happ</div>
                        <div class="step-desc">Установите приложение из Google Play или скачайте APK напрямую.</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="https://play.google.com/store/apps/details?id=com.happproxy" class="btn btn-outline" target="_blank">📥 GOOGLE PLAY</a>
                            <a href="https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk" class="btn btn-outline" target="_blank">📦 APK</a>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже, чтобы добавить подписку</div>
                        <a href="{deep_link_happ}" class="btn btn-primary">Добавить подписку</a>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>

            <div id="android-v2raytun" class="app-content">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте V2RayTun</div>
                        <div class="step-desc">Установите приложение из Google Play или скачайте APK напрямую.</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="https://play.google.com/store/apps/details?id=com.v2raytun.android" class="btn btn-outline" target="_blank">📥 GOOGLE PLAY</a>
                            <a href="https://github.com/DigneZzZ/v2raytun/releases/download/3.12.46/v2RayTun_arm64-v8a.apk" class="btn btn-outline" target="_blank">📦 APK</a>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже, чтобы добавить подписку</div>
                        <a href="{deep_link_v2raytun}" class="btn btn-primary">Добавить подписку</a>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- iOS Content -->
        <div id="ios-content" class="platform-content">
            <div class="app-tabs">
                <button class="app-tab active" onclick="switchApp('ios', 'happ')">⭐ Happ</button>
                <button class="app-tab" onclick="switchApp('ios', 'v2raytun')">V2RayTun</button>
            </div>

            <div id="ios-happ" class="app-content active">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте Happ</div>
                        <div class="step-desc">Выберите версию для вашего региона:</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215" class="btn btn-outline" target="_blank">🌍 Global</a>
                            <a href="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973" class="btn btn-outline" target="_blank">🇷🇺 Россия</a>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже, чтобы добавить подписку</div>
                        <a href="{deep_link_happ}" class="btn btn-primary">Добавить подписку</a>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>

            <div id="ios-v2raytun" class="app-content">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте V2RayTun</div>
                        <div class="step-desc">Установите приложение из App Store</div>
                        <a href="https://apps.apple.com/app/v2raytun/id6476628951" class="btn btn-outline" target="_blank">📥 APP STORE</a>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже, чтобы добавить подписку</div>
                        <a href="{deep_link_v2raytun}" class="btn btn-primary">Добавить подписку</a>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- macOS Content -->
        <div id="macos-content" class="platform-content">
            <div class="app-tabs">
                <button class="app-tab active" onclick="switchApp('macos', 'happ')">⭐ Happ</button>
            </div>

            <div id="macos-happ" class="app-content active">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте Happ</div>
                        <div class="step-desc">Выберите версию для вашего региона:</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215" class="btn btn-outline" target="_blank">🌍 Global</a>
                            <a href="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973" class="btn btn-outline" target="_blank">🇷🇺 Россия</a>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже или скопируйте ссылку вручную</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="{deep_link_happ}" class="btn btn-primary">Добавить подписку</a>
                            <button class="btn btn-outline" onclick="copyUrl()">📋 Скопировать</button>
                        </div>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Windows Content -->
        <div id="windows-content" class="platform-content">
            <div class="app-tabs">
                <button class="app-tab active" onclick="switchApp('windows', 'happ')">⭐ Happ</button>
                <button class="app-tab" onclick="switchApp('windows', 'v2raytun')">V2RayTun</button>
            </div>

            <div id="windows-happ" class="app-content active">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте Happ</div>
                        <div class="step-desc">Нажмите на кнопку ниже и установите приложение.</div>
                        <a href="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe" class="btn btn-outline" target="_blank">📥 WINDOWS</a>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже или скопируйте ссылку вручную</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="{deep_link_happ}" class="btn btn-primary">Добавить подписку</a>
                            <button class="btn btn-outline" onclick="copyUrl()">📋 Скопировать</button>
                        </div>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>

            <div id="windows-v2raytun" class="app-content">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте V2RayTun</div>
                        <div class="step-desc">Нажмите на кнопку ниже и установите приложение.</div>
                        <a href="/static/v2raytun_setup.exe" class="btn btn-outline" target="_blank">📥 WINDOWS</a>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Добавить подписку</div>
                        <div class="step-desc">Нажмите кнопку ниже или скопируйте ссылку вручную</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="{deep_link_v2raytun}" class="btn btn-primary">Добавить подписку</a>
                            <button class="btn btn-outline" onclick="copyUrl()">📋 Скопировать</button>
                        </div>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Откройте приложение и подключитесь к серверу</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TV Content -->
        <div id="tv-content" class="platform-content">
            <div class="app-tabs">
                <button class="app-tab active" onclick="switchApp('tv', 'androidtv')">🤖 Android TV</button>
                <button class="app-tab" onclick="switchApp('tv', 'appletv')">🍎 Apple TV</button>
            </div>

            <div id="tv-androidtv" class="app-content active">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте Happ для Android TV</div>
                        <div class="step-desc">Установите приложение из Google Play</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="https://play.google.com/store/apps/details?id=com.happproxy" class="btn btn-outline" target="_blank">📥 GOOGLE PLAY</a>
                            <a href="https://www.happ.su/main/ru/faq/android-tv" class="btn btn-outline" target="_blank">📖 Инструкция</a>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Ссылка на подписку</div>
                        <div class="step-desc">Скопируйте ссылку для добавления в приложение</div>
                        <button class="btn btn-primary" onclick="copyUrl()">📋 Скопировать ссылку</button>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Следуйте инструкции и подключитесь к серверу</div>
                    </div>
                </div>
            </div>

            <div id="tv-appletv" class="app-content">
                <div class="steps">
                    <div class="step">
                        <div class="step-icon">↓</div>
                        <div class="step-title">Скачайте Happ для Apple TV</div>
                        <div class="step-desc">Установите приложение из App Store</div>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274" class="btn btn-outline" target="_blank">📥 APP STORE</a>
                            <a href="https://www.happ.su/main/ru/faq/apple-tv-tvos" class="btn btn-outline" target="_blank">📖 Инструкция</a>
                        </div>
                    </div>
                    <div class="step">
                        <div class="step-icon">⊕</div>
                        <div class="step-title">Ссылка на подписку</div>
                        <div class="step-desc">Скопируйте ссылку для добавления в приложение</div>
                        <button class="btn btn-primary" onclick="copyUrl()">📋 Скопировать ссылку</button>
                    </div>
                    <div class="step completed">
                        <div class="step-icon">✓</div>
                        <div class="step-title">Подключите и используйте</div>
                        <div class="step-desc">Следуйте инструкции и подключитесь к серверу</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tips -->
        <div class="tips">
            <div class="tips-title">Если у вас не работает Интернет после подключения VPN:</div>
            1. Перейдите в настройки в боковой панели приложения<br>
            2. Перейдите в пункт "Дополнительные настройки"<br>
            - Установите галочку <code>Использовать локальный DNS</code><br>
            - Снимите галочку с <code>TUN</code> и включите <code>Системный прокси</code><br><br>
            Если не помогло, включите <code>TUN</code> и выключите <code>Системный прокси</code>
        </div>

        <!-- Navigation -->
        <div class="nav-buttons">
            <a href="/connect/{token}" class="nav-btn nav-btn-outline">
                <span>🏠</span> Главное меню
            </a>
        </div>
    </div>

    <!-- Copy Toast -->
    <div class="copy-toast" id="copyToast">✓ Ссылка скопирована!</div>

    <script>
        const subscriptionUrl = "{subscription_url}";

        function switchPlatform(platform) {{
            // Update tabs
            document.querySelectorAll('.platform-tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');

            // Update content
            document.querySelectorAll('.platform-content').forEach(content => content.classList.remove('active'));
            document.getElementById(platform + '-content').classList.add('active');
        }}

        function switchApp(platform, app) {{
            // Update tabs within platform
            const container = document.getElementById(platform + '-content');
            container.querySelectorAll('.app-tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');

            // Update app content
            container.querySelectorAll('.app-content').forEach(content => content.classList.remove('active'));
            document.getElementById(platform + '-' + app).classList.add('active');
        }}

        function copyUrl() {{
            navigator.clipboard.writeText(subscriptionUrl).then(() => {{
                const toast = document.getElementById('copyToast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
            }});
        }}
    </script>
</body>
</html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        log.error(f"[Deep Link] Error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=get_error_page("Ошибка", "Что-то пошло не так. Попробуйте ещё раз."),
            status_code=500
        )


# ==================== OUTLINE DEEP LINK ENDPOINT ====================

@app.get("/outline/{encoded_key}", response_class=HTMLResponse, tags=["Outline"])
async def outline_deeplink(encoded_key: str, request: Request, token: str = None):
    """
    Beautiful landing page for adding Outline key to VPN apps.
    Key is passed as base64 encoded string.
    Token is optional query parameter for navigation.
    """
    import base64
    import urllib.parse

    try:
        # Decode the key
        try:
            outline_key = base64.urlsafe_b64decode(encoded_key).decode('utf-8')
        except Exception:
            return HTMLResponse(content=get_error_page("Неверная ссылка", "Ссылка на ключ недействительна."), status_code=400)

        # Extract server name from key (after #)
        server_name = "Outline"
        if '#' in outline_key:
            server_name = urllib.parse.unquote(outline_key.split('#')[-1])

        # Create ssconf:// deep link for Outline
        # Format: ssconf://base64(ss://...)
        outline_key_encoded = urllib.parse.quote(outline_key, safe='')

        log.info(f"[Outline] Serving key page from {request.client.host}, token={'yes' if token else 'no'}")

        html_content = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🪐</text></svg>">
    <title>Outline VPN - NoBorder</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 500px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 0;
            margin-bottom: 20px;
        }}
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #00bfa5, #1de9b6);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}
        .brand-name {{
            font-size: 18px;
            font-weight: 600;
        }}
        .header-icons {{
            display: flex;
            gap: 10px;
        }}
        .header-icon {{
            width: 36px;
            height: 36px;
            background: rgba(255,255,255,0.1);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            text-decoration: none;
            color: #fff;
            transition: background 0.2s;
        }}
        .header-icon:hover {{
            background: rgba(255,255,255,0.2);
        }}

        /* Server Info */
        .server-info-card {{
            text-align: center;
            margin-bottom: 20px;
        }}
        .server-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #00bfa5, #1de9b6);
            color: #000;
            padding: 8px 20px;
            border-radius: 20px;
            font-size: 16px;
            font-weight: 600;
        }}

        /* Key Card */
        .key-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 30px;
        }}
        .key-title {{
            font-size: 14px;
            color: #888;
            margin-bottom: 10px;
        }}
        .key-value {{
            font-family: monospace;
            font-size: 12px;
            word-break: break-all;
            color: #00bfa5;
            background: rgba(0,191,165,0.1);
            padding: 12px;
            border-radius: 8px;
            cursor: pointer;
        }}

        /* Section Title */
        .section-title {{
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
        }}

        /* Platform Tabs */
        .platform-tabs {{
            display: flex;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 4px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }}
        .platform-tab {{
            flex: 1;
            padding: 12px 8px;
            border-radius: 10px;
            border: none;
            background: transparent;
            color: #888;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            min-width: 80px;
        }}
        .platform-tab.active {{
            background: rgba(255,255,255,0.1);
            color: #fff;
        }}
        .platform-tab:hover {{
            color: #fff;
        }}

        /* Platform Content */
        .platform-content {{
            display: none;
        }}
        .platform-content.active {{
            display: block;
        }}

        /* Steps */
        .steps {{
            position: relative;
            padding-left: 40px;
        }}
        .steps::before {{
            content: '';
            position: absolute;
            left: 12px;
            top: 30px;
            bottom: 30px;
            width: 2px;
            background: linear-gradient(180deg, #00bfa5 0%, #1de9b6 100%);
        }}
        .step {{
            position: relative;
            margin-bottom: 30px;
        }}
        .step:last-child {{
            margin-bottom: 0;
        }}
        .step-icon {{
            position: absolute;
            left: -40px;
            width: 26px;
            height: 26px;
            background: #0f0f1a;
            border: 2px solid #00bfa5;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: #00bfa5;
        }}
        .step.completed .step-icon {{
            background: #00bfa5;
            color: #000;
        }}
        .step-title {{
            font-weight: 600;
            font-size: 16px;
            margin-bottom: 6px;
        }}
        .step-desc {{
            font-size: 14px;
            color: #888;
            margin-bottom: 12px;
        }}

        /* Buttons */
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 14px 24px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
        }}
        .btn-outline {{
            background: transparent;
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
        }}
        .btn-outline:hover {{
            background: rgba(255,255,255,0.1);
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #00bfa5 0%, #1de9b6 100%);
            color: #000;
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 191, 165, 0.3);
        }}

        /* Copy notification */
        .copy-toast {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: #00bfa5;
            color: #000;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 500;
            opacity: 0;
            transition: all 0.3s;
        }}
        .copy-toast.show {{
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }}

        /* Navigation buttons */
        .nav-buttons {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 30px;
        }}
        .nav-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 14px 24px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            text-decoration: none;
            transition: all 0.2s;
            cursor: pointer;
            border: none;
        }}
        .nav-btn-primary {{
            background: linear-gradient(135deg, #00bfa5, #1de9b6);
            color: #000;
        }}
        .nav-btn-primary:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(0, 191, 165, 0.3);
        }}
        .nav-btn-outline {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
        }}
        .nav-btn-outline:hover {{
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.3);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-section">
                <div class="logo">🪐</div>
                <span class="brand-name">Outline VPN</span>
            </div>
            <div class="header-icons">
                <a href="https://t.me/VPN_NB_test_bot" class="header-icon" title="Открыть бота">✈️</a>
            </div>
        </div>

        <!-- Server Info -->
        <div class="server-info-card">
            <div class="server-badge">{server_name}</div>
        </div>

        <!-- Key Card -->
        <div class="key-card">
            <div class="key-title">🔑 Ваш ключ (нажмите чтобы скопировать)</div>
            <div class="key-value" onclick="copyKey()">{outline_key[:50]}...</div>
        </div>

        <!-- Installation Section -->
        <div class="section-title">Установка</div>

        <!-- Platform Tabs -->
        <div class="platform-tabs">
            <button class="platform-tab active" onclick="switchPlatform('android')">📱 Android</button>
            <button class="platform-tab" onclick="switchPlatform('ios')">🍎 iPhone</button>
            <button class="platform-tab" onclick="switchPlatform('windows')">🖥 Windows</button>
            <button class="platform-tab" onclick="switchPlatform('macos')">🍏 macOS</button>
            <button class="platform-tab" onclick="switchPlatform('linux')">🐧 Linux</button>
        </div>

        <!-- Android Content -->
        <div id="android-content" class="platform-content active">
            <div class="steps">
                <div class="step">
                    <div class="step-icon">↓</div>
                    <div class="step-title">Скачайте Outline</div>
                    <div class="step-desc">Установите приложение из Google Play</div>
                    <a href="https://play.google.com/store/apps/details?id=org.outline.android.client" class="btn btn-outline" target="_blank">📥 GOOGLE PLAY</a>
                </div>
                <div class="step">
                    <div class="step-icon">⊕</div>
                    <div class="step-title">Добавить ключ</div>
                    <div class="step-desc">Нажмите кнопку — ключ скопируется и откроется приложение</div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button class="btn btn-primary" onclick="addToOutline()">🔌 Добавить ключ</button>
                        <button class="btn btn-outline" onclick="copyKey()">📋 Скопировать</button>
                    </div>
                </div>
                <div class="step completed">
                    <div class="step-icon">✓</div>
                    <div class="step-title">Подключитесь</div>
                    <div class="step-desc">Если ключ не добавился — вставьте из буфера обмена</div>
                </div>
            </div>
        </div>

        <!-- iOS Content -->
        <div id="ios-content" class="platform-content">
            <div class="steps">
                <div class="step">
                    <div class="step-icon">↓</div>
                    <div class="step-title">Скачайте Outline</div>
                    <div class="step-desc">Установите приложение из App Store</div>
                    <a href="https://apps.apple.com/us/app/outline-app/id1356177741" class="btn btn-outline" target="_blank">📥 APP STORE</a>
                </div>
                <div class="step">
                    <div class="step-icon">⊕</div>
                    <div class="step-title">Добавить ключ</div>
                    <div class="step-desc">Нажмите кнопку — ключ скопируется и откроется приложение</div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button class="btn btn-primary" onclick="addToOutline()">🔌 Добавить ключ</button>
                        <button class="btn btn-outline" onclick="copyKey()">📋 Скопировать</button>
                    </div>
                </div>
                <div class="step completed">
                    <div class="step-icon">✓</div>
                    <div class="step-title">Подключитесь</div>
                    <div class="step-desc">Если ключ не добавился — вставьте из буфера обмена</div>
                </div>
            </div>
        </div>

        <!-- Windows Content -->
        <div id="windows-content" class="platform-content">
            <div class="steps">
                <div class="step">
                    <div class="step-icon">↓</div>
                    <div class="step-title">Скачайте Outline</div>
                    <div class="step-desc">Скачайте и установите приложение</div>
                    <a href="https://github.com/Jigsaw-Code/outline-apps/releases/latest" class="btn btn-outline" target="_blank">📥 СКАЧАТЬ</a>
                </div>
                <div class="step">
                    <div class="step-icon">⊕</div>
                    <div class="step-title">Добавить ключ</div>
                    <div class="step-desc">Нажмите кнопку — ключ скопируется и откроется приложение</div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button class="btn btn-primary" onclick="addToOutline()">🔌 Добавить ключ</button>
                        <button class="btn btn-outline" onclick="copyKey()">📋 Скопировать</button>
                    </div>
                </div>
                <div class="step completed">
                    <div class="step-icon">✓</div>
                    <div class="step-title">Подключитесь</div>
                    <div class="step-desc">Если ключ не добавился — вставьте из буфера обмена</div>
                </div>
            </div>
        </div>

        <!-- macOS Content -->
        <div id="macos-content" class="platform-content">
            <div class="steps">
                <div class="step">
                    <div class="step-icon">↓</div>
                    <div class="step-title">Скачайте Outline</div>
                    <div class="step-desc">Установите приложение из App Store</div>
                    <a href="https://apps.apple.com/us/app/outline-app/id1356178125" class="btn btn-outline" target="_blank">📥 APP STORE</a>
                </div>
                <div class="step">
                    <div class="step-icon">⊕</div>
                    <div class="step-title">Добавить ключ</div>
                    <div class="step-desc">Нажмите кнопку — ключ скопируется и откроется приложение</div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button class="btn btn-primary" onclick="addToOutline()">🔌 Добавить ключ</button>
                        <button class="btn btn-outline" onclick="copyKey()">📋 Скопировать</button>
                    </div>
                </div>
                <div class="step completed">
                    <div class="step-icon">✓</div>
                    <div class="step-title">Подключитесь</div>
                    <div class="step-desc">Если ключ не добавился — вставьте из буфера обмена</div>
                </div>
            </div>
        </div>

        <!-- Linux Content -->
        <div id="linux-content" class="platform-content">
            <div class="steps">
                <div class="step">
                    <div class="step-icon">↓</div>
                    <div class="step-title">Скачайте Outline</div>
                    <div class="step-desc">Скачайте AppImage для Linux</div>
                    <a href="https://github.com/Jigsaw-Code/outline-apps/releases/latest" class="btn btn-outline" target="_blank">📥 СКАЧАТЬ</a>
                </div>
                <div class="step">
                    <div class="step-icon">⊕</div>
                    <div class="step-title">Добавить ключ</div>
                    <div class="step-desc">Нажмите кнопку — ключ скопируется и откроется приложение</div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button class="btn btn-primary" onclick="addToOutline()">🔌 Добавить ключ</button>
                        <button class="btn btn-outline" onclick="copyKey()">📋 Скопировать</button>
                    </div>
                </div>
                <div class="step completed">
                    <div class="step-icon">✓</div>
                    <div class="step-title">Подключитесь</div>
                    <div class="step-desc">Если ключ не добавился — вставьте из буфера обмена</div>
                </div>
            </div>
        </div>

        <!-- Navigation buttons (only if token is present) -->
        {"" if not token else f'''
        <div class="nav-buttons">
            <a href="/outline-servers/{token}" class="nav-btn nav-btn-primary">
                <span>➕</span> Добавить ещё один ключ
            </a>
            <a href="/connect/{token}" class="nav-btn nav-btn-outline">
                <span>🏠</span> Главное меню
            </a>
        </div>
        '''}
    </div>

    <!-- Copy Toast -->
    <div class="copy-toast" id="copyToast">✓ Ключ скопирован!</div>

    <script>
        const outlineKey = "{outline_key}";

        function switchPlatform(platform) {{
            document.querySelectorAll('.platform-tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');
            document.querySelectorAll('.platform-content').forEach(content => content.classList.remove('active'));
            document.getElementById(platform + '-content').classList.add('active');
        }}

        function copyKey() {{
            navigator.clipboard.writeText(outlineKey).then(() => {{
                const toast = document.getElementById('copyToast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
            }});
        }}

        function addToOutline() {{
            // Сначала копируем ключ в буфер обмена
            navigator.clipboard.writeText(outlineKey).then(() => {{
                // Показываем уведомление
                const toast = document.getElementById('copyToast');
                toast.textContent = '✓ Ключ скопирован! Вставьте в Outline';
                toast.classList.add('show');

                // Открываем Outline через deep link
                setTimeout(() => {{
                    window.location.href = outlineKey;
                }}, 500);

                setTimeout(() => {{
                    toast.classList.remove('show');
                    toast.textContent = '✓ Ключ скопирован!';
                }}, 3000);
            }}).catch(() => {{
                // Если копирование не сработало, просто открываем
                window.location.href = outlineKey;
            }});
        }}
    </script>
</body>
</html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        log.error(f"[Outline] Error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=get_error_page("Ошибка", "Что-то пошло не так. Попробуйте ещё раз."),
            status_code=500
        )


# ==================== UNIFIED CONNECT PAGE ====================

@app.get("/connect/{token}", response_class=HTMLResponse, tags=["Subscription"])
async def connect_page(token: str, request: Request):
    """
    Unified landing page for choosing VPN protocol.
    User can select between VLESS/Shadowsocks (subscription) or Outline.
    """
    client_ip = request.client.host

    try:
        # Verify token first
        user_id = verify_subscription_token(token)
        if not user_id:
            record_failed_attempt(client_ip, reason="invalid_token")
            return HTMLResponse(content=get_error_page("Неверная ссылка", "Ссылка недействительна или истекла.<br>Получите новую ссылку в боте."), status_code=401)

        # Get user info
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            statement = select(Persons).filter(Persons.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()

        # Calculate subscription expiry
        expiry_text = "Неизвестно"
        if user and user.subscription:
            from datetime import datetime
            expiry_date = datetime.fromtimestamp(user.subscription)
            now = datetime.now()
            diff = expiry_date - now
            if diff.days > 30:
                months = diff.days // 30
                expiry_text = f"Истекает через {months} мес."
            elif diff.days > 0:
                expiry_text = f"Истекает через {diff.days} дн."
            elif diff.days == 0:
                expiry_text = "Истекает сегодня"
            else:
                expiry_text = "Подписка истекла"

        user_display = f"_{user.tgid}" if user else "Пользователь"

        log.info(f"[Connect] User {user_id} accessing connect page from {client_ip}")

        html_content = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌐</text></svg>">
    <title>NoBorder VPN - Выбор протокола</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 500px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 0;
            margin-bottom: 20px;
        }}
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #ff8c00, #ffb347);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}
        .brand-name {{
            font-size: 18px;
            font-weight: 600;
        }}

        /* User Card */
        .user-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 16px 20px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .user-check {{
            width: 24px;
            height: 24px;
            background: #00d9ff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #000;
            font-size: 14px;
        }}
        .user-info {{
            flex: 1;
        }}
        .user-name {{
            font-size: 14px;
            opacity: 0.8;
        }}
        .user-status {{
            font-size: 12px;
            opacity: 0.6;
        }}

        /* Title */
        .page-title {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .page-title h1 {{
            font-size: 24px;
            margin-bottom: 8px;
        }}
        .page-title p {{
            font-size: 14px;
            opacity: 0.7;
        }}

        /* Protocol Cards */
        .protocol-cards {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .protocol-card {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 24px;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            color: inherit;
            display: block;
        }}
        .protocol-card:hover {{
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.2);
            transform: translateY(-2px);
        }}
        .protocol-card.recommended {{
            border-color: #00d9ff;
            background: rgba(0, 217, 255, 0.1);
        }}
        .protocol-card.recommended:hover {{
            border-color: #00d9ff;
            background: rgba(0, 217, 255, 0.15);
        }}
        .card-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 12px;
        }}
        .card-icon {{
            width: 56px;
            height: 56px;
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
        }}
        .card-icon.vless {{
            background: linear-gradient(135deg, #00d9ff, #0099ff);
        }}
        .card-icon.outline {{
            background: linear-gradient(135deg, #00c853, #00e676);
        }}
        .card-title {{
            flex: 1;
        }}
        .card-title h3 {{
            font-size: 18px;
            margin-bottom: 4px;
        }}
        .card-title .badge {{
            display: inline-block;
            background: #00d9ff;
            color: #000;
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 10px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .card-description {{
            font-size: 13px;
            opacity: 0.7;
            line-height: 1.5;
            margin-bottom: 16px;
        }}
        .card-features {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .feature-tag {{
            background: rgba(255,255,255,0.1);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .feature-tag.highlight {{
            background: rgba(0, 217, 255, 0.2);
            color: #00d9ff;
        }}
        .arrow {{
            margin-left: auto;
            font-size: 20px;
            opacity: 0.5;
        }}

        /* Footer */
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            opacity: 0.5;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-section">
                <div class="logo">🌐</div>
                <span class="brand-name">NoBorder VPN</span>
            </div>
        </div>

        <!-- User Card -->
        <div class="user-card">
            <div class="user-check">✓</div>
            <div class="user-info">
                <div class="user-name">{user_display}</div>
                <div class="user-status">{expiry_text}</div>
            </div>
        </div>

        <!-- Title -->
        <div class="page-title">
            <h1>Выберите протокол</h1>
            <p>Выберите тип VPN подключения</p>
        </div>

        <!-- Protocol Cards -->
        <div class="protocol-cards">
            <!-- VLESS Card -->
            <a href="/add/{token}" class="protocol-card recommended">
                <div class="card-header">
                    <div class="card-icon vless">🔷</div>
                    <div class="card-title">
                        <h3>VLESS</h3>
                        <span class="badge">Рекомендуем</span>
                    </div>
                    <span class="arrow">→</span>
                </div>
                <div class="card-description">
                    Современный протокол с высокой скоростью и надёжностью.
                    Автоматическое обновление серверов через подписку.
                </div>
                <div class="card-features">
                    <span class="feature-tag highlight">🚀 Быстрый</span>
                    <span class="feature-tag">🔄 Авто-обновление</span>
                    <span class="feature-tag">🌍 Все серверы</span>
                </div>
            </a>

            <!-- Outline Card -->
            <a href="/outline-servers/{token}" class="protocol-card">
                <div class="card-header">
                    <div class="card-icon outline">🔐</div>
                    <div class="card-title">
                        <h3>Outline VPN</h3>
                    </div>
                    <span class="arrow">→</span>
                </div>
                <div class="card-description">
                    Простой и надёжный протокол от Google Jigsaw.
                    Легко настраивается, работает везде.
                </div>
                <div class="card-features">
                    <span class="feature-tag">📱 Простой</span>
                    <span class="feature-tag">🛡️ Надёжный</span>
                    <span class="feature-tag">🔑 По серверам</span>
                </div>
            </a>
        </div>

        <!-- Footer -->
        <div class="footer">
            NoBorder VPN © 2024
        </div>
    </div>
</body>
</html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        log.error(f"[Connect] Error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=get_error_page("Ошибка", "Что-то пошло не так. Попробуйте ещё раз."),
            status_code=500
        )


# ==================== OUTLINE SERVERS PAGE ====================

@app.get("/outline-servers/{token}", response_class=HTMLResponse, tags=["Outline"])
async def outline_servers_page(token: str, request: Request):
    """
    Page to select Outline server and get a key.
    Shows all available Outline servers (type_vpn=0).
    """
    client_ip = request.client.host

    try:
        # Verify token first
        user_id = verify_subscription_token(token)
        if not user_id:
            record_failed_attempt(client_ip, reason="invalid_token")
            return HTMLResponse(content=get_error_page("Неверная ссылка", "Ссылка недействительна или истекла.<br>Получите новую ссылку в боте."), status_code=401)

        # Get user info
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            statement = select(Persons).filter(Persons.id == user_id)
            result = await db.execute(statement)
            user = result.scalar_one_or_none()

            # Get all active Outline servers (type_vpn=0, work=True), sorted by name
            servers_statement = select(Servers).filter(Servers.type_vpn == 0, Servers.work == True).order_by(Servers.name)
            servers_result = await db.execute(servers_statement)
            outline_servers = servers_result.scalars().all()

        if not user:
            return HTMLResponse(content=get_error_page("Ошибка", "Пользователь не найден."), status_code=404)

        # Calculate subscription expiry
        expiry_text = "Неизвестно"
        if user.subscription:
            from datetime import datetime
            expiry_date = datetime.fromtimestamp(user.subscription)
            now = datetime.now()
            diff = expiry_date - now
            if diff.days > 30:
                months = diff.days // 30
                expiry_text = f"Истекает через {months} мес."
            elif diff.days > 0:
                expiry_text = f"Истекает через {diff.days} дн."
            elif diff.days == 0:
                expiry_text = "Истекает сегодня"
            else:
                expiry_text = "Подписка истекла"

        user_display = f"_{user.tgid}"
        telegram_id = user.tgid

        log.info(f"[Outline Servers] User {user_id} accessing page from {client_ip}, found {len(outline_servers)} servers")

        # Function to get country code for flag image
        def get_country_code(name):
            name_lower = name.lower()
            if 'russia' in name_lower or 'рос' in name_lower or 'moscow' in name_lower:
                return 'ru'
            elif 'kazakhstan' in name_lower or 'казах' in name_lower:
                return 'kz'
            elif 'spain' in name_lower or 'madrid' in name_lower or 'испан' in name_lower:
                return 'es'
            elif 'germany' in name_lower or 'frankfurt' in name_lower or 'герман' in name_lower:
                return 'de'
            elif 'netherlands' in name_lower or 'amsterdam' in name_lower or 'нидерланд' in name_lower:
                return 'nl'
            elif 'usa' in name_lower or 'united states' in name_lower or 'америк' in name_lower or 'сша' in name_lower:
                return 'us'
            elif 'uk' in name_lower or 'britain' in name_lower or 'london' in name_lower:
                return 'gb'
            elif 'france' in name_lower or 'paris' in name_lower or 'франц' in name_lower:
                return 'fr'
            elif 'turkey' in name_lower or 'турц' in name_lower:
                return 'tr'
            elif 'finland' in name_lower or 'финлянд' in name_lower:
                return 'fi'
            return None

        def get_flag_html(name):
            code = get_country_code(name)
            if code:
                return f'<img src="/static/flags/{code}.png" alt="{code}" class="flag-img">'
            return '🌐'

        # Build server cards HTML
        server_cards_html = ""
        for server in outline_servers:
            flag = get_flag_html(server.name)
            # Extract country name from server name (remove "Outline" suffix)
            country_name = server.name.replace('Outline', '').strip()
            server_cards_html += f"""
            <div class="server-card" data-server-id="{server.id}" data-server-name="{server.name}">
                <div class="server-info">
                    <div class="server-icon">{flag}</div>
                    <div class="server-details">
                        <div class="server-name">{country_name}</div>
                        <div class="server-location">Outline VPN</div>
                    </div>
                </div>
                <button class="get-key-btn" onclick="getOutlineKey({server.id}, '{server.name}')">
                    <span class="btn-text">Получить ключ</span>
                    <span class="btn-loading" style="display:none;">⏳</span>
                </button>
            </div>
            """

        if not outline_servers:
            server_cards_html = """
            <div class="no-servers">
                <p>😔 Outline серверы временно недоступны</p>
            </div>
            """

        html_content = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔐</text></svg>">
    <title>NoBorder VPN - Outline серверы</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 500px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 0;
            margin-bottom: 20px;
        }}
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #00c853, #00e676);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}
        .brand-name {{
            font-size: 18px;
            font-weight: 600;
        }}
        .back-btn {{
            background: rgba(255,255,255,0.1);
            border: none;
            color: #fff;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            transition: background 0.2s;
        }}
        .back-btn:hover {{
            background: rgba(255,255,255,0.2);
        }}

        /* User Card */
        .user-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 16px 20px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .user-check {{
            width: 24px;
            height: 24px;
            background: #00c853;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #000;
            font-size: 14px;
        }}
        .user-info {{
            flex: 1;
        }}
        .user-name {{
            font-size: 14px;
            opacity: 0.8;
        }}
        .user-status {{
            font-size: 12px;
            opacity: 0.6;
        }}

        /* Title */
        .page-title {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .page-title h1 {{
            font-size: 24px;
            margin-bottom: 8px;
        }}
        .page-title p {{
            font-size: 14px;
            opacity: 0.7;
        }}

        /* Server Cards */
        .server-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .server-card {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: all 0.2s;
        }}
        .server-card:hover {{
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.2);
        }}
        .server-info {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .server-icon {{
            width: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
        }}
        .flag-img {{
            width: 40px;
            height: auto;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }}
        .server-details {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .server-name {{
            font-size: 16px;
            font-weight: 500;
        }}
        .server-location {{
            font-size: 12px;
            opacity: 0.5;
        }}
        .get-key-btn {{
            background: linear-gradient(135deg, #00c853, #00e676);
            border: none;
            color: #000;
            padding: 10px 20px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
            min-width: 130px;
        }}
        .get-key-btn:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(0, 200, 83, 0.3);
        }}
        .get-key-btn:disabled {{
            opacity: 0.7;
            cursor: not-allowed;
            transform: none;
        }}

        .no-servers {{
            text-align: center;
            padding: 40px;
            opacity: 0.7;
        }}

        /* Navigation buttons */
        .nav-buttons {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 30px;
        }}
        .nav-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 14px 24px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            text-decoration: none;
            transition: all 0.2s;
            cursor: pointer;
            border: none;
        }}
        .nav-btn-primary {{
            background: linear-gradient(135deg, #00c853, #00e676);
            color: #000;
        }}
        .nav-btn-primary:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(0, 200, 83, 0.3);
        }}
        .nav-btn-outline {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
        }}
        .nav-btn-outline:hover {{
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.3);
        }}

        /* Toast */
        .toast {{
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: rgba(0, 200, 83, 0.9);
            color: #fff;
            padding: 12px 24px;
            border-radius: 12px;
            font-size: 14px;
            transition: transform 0.3s ease;
            z-index: 1000;
        }}
        .toast.error {{
            background: rgba(255, 82, 82, 0.9);
        }}
        .toast.show {{
            transform: translateX(-50%) translateY(0);
        }}

        /* Footer */
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            opacity: 0.5;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-section">
                <div class="logo">🔐</div>
                <span class="brand-name">Outline VPN</span>
            </div>
            <a href="/connect/{token}" class="back-btn">← Назад</a>
        </div>

        <!-- User Card -->
        <div class="user-card">
            <div class="user-check">✓</div>
            <div class="user-info">
                <div class="user-name">{user_display}</div>
                <div class="user-status">{expiry_text}</div>
            </div>
        </div>

        <!-- Title -->
        <div class="page-title">
            <h1>Выберите сервер</h1>
            <p>Нажмите "Получить ключ" для выбранного сервера</p>
        </div>

        <!-- Server List -->
        <div class="server-list">
            {server_cards_html}
        </div>

        <!-- Navigation -->
        <div class="nav-buttons">
            <a href="/connect/{token}" class="nav-btn nav-btn-outline">
                <span>🏠</span> Главное меню
            </a>
        </div>

        <!-- Footer -->
        <div class="footer">
            NoBorder VPN © 2024
        </div>
    </div>

    <!-- Toast -->
    <div class="toast" id="toast"></div>

    <script>
        const token = "{token}";
        const telegramId = "{telegram_id}";

        function showToast(message, isError = false) {{
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = isError ? 'toast error show' : 'toast show';
            setTimeout(() => toast.classList.remove('show'), 3000);
        }}

        async function getOutlineKey(serverId, serverName) {{
            const btn = event.target.closest('.get-key-btn');
            const btnText = btn.querySelector('.btn-text');
            const btnLoading = btn.querySelector('.btn-loading');

            // Show loading state
            btn.disabled = true;
            btnText.style.display = 'none';
            btnLoading.style.display = 'inline';

            try {{
                const response = await fetch('/api/outline/create-key', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        token: token,
                        server_id: serverId
                    }})
                }});

                const data = await response.json();

                if (response.ok && data.success) {{
                    showToast('✓ Ключ создан! Переход...');
                    setTimeout(() => {{
                        window.location.href = data.redirect_url;
                    }}, 1000);
                }} else {{
                    showToast(data.error || 'Ошибка создания ключа', true);
                    btn.disabled = false;
                    btnText.style.display = 'inline';
                    btnLoading.style.display = 'none';
                }}
            }} catch (error) {{
                showToast('Ошибка сети. Попробуйте ещё раз.', true);
                btn.disabled = false;
                btnText.style.display = 'inline';
                btnLoading.style.display = 'none';
            }}
        }}
    </script>
</body>
</html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        log.error(f"[Outline Servers] Error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=get_error_page("Ошибка", "Что-то пошло не так. Попробуйте ещё раз."),
            status_code=500
        )


# ==================== OUTLINE API ENDPOINTS ====================

@app.post("/api/outline/create-key", tags=["Outline API"])
async def create_outline_key(request: Request):
    """
    API endpoint to create Outline key for a user on selected server.
    Returns redirect URL to outline page with the key.
    """
    client_ip = request.client.host

    try:
        data = await request.json()
        token = data.get('token')
        server_id = data.get('server_id')

        if not token or not server_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Требуется token и server_id"}
            )

        # Verify token
        user_id = verify_subscription_token(token)
        if not user_id:
            record_failed_attempt(client_ip, reason="invalid_token")
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Недействительный токен"}
            )

        # Get user and server
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            # Get user
            user_stmt = select(Persons).filter(Persons.id == user_id)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()

            if not user:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "Пользователь не найден"}
                )

            # Get server
            server_stmt = select(Servers).filter(Servers.id == server_id, Servers.type_vpn == 0)
            server_result = await db.execute(server_stmt)
            server = server_result.scalar_one_or_none()

            if not server:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "Сервер не найден"}
                )

        # Create Outline key
        from bot.misc.VPN.Outline import Outline
        outline = Outline(server)
        await outline.login()

        # Get or create key for user
        outline_key = await outline.get_key_user(str(user.tgid), server.name)

        if not outline_key:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Не удалось создать ключ"}
            )

        log.info(f"[Outline API] Created key for user {user.tgid} on server {server.name}")

        # Encode key for URL
        import base64
        encoded_key = base64.urlsafe_b64encode(outline_key.encode()).decode()

        return JSONResponse(content={
            "success": True,
            "redirect_url": f"/outline/{encoded_key}?token={token}"
        })

    except Exception as e:
        log.error(f"[Outline API] Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Внутренняя ошибка сервера"}
        )


# ==================== ERROR HANDLERS ====================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "path": str(request.url.path)}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Handle 500 errors"""
    log.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn

    log.info("Starting Subscription API server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
