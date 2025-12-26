from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from bot.misc.callbackData import (
    ChoosingConnectionMethod,
    ChoosingPanel,
    ServerWork,
    ServerUserList,
    EditUserPanel,
    DeleteTimeClient,
    DeleteStaticUser,
    MissingMessage,
    ChoosingVPN,
    PromocodeDelete,
    AplicationReferral,
    ApplicationSuccess, MessageAdminUser, EditBalanceUser, GroupAction,
    RegenerateKeys, RegenerateServerToggle, RegenerateProtocolToggle,
    AdminMenuNav
)
from bot.misc.language import Localization

_ = Localization.text


async def choosing_connection() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text='HTTP 🔌',
        callback_data=ChoosingConnectionMethod(connection=False)
    )
    kb.button(
        text='HTTPS 🔌',
        callback_data=ChoosingConnectionMethod(connection=True)
    )
    kb.adjust(2)
    return kb.as_markup()


async def choosing_vpn() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text='Outline 🪐',
        callback_data=ChoosingVPN(type=0)
    )
    kb.button(
        text='Vless 🐊',
        callback_data=ChoosingVPN(type=1)
    )
    kb.button(
        text='Shadowsocks 🦈',
        callback_data=ChoosingVPN(type=2)
    )
    kb.adjust(1)
    return kb.as_markup()


async def choosing_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text='Sanaei 🖲',
        callback_data=ChoosingPanel(panel='sanaei')
    )
    kb.button(
        text='Alireza 🕹',
        callback_data=ChoosingPanel(panel='alireza')
    )
    kb.adjust(2)
    return kb.as_markup()


async def server_control(work, name_server, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if work:
        kb.button(
            text=_('not_uses_server_btn', lang),
            callback_data=ServerWork(work=False, name_server=name_server)
        )
    else:
        kb.button(
            text=_('uses_server_btn', lang),
            callback_data=ServerWork(work=True, name_server=name_server)
        )
    kb.button(
        text=_('list_user_server_btn', lang),
        callback_data=ServerUserList(name_server=name_server, action=True)
    )
    kb.button(
        text=_('delete_key_server_btn', lang),
        callback_data=ServerUserList(name_server=name_server, action=False)
    )
    kb.adjust(1)
    return kb.as_markup()


async def edit_client_menu(tgid_user, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('admin_user_add_time_btn', lang),
        callback_data=EditUserPanel(action='add_time')
    )
    kb.button(
        text=_('admin_user_edit_balance_btn', lang),
        callback_data=EditBalanceUser(id_user=tgid_user)
    )
    kb.button(
        text=_('admin_user_message_client_btn', lang),
        callback_data=MessageAdminUser(id_user=tgid_user)
    )
    kb.button(
        text=_('admin_user_delete_time_btn', lang),
        callback_data=EditUserPanel(action='delete')
    )
    kb.adjust(1)
    return kb.as_markup()


async def delete_time_client(lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('definitely_dropping_btn', lang),
        callback_data=DeleteTimeClient(delete_time=True)
    )
    kb.adjust(1)
    return kb.as_markup()


async def delete_static_user(name, server, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('delete_static_user_btn', lang),
        callback_data=DeleteStaticUser(name=name, server_name=server)
    )
    kb.adjust(1)
    return kb.as_markup()


async def missing_user_menu(lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('admin_user_mailing_all_btn', lang),
        callback_data=MissingMessage(option='all')
    )
    kb.button(
        text=_('admin_user_mailing_sub_btn', lang),
        callback_data=MissingMessage(option='sub')
    )
    kb.button(
        text=_('admin_user_mailing_not_sub_btn', lang),
        callback_data=MissingMessage(option='no')
    )
    kb.button(
        text='📡 По типу VPN',
        callback_data=MissingMessage(option='by_vpn_type')
    )
    kb.button(
        text='🌍 По серверу',
        callback_data=MissingMessage(option='by_server')
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='main').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def vpn_type_selection_menu(lang) -> InlineKeyboardMarkup:
    """Меню выбора типа VPN для рассылки"""
    kb = InlineKeyboardBuilder()
    kb.button(
        text='Outline 🪐',
        callback_data=MissingMessage(option='vpn_type', vpn_type=0)
    )
    kb.button(
        text='Vless 🐊',
        callback_data=MissingMessage(option='vpn_type', vpn_type=1)
    )
    kb.button(
        text='Shadowsocks 🦈',
        callback_data=MissingMessage(option='vpn_type', vpn_type=2)
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='mailing').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def server_selection_menu(servers, lang) -> InlineKeyboardMarkup:
    """Меню выбора сервера для рассылки"""
    kb = InlineKeyboardBuilder()
    for server in servers:
        kb.button(
            text=f'{server.name}',
            callback_data=MissingMessage(option='server', server_id=server.id)
        )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='mailing').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def promocode_menu(lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('promo_add_new_btn', lang),
        callback_data='new_promo'
    )
    kb.button(
        text=_('promo_show_all_btn', lang),
        callback_data='show_promo'
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='main').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def application_referral_menu(lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('applications_show_all_btn', lang),
        callback_data=AplicationReferral(type=True)
    )
    kb.button(
        text=_('applications_show_active_btn', lang),
        callback_data=AplicationReferral(type=False)
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='main').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def promocode_delete(id_promo, mes_id, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('delete_static_user_btn', lang),
        callback_data=PromocodeDelete(id_promo=id_promo, mes_id=mes_id)
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='promo').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def application_success(
        id_application,
        mes_id,
        lang
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('applications_success_btn', lang),
        callback_data=ApplicationSuccess(
            id_application=id_application,
            mes_id=mes_id
        )
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='referral').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def group_control(lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('admin_groups_client_show_btn', lang),
        callback_data=GroupAction(action='show')
    )
    kb.button(
        text=_('admin_groups_client_add_btn', lang),
        callback_data=GroupAction(action='add')
    )
    kb.button(
        text=_('admin_groups_client_exclude_btn', lang),
        callback_data=GroupAction(action='exclude')
    )
    kb.button(
        text=_('admin_groups_client_delete_btn', lang),
        callback_data=GroupAction(action='delete')
    )
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='main').pack()
    )
    kb.adjust(1)
    return kb.as_markup()


async def regenerate_server_selection_menu(servers, selected_servers, lang) -> InlineKeyboardMarkup:
    """Меню множественного выбора серверов для регенерации ключей"""
    from bot.misc.VPN.ServerManager import ServerManager
    from bot.database.methods.get import get_users_by_server_and_vpn_type

    kb = InlineKeyboardBuilder()
    for server in servers:
        # Только Outline, Vless и Shadowsocks (type 0, 1 и 2)
        if server.type_vpn not in [0, 1, 2]:
            continue

        # Подсчитываем активных пользователей на сервере
        users = await get_users_by_server_and_vpn_type(server_id=server.id)
        # Фильтруем только активных (subscription > current_time и не banned)
        import time
        active_users = [u for u in users if u.subscription and u.subscription > int(time.time()) and not u.banned]

        checkbox = '☑️' if server.id in selected_servers else '☐'
        vpn_name = ServerManager.VPN_TYPES.get(server.type_vpn).NAME_VPN
        kb.button(
            text=f'{checkbox} {server.name} ({vpn_name}) - {len(active_users)} активных',
            callback_data=RegenerateServerToggle(server_id=server.id)
        )

    kb.adjust(1)

    # Кнопки навигации
    if selected_servers:
        kb.row(
            InlineKeyboardButton(
                text='Продолжить ➡️',
                callback_data=RegenerateKeys(action='select_protocols').pack()
            )
        )
    kb.row(
        InlineKeyboardButton(
            text='❌ Отмена',
            callback_data=RegenerateKeys(action='cancel').pack()
        )
    )

    return kb.as_markup()


async def regenerate_protocol_selection_menu(selected_protocols, user_count_by_protocol, lang) -> InlineKeyboardMarkup:
    """Меню множественного выбора протоколов для регенерации ключей"""
    import logging
    log = logging.getLogger(__name__)

    log.info(f"=== Building protocol menu ===")
    log.info(f"selected_protocols: {selected_protocols}")
    log.info(f"user_count_by_protocol: {user_count_by_protocol}")

    kb = InlineKeyboardBuilder()

    # Маппинг: строка -> (тип_id, название)
    protocols = {
        'outline': (0, 'Outline 🪐'),
        'vless': (1, 'Vless 🐊'),
        'shadowsocks': (2, 'Shadowsocks 🦈')
    }

    for protocol_key, (protocol_id, protocol_name) in protocols.items():
        checkbox = '☑️' if protocol_key in selected_protocols else '☐'
        user_count = user_count_by_protocol.get(protocol_id, 0)
        button_text = f'{checkbox} {protocol_name} ({user_count} пользователей)'

        log.info(f"Creating button for {protocol_key}: text='{button_text}', callback_data=RegenerateProtocolToggle(protocol='{protocol_key}')")

        kb.button(
            text=button_text,
            callback_data=RegenerateProtocolToggle(protocol=protocol_key)
        )

    kb.adjust(1)

    # Кнопки навигации
    kb.row(
        InlineKeyboardButton(
            text='⬅️ Назад',
            callback_data=RegenerateKeys(action='select_servers').pack()
        )
    )
    if selected_protocols:
        kb.row(
            InlineKeyboardButton(
                text='Продолжить ➡️',
                callback_data=RegenerateKeys(action='confirm').pack()
            )
        )
    kb.row(
        InlineKeyboardButton(
            text='❌ Отмена',
            callback_data=RegenerateKeys(action='cancel').pack()
        )
    )

    return kb.as_markup()


async def regenerate_confirm_menu(lang) -> InlineKeyboardMarkup:
    """Меню подтверждения регенерации ключей"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text='✅ ПОДТВЕРДИТЬ',
            callback_data=RegenerateKeys(action='execute').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text='⬅️ Назад',
            callback_data=RegenerateKeys(action='select_protocols').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text='❌ ОТМЕНА',
            callback_data=RegenerateKeys(action='cancel').pack()
        )
    )

    return kb.as_markup()


# =====================================================
# INLINE ADMIN MENUS (replacement for reply keyboards)
# =====================================================

async def admin_main_inline_menu(lang) -> InlineKeyboardMarkup:
    """Главное inline меню администратора (замена reply keyboard)"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=_('admin_users_btn', lang),
            callback_data=AdminMenuNav(menu='users').pack()
        ),
        InlineKeyboardButton(
            text=_('admin_promo_btn', lang),
            callback_data=AdminMenuNav(menu='promo').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_servers_btn', lang),
            callback_data=AdminMenuNav(menu='servers').pack()
        ),
        InlineKeyboardButton(
            text=_('admin_reff_system_btn', lang),
            callback_data=AdminMenuNav(menu='referral').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_send_message_users_btn', lang),
            callback_data=AdminMenuNav(menu='mailing').pack()
        ),
        InlineKeyboardButton(
            text=_('admin_groups_btn', lang),
            callback_data=AdminMenuNav(menu='groups').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_super_offer_btn', lang),
            callback_data=AdminMenuNav(menu='super_offer').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('back_general_menu_btn', lang),
            callback_data=AdminMenuNav(menu='exit').pack()
        )
    )

    return kb.as_markup()


async def admin_users_inline_menu(lang) -> InlineKeyboardMarkup:
    """Inline меню управления пользователями"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=_('admin_show_statistic_btn', lang),
            callback_data=AdminMenuNav(menu='show_users').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_edit_user_btn', lang),
            callback_data=AdminMenuNav(menu='users', action='edit').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_back_admin_menu_btn', lang),
            callback_data=AdminMenuNav(menu='main').pack()
        )
    )

    return kb.as_markup()


async def admin_groups_inline_menu(lang) -> InlineKeyboardMarkup:
    """Inline меню управления группами"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=_('admin_groups_show_btn', lang),
            callback_data=AdminMenuNav(menu='groups', action='show').pack()
        ),
        InlineKeyboardButton(
            text=_('admin_groups_add_btn', lang),
            callback_data=AdminMenuNav(menu='groups', action='add').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_back_admin_menu_btn', lang),
            callback_data=AdminMenuNav(menu='main').pack()
        )
    )

    return kb.as_markup()


async def admin_static_users_inline_menu(lang) -> InlineKeyboardMarkup:
    """Inline меню статических пользователей"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=_('admin_static_add_user_btn', lang),
            callback_data=AdminMenuNav(menu='static_users', action='add').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_static_show_users_btn', lang),
            callback_data=AdminMenuNav(menu='static_users', action='show').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_back_users_menu_btn', lang),
            callback_data=AdminMenuNav(menu='users').pack()
        )
    )

    return kb.as_markup()


async def admin_show_users_inline_menu(lang) -> InlineKeyboardMarkup:
    """Inline меню просмотра пользователей"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=_('admin_statistic_show_all_users_btn', lang),
            callback_data=AdminMenuNav(menu='show_users', action='all').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_statistic_show_sub_users_btn', lang),
            callback_data=AdminMenuNav(menu='show_users', action='sub').pack()
        ),
        InlineKeyboardButton(
            text=_('admin_statistic_show_payments_btn', lang),
            callback_data=AdminMenuNav(menu='show_users', action='payments').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📊 Текущий трафик",
            callback_data=AdminMenuNav(menu='show_users', action='traffic_current').pack()
        ),
        InlineKeyboardButton(
            text="📈 Весь трафик",
            callback_data=AdminMenuNav(menu='show_users', action='traffic_total').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_back_users_menu_btn', lang),
            callback_data=AdminMenuNav(menu='users').pack()
        )
    )

    return kb.as_markup()


async def admin_servers_inline_menu(lang) -> InlineKeyboardMarkup:
    """Inline меню управления серверами"""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=_('admin_server_show_all_btn', lang),
            callback_data=AdminMenuNav(menu='servers', action='show').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_server_add_btn', lang),
            callback_data=AdminMenuNav(menu='servers', action='add').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_server_delete_btn', lang),
            callback_data=AdminMenuNav(menu='servers', action='delete').pack()
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=_('admin_back_admin_menu_btn', lang),
            callback_data=AdminMenuNav(menu='main').pack()
        )
    )

    return kb.as_markup()


async def admin_back_inline_menu(back_to: str, lang) -> InlineKeyboardMarkup:
    """Универсальная кнопка возврата"""
    kb = InlineKeyboardBuilder()

    if back_to == 'main':
        text = _('admin_back_admin_menu_btn', lang)
    elif back_to == 'users':
        text = _('admin_back_users_menu_btn', lang)
    elif back_to == 'servers':
        text = _('admin_server_cancellation', lang)
    else:
        text = _('admin_exit_btn', lang)

    kb.row(
        InlineKeyboardButton(
            text=text,
            callback_data=AdminMenuNav(menu=back_to).pack()
        )
    )

    return kb.as_markup()
