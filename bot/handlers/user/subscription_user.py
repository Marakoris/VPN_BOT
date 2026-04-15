"""
Subscription handlers for user

Handles subscription URL generation and management
"""
import logging
import time
import urllib.parse
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from bot.database.methods.get import get_person
from bot.misc.subscription import activate_subscription, get_user_subscription_status, sync_subscription_keys
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

subscription_router = Router()


# ==================== PERSONAL CABINET HANDLER ====================

@subscription_router.message(F.text.in_(["🌐 Личный кабинет", "🌐 Personal Cabinet"]))
async def personal_cabinet_handler(message: Message, state: FSMContext) -> None:
    """Send personal dashboard auth link to user."""
    lang = await get_lang(message.from_user.id, state)
    person = await get_person(message.from_user.id)

    if not person:
        await message.answer("❌ User not found")
        return

    # Get or generate subscription token
    from bot.misc.subscription import generate_subscription_token
    status = await get_user_subscription_status(person.tgid)
    token = status.get('token') if status else None

    if not token:
        # Generate and save token
        from sqlalchemy import select as sa_select
        from sqlalchemy.ext.asyncio import AsyncSession as AS
        from bot.database.main import engine as db_engine
        from bot.database.models.main import Persons as PersonsModel
        token = generate_subscription_token(person.id)
        async with AS(autoflush=False, bind=db_engine()) as db:
            stmt = sa_select(PersonsModel).filter(PersonsModel.tgid == person.tgid)
            result = await db.execute(stmt)
            u = result.scalar_one_or_none()
            if u:
                u.subscription_token = token
                await db.commit()

    encoded_token = urllib.parse.quote(token, safe='')
    cabinet_url = f"{CONFIG.subscription_api_url}/dashboard/auth/token?t={encoded_token}"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="🌐 Открыть личный кабинет",
        url=cabinet_url
    ))

    await message.answer(
        "🌐 <b>Личный кабинет</b>\n\n"
        "Нажмите кнопку ниже, чтобы открыть личный кабинет "
        "в браузере.\n\n"
        "Там вы можете:\n"
        "• Просмотреть статус подписки\n"
        "• Проверить трафик\n"
        "• Пополнить баланс\n"
        "• Получить ссылку подключения",
        reply_markup=kb.as_markup()
    )


# ==================== SUBSCRIPTION URL HANDLER ====================

@subscription_router.message(F.text.in_(["🔌 Подключить VPN", "📲 Subscription URL", "📲 Subscription", "Subscription"]))
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

    # User has active subscription - sync keys on new servers first
    sync_result = await sync_subscription_keys(person.tgid)
    if sync_result['created'] > 0:
        log.info(f"[Subscription] Synced {sync_result['created']} new keys for user {person.tgid}")

    # Show URL
    # URL-encode token (base64 may contain = which needs encoding)
    encoded_token = urllib.parse.quote(status['token'], safe='')
    subscription_url = f"{CONFIG.subscription_api_url}/sub/{encoded_token}"
    connect_url = f"{CONFIG.subscription_api_url}/connect/{encoded_token}"
    # Raw URL for happ:// deep links (without URL encoding)
    raw_subscription_url = f"{CONFIG.subscription_api_url}/sub/{status['token']}"

    # Create keyboard with Happ download links (by platform)
    kb = InlineKeyboardBuilder()

    # 🔌 ГЛАВНАЯ КНОПКА - Подключиться (страница выбора протокола)
    kb.row(
        InlineKeyboardButton(
            text="🔌 Подключиться",
            url=connect_url
        )
    )

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
    # Windows с deep link для Happ (используем raw URL без encoding)
    happ_deep_link = f"happ://add/{raw_subscription_url}"
    kb.row(
        InlineKeyboardButton(
            text="🖥 Скачать Happ (Win)",
            url="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"
        ),
        InlineKeyboardButton(
            text="📲 Добавить в Happ",
            url=happ_deep_link
        )
    )
    # macOS
    kb.row(
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
        "📱 <b>Как подключиться:</b>\n"
        "Нажмите <b>🔌 Подключиться</b> — откроется страница настройки, "
        "где можно скачать приложение и добавить подписку\n\n"
        "📋 <b>Или вручную:</b>\n"
        "1. Установите приложение Happ\n"
        "2. Скопируйте URL выше\n"
        "3. Вставьте в приложении\n\n"
        "🔄 Список серверов обновляется автоматически"
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

    # Проверяем, не забанен ли пользователь (истекла подписка или реальный бан)
    if person.banned:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="💳 Продлить подписку",
            callback_data="buy_subscription"
        ))
        await callback.answer("⏰ Подписка истекла", show_alert=True)
        await callback.message.edit_text(
            "⏰ <b>Ваша подписка закончилась!</b>\n\n"
            "Если хотите продолжить пользоваться нашими услугами, "
            "пожалуйста продлите подписку.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
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
            "⏰ <b>Ваша подписка закончилась!</b>\n\n"
            "Если хотите продолжить пользоваться нашими услугами, "
            "пожалуйста продлите подписку.",
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
        # URL-encode token (base64 may contain = which needs encoding)
        encoded_token = urllib.parse.quote(token, safe='')
        subscription_url = f"{CONFIG.subscription_api_url}/sub/{encoded_token}"
        connect_url = f"{CONFIG.subscription_api_url}/connect/{encoded_token}"
        # Raw URL for happ:// deep links (without URL encoding)
        raw_subscription_url = f"{CONFIG.subscription_api_url}/sub/{token}"

        # Create keyboard with Happ download links (by platform)
        kb = InlineKeyboardBuilder()

        # 🔌 ГЛАВНАЯ КНОПКА - Подключиться (страница выбора протокола)
        kb.row(
            InlineKeyboardButton(
                text="🔌 Подключиться",
                url=connect_url
            )
        )

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
        # Windows с deep link для Happ (используем raw URL без encoding)
        happ_deep_link = f"happ://add/{raw_subscription_url}"
        kb.row(
            InlineKeyboardButton(
                text="🖥 Скачать Happ (Win)",
                url="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"
            ),
            InlineKeyboardButton(
                text="📲 Добавить в Happ",
                url=happ_deep_link
            )
        )
        # macOS
        kb.row(
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
            "📱 <b>Как подключиться:</b>\n"
            "Нажмите <b>🔌 Подключиться</b> — откроется страница настройки, "
            "где можно скачать приложение и добавить подписку\n\n"
            "📋 <b>Или вручную:</b>\n"
            "1. Установите приложение Happ\n"
            "2. Скопируйте URL выше\n"
            "3. Вставьте в приложении\n\n"
            "🔄 Список серверов обновляется автоматически"
        )

        await callback.message.edit_text(
            message_text,
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        log.error(f"Subscription activation error: {e}")
        await callback.message.edit_text("❌ <b>Error activating subscription</b>\n\nPlease try again later.")


# ==================== BYPASS QR CODE ====================

@subscription_router.callback_query(F.data == "bypass_qr")
async def bypass_qr_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Show submenu: bypass mode (whitelist) or full subscription."""
    await callback.answer()

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📱 Мобильный режим (LTE / мобильный интернет)",
        callback_data="bypass_qr_whitelist"
    ))
    kb.row(InlineKeyboardButton(
        text="🌍 Полная подписка (Wi-Fi / обычный интернет)",
        callback_data="bypass_qr_full"
    ))

    await callback.message.answer(
        "📲 <b>Добавить подписку на устройство</b>\n\n"
        "📱 <b>Мобильный режим</b> — если VPN не запускается на мобильном интернете (LTE). "
        "Сначала добавьте мобильный сервер, затем подключитесь и обновите подписку.\n\n"
        "🌍 <b>Полная подписка</b> — если на устройстве есть обычный интернет "
        "(Wi-Fi, VPN, безлимитный LTE). Добавьте всю подписку сразу.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@subscription_router.callback_query(F.data == "bypass_qr_whitelist")
async def bypass_qr_whitelist_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Generate QR codes for both bypass servers."""
    person = await get_person(callback.from_user.id)

    if not person:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    if not person.subscription or person.subscription < int(time.time()):
        await callback.answer("⏰ Подписка не активна", show_alert=True)
        return

    await callback.answer("⏳ Генерирую QR-коды...")

    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        from bot.database.main import engine
        from bot.database.models.main import Servers
        from bot.misc.VPN.ServerManager import ServerManager
        import io
        import qrcode
        from aiogram.types import BufferedInputFile, InputMediaPhoto

        # Get all bypass servers
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(Servers).filter(
                Servers.work == True,
                Servers.is_bypass == True,
                Servers.type_vpn.in_([1, 2])
            ).order_by(Servers.id)
            result = await db.execute(stmt)
            bypass_servers = result.scalars().all()

        if not bypass_servers:
            await callback.message.answer(
                "❌ <b>Мобильные серверы временно недоступны</b>\n\nОбратитесь в поддержку.",
                parse_mode="HTML"
            )
            return

        # Collect keys from all bypass servers
        keys = []
        for server in bypass_servers:
            try:
                sm = ServerManager(server)
                await sm.login()
                key = await sm.get_key(str(person.tgid), f"Bypass {server.name}")
                if key:
                    keys.append((server.name, key))
            except Exception as e:
                log.warning(f"[BypassQR] Failed to get key from {server.name}: {e}")

        if not keys:
            await callback.message.answer(
                "❌ <b>Не удалось получить ключи</b>\n\nПопробуйте позже или обратитесь в поддержку.",
                parse_mode="HTML"
            )
            return

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💬 Написать в поддержку", url="https://t.me/VPN_YouSupport_bot"))

        await callback.message.answer(
            "📱 <b>QR-коды для мобильного режима</b>\n\n"
            "<b>Инструкция:</b>\n"
            "1. Откройте <b>Happ</b> на устройстве где не работает VPN\n"
            "2. Отсканируйте один из QR-кодов ниже\n"
            "3. Подключитесь к мобильному серверу\n"
            "4. Теперь в Happ обновите подписку — появятся все серверы\n\n"
            "💡 <i>Достаточно добавить один любой сервер</i>",
            parse_mode="HTML"
        )

        # Send QR for each bypass server
        for server_name, vless_link in keys:
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(vless_link)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            photo = BufferedInputFile(buf.read(), filename=f"bypass_qr_{server_name}.png")
            await callback.message.answer_photo(
                photo=photo,
                caption=(
                    f"🖥 <b>{server_name}</b>\n\n"
                    f"<tg-spoiler>{vless_link}</tg-spoiler>"
                ),
                reply_markup=kb.as_markup() if server_name == keys[-1][0] else None,
                parse_mode="HTML"
            )

    except Exception as e:
        log.error(f"[BypassQR] Error: {e}")
        await callback.message.answer(
            "❌ <b>Ошибка генерации QR-кода</b>\n\nПопробуйте позже.",
            parse_mode="HTML"
        )


@subscription_router.callback_query(F.data == "bypass_qr_full")
async def bypass_qr_full_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Generate QR code with full subscription link."""
    person = await get_person(callback.from_user.id)

    if not person:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    if not person.subscription or person.subscription < int(time.time()):
        await callback.answer("⏰ Подписка не активна", show_alert=True)
        return

    if not person.subscription_token:
        await callback.answer("❌ Токен подписки не найден", show_alert=True)
        return

    await callback.answer("⏳ Генерирую QR-код...")

    try:
        import io
        import qrcode
        from aiogram.types import BufferedInputFile
        from urllib.parse import quote

        connect_url = f"{CONFIG.subscription_api_url}/connect/{quote(person.subscription_token, safe='')}"

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(connect_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        photo = BufferedInputFile(buf.read(), filename="subscription_qr.png")

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔌 Открыть ссылку", url=connect_url))
        kb.row(InlineKeyboardButton(text="💬 Написать в поддержку", url="https://t.me/VPN_YouSupport_bot"))

        await callback.message.answer_photo(
            photo=photo,
            caption=(
                "🌍 <b>QR-код полной подписки</b>\n\n"
                "<b>Инструкция:</b>\n"
                "1. Откройте <b>Happ</b> на устройстве\n"
                "2. Отсканируйте QR-код или нажмите кнопку «Открыть ссылку»\n"
                "3. Все серверы добавятся автоматически\n\n"
                "⚠️ <i>Требуется обычный доступ к интернету (Wi-Fi или безлимитный LTE)</i>"
            ),
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    except Exception as e:
        log.error(f"[FullSubQR] Error: {e}")
        await callback.message.answer(
            "❌ <b>Ошибка генерации QR-кода</b>\n\nПопробуйте позже.",
            parse_mode="HTML"
        )
