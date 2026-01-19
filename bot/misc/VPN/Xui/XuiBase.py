import re
import random
import string
import json
import uuid
import asyncio
import subprocess
import time

from abc import ABC

from pyxui_async import XUI

from bot.misc.VPN.BaseVpn import BaseVpn


class XuiBase(BaseVpn, ABC):

    NAME_VPN: str

    def __init__(self, server):
        if server.connection_method:
            self.type_con = 'https://'
        else:
            self.type_con = 'http://'
        full_address = f'{self.type_con}{server.ip}'
        self.adress = get_domain(server.ip)
        self.xui = XUI(
            full_address=full_address,
            panel=server.panel,
            https=server.connection_method
        )
        self.inbound_id = int(server.inbound_id)
        self.login_user = server.login
        self.password = server.password
        self.traffic_limit = getattr(server, "traffic_limit", None)
        # SSH credentials for fallback (x-ui 2.8.7+ compatibility)
        # If vds_password is set, SSH fallback will be used when API fails
        self.vds_password = getattr(server, "vds_password", None)
        self.server_ip = get_domain(server.ip)  # Just IP without port

    async def login(self):
        await self.xui.login(username=self.login_user, password=self.password)

    async def get_inbound_server(self):
        try:
            info = await self.xui.get_inbounds()
            obj = info['obj']
            for inbound in obj:
                if inbound['id'] == self.inbound_id:
                    return inbound
        except IndexError:
            return "Error inbound"

    async def get_all_user_server(self):
        try:
            inbound_server = await self.get_inbound_server()
            return inbound_server.get('clientStats')
        except IndexError:
            return "Error inbound"

    def random_lower_and_num(self, length):
        seq = string.ascii_lowercase + string.digits
        result = ''.join(random.choice(seq) for _ in range(length))
        return result

    # ========== SSH Fallback Methods for x-ui 2.8.7+ ==========

    def _run_ssh_command(self, command: str) -> str:
        """Execute command on server via SSH"""
        if not self.vds_password:
            raise Exception("SSH password not configured for this server")

        result = subprocess.run(
            ['sshpass', '-p', self.vds_password,
             'ssh', '-o', 'StrictHostKeyChecking=no',
             f'root@{self.server_ip}', command],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise Exception(f"SSH command failed: {result.stderr}")
        return result.stdout

    async def _ssh_get_inbound_settings(self) -> dict:
        """Get inbound settings via SSH (fallback for API issues)"""
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            self._run_ssh_command,
            f'sqlite3 /etc/x-ui/x-ui.db "SELECT settings FROM inbounds WHERE id={self.inbound_id};"'
        )
        return json.loads(output.strip())

    async def _ssh_get_client(self, email: str) -> dict:
        """Get client by email via SSH"""
        try:
            settings = await self._ssh_get_inbound_settings()
            for client in settings.get('clients', []):
                if client.get('email') == email:
                    return client
            return None
        except Exception as e:
            print(f"[SSH] get_client error: {e}")
            return None

    async def _ssh_add_client(self, email: str, client_uuid: str, limit_ip: int = 5,
                              total_gb: int = 0, flow: str = "xtls-rprx-vision") -> bool:
        """Add client via SSH direct DB access (fallback for x-ui 2.8.7+)"""
        try:
            settings = await self._ssh_get_inbound_settings()
            clients = settings.get('clients', [])

            # Check if already exists
            for c in clients:
                if c.get('email') == email:
                    print(f"[SSH] Client {email} already exists")
                    return True

            # Add new client
            current_time = int(time.time() * 1000)
            new_client = {
                "id": client_uuid,
                "email": email,
                "limitIp": limit_ip,
                "totalGB": total_gb,
                "expiryTime": 0,
                "enable": True,
                "tgId": "",
                "subId": "",
                "reset": 0,
                "flow": flow,
                "created_at": current_time,
                "updated_at": current_time
            }
            clients.append(new_client)
            settings['clients'] = clients

            # Save via SSH
            settings_json = json.dumps(settings).replace("'", "'\\''")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ssh_command,
                f"python3 -c \"import json, sqlite3; conn = sqlite3.connect('/etc/x-ui/x-ui.db'); conn.execute('UPDATE inbounds SET settings=? WHERE id={self.inbound_id}', ('{settings_json}',)); conn.commit(); conn.close()\""
            )

            print(f"[SSH] Added client {email} successfully")
            return True

        except Exception as e:
            print(f"[SSH] add_client error: {e}")
            return False

    async def _ssh_update_client(self, email: str, enable: bool = None,
                                  total_gb: int = None) -> bool:
        """Update client via SSH (for enable/disable) - VLESS"""
        try:
            settings = await self._ssh_get_inbound_settings()
            clients = settings.get('clients', [])

            updated = False
            for client in clients:
                if client.get('email') == email:
                    if enable is not None:
                        client['enable'] = enable
                    if total_gb is not None:
                        client['totalGB'] = total_gb
                    client['updated_at'] = int(time.time() * 1000)
                    updated = True
                    break

            if not updated:
                print(f"[SSH] Client {email} not found for update")
                return False

            settings['clients'] = clients
            settings_json = json.dumps(settings).replace("'", "'\\''")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ssh_command,
                f"python3 -c \"import json, sqlite3; conn = sqlite3.connect('/etc/x-ui/x-ui.db'); conn.execute('UPDATE inbounds SET settings=? WHERE id={self.inbound_id}', ('{settings_json}',)); conn.commit(); conn.close()\""
            )

            print(f"[SSH] Updated client {email}: enable={enable}, total_gb={total_gb}")
            return True

        except Exception as e:
            print(f"[SSH] update_client error: {e}")
            return False

    # ========== SSH Fallback Methods for Shadowsocks ==========

    async def _ssh_get_client_ss(self, email: str) -> dict:
        """Get Shadowsocks client by email via SSH"""
        try:
            settings = await self._ssh_get_inbound_settings()
            for client in settings.get('clients', []):
                if client.get('email') == email:
                    return client
            return None
        except Exception as e:
            print(f"[SSH] get_client_ss error: {e}")
            return None

    async def _ssh_add_client_ss(self, email: str, password: str, limit_ip: int = 5,
                                  total_gb: int = 0, enable: bool = True) -> bool:
        """Add Shadowsocks client via SSH direct DB access"""
        try:
            settings = await self._ssh_get_inbound_settings()
            clients = settings.get('clients', [])

            # Check if already exists
            for c in clients:
                if c.get('email') == email:
                    print(f"[SSH] SS Client {email} already exists")
                    return True

            # Add new client
            new_client = {
                "email": email,
                "enable": enable,
                "expiryTime": 0,
                "limitIp": limit_ip,
                "method": "",
                "password": password,
                "subId": self.random_lower_and_num(16),
                "tgId": "",
                "totalGB": total_gb
            }
            clients.append(new_client)
            settings['clients'] = clients

            # Save via SSH
            settings_json = json.dumps(settings).replace("'", "'\\''")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ssh_command,
                f"python3 -c \"import json, sqlite3; conn = sqlite3.connect('/etc/x-ui/x-ui.db'); conn.execute('UPDATE inbounds SET settings=? WHERE id={self.inbound_id}', ('{settings_json}',)); conn.commit(); conn.close()\""
            )

            print(f"[SSH] Added SS client {email} successfully")
            return True

        except Exception as e:
            print(f"[SSH] add_client_ss error: {e}")
            return False

    async def _ssh_update_client_ss(self, email: str, enable: bool = None,
                                     total_gb: int = None, password: str = None) -> bool:
        """Update Shadowsocks client via SSH"""
        try:
            settings = await self._ssh_get_inbound_settings()
            clients = settings.get('clients', [])

            updated = False
            for client in clients:
                if client.get('email') == email:
                    if enable is not None:
                        client['enable'] = enable
                    if total_gb is not None:
                        client['totalGB'] = total_gb
                    if password is not None:
                        client['password'] = password
                    updated = True
                    break

            if not updated:
                print(f"[SSH] SS Client {email} not found for update")
                return False

            settings['clients'] = clients
            settings_json = json.dumps(settings).replace("'", "'\\''")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_ssh_command,
                f"python3 -c \"import json, sqlite3; conn = sqlite3.connect('/etc/x-ui/x-ui.db'); conn.execute('UPDATE inbounds SET settings=? WHERE id={self.inbound_id}', ('{settings_json}',)); conn.commit(); conn.close()\""
            )

            print(f"[SSH] Updated SS client {email}: enable={enable}, total_gb={total_gb}")
            return True

        except Exception as e:
            print(f"[SSH] update_client_ss error: {e}")
            return False


def get_domain(url: str) -> str:
    """
    Извлекает домен или IP-адрес из переданной строки.

    :param url: Строка с URL или адресом.
    :return: Домен или IP-адрес.
    """
    pattern = r"^(?:https?://)?([a-zA-Z0-9.-]+)(?::\d+)?(?:/.*)?$"
    match = re.match(pattern, url)
    if match:
        return match.group(1)
    raise ValueError("Invalid URL server")