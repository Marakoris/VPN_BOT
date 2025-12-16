from sys import prefix

from aiogram.filters.callback_data import CallbackData


class ChoosingMonths(CallbackData, prefix='month'):
    price: int
    days_count: int
    price_on_db: int

class ChoosedSuperOffer(CallbackData, prefix='super_offer'):
    price: int
    days_count: int

class ChoosingPayment(CallbackData, prefix='payment'):
    payment: str
    price: int
    days_count: int
    price_on_db: int


class CheckPayment(CallbackData, prefix='c'):
    payment_id: str
    payment_price: int
    id_message: int
    payment: str


class ChoosingPrise(CallbackData, prefix='price'):
    price: int
    payment: str


class ChoosingVPN(CallbackData, prefix='VPN_type'):
    type: int


class ChoosingConnectionMethod(CallbackData, prefix='connect'):
    connection: bool


class ChoosingPanel(CallbackData, prefix='panel'):
    panel: str


class ServerWork(CallbackData, prefix='server_work'):
    work: bool
    name_server: str


class ServerUserList(CallbackData, prefix='server_list'):
    action: bool
    name_server: str


class EditUserPanel(CallbackData, prefix='edit_user'):
    action: str


class DeleteTimeClient(CallbackData, prefix='delete_time'):
    delete_time: bool


class DeleteStaticUser(CallbackData, prefix='delete_static_user'):
    name: str
    server_name: str


class MissingMessage(CallbackData, prefix='missing_user'):
    option: str
    server_id: int = 0
    vpn_type: int = -1


class PromocodeDelete(CallbackData, prefix='delete_promo'):
    id_promo: int
    mes_id: int


class AplicationReferral(CallbackData, prefix='app_referral'):
    type: bool


class ApplicationSuccess(CallbackData, prefix='app_referral_id'):
    id_application: int
    mes_id: int


class ChooseServer(CallbackData, prefix='choose_server'):
    id_server: int


class MessageAdminUser(CallbackData, prefix='message_admin_user'):
    id_user: int


class EditBalanceUser(CallbackData, prefix='edit_balance_user'):
    id_user: int


class ChoosingLang(CallbackData, prefix='language'):
    lang: str


class GroupAction(CallbackData, prefix='group_action'):
    action: str


class ChooseTypeVpn(CallbackData, prefix='choose_type_vpn'):
    type_vpn: int


class RegenerateKeys(CallbackData, prefix='regen_keys'):
    action: str  # 'start', 'select_servers', 'select_protocols', 'confirm', 'execute'


class RegenerateServerToggle(CallbackData, prefix='regen_srv_toggle'):
    server_id: int


class RegenerateProtocolToggle(CallbackData, prefix='regen_proto_toggle'):
    protocol: str  # 'outline', 'vless', 'shadowsocks'


class DownloadClient(CallbackData, prefix='download_client'):
    platform: str  # 'iphone', 'android', 'windows', 'macos', 'linux'


class DownloadHiddify(CallbackData, prefix='download_hiddify'):
    platform: str  # 'iphone', 'android', 'windows', 'macos', 'linux'


class ChooseOutlineServer(CallbackData, prefix='choose_outline'):
    id_server: int


class MainMenuAction(CallbackData, prefix='main_menu'):
    action: str  # 'subscription_url', 'outline', 'subscription', 'referral', 'bonus', 'about', 'language', 'help', 'admin'
