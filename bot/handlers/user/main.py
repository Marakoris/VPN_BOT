import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, ReplyKeyboardRemove
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
    choosing_lang, choose_type_vpn, user_menu_inline
)
from bot.keyboards.reply.user_reply import (
    user_menu
)
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.callbackData import ChooseServer, ChoosingLang, ChooseTypeVpn, DownloadClient, DownloadHiddify, MainMenuAction
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG
from .payment_user import callback_user
from .referral_user import referral_router, message_admin
from .subscription_user import subscription_router
from .outline_user import outline_router
from ...misc.notification_script import subscription_button
from ...misc.yandex_metrika import YandexMetrikaAPI

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

user_router = Router()
user_router.include_routers(callback_user, referral_router, subscription_router, outline_router)


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
    # Убираем нижнее меню
    remove_msg = await m.answer(
        text="⚙️",
        reply_markup=ReplyKeyboardRemove()
    )
    # Отправляем inline меню
    from datetime import datetime
    import time
    subscription_end = datetime.utcfromtimestamp(
        int(person.subscription) + CONFIG.UTC_time * 3600
    ).strftime('%d.%m.%Y %H:%M')

    # Определяем статус подписки (только по timestamp, игнорируем флаг subscription_expired)
    if person.subscription < int(time.time()):
        subscription_info = f"❌ Подписка истекла: {subscription_end}"
    else:
        subscription_info = f"⏰ Подписка активна до: {subscription_end}"

    await m.answer(
        text=_('start_message', lang).format(
            subscription_info=subscription_info,
            tgid=person.tgid,
            balance=person.balance,
            referral_money=person.referral_balance
        ),
        reply_markup=await user_menu_inline(person, lang)
    )
    # Удаляем техническое сообщение
    try:
        await remove_msg.delete()
    except:
        pass

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


# ==================== OLD MENU (DEPRECATED 2025-12-08) ====================
# The following handlers are deprecated and replaced by:
# - "📲 Subscription URL" (subscription_user.py) for VLESS + Shadowsocks
# - "🔑 Outline VPN" (outline_user.py) for Outline servers
#
# These handlers are commented out to prevent conflicts with new subscription system.
# They can be removed completely after successful migration.
# ===========================================================================

# @user_router.message(F.text.in_(btn_text('vpn_connect_btn')))
# async def choose_server_user(message: Message, state: FSMContext) -> None:
#     """OLD: Choose VPN protocol (Outline/VLESS/Shadowsocks) - DEPRECATED"""
#     lang = await get_lang(message.from_user.id, state)
#     await message.answer_photo(
#         photo=FSInputFile('bot/img/choose_protocol.jpg'),
#         caption=_('choosing_connect_type', lang),
#         reply_markup=await choose_type_vpn()
#     )
#
#     person = await get_person(message.from_user.id)
#     if person is not None and person.client_id is not None:
#         client_id = person.client_id
#         ym_api = YandexMetrikaAPI(counter_id=CONFIG.ym_counter, oauth_token=CONFIG.ym_oauth_token)
#         upload_id = ym_api.send_offline_conversion_action(client_id, datetime.now().astimezone(), 'ButtonConnectVPN')
#         if upload_id:
#             log.info(ym_api.check_conversion_status(upload_id))


# @user_router.callback_query(F.data == 'back_type_vpn')
# async def call_choose_server(call: CallbackQuery, state: FSMContext) -> None:
#     """OLD: Back to VPN type selection - DEPRECATED"""
#     lang = await get_lang(call.from_user.id, state)
#     await call.message.delete()
#     await call.message.answer_photo(
#         photo=FSInputFile('bot/img/choose_protocol.jpg'),
#         caption=_('choosing_connect_type', lang),
#         reply_markup=await choose_type_vpn()
#     )


# @user_router.callback_query(ChooseTypeVpn.filter())
# async def choose_server_free(
#         call: CallbackQuery,
#         callback_data: ChooseTypeVpn,
#         state: FSMContext
# ) -> None:
#     """OLD: Choose server by VPN type - DEPRECATED"""
#     lang = await get_lang(call.from_user.id, state)
#     user = await get_person(call.from_user.id)
#     try:
#         all_active_server = await get_free_servers(
#             user.group, callback_data.type_vpn
#         )
#     except FileNotFoundError as e:
#         log.info('Error get free servers -- OK')
#         await call.message.answer(_('not_server', lang))
#         await call.answer()
#         return
#     await call.message.delete()
#     await call.message.answer_photo(
#         photo=FSInputFile('bot/img/locations.jpg'),
#         caption=_('choosing_connect_location', lang),
#         reply_markup=await choose_server(
#             all_active_server,
#             user.server,
#             lang
#         )
#     )


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


# ===========================================================================
# NOTE: This handler is kept for backward compatibility and edge cases.
# New users should use:
# - "📲 Subscription URL" for VLESS + Shadowsocks
# - "🔑 Outline VPN" for Outline (uses ChooseOutlineServer callback instead)
#
# This handler may still be called from:
# - Old deep links
# - Admin regeneration flows
# - Edge cases during migration
# ===========================================================================

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
async def info_subscription(m: Message | CallbackQuery, state: FSMContext, bot: Bot) -> None:
    # Handle both Message and CallbackQuery
    user_id = m.from_user.id

    # If it's a callback, answer it first
    if isinstance(m, CallbackQuery):
        await m.answer()

    lang = await get_lang(user_id, state)
    person = await get_person(user_id)

    await bot.send_photo(
        chat_id=user_id,
        photo=FSInputFile('bot/img/pay_subscribe.jpg'),
        caption=_('choosing_month_sub', lang),
        reply_markup=await renew(CONFIG, lang, user_id, person.payment_method_id)
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


@user_router.callback_query(DownloadClient.filter())
async def download_client_handler(callback: CallbackQuery, callback_data: DownloadClient, state: FSMContext):
    """Handler для скачивания Outline клиентов с сервера"""
    await callback.answer()

    platform = callback_data.platform
    lang = await get_lang(callback.from_user.id, state)

    # Определяем путь к файлу (внутри Docker контейнера)
    file_paths = {
        'android': '/app/vpn_clients/Outline/Outline-Client.apk',
        'windows': '/app/vpn_clients/Outline/Outline-Client.exe',
        'macos': '/app/vpn_clients/Outline/Outline-Client.AppImage',
        'linux': '/app/vpn_clients/Outline/Outline-Client.AppImage'
    }

    file_names = {
        'android': 'Outline-Client.apk',
        'windows': 'Outline-Client.exe',
        'macos': 'Outline-Client.AppImage',
        'linux': 'Outline-Client.AppImage'
    }

    platform_names = {
        'iphone': 'iPhone',
        'android': 'Android',
        'windows': 'Windows',
        'macos': 'Mac OS',
        'linux': 'Linux'
    }

    # Ссылки на официальные источники для файлов > 50MB (лимит Telegram)
    download_urls = {
        'iphone': 'https://apps.apple.com/us/app/outline-app/id1356177741',
        'windows': 'https://github.com/Jigsaw-Code/outline-apps/releases/download/v1.10.1/Outline-Client.exe',
        'macos': 'https://apps.apple.com/us/app/outline-app/id1356178125',  # Mac App Store
        'linux': 'https://github.com/Jigsaw-Code/outline-apps/releases/download/v1.10.1/Outline-Client.AppImage'
    }

    if platform not in platform_names:
        await callback.message.answer("❌ Неизвестная платформа")
        return

    platform_name = platform_names[platform]

    try:
        # Для Android отправляем файл (< 50MB), для остальных - ссылку
        if platform == 'android':
            # Отправляем сообщение о начале загрузки
            status_msg = await callback.message.answer(f"⏳ Подготовка клиента {platform_name}...")

            # Отправляем файл
            document = FSInputFile(file_paths[platform], filename=file_names[platform])
            await callback.message.answer_document(
                document=document,
                caption=f"✅ Outline Client для {platform_name}\n\n"
                        f"📱 Установите приложение и добавьте ваш VPN ключ для начала работы."
            )

            # Удаляем сообщение о загрузке
            await status_msg.delete()
            log.info(f"User {callback.from_user.id} downloaded Outline client for {platform}")
        else:
            # Для iPhone/Windows/Mac/Linux отправляем ссылку на официальный источник
            kb = InlineKeyboardBuilder()
            kb.button(text=f'📥 Скачать {platform_name}', url=download_urls[platform])

            await callback.message.answer(
                text=f"✅ Outline Client для {platform_name}\n\n"
                     f"📱 Нажмите кнопку ниже, чтобы скачать приложение.\n"
                     f"После установки добавьте ваш VPN ключ для начала работы.",
                reply_markup=kb.as_markup()
            )
            log.info(f"User {callback.from_user.id} requested Outline client for {platform}")

    except Exception as e:
        log.error(f"Failed to send Outline client for {platform}: {e}")
        await callback.message.answer(f"❌ Не удалось отправить файл. Попробуйте позже.")


@user_router.callback_query(DownloadHiddify.filter())
async def download_hiddify_handler(callback: CallbackQuery, callback_data: DownloadHiddify, state: FSMContext):
    """Handler для скачивания Hiddify клиентов (VLESS/Shadowsocks)"""
    await callback.answer()

    platform = callback_data.platform
    lang = await get_lang(callback.from_user.id, state)

    # Определяем URLs для Hiddify
    download_urls = {
        'iphone': 'https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532',
        'android': 'https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-Android-universal.apk',
        'windows': 'https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-Windows-Setup-x64.exe',
        'macos': 'https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-MacOS.dmg',
        'linux': 'https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-Linux-x64.AppImage'
    }

    platform_names = {
        'iphone': 'iPhone',
        'android': 'Android',
        'windows': 'Windows',
        'macos': 'Mac OS',
        'linux': 'Linux'
    }

    if platform not in download_urls:
        await callback.message.answer("❌ Неизвестная платформа")
        return

    download_url = download_urls[platform]
    platform_name = platform_names[platform]

    try:
        # Отправляем сообщение со ссылкой на скачивание
        kb = InlineKeyboardBuilder()
        kb.button(text=f'📥 Скачать {platform_name}', url=download_url)

        await callback.message.answer(
            text=f"✅ Hiddify Client для {platform_name}\n\n"
                 f"📱 Нажмите кнопку ниже, чтобы скачать приложение.\n"
                 f"После установки добавьте ваш VPN ключ для начала работы.",
            reply_markup=kb.as_markup()
        )

        log.info(f"User {callback.from_user.id} requested Hiddify client for {platform}")

    except Exception as e:
        log.error(f"Failed to send Hiddify link for {platform}: {e}")
        await callback.message.answer(f"❌ Не удалось отправить ссылку. Попробуйте позже.")


@user_router.callback_query(MainMenuAction.filter())
async def handle_main_menu_action(callback: CallbackQuery, callback_data: MainMenuAction, state: FSMContext, bot: Bot):
    """Обработчик для inline-кнопок главного меню"""
    from bot.misc.callbackData import MainMenuAction
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    action = callback_data.action
    log.info(f"[MainMenu] Handler triggered! Action: {action}, User: {callback.from_user.id}")

    await callback.answer()
    lang = await get_lang(callback.from_user.id, state)

    if action == 'subscription_url':
        # Inline version of subscription URL handler
        import time
        person = await get_person(callback.from_user.id)

        if not person:
            await callback.message.answer("❌ User not found")
            return

        # Проверяем, не забанен ли пользователь (РЕАЛЬНЫЙ бан)
        if person.banned:
            await callback.message.answer("⛔ <b>Доступ заблокирован</b>\n\nВаш аккаунт заблокирован.", parse_mode="HTML")
            return

        # Проверяем подписку (только по timestamp)
        if person.subscription < int(time.time()):
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            from bot.misc.callbackData import MainMenuAction
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text=_('to_extend_btn', lang),
                callback_data=MainMenuAction(action='subscription').pack()
            ))
            await callback.message.answer(
                _('ended_sub_message', lang),
                reply_markup=kb.as_markup()
            )
            return

        # Import subscription functions
        from bot.misc.subscription import get_user_subscription_status
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        # Check subscription status
        status = await get_user_subscription_status(person.tgid)

        if 'error' in status:
            await callback.message.answer("❌ Error getting subscription status")
            return

        # If no token or not active, offer to activate
        if not status.get('token') or not status.get('active'):
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text="✅ Активировать подписку",
                callback_data="activate_subscription"
            ))
            kb.row(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=MainMenuAction(action='my_keys').pack()
            ))

            # Delete old message and send new one
            try:
                await callback.message.delete()
            except:
                pass

            await bot.send_message(
                chat_id=callback.from_user.id,
                text="📡 <b>Единая подписка на VPN</b>\n\n"
                "⚠️ Подписка не активирована\n\n"
                "🔐 <b>Что вы получите:</b>\n"
                "• Один URL для всех серверов\n"
                "• Протоколы: VLESS Reality + Shadowsocks 2022\n"
                "• Автоматическое обновление списка серверов\n"
                "• Проще в использовании, чем отдельные ключи\n\n"
                "💡 Нажмите кнопку ниже для активации:",
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
            return

        # User has active subscription - show URL
        from bot.misc.util import CONFIG
        subscription_url = f"{CONFIG.subscription_api_url}/sub/{status['token']}"

        kb = InlineKeyboardBuilder()

        # 📱 МОБИЛЬНЫЕ (самые популярные)
        # Android - одна кнопка на всю ширину
        kb.row(
            InlineKeyboardButton(
                text="📱 Android",
                url="https://play.google.com/store/apps/details?id=com.happproxy"
            )
        )

        # iPhone - две версии в одном ряду
        kb.row(
            InlineKeyboardButton(
                text="📱 iPhone (Global)",
                url="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"
            ),
            InlineKeyboardButton(
                text="📱 iPhone (RUS)",
                url="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"
            )
        )

        # 🖥 ДЕСКТОП
        # Windows и macOS в одном ряду
        kb.row(
            InlineKeyboardButton(
                text="🖥 Windows",
                url="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"
            ),
            InlineKeyboardButton(
                text="🖥 macOS",
                url="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg"
            )
        )

        # Linux - отдельная кнопка
        kb.row(
            InlineKeyboardButton(
                text="🖥 Linux (deb)",
                url="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb"
            )
        )

        # 📺 ТЕЛЕВИЗОРЫ
        # Android TV и Apple TV в одном ряду
        kb.row(
            InlineKeyboardButton(
                text="📺 Android TV",
                url="https://play.google.com/store/apps/details?id=com.happproxy"
            ),
            InlineKeyboardButton(
                text="📺 Apple TV",
                url="https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274"
            )
        )

        kb.row(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MainMenuAction(action='my_keys').pack()
        ))

        message_text = (
            "✅ <b>Единая подписка на VPN</b>\n\n"
            "📡 <b>Ваш URL подписки:</b>\n"
            f"<code>{subscription_url}</code>\n\n"
            "🔐 <b>Доступные протоколы:</b>\n"
            "• VLESS Reality - максимальная безопасность\n"
            "• Shadowsocks 2022 - высокая скорость\n\n"
            "📱 <b>Как использовать:</b>\n"
            "1. Скачайте приложение Happ для вашей платформы\n"
            "2. Нажмите \"Добавить подписку\" / \"Add Subscription\"\n"
            "3. Вставьте URL выше\n"
            "4. Обновите список серверов\n"
            "5. Подключайтесь к любому серверу!\n\n"
            "🔄 <b>Список серверов обновляется автоматически</b>\n"
            "💡 При добавлении новых серверов - просто обновите подписку в приложении"
        )

        # Delete old message and send new one
        try:
            await callback.message.delete()
        except:
            pass

        await bot.send_message(
            chat_id=callback.from_user.id,
            text=message_text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    elif action == 'outline':
        # Inline version of outline menu handler
        import time
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        from bot.misc.callbackData import ChooseOutlineServer
        from bot.database.methods.get import get_free_servers

        person = await get_person(callback.from_user.id)

        if not person:
            await callback.message.answer("❌ User not found")
            return

        # Check subscription
        if person.subscription < int(time.time()):
            from bot.misc.callbackData import MainMenuAction
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text=_('to_extend_btn', lang),
                callback_data=MainMenuAction(action='subscription').pack()
            ))
            await callback.message.answer(
                _('ended_sub_message', lang),
                reply_markup=kb.as_markup()
            )
            return

        # Get Outline servers (type_vpn=0)
        try:
            outline_servers = await get_free_servers(person.group, type_vpn=0)
        except Exception as e:
            log.error(f"Error getting Outline servers: {e}")
            await callback.message.answer(
                "❌ Outline серверы временно недоступны\n\n"
                "Используйте: 📲 Subscription URL для VLESS/Shadowsocks"
            )
            return

        if not outline_servers:
            await callback.message.answer(
                "❌ Нет доступных Outline серверов\n\n"
                "Используйте: 📲 Subscription URL для VLESS/Shadowsocks"
            )
            return

        # Show server selection menu
        kb = InlineKeyboardBuilder()
        for server in outline_servers:
            kb.row(InlineKeyboardButton(
                text=f"{server.name} 🪐",
                callback_data=ChooseOutlineServer(id_server=server.id).pack()
            ))

        # Add back button
        kb.row(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MainMenuAction(action='my_keys').pack()
        ))

        caption = (
            "🔑 <b>Outline VPN</b>\n\n"
            "Выберите сервер для подключения:\n\n"
            "💡 Для каждого сервера создается отдельный ключ\n"
            "💡 Переключайтесь между серверами в любое время"
        )

        # Delete old message and send new without photo
        try:
            await callback.message.delete()
        except:
            pass

        await bot.send_message(
            chat_id=callback.from_user.id,
            text=caption,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    elif action == 'subscription':
        # Показываем меню подписки
        from bot.misc.util import CONFIG
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from bot.misc.callbackData import MainMenuAction

        person = await get_person(callback.from_user.id)

        # Формируем клавиатуру с кнопкой "Назад"
        kb = await renew(CONFIG, lang, callback.from_user.id, person.payment_method_id)
        kb_with_back = InlineKeyboardBuilder()
        for row in kb.inline_keyboard:
            for button in row:
                kb_with_back.button(text=button.text, callback_data=button.callback_data)
        kb_with_back.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        kb_with_back.adjust(1)

        # Редактируем текущее сообщение
        try:
            await callback.message.edit_text(
                text=_('choosing_month_sub', lang),
                reply_markup=kb_with_back.as_markup()
            )
        except:
            # Если не получилось, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=_('choosing_month_sub', lang),
                reply_markup=kb_with_back.as_markup()
            )

    elif action == 'referral':
        # Inline версия реферального меню
        from bot.database.methods.get import get_count_referral_user, get_referral_balance
        from bot.keyboards.inline.user_inline import share_link
        from bot.misc.util import CONFIG
        from bot.handlers.user.referral_user import get_referral_link

        count_referral_user = await get_count_referral_user(callback.from_user.id)
        balance = await get_referral_balance(callback.from_user.id)
        link_ref = await get_referral_link(callback.message)

        message_text = (
            _('referral_menu_text', lang)
            .format(
                link_ref=link_ref,
                referral_percent=CONFIG.referral_percent,
                minimum_amount=CONFIG.minimum_withdrawal_amount,
                count_referral_user=count_referral_user,
                balance=balance,
                link_referral_conditions="https://heavy-weight-a87.notion.site/NoBorderVPN-18d2ac7dfb078050a322df104dcaa4c2",
                link_free_promotion="https://heavy-weight-a87.notion.site/18e2ac7dfb0780728d6ddfa0c8f88410",
                link_paid_promotion="https://heavy-weight-a87.notion.site/NoBorderVPN-18e2ac7dfb078096a214cbe65782b386",
            )
        )

        # Отправляем текстовое сообщение вместо фото
        try:
            await callback.message.edit_text(
                text=message_text,
                reply_markup=await share_link(link_ref, lang, balance)
            )
        except:
            try:
                await callback.message.delete()
            except:
                pass
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=message_text,
                reply_markup=await share_link(link_ref, lang, balance)
            )

    elif action == 'bonus':
        # Показываем только меню ввода промокода (без реферальной программы)
        from bot.keyboards.inline.user_inline import promo_code_button

        try:
            await callback.message.edit_text(
                text=_('referral_promo_code', lang),
                reply_markup=await promo_code_button(lang)
            )
        except:
            await callback.message.answer(
                text=_('referral_promo_code', lang),
                reply_markup=await promo_code_button(lang)
            )

    elif action == 'about':
        # Обновляем сообщение вместо отправки нового
        try:
            await callback.message.edit_text(
                text=_('about_message', lang).format(name_bot=CONFIG.name),
                reply_markup=create_back_to_menu_keyboard(lang)
            )
        except:
            # Если не получилось отредактировать (нет текста), отправляем новое
            await callback.message.answer(
                text=_('about_message', lang).format(name_bot=CONFIG.name),
                reply_markup=create_back_to_menu_keyboard(lang)
            )

    elif action == 'language':
        # Обновляем сообщение вместо отправки нового
        kb = await choosing_lang()
        # Добавляем кнопку "Назад"
        kb_with_back = InlineKeyboardBuilder()
        for row in kb.inline_keyboard:
            for button in row:
                kb_with_back.button(text=button.text, callback_data=button.callback_data)
        kb_with_back.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        kb_with_back.adjust(1)

        try:
            await callback.message.edit_text(
                text=_('select_language', lang),
                reply_markup=kb_with_back.as_markup()
            )
        except:
            await callback.message.answer(
                text=_('select_language', lang),
                reply_markup=kb_with_back.as_markup()
            )

    elif action == 'free_trial':
        # Показываем меню выбора типа VPN для пробного доступа
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.button(
            text="📡 Единая подписка (рекомендуем)",
            callback_data=MainMenuAction(action='free_trial_subscription')
        )
        builder.button(
            text="🪐 Outline VPN",
            callback_data=MainMenuAction(action='free_trial_outline')
        )
        builder.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        builder.adjust(1)

        try:
            await callback.message.edit_text(
                text="🆓 <b>Пробный доступ на 3 дня</b>\n\n"
                     "Выберите способ подключения:\n\n"
                     "📡 <b>Единая подписка</b> (рекомендуем)\n"
                     "• Один URL для всех серверов\n"
                     "• Протоколы: VLESS Reality + Shadowsocks 2022\n"
                     "• Автоматическое обновление списка серверов\n"
                     "• Проще в использовании\n\n"
                     "🪐 <b>Outline VPN</b>\n"
                     "• Классический вариант\n"
                     "• Отдельный ключ для каждого сервера\n"
                     "• Протокол: Shadowsocks (Outline)",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except:
            await callback.message.answer(
                text="🆓 <b>Пробный доступ на 3 дня</b>\n\n"
                     "Выберите способ подключения:\n\n"
                     "📡 <b>Единая подписка</b> (рекомендуем)\n"
                     "• Один URL для всех серверов\n"
                     "• Протоколы: VLESS Reality + Shadowsocks 2022\n"
                     "• Автоматическое обновление списка серверов\n"
                     "• Проще в использовании\n\n"
                     "🪐 <b>Outline VPN</b>\n"
                     "• Классический вариант\n"
                     "• Отдельный ключ для каждого сервера\n"
                     "• Протокол: Shadowsocks (Outline)",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )

    elif action == 'free_trial_subscription':
        # Активируем пробный период и показываем единую подписку
        from bot.database.methods.update import add_time_person
        from bot.misc.util import CONFIG
        import time

        person = await get_person(callback.from_user.id)

        # Проверяем, не забанен ли пользователь (РЕАЛЬНЫЙ бан)
        # Пользователи с истекшей подпиской (subscription_expired) МОГУТ использовать пробный период
        if person.banned:
            await callback.answer(
                "⛔ Доступ заблокирован",
                show_alert=True
            )
            return

        # Проверяем, не использовал ли пользователь уже пробный период
        if person.free_trial_used:
            await callback.answer(
                "⚠️ Вы уже использовали пробный период",
                show_alert=True
            )
            return

        # Добавляем 3 дня
        trial_seconds = 3 * CONFIG.COUNT_SECOND_DAY
        await add_time_person(person.tgid, trial_seconds)

        # Устанавливаем флаг что пробный период использован
        from bot.database.main import session_marker
        async with session_marker() as session:
            person.free_trial_used = True
            session.add(person)
            await session.commit()

        # Перенаправляем на subscription_url
        # Обновляем person после добавления времени
        person = await get_person(callback.from_user.id)

        # Показываем сообщение об активации
        await callback.message.answer(
            "🎉 <b>Пробный период активирован!</b>\n\n"
            "✅ Вам добавлено 3 дня подписки\n\n"
            "Сейчас покажу вашу единую подписку...",
            parse_mode="HTML"
        )

        # Вызываем обработчик subscription_url
        from bot.misc.subscription import get_user_subscription_status
        status = await get_user_subscription_status(person.tgid)

        if not status.get('token') or not status.get('active'):
            # Активируем подписку
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton

            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text="✅ Активировать подписку",
                callback_data="activate_subscription"
            ))
            kb.row(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=MainMenuAction(action='back_to_menu').pack()
            ))

            await callback.message.answer(
                "📡 <b>Единая подписка</b>\n\n"
                "Нажмите кнопку ниже чтобы активировать подписку:",
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
        else:
            # Подписка уже активна, показываем URL
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton

            subscription_url = f"{CONFIG.SUBSCRIPTION_API_URL}/sub/{status['token']}"

            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="📋 Копировать URL", url=subscription_url))
            kb.row(InlineKeyboardButton(text="📱 V2RayNG (Android)", url="https://play.google.com/store/apps/details?id=com.v2ray.ang"))
            kb.row(InlineKeyboardButton(text="🍎 Shadowrocket (iOS)", url="https://apps.apple.com/app/shadowrocket/id932747118"))
            kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu').pack()))

            await callback.message.answer(
                f"✅ <b>Ваш Subscription URL:</b>\n\n"
                f"<code>{subscription_url}</code>\n\n"
                f"📱 <b>Как использовать:</b>\n"
                f"1. Установите V2RayNG (Android) или Shadowrocket (iOS)\n"
                f"2. Добавьте подписку используя URL выше\n"
                f"3. Обновите подписку для получения всех серверов\n"
                f"4. Подключитесь к любому серверу!",
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )

    elif action == 'free_trial_outline':
        # Активируем пробный период и показываем Outline
        from bot.database.methods.update import add_time_person
        from bot.misc.util import CONFIG
        import time

        person = await get_person(callback.from_user.id)

        # Проверяем, не забанен ли пользователь (РЕАЛЬНЫЙ бан)
        # Пользователи с истекшей подпиской (subscription_expired) МОГУТ использовать пробный период
        if person.banned:
            await callback.answer(
                "⛔ Доступ заблокирован",
                show_alert=True
            )
            return

        # Проверяем, не использовал ли пользователь уже пробный период
        if person.free_trial_used:
            await callback.answer(
                "⚠️ Вы уже использовали пробный период",
                show_alert=True
            )
            return

        # Добавляем 3 дня
        trial_seconds = 3 * CONFIG.COUNT_SECOND_DAY
        await add_time_person(person.tgid, trial_seconds)

        # Устанавливаем флаг что пробный период использован
        from bot.database.main import session_marker
        async with session_marker() as session:
            person.free_trial_used = True
            session.add(person)
            await session.commit()

        # Показываем сообщение об активации
        await callback.message.answer(
            "🎉 <b>Пробный период активирован!</b>\n\n"
            "✅ Вам добавлено 3 дня подписки\n\n"
            "Сейчас покажу доступные Outline серверы...",
            parse_mode="HTML"
        )

        # Перенаправляем на outline меню (вызываем тот же код что и в action='outline')
        # Но так как мы только что добавили время, проверка subscription пройдет
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        from bot.database.methods.get import get_free_servers
        from bot.misc.callbackData import ChooseOutlineServer

        person = await get_person(callback.from_user.id)

        try:
            outline_servers = await get_free_servers(person.group, type_vpn=0)
        except Exception as e:
            await callback.message.answer(
                "❌ Outline серверы временно недоступны\n\n"
                "Используйте: 📲 Subscription URL для VLESS/Shadowsocks"
            )
            return

        if not outline_servers:
            await callback.message.answer(
                "❌ Нет доступных Outline серверов\n\n"
                "Используйте: 📲 Subscription URL для VLESS/Shadowsocks"
            )
            return

        kb = InlineKeyboardBuilder()
        for server in outline_servers:
            kb.row(InlineKeyboardButton(
                text=f"{server.name} 🪐",
                callback_data=ChooseOutlineServer(id_server=server.id).pack()
            ))

        kb.row(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MainMenuAction(action='back_to_menu').pack()
        ))

        await callback.message.answer(
            text="🔑 <b>Outline VPN</b>\n\n"
                 "Выберите сервер для получения ключа:\n\n"
                 "💡 Ключи создаются автоматически\n"
                 "💡 Переключайтесь между серверами в любое время",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    elif action == 'my_keys':
        # Показываем меню выбора типа VPN для получения ключей
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.button(
            text="📡 Единая подписка (рекомендуем)",
            callback_data=MainMenuAction(action='subscription_url')
        )
        builder.button(
            text="🪐 Outline VPN",
            callback_data=MainMenuAction(action='outline')
        )
        builder.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        builder.adjust(1)

        try:
            await callback.message.edit_text(
                text="🔑 <b>Выберите способ подключения к VPN:</b>\n\n"
                     "📡 <b>Единая подписка</b> (рекомендуем)\n"
                     "• Один URL для всех серверов\n"
                     "• Протоколы: VLESS Reality + Shadowsocks 2022\n"
                     "• Автоматическое обновление списка серверов\n"
                     "• Проще в использовании\n\n"
                     "🪐 <b>Outline VPN</b>\n"
                     "• Классический вариант\n"
                     "• Отдельный ключ для каждого сервера\n"
                     "• Протокол: Shadowsocks (Outline)",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except:
            await callback.message.answer(
                text="🔑 <b>Выберите способ подключения к VPN:</b>\n\n"
                     "📡 <b>Единая подписка</b> (рекомендуем)\n"
                     "• Один URL для всех серверов\n"
                     "• Протоколы: VLESS Reality + Shadowsocks 2022\n"
                     "• Автоматическое обновление списка серверов\n"
                     "• Проще в использовании\n\n"
                     "🪐 <b>Outline VPN</b>\n"
                     "• Классический вариант\n"
                     "• Отдельный ключ для каждого сервера\n"
                     "• Протокол: Shadowsocks (Outline)",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )

    elif action == 'bonuses':
        # Объединенное меню бонусов и рефералов
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        person = await get_person(callback.from_user.id)

        # Создаем меню с обеими опциями
        builder = InlineKeyboardBuilder()
        builder.button(text="👥 Реферальная программа", callback_data=MainMenuAction(action='referral'))
        builder.button(text="🎁 Ввести промокод", callback_data=MainMenuAction(action='bonus'))
        builder.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        builder.adjust(1)

        try:
            await callback.message.edit_text(
                text=f"💰 <b>Бонусы и друзья</b>\n\n"
                     f"💵 Ваш баланс бонусов: {person.referral_balance} руб.\n"
                     f"💳 Основной баланс: {person.balance} руб.\n\n"
                     f"Выберите действие:",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except:
            await callback.message.answer(
                text=f"💰 <b>Бонусы и друзья</b>\n\n"
                     f"💵 Ваш баланс бонусов: {person.referral_balance} руб.\n"
                     f"💳 Основной баланс: {person.balance} руб.\n\n"
                     f"Выберите действие:",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )

    elif action == 'help':
        # Обновляем сообщение вместо отправки нового
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.button(text=_('help_btn', lang), url="https://t.me/VPN_YouSupport_bot")
        builder.button(text="📚 Документация", url="https://www.notion.so/VPN-NoBorderVPN-18d2ac7dfb0780cb9182e69cca39a1b6")
        builder.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        builder.adjust(1)

        try:
            await callback.message.edit_text(
                text=_('support_message'),
                reply_markup=builder.as_markup()
            )
        except:
            await callback.message.answer(
                text=_('support_message'),
                reply_markup=builder.as_markup()
            )

    elif action == 'admin':
        # Inline-версия админ панели
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.button(text="👥 Управление пользователями", callback_data=MainMenuAction(action='admin_users'))
        builder.button(text="🎟️ Промокоды", callback_data=MainMenuAction(action='admin_promo'))
        builder.button(text="🖥️ Управление серверами", callback_data=MainMenuAction(action='admin_servers'))
        builder.button(text="👨‍👩‍👧‍👦 Реферальная система", callback_data=MainMenuAction(action='admin_reff'))
        builder.button(text="📢 Рассылка", callback_data=MainMenuAction(action='admin_mailing'))
        builder.button(text="👥 Группы", callback_data=MainMenuAction(action='admin_groups'))
        builder.button(text="⭐ Супер предложение", callback_data=MainMenuAction(action='admin_super_offer'))
        builder.button(text="🔄 Регенерация ключей", callback_data=MainMenuAction(action='admin_regenerate'))
        builder.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu'))
        builder.adjust(1)

        try:
            await callback.message.edit_text(
                text="⚙️ <b>Панель администратора</b>\n\n"
                     "Выберите действие:",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except:
            try:
                await callback.message.delete()
            except:
                pass
            await bot.send_message(
                chat_id=callback.from_user.id,
                text="⚙️ <b>Панель администратора</b>\n\n"
                     "Выберите действие:",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )

    # Обработчики для админских кнопок
    elif action == 'admin_users':
        from bot.handlers.admin.user_management import command as user_management_handler
        await user_management_handler(callback.message, state)

    elif action == 'admin_promo':
        from bot.handlers.admin.referal_admin import promo_handler
        await promo_handler(callback.message, state)

    elif action == 'admin_servers':
        from bot.handlers.admin.main import command as servers_handler
        await servers_handler(callback.message, state)

    elif action == 'admin_reff':
        from bot.handlers.admin.referal_admin import referral_system_handler
        await referral_system_handler(callback.message, state)

    elif action == 'admin_mailing':
        from bot.handlers.admin.main import out_message_bot
        await out_message_bot(callback.message, state)

    elif action == 'admin_groups':
        from bot.handlers.admin.group_mangment import group_panel
        await group_panel(callback.message, state)

    elif action == 'admin_super_offer':
        from bot.handlers.admin.main import start_super_offer_dialog
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        # Super offer uses aiogram-dialog, need to get dialog manager from middleware
        # For now, send message that this function requires dialog manager
        await callback.message.edit_text(
            text="⭐ Супер предложение\n\nЭта функция использует специальный dialog. Пожалуйста, используйте команду из текстового меню.",
            reply_markup=InlineKeyboardBuilder().button(
                text="⬅️ Назад",
                callback_data=MainMenuAction(action='admin')
            ).as_markup()
        )
        return

    elif action == 'admin_regenerate':
        from bot.handlers.admin.main import regenerate_keys_menu
        await regenerate_keys_menu(callback.message, state)

    elif action == 'back_to_menu':
        # Возврат в главное меню
        from bot.misc.util import CONFIG
        from bot.keyboards.inline.user_inline import user_menu_inline
        from datetime import datetime
        import time

        person = await get_person(callback.from_user.id)
        subscription_end = datetime.utcfromtimestamp(
            int(person.subscription) + CONFIG.UTC_time * 3600
        ).strftime('%d.%m.%Y %H:%M')

        # Определяем статус подписки (только по timestamp, игнорируем флаг subscription_expired)
        if person.subscription < int(time.time()):
            subscription_info = f"❌ Подписка истекла: {subscription_end}"
        else:
            subscription_info = f"⏰ Подписка активна до: {subscription_end}"

        message_text = _('start_message', lang).format(
            subscription_info=subscription_info,
            tgid=person.tgid,
            balance=person.balance,
            referral_money=person.referral_balance
        )

        try:
            # Пробуем отредактировать текст
            await callback.message.edit_text(
                text=message_text,
                reply_markup=await user_menu_inline(person, lang)
            )
        except:
            # Если не получилось, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass

            await bot.send_message(
                chat_id=callback.from_user.id,
                text=message_text,
                reply_markup=await user_menu_inline(person, lang)
            )


def create_back_to_menu_keyboard(lang):
    """Создает клавиатуру с кнопкой Назад"""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=MainMenuAction(action='back_to_menu').pack())
    return kb.as_markup()
