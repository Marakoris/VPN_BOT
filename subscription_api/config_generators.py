"""
Configuration Generators for Subscription API

This module generates VPN configuration URLs for VLESS and Shadowsocks protocols.
Configurations are compatible with V2RayNG, Shadowrocket, and other clients.
"""
import json
import logging
from typing import Optional, Dict
from urllib.parse import quote

from bot.misc.VPN.ServerManager import ServerManager

log = logging.getLogger(__name__)


# ==================== VLESS CONFIG GENERATOR ====================

async def generate_vless_config(
    server,
    telegram_id: int,
    server_name: str = None
) -> Optional[str]:
    """
    Generate VLESS configuration URL

    Format:
    vless://{uuid}@{host}:{port}?type={network}&security={security}&fp={fingerprint}&
    pbk={publicKey}&sni={serverName}&sid={shortId}&spx=%2F#{remark}

    Args:
        server: Server object from database
        telegram_id: User's telegram ID
        server_name: Optional custom name for the server

    Returns:
        VLESS configuration URL or None if error
    """
    try:
        log.debug(f"[VLESS Generator] Generating config for user {telegram_id} on server {server.id}")

        # Get server manager and login
        server_manager = ServerManager(server)
        await server_manager.login()

        # Get client info
        client = await server_manager.get_user(telegram_id)
        if not client or client == 'User not found':
            log.error(f"[VLESS Generator] Client not found for user {telegram_id}")
            return None

        # Get inbound info (stream settings)
        inbound_info = await server_manager.client.get_inbound_server()
        if not inbound_info:
            log.error(f"[VLESS Generator] Failed to get inbound info")
            return None

        # Parse stream settings
        stream_settings = json.loads(inbound_info['streamSettings'])

        # Extract Reality settings
        reality_settings = stream_settings.get("realitySettings", {})
        settings_data = reality_settings.get("settings", {})

        fingerprint = settings_data.get("fingerprint", "chrome")
        public_key = settings_data.get("publicKey", "")
        server_names = reality_settings.get("serverNames", [])
        short_ids = reality_settings.get("shortIds", [])

        # Build configuration URL
        uuid = client.get('id') or client.get('uuid')
        host = server.ip
        port = inbound_info['port']
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "reality")
        sni = server_names[0] if server_names else ""
        sid = short_ids[0] if short_ids else ""

        # Generate remark (server display name)
        if not server_name:
            server_name = server.name

        remark = quote(server_name)

        # Build VLESS URL
        vless_url = (
            f"vless://{uuid}@{host}:{port}?"
            f"type={network}&"
            f"security={security}&"
            f"fp={fingerprint}&"
            f"pbk={public_key}&"
            f"sni={sni}&"
            f"sid={sid}&"
            f"spx=%2F"
            f"#{remark}"
        )

        log.info(f"[VLESS Generator] ✅ Generated config for {server_name}")
        return vless_url

    except Exception as e:
        log.error(f"[VLESS Generator] Error generating config: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==================== SHADOWSOCKS CONFIG GENERATOR ====================

async def generate_shadowsocks_config(
    server,
    telegram_id: int,
    server_name: str = None
) -> Optional[str]:
    """
    Generate Shadowsocks configuration URL

    Format:
    ss://{base64(method:server_password:user_password)}@{host}:{port}?type={network}#{remark}

    Args:
        server: Server object from database
        telegram_id: User's telegram ID
        server_name: Optional custom name for the server

    Returns:
        Shadowsocks configuration URL or None if error
    """
    try:
        log.debug(f"[SS Generator] Generating config for user {telegram_id} on server {server.id}")

        # Get server manager and login
        server_manager = ServerManager(server)
        await server_manager.login()

        # Get client info (with _ss suffix for Shadowsocks)
        client = await server_manager.get_user(telegram_id)
        if not client or client == 'User not found' or not isinstance(client, dict):
            log.error(f"[SS Generator] Client not found for user {telegram_id}")
            return None

        # Get inbound info
        inbound_info = await server_manager.client.get_inbound_server()
        if not inbound_info:
            log.error(f"[SS Generator] Failed to get inbound info")
            return None

        # Parse settings
        stream_settings = json.loads(inbound_info['streamSettings'])
        settings = json.loads(inbound_info['settings'])

        # Extract Shadowsocks parameters
        method = settings.get("method", "")
        server_password = settings.get("password", "")
        user_password = client.get("password", "")

        if not user_password:
            log.error(f"[SS Generator] User password not found")
            return None

        # Build configuration
        host = server.ip
        port = inbound_info['port']
        network = stream_settings.get("network", "tcp")

        # Generate remark (server display name)
        if not server_name:
            server_name = server.name

        remark = quote(server_name)

        # Build credentials string
        credentials = f"{method}:{server_password}:{user_password}"

        # Base64 encode credentials
        import base64
        credentials_b64 = base64.b64encode(credentials.encode()).decode()

        # Build Shadowsocks URL
        ss_url = (
            f"ss://{credentials_b64}@{host}:{port}?"
            f"type={network}#"
            f"{remark}"
        )

        log.info(f"[SS Generator] ✅ Generated config for {server_name}")
        return ss_url

    except Exception as e:
        log.error(f"[SS Generator] Error generating config: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==================== UNIFIED GENERATOR ====================

async def generate_config(
    server,
    telegram_id: int,
    server_name: str = None
) -> Optional[str]:
    """
    Generate VPN configuration for any protocol

    Automatically detects protocol type and calls appropriate generator.

    Args:
        server: Server object from database
        telegram_id: User's telegram ID
        server_name: Optional custom name for the server

    Returns:
        Configuration URL or None if error
    """
    try:
        # Detect VPN type
        vpn_type = server.type_vpn

        if vpn_type == 1:  # VLESS
            return await generate_vless_config(server, telegram_id, server_name)
        elif vpn_type == 2:  # Shadowsocks
            return await generate_shadowsocks_config(server, telegram_id, server_name)
        elif vpn_type == 0:  # Outline (not supported in subscription yet)
            log.warning(f"[Config Generator] Outline not supported in subscription")
            return None
        else:
            log.error(f"[Config Generator] Unknown VPN type: {vpn_type}")
            return None

    except Exception as e:
        log.error(f"[Config Generator] Error: {e}")
        return None


# ==================== BATCH GENERATOR ====================

async def generate_configs_batch(
    servers: list,
    telegram_id: int
) -> Dict[int, Optional[str]]:
    """
    Generate configurations for multiple servers

    Args:
        servers: List of server objects
        telegram_id: User's telegram ID

    Returns:
        Dictionary mapping server_id to configuration URL
    """
    results = {}

    for server in servers:
        try:
            config = await generate_config(server, telegram_id)
            results[server.id] = config
        except Exception as e:
            log.error(f"[Batch Generator] Error for server {server.id}: {e}")
            results[server.id] = None

    return results
