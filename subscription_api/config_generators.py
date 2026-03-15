"""
Configuration Generators for Subscription API

This module generates VPN configuration URLs for VLESS and Shadowsocks protocols.
Configurations are compatible with V2RayNG, Shadowrocket, and other clients.
"""
import json
import logging
import re
from typing import Optional, Dict
from urllib.parse import quote
import aiohttp

from bot.misc.VPN.ServerManager import ServerManager

log = logging.getLogger(__name__)


# ==================== RELAXED JSON PARSER FOR x-ui 2.4.0+ ====================

def relaxed_to_json(s: str) -> str:
    """Convert x-ui 2.4.0+ relaxed JSON to standard JSON.

    x-ui 2.4.0+ stores settings in relaxed JSON format without quotes around keys:
    {clients: [{email: test, enable: true}]}

    This converts it to standard JSON:
    {"clients": [{"email": "test", "enable": true}]}
    """
    # Add quotes around unquoted keys
    s = re.sub(r'(?<=[{\[,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', s)
    # Handle special value 'none' -> null
    s = re.sub(r':\s*none\s*([,}\]])', r': null\1', s)
    # Handle empty values (key: ,) -> "key": ""
    s = re.sub(r':\s*,', r': "",', s)
    s = re.sub(r':\s*\}', r': ""}', s)
    s = re.sub(r':\s*\]', r': ""]', s)
    # Add quotes to unquoted string values (careful with true/false/null/numbers)
    def quote_string_values(match):
        key, val, end = match.groups()
        if val in ('true', 'false', 'null') or val.replace('-','').replace('.','').isdigit():
            return f'{key}: {val}{end}'
        return f'{key}: "{val}"{end}'
    s = re.sub(r'("[\w]+"):\s*([a-zA-Z0-9_\-\.]+)\s*([,}\]])', quote_string_values, s)
    return s


def safe_json_loads(s: str) -> dict:
    """Parse JSON with fallback to relaxed JSON for x-ui 2.4.0+ compatibility"""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Try relaxed JSON conversion
        fixed = relaxed_to_json(s)
        return json.loads(fixed)


# ==================== HTTP FALLBACK FOR 3x-ui ====================

async def generate_vless_config_http(server, telegram_id: int, server_name: str = None):
    """HTTP fallback for 3x-ui panels that dont work with pyxui"""
    import json as json_mod
    try:
        ip_port = server.ip.split("/")[0]
        base_url = f"http://{ip_port}"
        inbound_id = getattr(server, "inbound_id", 1)
        
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            async with session.post(f"{base_url}/login", data={"username": server.login, "password": server.password}) as resp:
                login_data = await resp.json()
                if not login_data.get("success"):
                    return None
            
            async with session.get(f"{base_url}/panel/api/inbounds/list") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("success"):
                    return None
                
                inbound = None
                for ib in data.get("obj", []):
                    if ib.get("id") == inbound_id:
                        inbound = ib
                        break
                if not inbound:
                    return None
                
                settings = safe_json_loads(inbound.get("settings", "{}"))
                stream_settings = safe_json_loads(inbound.get("streamSettings", "{}"))
                
                client = None
                tgid_str = str(telegram_id)
                for c in settings.get("clients", []):
                    if c.get("email", "").startswith(tgid_str):
                        client = c
                        break
                if not client:
                    return None
                
                reality_settings = stream_settings.get("realitySettings", {})
                settings_data = reality_settings.get("settings", {})
                fp = settings_data.get("fingerprint") or reality_settings.get("fingerprint", "chrome")
                pbk = settings_data.get("publicKey") or reality_settings.get("publicKey", "")
                sni = (reality_settings.get("serverNames", []) or [""])[0]
                sid = (reality_settings.get("shortIds", []) or [""])[0]
                
                uuid = client.get("id")
                host = server.ip.split(":")[0]
                port = inbound.get("port")
                flow = client.get("flow", "")
                remark = quote(server_name or server.name)
                
                url = f"vless://{uuid}@{host}:{port}?type=tcp&security=reality&"
                if flow:
                    url += f"flow={flow}&"
                url += f"fp={fp}&pbk={pbk}&sni={sni}&sid={sid}&spx=%2F#{remark}"
                return url
    except:
        return None



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
            log.warning(f"[VLESS Generator] Client not found via pyxui for user {telegram_id}, trying HTTP fallback")
            # Try HTTP fallback for x-ui 2.4.0+ which has relaxed JSON format
            http_result = await generate_vless_config_http(server, telegram_id, server_name)
            if http_result:
                log.info(f"[VLESS Generator] ✅ HTTP fallback succeeded for {server.name}")
                return http_result
            log.error(f"[VLESS Generator] HTTP fallback also failed for user {telegram_id}")
            return None

        # Get inbound info (stream settings)
        inbound_info = await server_manager.client.get_inbound_server()
        if not inbound_info:
            log.error(f"[VLESS Generator] Failed to get inbound info")
            return None

        # Parse stream settings (use safe_json_loads for x-ui 2.4.0+ relaxed JSON)
        stream_settings = safe_json_loads(inbound_info['streamSettings'])

        # Extract Reality settings
        reality_settings = stream_settings.get("realitySettings", {})
        settings_data = reality_settings.get("settings", {})

        # Check both locations for fingerprint and publicKey (different x-ui versions)
        # Old format: realitySettings.settings.publicKey
        # New format: realitySettings.publicKey
        fingerprint = settings_data.get("fingerprint") or reality_settings.get("fingerprint", "chrome")
        public_key = settings_data.get("publicKey") or reality_settings.get("publicKey", "")
        # Fix for bypass servers which do not store publicKey in panel
        # node-ru-2: Bypass server with maps.yandex.ru SNI
        if "158.160.108.166" in server.ip and not public_key:
            public_key = "HSqvhRega6eWr3WtfWUZskn4rVF5g4d_MoAJCCSw83o"
        # node-ru-4: Bypass server with maps.yandex.ru SNI
        elif "178.154.207.0" in server.ip and not public_key:
            public_key = "E6MPRwSW5xVzROOmUVPIXPmRis42UH-xidxaOlH4ygU"
        # Legacy bypass server
        elif "84.201.128.231" in server.ip and not public_key:
            public_key = "yMmi7MkhSSv4DW2PXJm3pS4RpmLFM8vSt3ZhesZDKz0"
        # Additional bypass servers from production
        elif "158.160.102.5" in server.ip and not public_key:
            public_key = "HSqvhRega6eWr3WtfWUZskn4rVF5g4d_MoAJCCSw83o"
        elif "158.160.51.15" in server.ip and not public_key:
            public_key = "E6MPRwSW5xVzROOmUVPIXPmRis42UH-xidxaOlH4ygU"
        elif "158.160.112.119" in server.ip and not public_key:
            public_key = "80RLQsdpGiR9OYBfdBoZd5njLDAP3zh5ikwLaI2VaUc"
        server_names = reality_settings.get("serverNames", [])
        short_ids = reality_settings.get("shortIds", [])

        # Build configuration URL
        uuid = client.get('id') or client.get('uuid')

        # Extract clean IP (remove port if present in server.ip)
        host = server.ip.split(':')[0] if ':' in server.ip else server.ip
        port = inbound_info['port']
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "reality")
        sni = server_names[0] if server_names else ""
        sid = short_ids[0] if short_ids else ""
        flow = client.get('flow', '')  # Получаем flow из клиента

        # Generate remark (server display name)
        if not server_name:
            server_name = server.name

        remark = quote(server_name)

        # Build VLESS URL с flow (если есть)
        vless_url_parts = [
            f"vless://{uuid}@{host}:{port}?",
            f"type={network}&",
            f"security={security}&",
        ]

        # Добавляем flow только если он установлен
        if flow:
            vless_url_parts.append(f"flow={flow}&")
            log.debug(f"[VLESS Generator] Adding flow: {flow}")

        vless_url_parts.extend([
            f"fp={fingerprint}&",
            f"pbk={public_key}&",
            f"sni={sni}&",
            f"sid={sid}&",
            f"spx=%2F",
            f"#{remark}"
        ])

        vless_url = ''.join(vless_url_parts)

        log.info(f"[VLESS Generator] ✅ Generated config for {server_name}")
        return vless_url

    except Exception as e:
        log.error(f"[VLESS Generator] Error generating config with pyxui: {e}, trying HTTP fallback")
        try:
            http_result = await generate_vless_config_http(server, telegram_id, server_name)
            if http_result:
                log.info(f"[VLESS Generator] ✅ HTTP fallback succeeded for {server.name}")
                return http_result
        except Exception as http_err:
            log.error(f"[VLESS Generator] HTTP fallback also failed: {http_err}")
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
        # Extract clean IP (remove port if present in server.ip)
        host = server.ip.split(':')[0] if ':' in server.ip else server.ip
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
