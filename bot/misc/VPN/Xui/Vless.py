import json
import uuid

import pyxui_async.errors

from bot.misc.VPN.Xui.XuiBase import XuiBase
from bot.misc.util import CONFIG


class Vless(XuiBase):
    NAME_VPN = 'Vless 🐊'

    def __init__(self, server):
        super().__init__(server)

    async def get_client(self, name):
        try:
            # Add _vless suffix to avoid conflicts with Shadowsocks on same server
            email = f"{name}_vless"
            return await self.xui.get_client(
                inbound_id=self.inbound_id,
                email=email,
            )
        except pyxui_async.errors.NotFound:
            return None

    async def add_client(self, name):
        try:
            # Add _vless suffix to avoid conflicts with Shadowsocks on same server
            email = f"{name}_vless"
            response = await self.xui.add_client(
                inbound_id=self.inbound_id,
                email=email,
                uuid=str(uuid.uuid4()),
                limit_ip=CONFIG.limit_ip,
                total_gb=CONFIG.limit_GB * 1073741824,
                flow="xtls-rprx-vision"  # Добавлено для защиты от DPI
            )
            # Логируем ответ для отладки
            print(f"[VLESS add_client] Created with email={email}, Response: {response}")
            if response['success']:
                return True
            return False
        except Exception as e:
            # Логируем все ошибки
            print(f"[VLESS add_client] Exception: {e}")
            return False

    async def delete_client(self, telegram_id):
        try:
            # Add _vless suffix to avoid conflicts with Shadowsocks on same server
            email = f"{telegram_id}_vless"
            print(f"[VLESS delete_client] Deleting email={email}, inbound_id={self.inbound_id}")
            response = await self.xui.delete_client(
                inbound_id=self.inbound_id,
                email=email,
            )
            print(f"[VLESS delete_client] Response: {response}")
            return response['success']
        except Exception as e:
            print(f"[VLESS delete_client] Exception: {e}")
            return False

    async def update_client_flow(self, telegram_id, flow="xtls-rprx-vision"):
        """Update existing client to add flow parameter"""
        try:
            # Add _vless suffix to avoid conflicts with Shadowsocks on same server
            email = f"{telegram_id}_vless"

            # Получаем существующего клиента
            client = await self.get_client(str(telegram_id))
            if not client:
                print(f"[VLESS update_flow] Client {email} not found")
                return False

            # Обновляем с flow
            response = await self.xui.update_client(
                inbound_id=self.inbound_id,
                email=email,  # Use email with suffix
                uuid=client['id'],
                enable=client['enable'],
                flow=flow,  # ← Добавляем flow!
                limit_ip=client.get('limitIp', CONFIG.limit_ip),
                total_gb=client.get('totalGB', 0),
                expire_time=client.get('expiryTime', 0),
                telegram_id="",
                subscription_id=""
            )

            print(f"[VLESS update_flow] Response: {response}")
            return response['success']

        except Exception as e:
            print(f"[VLESS update_flow] Exception: {e}")
            return False

    async def disable_client(self, telegram_id):
        """Disable client without deleting - sets enable=false"""
        try:
            # Add _vless suffix to avoid conflicts with Shadowsocks on same server
            email = f"{telegram_id}_vless"
            print(f"[VLESS] disable_client called for email={email}")
            client = await self.get_client(telegram_id)
            if not client:
                print(f"[VLESS] Client not found for disable")
                return False

            print(f"[VLESS] Disabling client: email={email}, uuid={client['id']}")
            # Update client with enable=false
            response = await self.xui.update_client(
                inbound_id=self.inbound_id,
                uuid=client['id'],
                email=email,  # Use email with suffix
                enable=False,
                limit_ip=client.get('limitIp', 0),
                total_gb=client.get('totalGB', 0),
                flow=client.get('flow', ''),
                expire_time=client.get('expiryTime', 0),
                telegram_id=client.get('tgId', ''),
                subscription_id=client.get('subId', '')
            )
            print(f"[VLESS] disable_client response: {response}")
            return response['success']
        except Exception as e:
            print(f"[VLESS] disable_client error: {e}")
            return False

    async def enable_client(self, telegram_id):
        """Enable client with unlimited traffic (enable=true, total_gb=0)"""
        try:
            # Add _vless suffix to avoid conflicts with Shadowsocks on same server
            email = f"{telegram_id}_vless"
            print(f"[VLESS] enable_client called for email={email}")
            client = await self.get_client(telegram_id)
            if not client:
                print(f"[VLESS] Client not found for enable")
                return False

            print(f"[VLESS] Enabling client: email={email}, uuid={client['id']}")
            # Update client with enable=true and unlimited traffic (total_gb=0)
            response = await self.xui.update_client(
                inbound_id=self.inbound_id,
                uuid=client['id'],
                email=email,  # Use email with suffix
                enable=True,
                limit_ip=client.get('limitIp', CONFIG.limit_ip),
                total_gb=0,  # 0 = unlimited traffic for subscription users
                flow=client.get('flow', ''),
                expire_time=client.get('expiryTime', 0),
                telegram_id=client.get('tgId', ''),
                subscription_id=client.get('subId', '')
            )
            print(f"[VLESS] enable_client response: {response}")
            return response['success']
        except Exception as e:
            print(f"[VLESS] enable_client error: {e}")
            return False

    async def get_key_user(self, name, name_key):
        info = await self.get_inbound_server()
        client = await self.get_client(name)
        if not client:
            await self.add_client(name)
            client = await self.get_client(name)
        stream_settings = json.loads(info['streamSettings'])
        fp = stream_settings["realitySettings"]["settings"]["fingerprint"]
        pbk = stream_settings["realitySettings"]["settings"]["publicKey"]

        # Получаем flow из клиента (если есть)
        flow = client.get('flow', '')

        # Строим URL
        key_parts = [
            f'vless://{client["id"]}@',
            f'{self.adress}:{info["port"]}?',
            f'type={stream_settings["network"]}&',
            f'security={stream_settings["security"]}&',
        ]

        # Добавляем flow только если он установлен
        if flow:
            key_parts.append(f'flow={flow}&')

        key_parts.extend([
            f'fp={fp}&',
            f'pbk={pbk}&',
            f'sni={stream_settings["realitySettings"]["serverNames"][0]}&',
            f'sid={stream_settings["realitySettings"]["shortIds"][0]}&',
            f'spx=%2F',
            f'#{name_key}'
        ])

        key = ''.join(key_parts)
        return key
