import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.payload import decode_payload

from bot.database.methods.get import (
    get_person,
    get_server_id,
    get_free_servers
)
from bot.database.methods.insert import add_new_person
from bot.database.methods.update import (
    person_delete_server,
    add_user_in_server,
    server_space_update, add_time_person, update_lang, add_client_id_person, delete_payment_method_id_person
)
from bot.keyboards.inline.user_inline import (
    renew,
    instruction_manual,
    choose_server,
    choosing_lang, choose_type_vpn
)
from bot.keyboards.reply.user_reply import (
    user_menu
)
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.callbackData import ChooseServer, ChoosingLang, ChooseTypeVpn
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG
from .payment_user import callback_user
from .referral_user import referral_router, message_admin
from ...misc.notification_script import subscription_button
from ...misc.yandex_metrika import YandexMetrikaAPI

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

user_router = Router()
user_router.include_routers(callback_user, referral_router)


@user_router.message(Command("start"))
async def command(m: Message, state: FSMContext, bot: Bot, command: CommandObject = None):
    # Получаем полный текст команды /start
    full_command = m.text

    # Извлечение аргументов, которые передаются после команды /start
    if ' ' in full_command:
        args = full_command.split(' ', 1)[1]  # Получаем всё, что после команды /start
    else:
        args = ''

    # Проверяем наличие client_id

    if args.startswith("client_id="):
        client_id = args.split('=')[1]  # Извлекаем client_id после "="
        log.info(f"Получен client_id из команды start {client_id}")
    else:
        client_id = None
        log.info("Не получен client_id из команды start")

    lang = await get_lang(m.from_user.id, state)
    await state.clear()
    if not await get_person(m.from_user.id):
        log.info("Человека нет в БД")
        try:
            user_name = f'@{str(m.from_user.username)}'
        except Exception as e:
            log.error(e)
            user_name = str(m.from_user.username)
        reference = decode_payload(command.args) if command.args else None
        if reference is not None:
            if reference.isdigit():
                reference = int(reference)
            else:
                reference = None
            if reference != m.from_user.id:
                await give_bonus_invitee(m, reference, lang)
            else:
                await m.answer(_('referral_error', lang))
                reference = None
        await add_new_person(
            m.from_user,
            user_name,
            CONFIG.trial_period,
            reference,
            client_id  # Добавляем ClientID в базу данных
        )
        await m.answer_photo(
            photo=FSInputFile('bot/img/hello_bot.jpg'),
            caption=_('hello_message', lang).format(name_bot=CONFIG.name)
        )
        if CONFIG.trial_period != 0:
            await m.answer(_('trial_message', lang))
    else:
        if client_id is not None:
            await add_client_id_person(m.from_user.id, client_id)
    person = await get_person(m.from_user.id)
    await m.answer_photo(
        photo=FSInputFile('bot/img/main_menu.jpg'),
        caption=_('start_message', lang),
        reply_markup=await user_menu(person, lang)
    )

    person = await get_person(m.from_user.id)
    # log.info(f"Был получен пользователь по {self.user_id} его данные {person}")
    # Если у пользователя есть client_id, то оправляем офлайн конверсию
    if person is not None and person.client_id is not None:
        client_id = person.client_id
        ym_api = YandexMetrikaAPI(counter_id=CONFIG.ym_counter, oauth_token=CONFIG.ym_oauth_token)
        # Отправка офлайн-конверсии
        upload_id = ym_api.send_offline_conversion_action(client_id, datetime.now().astimezone(), 'CommandStart')
        # log.info(f"Uload_id {upload_id}")
        # Проверка статуса загрузки (если загрузка прошла успешно)
        if upload_id:
            log.info(ym_api.check_conversion_status(upload_id))
    # else:
    #     log.info("У вас нет client_id")


async def give_bonus_invitee(m, reference, lang):
    if reference is None:
        return
    await m.bot.send_message(reference, _('referral_new_user', lang))
    await add_time_person(
        reference,
        CONFIG.referral_day * CONFIG.COUNT_SECOND_DAY
    )


@user_router.message(F.text.in_(btn_text('help_btn')))
async def send_help_message(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    builder = InlineKeyboardBuilder()
    builder.button(text=_('help_btn', lang), url="https://t.me/VPN_YouSupport_bot")
    builder.button(text="📚 Документация", url="https://www.notion.so/VPN-NoBorderVPN-18d2ac7dfb0780cb9182e69cca39a1b6")
    builder.adjust(1)
    await message.answer(
        text=_('support_message'),
        reply_markup=builder.as_markup()
    )


@user_router.message(F.text.in_(btn_text('vpn_connect_btn')))
async def choose_server_user(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer_photo(
photo=FSInputFile('bot/img/choose_protocol.jpg'),
        caption=_('choosing_connect_type', lang),
        reply_markup=await choose_type_vpn()
    )

    person = await get_person(message.from_user.id)
    # log.info(f"Был получен пользователь по {self.user_id} его данные {person}")
    # Если у пользователя есть client_id, то оправляем офлайн конверсию
    if person is not None and person.client_id is not None:
        client_id = person.client_id
        ym_api = YandexMetrikaAPI(counter_id=CONFIG.ym_counter, oauth_token=CONFIG.ym_oauth_token)
        # Отправка офлайн-конверсии
        upload_id = ym_api.send_offline_conversion_action(client_id, datetime.now().astimezone(), 'ButtonConnectVPN')
        # log.info(f"Uload_id {upload_id}")
        # Проверка статуса загрузки (если загрузка прошла успешно)
        if upload_id:
            log.info(ym_api.check_conversion_status(upload_id))
    # else:
    #     log.info("У вас нет client_id")


@user_router.callback_query(F.data == 'back_type_vpn')
async def call_choose_server(call: CallbackQuery, state: FSMContext) -> None:
    lang = await get_lang(call.from_user.id, state)
    await call.message.delete()
    await call.message.answer_photo(
photo=FSInputFile('bot/img/choose_protocol.jpg'),
        caption=_('choosing_connect_type', lang),
        reply_markup=await choose_type_vpn()
    )


@user_router.callback_query(ChooseTypeVpn.filter())
async def choose_server_free(
        call: CallbackQuery,
        callback_data: ChooseTypeVpn,
        state: FSMContext
) -> None:
    lang = await get_lang(call.from_user.id, state)
    user = await get_person(call.from_user.id)
    try:
        all_active_server = await get_free_servers(
            user.group, callback_data.type_vpn
        )
    except FileNotFoundError as e:
        log.info('Error get free servers -- OK')
        await call.message.answer(_('not_server', lang))
        await call.answer()
        return
    await call.message.delete()
    await call.message.answer_photo(
        photo=FSInputFile('bot/img/locations.jpg'),
        caption=_('choosing_connect_location', lang),
        reply_markup=await choose_server(
            all_active_server,
            user.server,
            lang
        )
    )


@user_router.message(F.text.in_(btn_text('language_btn')))
async def choose_server_user(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('select_language', lang),
        reply_markup=await choosing_lang()
    )


@user_router.callback_query(ChoosingLang.filter())
async def deposit_balance(
        call: CallbackQuery,
        state: FSMContext,
        callback_data: ChoosingLang
) -> None:
    lang = callback_data.lang
    await update_lang(lang, call.from_user.id)
    await state.update_data(lang=lang)
    person = await get_person(call.from_user.id)
    await call.message.answer(
        _('inform_language', lang),
        reply_markup=await user_menu(person, person.lang)
    )
    await call.answer()


@user_router.callback_query(ChooseServer.filter())
async def connect_vpn(
        call: CallbackQuery,
        callback_data: ChooseServer,
        state: FSMContext
) -> None:
    lang = await get_lang(call.from_user.id, state)
    choosing_server_id = callback_data.id_server
    client = await get_person(call.from_user.id)
    if client.banned:
        await call.message.answer(_('ended_sub_message', lang))
        await call.answer()
        return
    old_m = await call.message.answer(_('connect_continue', lang))
    if client.server == choosing_server_id:
        try:
            server = await get_server_id(client.server)
            server_manager = ServerManager(server)
            await server_manager.login()
            config = await server_manager.get_key(
                name=call.from_user.id,
                name_key=CONFIG.name
            )
            if config is None:
                raise Exception('Server Not Connected')
        except Exception as e:
            await server_not_found(call.message, e, lang)
            await call.answer()
            return
    else:
        try:
            server = await get_server_id(choosing_server_id)
            if client.server is not None:
                try:
                    await disable_key_old_server(client.server, call.from_user.id)
                except Exception as e:
                    # Логируем ошибку, но НЕ прерываем процесс подключения к новому серверу
                    log.warning(f"Failed to disable key on old server (user {call.from_user.id}): {e}")
                    # Продолжаем подключение к новому серверу
        except Exception as e:
            await call.message.answer(_('server_not_connected', lang))
            log.error(f"Failed to get new server info: {e}")
            return
        try:
            server_manager = ServerManager(server)
            await server_manager.login()

            # Try to add client (creates new or returns False if exists)
            add_result = await server_manager.add_client(call.from_user.id)

            # If add_client returned False, client might already exist but be disabled
            # Try to enable it
            if add_result is False:
                log.info(f"Client already exists for user {call.from_user.id}, attempting to enable...")
                try:
                    await server_manager.enable_client(call.from_user.id)
                    log.info(f"Successfully enabled client for user {call.from_user.id}")
                except Exception as enable_error:
                    log.warning(f"Failed to enable client: {enable_error}")
            elif add_result is None:
                raise Exception('user/main.py add client error')

            config = await server_manager.get_key(
                call.from_user.id,
                name_key=CONFIG.name
            )
            server_parameters = await server_manager.get_all_user()
            if await add_user_in_server(call.from_user.id, server):
                raise _('error_add_server_client', lang)
            await server_space_update(
                server.name,
                len(server_parameters)
            )
        except Exception as e:
            # НЕ удаляем привязку к серверу, если новый сервер недоступен
            # Пользователь остается на текущем сервере
            # await person_delete_server(call.from_user.id)  # Закомментировано
            await server_not_found(call.message, e, lang)
            await call.answer()
            log.error(f'Failed to connect to new server (server_id={choosing_server_id}): {e}')
            return
    try:
        await call.message.delete()
        await call.message.bot.delete_message(
            call.from_user.id,
            old_m.message_id
        )
    except Exception as e:
        log.info('not delete message chossing connect VPN', e)
    if server.type_vpn == 0:
        connect_message = _('how_to_connect_info_outline', lang)
        await call.message.answer_photo(
            photo=FSInputFile('bot/img/outline.jpg'),
            caption=connect_message,
            reply_markup=await instruction_manual(server.type_vpn, lang)
        )
    elif server.type_vpn == 1 or server.type_vpn == 2:
        connect_message = _('how_to_connect_info_vless', lang)
        if server.type_vpn == 1:
            await call.message.answer_photo(
                photo=FSInputFile('bot/img/vless.jpg'),
                caption=connect_message,
                reply_markup=await instruction_manual(server.type_vpn, lang)
            )
        else:
            await call.message.answer_photo(
                photo=FSInputFile('bot/img/shadow_socks.jpg'),
                caption=connect_message,
                reply_markup=await instruction_manual(server.type_vpn, lang)
            )
    else:
        raise Exception(f'The wrong type VPN - {server.type_vpn}')
    await call.message.answer(f'<code>{config}</code>')
    await call.message.answer(
        _('config_user', lang)
        .format(name_vpn=ServerManager.VPN_TYPES.get(server.type_vpn).NAME_VPN)
    )
    await call.answer()


async def delete_key_old_server(server_id, user_id):
    server = await get_server_id(server_id)
    server_manager = ServerManager(server)
    await server_manager.login()
    await server_manager.delete_client(user_id)


async def disable_key_old_server(server_id, user_id):
    """
    Disable VPN key on old server when user switches to another server.
    Key is preserved and can be re-enabled if user returns.
    """
    server = await get_server_id(server_id)
    server_manager = ServerManager(server)
    await server_manager.login()
    await server_manager.disable_client(user_id)


async def server_not_found(m, e, lang):
    await m.answer(_('server_not_connected', lang))
    log.error(e)


@user_router.message(Command("subscription"))
@user_router.message(
    (F.text.in_(btn_text('subscription_btn')))
    | (F.text.in_(btn_text('back_subscription_menu_btn')))
)
@user_router.callback_query(F.data == 'buy_subscription')
async def info_subscription(m: Message, state: FSMContext, bot: Bot) -> None:
    lang = await get_lang(m.from_user.id, state)
    person = await get_person(m.from_user.id)
    await bot.send_photo(
        chat_id=m.from_user.id,
        photo=FSInputFile('bot/img/pay_subscribe.jpg'),
        caption=_('choosing_month_sub', lang),
        reply_markup=await renew(CONFIG, lang, m.from_user.id, person.payment_method_id)
    )

    # log.info(f"Был получен пользователь по {self.user_id} его данные {person}")
    # Если у пользователя есть client_id, то оправляем офлайн конверсию
    if person is not None and person.client_id is not None:
        client_id = person.client_id
        ym_api = YandexMetrikaAPI(counter_id=CONFIG.ym_counter, oauth_token=CONFIG.ym_oauth_token)
        # Отправка офлайн-конверсии
        upload_id = ym_api.send_offline_conversion_action(client_id, datetime.now().astimezone(), 'ButtonSubscription')
        # log.info(f"Uload_id {upload_id}")
        # Проверка статуса загрузки (если загрузка прошла успешно)
        if upload_id:
            log.info(ym_api.check_conversion_status(upload_id))
    # else:
    #     log.info("У вас нет client_id")


@user_router.message(F.text.in_(btn_text('back_general_menu_btn')))
async def back_user_menu(m: Message, state: FSMContext) -> None:
    lang = await get_lang(m.from_user.id, state)
    await state.clear()
    person = await get_person(m.from_user.id)
    await m.answer(
        _('main_message', lang),
        reply_markup=await user_menu(person, lang)
    )


@user_router.message(F.text.in_(btn_text('about_vpn_btn')))
async def info_message_handler(m: Message, state: FSMContext) -> None:
    await m.answer_photo(
        photo=FSInputFile('bot/img/about.jpg'),
        caption=_('about_message', await get_lang(m.from_user.id, state))
        .format(name_bot=CONFIG.name)
    )


@user_router.callback_query(F.data == 'turn_off_autopay')
async def turn_off_autopay_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if await delete_payment_method_id_person(callback.from_user.id):
        await callback.message.answer(
            text=_('turned_off_autopay', await get_lang(callback.from_user.id, state))
        )
    else:
        await callback.message.answer(
            text=_('no_user_in_db', await get_lang(callback.from_user.id, state))
        )
