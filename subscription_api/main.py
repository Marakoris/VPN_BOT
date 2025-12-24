"""
Subscription API - main application

This FastAPI application provides subscription endpoints for VPN clients.
"""
import sys
import os
import logging
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse

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
    security_manager
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="VPN Subscription API",
    description="Subscription-based VPN access API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


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

            # 5. Check which servers have keys for this user
            user_servers = []
            for server in all_servers:
                try:
                    server_manager = ServerManager(server)
                    await server_manager.login()
                    existing_client = await server_manager.get_user(user.tgid)

                    if existing_client:
                        user_servers.append(server)
                except Exception as e:
                    log.debug(f"[Subscription API] Error checking server {server.id}: {e}")
                    continue

            if not user_servers:
                log.warning(f"[Subscription API] No keys found for user {user.tgid}")
                return ""

            # 6. Generate actual VPN configurations
            config_lines = []

            for server in user_servers:
                try:
                    # Generate config URL for this server
                    config_url = await generate_config(server, user.tgid)

                    if config_url:
                        config_lines.append(config_url)
                    else:
                        log.warning(f"[Subscription API] Failed to generate config for server {server.id}")

                except Exception as e:
                    log.error(f"[Subscription API] Error generating config for server {server.id}: {e}")
                    continue

            # 7. Log access
            await log_subscription_access(
                user_id=user.id,
                ip_address=request.client.host,
                user_agent=request.headers.get("user-agent", "unknown"),
                servers_count=len(user_servers)
            )

            log.info(
                f"[Subscription API] ✅ Served subscription for user {user.tgid}: "
                f"{len(user_servers)} servers from {request.client.host}"
            )

            # Prepare response with custom headers for subscription title
            content = "\n".join(config_lines)

            # Add headers for readable subscription name in VPN clients
            headers = {
                "content-disposition": 'attachment; filename="NoBorder VPN.txt"',
                "profile-title": "NoBorder VPN",
                "subscription-userinfo": f"upload=0; download=0; expire={int(user.subscription)}"
            }

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


# ==================== DEEP LINK ENDPOINT ====================

@app.get("/add/{token}", response_class=HTMLResponse, tags=["Subscription"])
async def add_subscription_deeplink(token: str, request: Request):
    """
    Deep link redirect for Happ app

    Opens Happ app and adds subscription automatically.
    Similar to https://add.aliusvpn.ru/ios?id=...&link=happ://add/?

    Args:
        token: Subscription token

    Returns:
        HTML page with automatic redirect to happ://add/?{subscription_url}
    """
    client_ip = request.client.host

    try:
        # Verify token first
        user_id = verify_subscription_token(token)
        if not user_id:
            record_failed_attempt(client_ip, reason="invalid_token")
            return HTMLResponse(
                content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Invalid Token</title>
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                               display: flex; justify-content: center; align-items: center;
                               height: 100vh; margin: 0; background: #1a1a2e; color: #fff; }
                        .container { text-align: center; padding: 20px; }
                        h1 { color: #ff6b6b; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Invalid Token</h1>
                        <p>The subscription link is invalid or expired.</p>
                        <p>Please get a new link from the bot.</p>
                    </div>
                </body>
                </html>
                """,
                status_code=401
            )

        # Build subscription URL
        subscription_url = f"http://185.58.204.196:8003/sub/{token}"

        # Build deep link for Happ
        deep_link = f"happ://add/?{subscription_url}"

        log.info(f"[Deep Link] User {user_id} accessing add link from {client_ip}")

        # Return HTML with automatic redirect
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>NoBorder VPN - Add Subscription</title>
            <meta http-equiv="refresh" content="1;url={deep_link}">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    color: #fff;
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    padding: 20px;
                }}
                .container {{
                    text-align: center;
                    max-width: 400px;
                    background: rgba(255,255,255,0.1);
                    border-radius: 20px;
                    padding: 40px 30px;
                    backdrop-filter: blur(10px);
                }}
                .logo {{ font-size: 48px; margin-bottom: 20px; }}
                h1 {{
                    font-size: 24px;
                    margin-bottom: 15px;
                    color: #4ade80;
                }}
                p {{
                    color: #94a3b8;
                    margin-bottom: 20px;
                    line-height: 1.6;
                }}
                .spinner {{
                    width: 40px;
                    height: 40px;
                    border: 3px solid rgba(255,255,255,0.1);
                    border-top-color: #4ade80;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    to {{ transform: rotate(360deg); }}
                }}
                .btn {{
                    display: inline-block;
                    background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
                    color: #000;
                    padding: 15px 30px;
                    border-radius: 12px;
                    text-decoration: none;
                    font-weight: 600;
                    margin-top: 20px;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px rgba(74, 222, 128, 0.3);
                }}
                .manual {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid rgba(255,255,255,0.1);
                }}
                .manual p {{ font-size: 14px; }}
                .copy-box {{
                    background: rgba(0,0,0,0.3);
                    border-radius: 8px;
                    padding: 12px;
                    margin: 10px 0;
                    word-break: break-all;
                    font-family: monospace;
                    font-size: 12px;
                    color: #94a3b8;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">🌐</div>
                <h1>Opening Happ...</h1>
                <div class="spinner"></div>
                <p>The app should open automatically.<br>If it doesn't, click the button below.</p>

                <a href="{deep_link}" class="btn">Open in Happ</a>

                <div class="manual">
                    <p>Don't have Happ installed?</p>
                    <p><a href="https://play.google.com/store/apps/details?id=com.happproxy" style="color: #4ade80;">Download for Android</a></p>
                    <p><a href="https://apps.apple.com/app/happ-proxy-utility/id6504287215" style="color: #4ade80;">Download for iPhone</a></p>

                    <p style="margin-top: 20px;">Or copy subscription URL:</p>
                    <div class="copy-box">{subscription_url}</div>
                </div>
            </div>

            <script>
                // Try to open deep link immediately
                window.location.href = "{deep_link}";
            </script>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        log.error(f"[Deep Link] Error: {e}")
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Error</title>
                <style>
                    body { font-family: -apple-system, sans-serif;
                           display: flex; justify-content: center; align-items: center;
                           height: 100vh; margin: 0; background: #1a1a2e; color: #fff; }
                    .container { text-align: center; }
                    h1 { color: #ff6b6b; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Error</h1>
                    <p>Something went wrong. Please try again.</p>
                </div>
            </body>
            </html>
            """,
            status_code=500
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
