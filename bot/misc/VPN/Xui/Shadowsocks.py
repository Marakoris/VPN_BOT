import base64
import json
import os
import secrets
import string

import pyxui_async.errors

from bot.misc.VPN.Xui.XuiBase import XuiBase
from bot.misc.util import CONFIG


def random_shadowsocks_password():
    array = os.urandom(32)
    return base64.b64encode(array).decode('utf-8')


class Shadowsocks(XuiBase):
    NAME_VPN = 'Shadowsocks 🦈'
    adress: str

    def __init__(self, server):
        super().__init__(server)

    async def get_client(self, name):
        try:
            # Use unique email suffix for Shadowsocks to avoid collision with other protocols
            email = f"{name}_ss"
            result = await self.get_client_ss(
                inbound_id=self.inbound_id,
                email=email
            )
            return result
        except pyxui_async.errors.NotFound:
            # Try SSH fallback for x-ui 2.8.7+
            if self.vds_password:
                email = f"{name}_ss"
                print(f"[SS get_client] API returned NotFound, trying SSH fallback for {email}")
                return await self._ssh_get_client_ss(email)
            return None
        except Exception as e:
            # Try SSH fallback for x-ui 2.8.7+ on any error
            if self.vds_password:
                email = f"{name}_ss"
                print(f"[SS get_client] API error: {e}, trying SSH fallback for {email}")
                return await self._ssh_get_client_ss(email)
            return None

    async def add_client(self, name):
        # Use unique email suffix for Shadowsocks to avoid collision with other protocols
        email = f"{name}_ss"
        total_gb = (self.traffic_limit if self.traffic_limit is not None else CONFIG.limit_GB) * 1073741824

        try:
            print(f"[SS] add_client: inbound_id={self.inbound_id}, email={email}")
            response = await self.add_client_ss(
                inbound_id=self.inbound_id,
                email=email,
                limit_ip=CONFIG.limit_ip,
                total_gb=total_gb
            )
            print(f"[SS] add_client response: {response}")

            # If duplicate email error, try to delete and re-add
            if not response['success'] and 'Duplicate email' in response.get('msg', ''):
                print(f"[SS] Duplicate email detected, trying to delete and re-add...")
                try:
                    await self.delete_client_ss(inbound_id=self.inbound_id, email=email)
                    print(f"[SS] Deleted old client, trying to add again...")
                    response = await self.add_client_ss(
                        inbound_id=self.inbound_id,
                        email=email,
                        limit_ip=CONFIG.limit_ip,
                        total_gb=total_gb
                    )
                    print(f"[SS] Second add_client response: {response}")
                except Exception as del_error:
                    print(f"[SS] Delete failed: {del_error}, but continuing...")

            return response['success']
        except pyxui_async.errors.NotFound as e:
            print(f"[SS] add_client NotFound error: {e}")
            # Try SSH fallback for x-ui 2.8.7+
            if self.vds_password:
                print(f"[SS] Trying SSH fallback for {email}")
                return await self._ssh_add_client_ss(
                    email=email,
                    password=random_shadowsocks_password(),
                    limit_ip=CONFIG.limit_ip,
                    total_gb=total_gb
                )
            return False
        except Exception as e:
            print(f"[SS] add_client unexpected error: {type(e).__name__}: {e}")
            # Try SSH fallback for x-ui 2.8.7+
            if self.vds_password:
                print(f"[SS] Trying SSH fallback for {email}")
                return await self._ssh_add_client_ss(
                    email=email,
                    password=random_shadowsocks_password(),
                    limit_ip=CONFIG.limit_ip,
                    total_gb=total_gb
                )
            return False

    async def delete_client(self, telegram_id):
        try:
            # Use unique email suffix for Shadowsocks to avoid collision with other protocols
            email = f"{telegram_id}_ss"
            response = await self.delete_client_ss(
                inbound_id=self.inbound_id,
                email=email,
            )
            return response['success']
        except pyxui_async.errors.NotFound:
            return False

    async def disable_client(self, telegram_id):
        """Disable client by setting traffic limit to 1 byte (similar to Outline)"""
        email = f"{telegram_id}_ss"
        print(f"[SS] disable_client: email={email}")

        try:
            client = await self.get_client_ss(inbound_id=self.inbound_id, email=email)
            if not client or not isinstance(client, dict):
                # Try SSH fallback to get client
                if self.vds_password:
                    client = await self._ssh_get_client_ss(email)
                if not client:
                    print(f"[SS] Client not found for disable")
                    return False

            # Delete and recreate client with 1 byte limit to effectively disable
            await self.delete_client_ss(inbound_id=self.inbound_id, email=email)

            response = await self.add_client_ss(
                inbound_id=self.inbound_id,
                email=email,
                password=client['password'],
                limit_ip=client.get('limitIp', 0),
                total_gb=1  # 1 byte - effectively disabled
            )
            print(f"[SS] disable_client (recreated with 1 byte): {response}")
            return response.get('success', False)
        except Exception as e:
            print(f"[SS] disable_client API error: {e}")

            # Try SSH fallback for x-ui 2.8.7+
            if self.vds_password:
                print(f"[SS] disable_client trying SSH fallback for {email}")
                return await self._ssh_update_client_ss(email=email, total_gb=1)
            return False

    async def enable_client(self, telegram_id):
        """Enable client with unlimited traffic (total_gb=0)"""
        email = f"{telegram_id}_ss"
        print(f"[SS] enable_client: email={email}")

        try:
            client = await self.get_client_ss(inbound_id=self.inbound_id, email=email)
            if not client or not isinstance(client, dict):
                # Try SSH fallback to get client
                if self.vds_password:
                    client = await self._ssh_get_client_ss(email)
                if not client:
                    print(f"[SS] Client not found for enable")
                    return False

            # Delete and recreate client with unlimited traffic (total_gb=0)
            await self.delete_client_ss(inbound_id=self.inbound_id, email=email)

            response = await self.add_client_ss(
                inbound_id=self.inbound_id,
                email=email,
                password=client['password'],
                limit_ip=CONFIG.limit_ip,
                total_gb=0  # 0 = unlimited traffic for subscription users
            )
            print(f"[SS] enable_client (recreated with unlimited traffic): {response}")
            return response.get('success', False)
        except Exception as e:
            print(f"[SS] enable_client API error: {e}")

            # Try SSH fallback for x-ui 2.8.7+
            if self.vds_password:
                print(f"[SS] enable_client trying SSH fallback for {email}")
                return await self._ssh_update_client_ss(email=email, total_gb=0)
            return False

    async def get_key_user(self, name, name_key):
        print(f"[SS] get_key_user called for name={name}, name_key={name_key}")
        info = await self.get_inbound_server()
        print(f"[SS] got inbound info: {info is not None}")

        client = await self.get_client(name)
        print(f"[SS] get_client result: type={type(client)}, value={client}")

        if client is None or not isinstance(client, dict):
            print(f"[SS] Client not found, creating new client...")
            add_result = await self.add_client(name)
            print(f"[SS] add_client result: {add_result}")
            client = await self.get_client(name)
            print(f"[SS] get_client after add: type={type(client)}, value={client}")

        # Final check - if still no valid client, return error
        if not isinstance(client, dict) or 'password' not in client:
            print(f"[SS] ERROR: Invalid client data, returning None")
            return None

        print(f"[SS] Proceeding to generate key...")
        stream_settings = json.loads(info['streamSettings'])
        settings = json.loads(info['settings'])
        user_base64 = base64.b64encode(
            f'{settings["method"]}:'
            f'{settings["password"]}:'
            f'{client["password"]}'
            .encode()).decode()
        key_str = (
            f'{user_base64}@'
            f'{self.adress}:'
            f'{info["port"]}?'
            f'type={stream_settings["network"]}#'
            f'{name_key}')
        key = f"ss://{key_str}"
        return key

    async def add_client_ss(
        self,
        inbound_id: int,
        email: str,
        password: str = None,
        enable: bool = True,
        limit_ip: int = 0,
        total_gb: int = 0,
        expire_time: int = 0,
        telegram_id: str = "",
        subscription_id: str = None,
    ):
        if password is None:
            password = random_shadowsocks_password()
        if subscription_id is None:
            subscription_id = self.random_lower_and_num(16)
        settings = {
            "clients": [
                {
                  "email": email,
                  "enable": enable,
                  "expiryTime": expire_time,
                  "limitIp": limit_ip,
                  "method": "",
                  "password": password,
                  "subId": subscription_id,
                  "tgId": telegram_id,
                  "totalGB": total_gb
                }
            ],
            "decryption": "none",
            "fallbacks": []
        }

        params = {
            "id": inbound_id,
            "settings": json.dumps(settings)
        }

        return await self.xui.request(
            path="addClient",
            method="POST",
            params=params
        )

    async def get_client_ss(
            self,
            inbound_id: int,
            email: str = False,
            password: str = False):

        print(f"[SS] get_client_ss: inbound_id={inbound_id}, email={email}, password={password}")
        get_inbounds = await self.xui.get_inbounds()

        if not email and not password:
            raise ValueError()

        for inbound in get_inbounds['obj']:
            if inbound['id'] != inbound_id:
                continue

            print(f"[SS] Found inbound {inbound_id}")
            settings = json.loads(inbound['settings'])
            print(f"[SS] Inbound has {len(settings['clients'])} clients")

            for client in settings['clients']:
                print(f"[SS] Checking client: email={client.get('email')}, looking_for={email}")
                # Check email match if email is provided
                if email and client['email'] == email:
                    print(f"[SS] FOUND matching client!")
                    return client
                # Check password match if password is provided
                if password and client['password'] == password:
                    print(f"[SS] FOUND matching client by password!")
                    return client

            # If we get here, client was not found in this inbound
            print(f"[SS] Client not found in inbound {inbound_id}")
            return None

    async def delete_client_ss(
            self,
            inbound_id: int,
            email: str = False,
            password: str = False
    ):
        find_client = await self.get_client_ss(
            inbound_id=inbound_id,
            email=email,
            password=password
        )

        return await self.xui.request(
            path=f"{inbound_id}/delClient/{find_client['email']}",
            method="POST"
        )

    async def update_client_ss(
            self,
            inbound_id: int,
            email: str,
            password: str,
            enable: bool = True,
            limit_ip: int = 0,
            total_gb: int = 0,
            expiry_time: int = 0,
            telegram_id: str = "",
            subscription_id: str = None,
    ):
        """Update existing Shadowsocks client settings"""
        if subscription_id is None:
            subscription_id = self.random_lower_and_num(16)

        settings = {
            "clients": [
                {
                  "email": email,
                  "enable": enable,
                  "expiryTime": expiry_time,
                  "limitIp": limit_ip,
                  "method": "",
                  "password": password,
                  "subId": subscription_id,
                  "tgId": telegram_id,
                  "totalGB": total_gb
                }
            ],
            "decryption": "none",
            "fallbacks": []
        }

        params = {
            "id": inbound_id,
            "settings": json.dumps(settings)
        }

        return await self.xui.request(
            path=f"{inbound_id}/updateClient/{email}",
            method="POST",
            params=params
        )