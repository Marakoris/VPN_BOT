"""
Outline VPN handlers

Handles Outline server selection and key creation on-demand.
Part of simplified menu refactoring (2025-12-08).
"""
import logging
import time
import base64
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, WebAppInfo

from bot.database.methods.get import get_person, get_server_id, get_free_servers
from bot.database.methods.update import add_user_in_server, server_space_update
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.callbackData import ChooseOutlineServer
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

# Outline page base URL
OUTLINE_PAGE_URL = "https://vpnnoborder.sytes.net/outline"

log = logging.getLogger(__name__)
_ = Localization.text
btn_text = Localization.get_reply_button

outline_router = Router()


@outline_router.message(F.text.in_(["🔑 Outline VPN", "Outline"]))
async def outline_menu(message: Message, state: FSMContext) -> None:
    """
    Show Outline servers menu

    If user has active subscription and keys already exist - show all keys.
    Otherwise - show server selection menu for on-demand key creation.
    """
    lang = await get_lang(message.from_user.id, state)
    person = await get_person(message.from_user.id)

    if not person:
        await message.answer("❌ User not found")
        return

    # Check subscription
    if person.subscription < int(time.time()):
        await message.answer(
            _('ended_sub_message', lang),
            reply_markup=await create_buy_subscription_keyboard(lang)
        )
        return

    # Get Outline servers (type_vpn=0)
    try:
        outline_servers = await get_free_servers(
            person.group,
            type_vpn=0  # Outline only
        )
    except Exception as e:
        log.error(f"Error getting Outline servers: {e}")
        await message.answer(
            "❌ Outline серверы временно недоступны\n\n"
            "Используйте: 📲 Subscription URL для VLESS/Shadowsocks"
        )
        return

    if not outline_servers:
        await message.answer(
            "❌ Нет доступных Outline серверов\n\n"
            "Используйте: 📲 Subscription URL для VLESS/Shadowsocks"
        )
        return

    # Always show server selection menu (clean interface, scalable for many servers)
    kb = InlineKeyboardBuilder()
    for server in outline_servers:
        kb.row(
            InlineKeyboardButton(
                text=f"{server.name} 🪐",
                callback_data=ChooseOutlineServer(id_server=server.id).pack()
            )
        )

    # Add back button
    from bot.misc.callbackData import MainMenuAction
    kb.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='back_to_menu').pack()
    ))

    # Check if user has active subscription (keys already created by admin)
    if person.subscription_active:
        caption = (
            "🔑 <b>Outline VPN</b>\n\n"
            "Выберите сервер для добавления:\n\n"
            "💡 Добавляйте любое количество серверов\n"
            "💡 Все добавленные серверы сохраняются в приложении"
        )
    else:
        caption = (
            "🔑 <b>Outline VPN</b>\n\n"
            "Выберите сервер для добавления:\n\n"
            "💡 Добавляйте любое количество серверов\n"
            "💡 Все добавленные серверы сохраняются в приложении"
        )

    await message.answer(
        text=caption,
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@outline_router.callback_query(ChooseOutlineServer.filter())
async def connect_outline(
    call: CallbackQuery,
    callback_data: ChooseOutlineServer,
    state: FSMContext,
    bot
) -> None:
    """
    Connect to selected Outline server

    Creates key on-demand if doesn't exist
    """
    lang = await get_lang(call.from_user.id, state)
    choosing_server_id = callback_data.id_server
    person = await get_person(call.from_user.id)

    # Check subscription
    if person.subscription < int(time.time()):
        await call.message.answer(_('ended_sub_message', lang))
        await call.answer()
        return

    # Show processing
    await call.answer("⏳ Создание Outline ключа...")
    status_msg = await call.message.answer("⏳ <b>Подготовка подключения...</b>")

    try:
        # Get server
        server = await get_server_id(choosing_server_id)

        if server.type_vpn != 0:
            await status_msg.edit_text("❌ Это не Outline сервер")
            return

        # Create server manager
        server_manager = ServerManager(server)
        await server_manager.login()

        # Try to add client (creates new or returns False if exists)
        add_result = await server_manager.add_client(call.from_user.id)

        # If client already exists, just get the key
        if add_result is False:
            log.info(f"Outline client already exists for user {call.from_user.id}")
        elif add_result is None:
            raise Exception('Failed to create Outline client')

        # Get the key with server name for identification
        config = await server_manager.get_key(
            call.from_user.id,
            name_key=f"{CONFIG.name} - {server.name}"
        )

        # Update server space
        server_parameters = await server_manager.get_all_user()
        await add_user_in_server(call.from_user.id, server)
        await server_space_update(server.name, len(server_parameters))

    except Exception as e:
        log.error(f'Failed to connect to Outline server {choosing_server_id}: {e}')
        await status_msg.edit_text(
            "❌ <b>Не удалось подключиться</b>\n\n"
            "Попробуйте снова или обратитесь в поддержку"
        )
        return

    # Success - send link to Outline page
    try:
        await call.message.delete()
        await status_msg.delete()
    except:
        pass

    # Encode key for URL
    encoded_key = base64.urlsafe_b64encode(config.encode('utf-8')).decode('utf-8')
    outline_page_link = f"{OUTLINE_PAGE_URL}/{encoded_key}"

    # Create keyboard with link to Outline page
    kb = InlineKeyboardBuilder()

    # Кнопка открытия страницы подключения
    kb.row(
        InlineKeyboardButton(
            text="🔌 Подключиться",
            url=outline_page_link
        )
    )

    # Кнопка "Назад"
    from bot.misc.callbackData import MainMenuAction
    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MainMenuAction(action='back_to_menu').pack()
        )
    )

    # Message with link
    message_text = (
        f"🪐 <b>Outline VPN - {server.name}</b>\n\n"
        f"Нажмите кнопку ниже для подключения.\n"
        f"На странице вы найдёте:\n"
        f"• Ссылки для скачивания приложения\n"
        f"• Ваш ключ для подключения\n"
        f"• Инструкции по настройке\n\n"
        f"💡 Страница работает на всех устройствах"
    )

    await bot.send_message(
        chat_id=call.from_user.id,
        text=message_text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

    await call.answer()


async def create_buy_subscription_keyboard(lang):
    """Create keyboard for buying subscription"""
    from bot.misc.callbackData import MainMenuAction
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=_('to_extend_btn', lang),
            callback_data=MainMenuAction(action='subscription').pack()
        )
    )
    return kb.as_markup()
