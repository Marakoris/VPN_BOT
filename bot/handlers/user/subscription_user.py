"""
Subscription handlers for user

Handles subscription URL generation and management
"""
import logging
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

    # Create keyboard with helpful links
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📱 V2RayNG (Android)",
            url="https://play.google.com/store/apps/details?id=com.v2ray.ang"
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🍎 Shadowrocket (iOS)",
            url="https://apps.apple.com/app/shadowrocket/id932747118"
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="📋 Copy URL",
            url=subscription_url
        )
    )

    message_text = (
        "✅ <b>Your Subscription URL:</b>\n\n"
        f"<code>{subscription_url}</code>\n\n"
        "📱 <b>How to use:</b>\n"
        "1. Install V2RayNG (Android) or Shadowrocket (iOS)\n"
        "2. Add subscription using URL above\n"
        "3. Update subscription to get all servers\n"
        "4. Connect to any server!\n\n"
        "🔄 The URL updates automatically when servers change"
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

    # Show processing message
    await callback.answer("⏳ Activating...")
    await callback.message.edit_text("⏳ <b>Activating subscription...</b>\n\nPlease wait, creating keys on all servers...")

    # Activate subscription
    try:
        token = await activate_subscription(person.tgid)

        if not token:
            await callback.message.edit_text("❌ <b>Activation failed</b>\n\nPlease try again later or contact support.")
            return

        # Success - show subscription URL
        subscription_url = f"{CONFIG.subscription_api_url}/sub/{token}"

        # Create keyboard with helpful links
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(
                text="📱 V2RayNG (Android)",
                url="https://play.google.com/store/apps/details?id=com.v2ray.ang"
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="🍎 Shadowrocket (iOS)",
                url="https://apps.apple.com/app/shadowrocket/id932747118"
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="📋 Copy URL",
                url=subscription_url
            )
        )

        message_text = (
            "✅ <b>Subscription Activated!</b>\n\n"
            f"<code>{subscription_url}</code>\n\n"
            "📱 <b>Next steps:</b>\n"
            "1. Install V2RayNG (Android) or Shadowrocket (iOS)\n"
            "2. Add subscription using URL above\n"
            "3. Update subscription to get all servers\n"
            "4. Connect and enjoy!\n\n"
            "🔄 URL updates automatically"
        )

        await callback.message.edit_text(
            message_text,
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        log.error(f"Subscription activation error: {e}")
        await callback.message.edit_text("❌ <b>Error activating subscription</b>\n\nPlease try again later.")
