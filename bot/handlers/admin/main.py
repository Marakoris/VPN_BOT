import io
import logging

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, BufferedInputFile, ReplyKeyboardRemove
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.formatting import Text, Bold, Spoiler, Code
from aiogram_dialog import DialogManager, StartMode

from bot.filters.main import IsAdmin
from bot.database.methods.get import (
    get_all_server,
    get_server,
    get_person_id,
    get_all_user,
    get_all_subscription,
    get_no_subscription,
    get_users_by_server_and_vpn_type
)
from bot.database.methods.update import (
    server_work_update,
    server_space_update,
    update_delete_users_server
)
from bot.handlers.admin.group_mangment import group_management
from bot.handlers.admin.referal_admin import referral_router
from bot.handlers.admin.super_offer_dialog import SuperOfferSG
from bot.handlers.admin.user_management import (
    user_management_router,
    string_user
)
from bot.handlers.admin.state_servers import state_admin_router
from bot.handlers.admin.state_servers import AddServer, RemoveServer
from bot.handlers.admin.regenerate_keys import regenerate_router
from bot.keyboards.inline.admin_inline import (
    server_control,
    missing_user_menu,
    vpn_type_selection_menu,
    server_selection_menu,
    admin_main_inline_menu,
    admin_users_inline_menu,
    admin_servers_inline_menu,
    admin_groups_inline_menu,
    admin_static_users_inline_menu,
    admin_show_users_inline_menu,
    admin_back_inline_menu,
    promocode_menu,
    application_referral_menu
)
from bot.keyboards.reply.admin_reply import (
    admin_menu,
    server_menu,
    back_server_menu, back_admin_menu
)
from bot.keyboards.reply.user_reply import user_menu
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG
from bot.misc.callbackData import ServerWork, ServerUserList, MissingMessage, AdminMenuNav

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

admin_router = Router()
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())
admin_router.include_routers(
    user_management_router,
    state_admin_router,
    referral_router,
    group_management,
    regenerate_router
)


class StateMailing(StatesGroup):
    input_text = State()


@admin_router.message(
    (F.text.in_(btn_text('admin_panel_btn'))) |
    (F.text.in_(btn_text('admin_back_admin_menu_btn')))
)
async def admin_panel(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    # Убираем reply keyboard и показываем inline меню
    await message.answer(
        _('bot_control', lang),
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        "📊 Выберите раздел:",
        reply_markup=await admin_main_inline_menu(lang)
    )
    await state.clear()

@admin_router.message(F.text.in_(btn_text('admin_super_offer_btn')))
async def start_super_offer_dialog(message: Message, state: FSMContext, dialog_manager: DialogManager):
    await dialog_manager.start(SuperOfferSG.TEXT, mode=StartMode.RESET_STACK)


# todo: Server management
@admin_router.message(
    F.text.in_(btn_text('admin_servers_btn'))
    or F.text == F.text.in_(btn_text('admin_back_users_menu_btn'))
)
async def command(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('servers_control', lang),
        reply_markup=await server_menu(lang)
    )


@admin_router.message(F.text.in_(btn_text('admin_server_cancellation')))
async def back_server_menu_bot(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await state.clear()
    await message.answer(
        _('servers_control', lang),
        reply_markup=await server_menu(lang)
    )


# todo:Вывод серверов
@admin_router.message(F.text.in_(btn_text('admin_server_show_all_btn')))
async def server_menu_bot(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    all_server = await get_all_server()
    if len(all_server) == 0:
        await message.answer(_('servers_none', lang))
        return
    await message.answer(_('list_all_servers', lang))
    space = 0
    for server in all_server:
        old_m = await message.answer(_('connect_continue', lang))
        try:
            client_server = await get_static_client(server)
            space = len(client_server)
            if not await server_space_update(server.name, space):
                raise ("Failed to update the data about "
                       "the free space on the server")
            connect = True
        except Exception as e:
            log.error(e, 'error connecting to server')
            connect = False
        text_server = await get_server_info(server, space, connect, lang)
        try:
            await message.bot.delete_message(message.chat.id, old_m.message_id)
        except Exception as e:
            log.error('error deleting message from server')
        await message.answer(
            **text_server.as_kwargs(),
            reply_markup=await server_control(server.work, server.name, lang),
        )


async def get_server_info(server, space, connect, lang):
    if connect:
        space_text = _('space_server_text', lang).format(
            space=space,
            max_space=CONFIG.max_people_server
        )
    else:
        space_text = _('server_not_connect_admin', lang)
    if server.group is not None:
        group = server.group
    else:
        group = '❌'
    if server.work:
        work_text = _("server_use_s", lang)
    else:
        work_text = _("server_not_use_s", lang)
    if server.type_vpn == 0:
        return Text(
            _('server_name_s', lang), Code(server.name), '\n',
            _('server_adress_s', lang), Code(server.ip), '\n',
            _('server_password_vds_s', lang), Spoiler(server.vds_password),
            '\n', _('server_group_s', lang), Bold(group),
            '\n', _('server_type_vpn_s', lang),
            ServerManager.VPN_TYPES.get(server.type_vpn).NAME_VPN, '\n',
            _('server_outline_connect_s', lang), Code(server.outline_link),
            '\n', work_text, '\n', space_text
        )
    else:
        return Text(
            _('server_name_s', lang), Code(server.name), '\n',
            _('server_adress_s', lang), Code(server.ip), '\n',
            _('server_password_vds_s', lang), Spoiler(server.vds_password),
            '\n', _('server_group_s', lang), Bold(group),
            '\n', _('server_type_vpn_s', lang),
            ServerManager.VPN_TYPES.get(server.type_vpn).NAME_VPN, '\n',
            _('server_type_connect_s', lang),
            f'{"Https" if server.connection_method else "Http"}', '\n',
            _('server_panel_control_s', lang),
            f'{"Alireza 🕹" if server.panel == "alireza" else "Sanaei 🖲"}',
            '\n',
            _('server_id_connect_s', lang), Bold(server.inbound_id), '\n',
            _('server_login_s', lang), Bold(server.login), '\n',
            _('server_password_s', lang), Spoiler(server.password), '\n',
            work_text, '\n', space_text
        )


@admin_router.callback_query(ServerWork.filter())
async def callback_work_server(
        call: CallbackQuery,
        state: FSMContext,
        callback_data: ServerWork
):
    lang = await get_lang(call.from_user.id, state)
    text_working = _('server_use_active', lang).format(
        name_server=callback_data.name_server
    )
    text_uncorking = _('server_not_use_active', lang).format(
        name_server=callback_data.name_server
    )
    text_message = text_working if callback_data.work else text_uncorking
    await server_work_update(callback_data.name_server, callback_data.work)
    await call.message.answer(text_message)
    await call.answer()


async def get_static_client(server):
    server_manager = ServerManager(server)
    await server_manager.login()
    return await server_manager.get_all_user()


async def get_text_client(all_client, bot_client, lang):
    text_client = ''
    count = 1
    for client in bot_client:
        text_client += await string_user(client, count, lang)
        count += 1
        all_client.remove(str(client.tgid))
    for unknown_client in all_client:
        text_client += _('not_found_key', lang).format(
            unknown_client=unknown_client
        )
    return text_client


@admin_router.callback_query(ServerUserList.filter())
async def call_list_server(
        call: CallbackQuery,
        callback_data: ServerUserList,
        state: FSMContext
):
    lang = await get_lang(call.from_user.id, state)
    server = await get_server(callback_data.name_server)
    try:
        client_stats = await get_static_client(server)
    except Exception as e:
        await call.message.answer(_('server_not_connect_admin', lang))
        await call.answer()
        log.error(e, 'server not connect')
        return
    try:
        if server.type_vpn == 0:
            client_id = []
            all_client = list({client.name for client in client_stats})
            for client in client_stats:
                if client.name.isdigit():
                    client_id.append(int(client.name))
        else:
            client_id = []
            all_client = list({client['email'] for client in client_stats})
            for client in client_stats:
                if client['email'].isdigit():
                    client_id.append(int(client['email']))
        bot_client = await get_person_id(client_id)
        if not callback_data.action:
            await delete_users_server(call.message, server, bot_client, lang)
            await call.message.answer(
                _('key_delete_server', lang)
                .format(name=callback_data.name_server)
            )
            await call.answer()
            return
        text_client = await get_text_client(all_client, bot_client, lang)
    except Exception as e:
        await call.message.answer(_('error_get_users_bd_text', lang))
        await call.answer()
        log.error(e, 'error get users BD')
        return
    if text_client == '':
        await call.message.answer(_('file_server_user_none', lang))
        await call.answer()
        return
    file_stream = io.BytesIO(text_client.encode()).getvalue()
    input_file = BufferedInputFile(file_stream, 'Clients_server.txt')
    try:
        await call.message.answer_document(
            input_file,
            caption=_('file_list_users_server', lang)
            .format(name_server=callback_data.name_server)
        )
    except Exception as e:
        await call.message.answer(_('error_file_list_users_server', lang))
        log.error(e, 'error file send Clients_server.txt')
    await call.answer()


async def delete_users_server(m, server, users, lang):
    server_manager = ServerManager(server)
    await server_manager.login()
    for user in users:
        try:
            await server_manager.delete_client(user.tgid)
        except Exception as e:
            log.error(e, 'not delete users server')
            await m.answer(_('error_delete_all_users_server', lang))
            return False
    await update_delete_users_server(server)
    return True


@admin_router.message(
    StateFilter(None),
    F.text.in_(btn_text('admin_server_add_btn'))
)
async def add_server_bot(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('input_name_server_admin', lang),
        reply_markup=await back_server_menu(lang))
    await state.set_state(AddServer.input_name)


@admin_router.message(F.text.in_(btn_text('admin_server_delete_btn')))
async def delete_server_bot(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('input_name_server_admin', lang),
        reply_markup=await back_server_menu(lang)
    )
    await state.set_state(RemoveServer.input_name)


# todo: Mailing list management
@admin_router.message(F.text.in_(btn_text('admin_send_message_users_btn')))
async def out_message_bot(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('who_should_i_send', lang),
        reply_markup=await missing_user_menu(lang)
    )


@admin_router.message(F.text == '🔄 Регенерация ключей')
async def regenerate_keys_menu(message: Message, state: FSMContext) -> None:
    """Обработчик кнопки регенерации ключей"""
    from bot.misc.callbackData import RegenerateKeys

    lang = await get_lang(message.from_user.id, state)

    # Создаем inline кнопку для запуска
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text='🚀 Начать регенерацию',
            callback_data=RegenerateKeys(action='start').pack()
        )
    )

    await message.answer(
        "🔄 Регенерация ключей VPN\n\n"
        "Этот инструмент позволяет массово обновить VPN ключи пользователей "
        "после изменения портов или других настроек серверов.\n\n"
        "📋 Процесс:\n"
        "1. Выбор серверов\n"
        "2. Выбор протоколов (Outline/Vless/Shadowsocks)\n"
        "3. Подтверждение\n"
        "4. Автоматическая регенерация и отправка новых ключей\n\n"
        "⚠️ Убедитесь, что изменения на серверах уже применены!",
        reply_markup=kb.as_markup()
    )


@admin_router.callback_query(MissingMessage.filter())
async def update_message_bot(
        call: CallbackQuery,
        callback_data: MissingMessage,
        state: FSMContext) -> None:
    lang = await get_lang(call.from_user.id, state)

    # Показать меню выбора типа VPN
    if callback_data.option == 'by_vpn_type':
        await call.message.edit_text(
            '📡 Выберите тип VPN для рассылки:',
            reply_markup=await vpn_type_selection_menu(lang)
        )
        await call.answer()
        return

    # Показать меню выбора сервера
    if callback_data.option == 'by_server':
        servers = await get_all_server()
        if not servers:
            await call.message.edit_text('❌ Нет доступных серверов')
            await call.answer()
            return
        await call.message.edit_text(
            '🌍 Выберите сервер для рассылки:',
            reply_markup=await server_selection_menu(servers, lang)
        )
        await call.answer()
        return

    # Сохраняем параметры фильтрации
    await state.update_data(
        option=callback_data.option,
        server_id=callback_data.server_id,
        vpn_type=callback_data.vpn_type
    )

    from bot.keyboards.inline.admin_inline import admin_back_inline_menu
    await call.message.edit_text(
        _('input_message_or_image', lang),
        reply_markup=await admin_back_inline_menu('mailing', lang)
    )
    await call.answer()
    await state.set_state(StateMailing.input_text)


@admin_router.message(StateMailing.input_text)
async def mailing_text(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    try:
        data = await state.get_data()
        option = data.get('option')
        server_id = data.get('server_id', 0)
        vpn_type = data.get('vpn_type', -1)

        # Определяем список пользователей в зависимости от опции
        if option == 'all':
            users = await get_all_user()
        elif option == 'sub':
            users = await get_all_subscription()
        elif option == 'no':
            users = await get_no_subscription()
        elif option == 'vpn_type':
            # Рассылка по типу VPN
            users = await get_users_by_server_and_vpn_type(vpn_type=vpn_type)
            vpn_names = {0: 'Outline', 1: 'Vless', 2: 'Shadowsocks'}
            log.info(f'Рассылка для пользователей с VPN типом: {vpn_names.get(vpn_type)}')
        elif option == 'server':
            # Рассылка по серверу
            users = await get_users_by_server_and_vpn_type(server_id=server_id)
            from bot.database.methods.get import get_server as get_server_id
            server = await get_server_id(server_id)
            log.info(f'Рассылка для пользователей сервера: {server.name if server else server_id}')
        else:
            users = await get_all_user()

        count_not_suc = 0

        # Отправка сообщений (с ReplyKeyboardRemove для скрытия старой клавиатуры)
        if message.photo:
            photo = message.photo[-1]
            caption = message.caption if message.caption else ''
            for user in users:
                try:
                    await message.bot.send_photo(
                        user.tgid,
                        photo.file_id,
                        caption=caption,
                        reply_markup=ReplyKeyboardRemove()
                    )
                except Exception as e:
                    log.info(e, 'user block bot')
                    count_not_suc += 1
                    continue
        else:
            for user in users:
                try:
                    await message.bot.send_message(
                        user.tgid, message.text,
                        reply_markup=ReplyKeyboardRemove()
                    )
                except Exception as e:
                    log.info(e, 'user block bot')
                    count_not_suc += 1
                    continue

        # Результат рассылки
        result_text = _('result_mailing_text', lang).format(
            all_count=len(users),
            suc_count=len(users) - count_not_suc,
            count_not_suc=count_not_suc
        )

        # Добавляем информацию о фильтрах
        if option == 'vpn_type':
            vpn_names = {0: 'Outline 🪐', 1: 'Vless 🐊', 2: 'Shadowsocks 🦈'}
            result_text += f'\n\n📡 Фильтр: {vpn_names.get(vpn_type, "Неизвестный")}'
        elif option == 'server':
            from bot.database.methods.get import get_server as get_server_id
            server = await get_server_id(server_id)
            result_text += f'\n\n🌍 Фильтр: Сервер {server.name if server else server_id}'

        from bot.keyboards.inline.admin_inline import admin_main_inline_menu
        await message.answer(
            result_text,
            reply_markup=await admin_main_inline_menu(lang)
        )
    except Exception as e:
        log.error(e, 'error mailing')
        from bot.keyboards.inline.admin_inline import admin_main_inline_menu
        await message.answer(
            _('error_mailing_text', lang),
            reply_markup=await admin_main_inline_menu(lang)
        )
    await state.clear()


# =====================================================
# INLINE ADMIN MENU NAVIGATION HANDLERS
# =====================================================

@admin_router.callback_query(AdminMenuNav.filter())
async def admin_menu_navigation(
        call: CallbackQuery,
        callback_data: AdminMenuNav,
        state: FSMContext,
        dialog_manager: DialogManager = None
) -> None:
    """Обработчик навигации по inline админ меню"""
    lang = await get_lang(call.from_user.id, state)
    menu = callback_data.menu
    action = callback_data.action

    # Главное админ меню
    if menu == 'main':
        await call.message.edit_text(
            "📊 Выберите раздел:",
            reply_markup=await admin_main_inline_menu(lang)
        )

    # Выход в пользовательское меню
    elif menu == 'exit':
        await call.message.delete()
        users = await get_person_id([call.from_user.id])
        user = users[0] if users else None
        await call.message.answer(
            _('main_message', lang),
            reply_markup=await user_menu(user, lang)
        )

    # Меню пользователей
    elif menu == 'users':
        if action == 'edit':
            # Редактирование пользователя - просим ввести ID
            await call.message.edit_text(
                _('input_user_id_admin', lang),
                reply_markup=await admin_back_inline_menu('users', lang)
            )
            from bot.handlers.admin.user_management import EditUser
            await state.set_state(EditUser.input_id)
        else:
            await call.message.edit_text(
                _('users_control', lang),
                reply_markup=await admin_users_inline_menu(lang)
            )

    # Меню статистики пользователей
    elif menu == 'show_users':
        if action == 'all':
            # Показать всех пользователей
            users = await get_all_user()
            await call.message.edit_text(
                f"👥 Всего пользователей: {len(users)}",
                reply_markup=await admin_back_inline_menu('show_users', lang)
            )
        elif action == 'sub':
            # Показать подписчиков
            users = await get_all_subscription()
            await call.message.edit_text(
                f"✅ Пользователей с подпиской: {len(users)}",
                reply_markup=await admin_back_inline_menu('show_users', lang)
            )
        elif action == 'payments':
            # Показать историю платежей
            from bot.database.methods.get import get_total_payments
            try:
                total = await get_total_payments()
                await call.message.edit_text(
                    f"💰 Общая сумма платежей: {total} ₽",
                    reply_markup=await admin_back_inline_menu('show_users', lang)
                )
            except:
                await call.message.edit_text(
                    "💰 Статистика платежей",
                    reply_markup=await admin_back_inline_menu('show_users', lang)
                )
        else:
            await call.message.edit_text(
                _('statistic_users', lang),
                reply_markup=await admin_show_users_inline_menu(lang)
            )

    # Меню статических пользователей
    elif menu == 'static_users':
        if action == 'add':
            await call.message.edit_text(
                _('input_user_id_admin', lang),
                reply_markup=await admin_back_inline_menu('static_users', lang)
            )
            from bot.handlers.admin.user_management import StaticUser
            await state.set_state(StaticUser.input_id)
        elif action == 'show':
            # Показать статических пользователей
            from bot.database.methods.get import get_all_static_users
            try:
                static_users = await get_all_static_users()
                text = f"📌 Статических пользователей: {len(static_users)}"
            except:
                text = "📌 Статические пользователи"
            await call.message.edit_text(
                text,
                reply_markup=await admin_back_inline_menu('static_users', lang)
            )
        else:
            await call.message.edit_text(
                _('static_users_menu', lang),
                reply_markup=await admin_static_users_inline_menu(lang)
            )

    # Меню серверов
    elif menu == 'servers':
        if action == 'show':
            # Показать все серверы
            await call.message.delete()
            all_server = await get_all_server()
            if len(all_server) == 0:
                await call.message.answer(
                    _('servers_none', lang),
                    reply_markup=await admin_back_inline_menu('servers', lang)
                )
            else:
                await call.message.answer(_('list_all_servers', lang))
                space = 0
                for server in all_server:
                    old_m = await call.message.answer(_('connect_continue', lang))
                    try:
                        client_server = await get_static_client(server)
                        space = len(client_server)
                        if not await server_space_update(server.name, space):
                            raise Exception("Failed to update server space")
                        connect = True
                    except Exception as e:
                        log.error(e, 'error connecting to server')
                        connect = False
                    text_server = await get_server_info(server, space, connect, lang)
                    try:
                        await call.message.bot.delete_message(call.message.chat.id, old_m.message_id)
                    except:
                        pass
                    await call.message.answer(
                        **text_server.as_kwargs(),
                        reply_markup=await server_control(server.work, server.name, lang),
                    )
                # Добавляем кнопку назад
                await call.message.answer(
                    "⬅️ Вернуться в меню серверов",
                    reply_markup=await admin_back_inline_menu('servers', lang)
                )
        elif action == 'add':
            await call.message.edit_text(
                _('input_name_server_admin', lang),
                reply_markup=await admin_back_inline_menu('servers', lang)
            )
            await state.set_state(AddServer.input_name)
        elif action == 'delete':
            await call.message.edit_text(
                _('input_name_server_admin', lang),
                reply_markup=await admin_back_inline_menu('servers', lang)
            )
            await state.set_state(RemoveServer.input_name)
        else:
            await call.message.edit_text(
                _('servers_control', lang),
                reply_markup=await admin_servers_inline_menu(lang)
            )

    # Меню промокодов
    elif menu == 'promo':
        await call.message.edit_text(
            _('promo_menu', lang),
            reply_markup=await promocode_menu(lang)
        )

    # Реферальная система
    elif menu == 'referral':
        await call.message.edit_text(
            _('referral_system', lang),
            reply_markup=await application_referral_menu(lang)
        )

    # Рассылка
    elif menu == 'mailing':
        await call.message.edit_text(
            _('who_should_i_send', lang),
            reply_markup=await missing_user_menu(lang)
        )

    # Группы
    elif menu == 'groups':
        if action == 'show':
            # Показать группы
            from bot.database.methods.get import get_all_groups
            try:
                groups = await get_all_groups()
                if groups:
                    text = "📁 Группы:\n\n" + "\n".join([f"• {g.name}" for g in groups])
                else:
                    text = "📁 Нет групп"
            except:
                text = "📁 Группы"
            await call.message.edit_text(
                text,
                reply_markup=await admin_back_inline_menu('groups', lang)
            )
        elif action == 'add':
            await call.message.edit_text(
                _('input_group_name', lang),
                reply_markup=await admin_back_inline_menu('groups', lang)
            )
            from bot.handlers.admin.group_mangment import AddGroup
            await state.set_state(AddGroup.input_name)
        else:
            await call.message.edit_text(
                _('groups_menu', lang),
                reply_markup=await admin_groups_inline_menu(lang)
            )

    # Super Offer
    elif menu == 'super_offer':
        await call.message.delete()
        if dialog_manager:
            await dialog_manager.start(SuperOfferSG.TEXT, mode=StartMode.RESET_STACK)

    # Регенерация ключей
    elif menu == 'regenerate':
        from bot.misc.callbackData import RegenerateKeys
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(
                text='🚀 Начать регенерацию',
                callback_data=RegenerateKeys(action='start').pack()
            )
        )
        kb.row(
            InlineKeyboardButton(
                text='⬅️ Назад',
                callback_data=AdminMenuNav(menu='main').pack()
            )
        )

        await call.message.edit_text(
            "🔄 Регенерация ключей VPN\n\n"
            "Этот инструмент позволяет массово обновить VPN ключи пользователей "
            "после изменения портов или других настроек серверов.\n\n"
            "📋 Процесс:\n"
            "1. Выбор серверов\n"
            "2. Выбор протоколов (Outline/Vless/Shadowsocks)\n"
            "3. Подтверждение\n"
            "4. Автоматическая регенерация и отправка новых ключей\n\n"
            "⚠️ Убедитесь, что изменения на серверах уже применены!",
            reply_markup=kb.as_markup()
        )

    await call.answer()
