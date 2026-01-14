import re
import random
import string

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