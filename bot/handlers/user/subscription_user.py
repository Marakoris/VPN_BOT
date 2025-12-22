"""
Subscription handlers for user

Handles subscription URL generation and management
"""
import logging
import time
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from bot.database.methods.get import get_person
from bot.misc.subscription import activate_subscription, get_user_subscription_status
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

subscription_router = Router()


# ==================== SUBSCRIPTION URL HANDLER ====================

@subscription_router.message(F.text.in_(["📲 Subscription URL", "📲 Subscription", "Subscription"]))
async def get_subscription_url(message: Message, state: FSMContext) -> None:
    """
    Handler for getting subscription URL

    Shows user their personal subscription URL for V2RayNG/Shadowrocket
    """
    lang = await get_lang(message.from_user.id, state)
    person = await get_person(message.from_user.id)

    if not person:
        await message.answer("❌ User not found")
        return

    # Check if subscription is active
    status = await get_user_subscription_status(person.tgid)

    if 'error' in status:
        await message.answer("❌ Error getting subscription status")
        return

    # If no token exists or subscription not active, offer to activate
    if not status.get('token') or not status.get('active'):
        await message.answer(
            "⚠️ Subscription not active. Click button below to activate:",
            reply_markup=await create_activate_keyboard(lang)
        )
        return

    # User has active subscription - show URL
    subscription_url = f"{CONFIG.subscription_api_url}/sub/{status['token']}"

    # Create keyboard with Happ download links (by platform)
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

    message_text = (
        "✅ <b>Ваш Subscription URL:</b>\n\n"
        f"<code>{subscription_url}</code>\n\n"
        "📱 <b>Как использовать:</b>\n"
        "1. Скачайте приложение Happ для вашей платформы\n"
        "2. Откройте приложение и добавьте подписку по URL выше\n"
        "3. Обновите список серверов\n"
        "4. Подключайтесь к любому серверу!\n\n"
        "🔄 URL обновляется автоматически при изменении серверов"
    )

    await message.answer(
        message_text,
        reply_markup=kb.as_markup()
    )


# ==================== ACTIVATION KEYBOARD ====================

async def create_activate_keyboard(lang):
    """Create keyboard for subscription activation"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Activate Subscription",
            callback_data="activate_subscription"
        )
    )
    return kb.as_markup()


# ==================== CALLBACK HANDLER ====================

@subscription_router.callback_query(F.data == "activate_subscription")
async def activate_subscription_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Handle subscription activation callback

    Activates subscription for user (creates keys on all servers)
    """
    lang = await get_lang(callback.from_user.id, state)
    person = await get_person(callback.from_user.id)

    if not person:
        await callback.answer("❌ User not found", show_alert=True)
        return

    # Проверяем, не забанен ли пользователь (РЕАЛЬНЫЙ бан)
    if person.banned:
        await callback.answer("⛔ Доступ заблокирован", show_alert=True)
        await callback.message.edit_text("⛔ <b>Доступ заблокирован</b>\n\nВаш аккаунт заблокирован.", parse_mode="HTML")
        return

    # Проверяем, не истекла ли подписка (только по timestamp)
    if person.subscription < int(time.time()):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="💳 Продлить подписку",
            callback_data="buy_subscription"
        ))
        await callback.answer("⏰ Подписка истекла", show_alert=True)
        await callback.message.edit_text(
            "⏰ <b>Подписка истекла</b>\n\nДля активации Единой подписки необходимо продлить подписку.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        return

    # Show processing message
    await callback.answer("⏳ Activating...")
    await callback.message.edit_text("⏳ <b>Activating subscription...</b>\n\nPlease wait, creating keys on all servers...")

    # Activate subscription
    # include_outline=True to activate ALL protocols (VLESS, Shadowsocks, Outline)
    try:
        token = await activate_subscription(person.tgid, include_outline=True)

        if not token:
            await callback.message.edit_text("❌ <b>Activation failed</b>\n\nPlease try again later or contact support.")
            return

        # Success - show subscription URL
        subscription_url = f"{CONFIG.subscription_api_url}/sub/{token}"

        # Create keyboard with Happ download links (by platform)
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

        message_text = (
            "✅ <b>Подписка активирована!</b>\n\n"
            f"<code>{subscription_url}</code>\n\n"
            "📱 <b>Следующие шаги:</b>\n"
            "1. Скачайте приложение Happ для вашей платформы\n"
            "2. Добавьте подписку используя URL выше\n"
            "3. Обновите список серверов\n"
            "4. Подключайтесь и наслаждайтесь!\n\n"
            "🔄 URL обновляется автоматически"
        )

        await callback.message.edit_text(
            message_text,
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        log.error(f"Subscription activation error: {e}")
        await callback.message.edit_text("❌ <b>Error activating subscription</b>\n\nPlease try again later.")
