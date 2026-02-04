import io
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.utils.formatting import Text, Code
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.methods.delete import delete_promo_code
from bot.database.methods.get import (
    get_all_promo_code,
    get_all_application_referral,
    get_application_referral_check_false,
    get_promo_code,
    get_promo_usage_with_dates
)
from bot.database.methods.insert import add_promo
from bot.database.methods.update import succes_aplication
from bot.keyboards.inline.admin_inline import (
    promocode_menu,
    promocode_delete,
    application_referral_menu, application_success,
    admin_back_inline_menu
)
from bot.keyboards.reply.admin_reply import back_admin_menu, admin_menu
from bot.misc.callbackData import (
    PromocodeDelete,
    PromocodeAction,
    AplicationReferral,
    ApplicationSuccess,
    AdminMenuNav
)
from bot.misc.language import Localization, get_lang

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

referral_router = Router()


class NewPromo(StatesGroup):
    input_text_promo = State()
    input_price_promo = State()
    input_expires = State()  # Срок действия промокода


@referral_router.message(F.text.in_(btn_text('admin_promo_btn')))
async def promo_handler(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('control_promo_text', lang),
        reply_markup=await promocode_menu(lang)
    )


@referral_router.message(F.text.in_(btn_text('admin_reff_system_btn')))
async def referral_system_handler(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('who_width_text', lang),
        reply_markup=await application_referral_menu(lang)
    )


@referral_router.callback_query(AplicationReferral.filter())
async def callback_work_server(
        call: CallbackQuery,
        callback_data: AplicationReferral,
        state: FSMContext
):
    lang = await get_lang(call.from_user.id, state)
    if callback_data.type:
        application_referral = await get_all_application_referral()
    else:
        application_referral = await get_application_referral_check_false()
    if len(application_referral) == 0:
        await call.message.answer(_('not_withdrawal', lang))
    for application in application_referral:
        text_application = await show_application_referral(application, lang)
        if application.check_payment:
            await call.message.answer(**text_application.as_kwargs())
        else:
            await call.message.answer(
                **text_application.as_kwargs(),
                reply_markup=await application_success(
                    application.id,
                    call.message.message_id,
                    lang
                )
            )
    await call.answer()


async def show_application_referral(data, lang):
    if data.check_payment:
        check_payment = _('withdrawal_success', lang)
    else:
        check_payment = _('withdrawal_payment_expected', lang)
    return Text(
        _('withdrawal_number_s', lang), data.id, '\n',
        _('withdrawal_amount_s', lang), Code(data.amount), '₽\n',
        _('withdrawal_info_s', lang), data.payment_info, '\n',
        _('withdrawal_user_connect_s', lang), data.communication, '\n',
        _('withdrawal_telegram_id_s', lang), Code(data.user_tgid), '\n',
        _('withdrawal_condition_s', lang), check_payment
    )


@referral_router.callback_query(F.data == 'new_promo')
async def callback_new_promo(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(call.from_user.id, state)
    from bot.keyboards.inline.admin_inline import admin_back_inline_menu
    await call.message.edit_text(
        f"{_('create_new_promo_text', lang)}\n\n{_('input_text_promo_message', lang)}",
        reply_markup=await admin_back_inline_menu('promo', lang)
    )
    await state.set_state(NewPromo.input_text_promo)
    await call.answer()


@referral_router.message(NewPromo.input_text_promo)
async def input_name(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    from bot.keyboards.inline.admin_inline import admin_back_inline_menu, admin_main_inline_menu
    try:
        await state.update_data(text_promo=message.text.strip())
        await message.answer(
            _('input_amount_add_days_message', lang),
            reply_markup=await admin_back_inline_menu('promo', lang)
        )
        await state.set_state(NewPromo.input_price_promo)
    except Exception as e:
        await message.answer(
            _('error_not_found', lang),
            reply_markup=await admin_main_inline_menu(lang)
        )
        log.error(e, 'error input name promo')
        await state.clear()


@referral_router.message(NewPromo.input_price_promo)
async def input_price_promo(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    from bot.keyboards.inline.admin_inline import admin_back_inline_menu
    try:
        add_days = int(message.text.strip())
    except Exception as e:
        await message.answer(_('error_input_number_add_days', lang))
        log.info(e)
        return

    await state.update_data(add_days=add_days)

    # Создаем кнопки для срока действия
    kb = InlineKeyboardBuilder()
    kb.button(text="7 дней", callback_data="promo_expires:7")
    kb.button(text="30 дней", callback_data="promo_expires:30")
    kb.button(text="90 дней", callback_data="promo_expires:90")
    kb.button(text="♾ Бессрочный", callback_data="promo_expires:0")
    kb.adjust(2)

    await message.answer(
        "📅 Выберите срок действия промокода:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(NewPromo.input_expires)


@referral_router.callback_query(F.data.startswith("promo_expires:"))
async def input_expires_promo(call: CallbackQuery, state: FSMContext):
    from datetime import datetime, timedelta
    from bot.keyboards.inline.admin_inline import promocode_menu

    lang = await get_lang(call.from_user.id, state)
    days = int(call.data.split(":")[1])

    data = await state.get_data()
    text_promo = data.get('text_promo')
    add_days = data.get('add_days')

    # Вычисляем дату истечения
    expires_at = None
    if days > 0:
        expires_at = datetime.now() + timedelta(days=days)

    try:
        await add_promo(text_promo, add_days, expires_at)

        expires_text = f"до {expires_at.strftime('%d.%m.%Y')}" if expires_at else "бессрочно"
        await call.message.edit_text(
            f"✅ Промокод <code>{text_promo}</code> создан!\n\n"
            f"📅 Дней подписки: {add_days}\n"
            f"⏰ Действует: {expires_text}",
            reply_markup=await promocode_menu(lang)
        )
    except Exception as e:
        await call.message.edit_text(
            _('error_new_promo_text', lang),
            reply_markup=await promocode_menu(lang)
        )
        log.error(f"Error creating promo: {e}")

    await call.answer()
    await state.clear()


@referral_router.callback_query(F.data.startswith('show_promo'))
async def callback_show_promo(call: CallbackQuery, state: FSMContext):
    from datetime import datetime

    lang = await get_lang(call.from_user.id, state)
    all_promo = await get_all_promo_code()

    # Определяем фильтр (active/archived/all)
    filter_type = 'active'  # по умолчанию
    if ':' in call.data:
        filter_type = call.data.split(':')[1]

    now = datetime.now()

    # Разделяем промокоды на активные и архивные
    active_promos = []
    archived_promos = []
    for promo in all_promo:
        if promo.expires_at and promo.expires_at < now:
            archived_promos.append(promo)
        else:
            active_promos.append(promo)

    # Выбираем какие показывать
    if filter_type == 'active':
        display_promos = active_promos
        title = "🎟 <b>Активные промокоды</b>"
    elif filter_type == 'archived':
        display_promos = archived_promos
        title = "📦 <b>Архивные промокоды</b>"
    else:
        display_promos = all_promo
        title = "🎟 <b>Все промокоды</b>"

    if len(display_promos) == 0:
        text = f"{title}\n\n❌ Нет промокодов"
    else:
        text = f"{title}\n\n"
        for promo in display_promos:
            usage_count = len(promo.person) if promo.person else 0
            # Статус промокода
            if promo.expires_at:
                if promo.expires_at < now:
                    status = "❌"
                else:
                    days_left = (promo.expires_at - now).days
                    status = f"⏰{days_left}д"
            else:
                status = "♾"
            text += (
                f"{status} <code>{promo.text}</code> — "
                f"{promo.add_days} дн. — "
                f"исп. {usage_count}\n"
            )

    text += "\n<i>Нажмите на промокод для деталей</i>"

    # Кнопки промокодов
    kb = InlineKeyboardBuilder()
    for promo in display_promos:
        usage_count = len(promo.person) if promo.person else 0
        # Иконка статуса в кнопке
        if promo.expires_at and promo.expires_at < now:
            icon = "❌"
        elif promo.expires_at:
            icon = "⏰"
        else:
            icon = "♾"
        kb.button(
            text=f"{icon} {promo.text} ({usage_count})",
            callback_data=PromocodeAction(id_promo=promo.id, action='view')
        )
    kb.adjust(2)

    # Кнопки фильтров
    kb.row()
    if filter_type != 'active':
        kb.button(text=f"✅ Активные ({len(active_promos)})", callback_data="show_promo:active")
    if filter_type != 'archived':
        kb.button(text=f"📦 Архив ({len(archived_promos)})", callback_data="show_promo:archived")
    kb.row()
    kb.button(text='⬅️ Назад', callback_data=AdminMenuNav(menu='promo').pack())

    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


@referral_router.callback_query(PromocodeAction.filter())
async def callback_promo_action(
        call: CallbackQuery,
        callback_data: PromocodeAction,
        state: FSMContext
):
    lang = await get_lang(call.from_user.id, state)
    promo_id = callback_data.id_promo
    action = callback_data.action

    # Получаем промокод
    all_promos = await get_all_promo_code()
    promo = next((p for p in all_promos if p.id == promo_id), None)

    if not promo:
        await call.answer("❌ Промокод не найден", show_alert=True)
        return

    if action == 'view':
        from datetime import datetime
        now = datetime.now()

        # Показываем детали промокода с датами использования
        usages = await get_promo_usage_with_dates(promo.id)
        usage_count = len(usages)

        # Статус промокода
        if promo.expires_at:
            if promo.expires_at < now:
                status = "❌ <b>Истёк</b>"
                expires_text = promo.expires_at.strftime("%d.%m.%Y")
            else:
                days_left = (promo.expires_at - now).days
                status = f"✅ <b>Активен</b> (ещё {days_left} дн.)"
                expires_text = promo.expires_at.strftime("%d.%m.%Y")
        else:
            status = "♾ <b>Бессрочный</b>"
            expires_text = None

        text = (
            f"🎟 <b>Промокод:</b> <code>{promo.text}</code>\n\n"
            f"📅 Дней подписки: <b>{promo.add_days}</b>\n"
            f"⏰ Статус: {status}\n"
        )
        if expires_text:
            text += f"📆 Действует до: {expires_text}\n"
        if promo.created_at:
            text += f"🕐 Создан: {promo.created_at.strftime('%d.%m.%Y')}\n"
        text += f"👥 Использован: <b>{usage_count}</b> раз\n"

        # Показываем кто использовал с датой (до 10 пользователей в сообщении)
        if usages:
            text += "\n<b>Использовали:</b>\n"
            for i, (tgid, username, fullname, used_at) in enumerate(usages[:10], 1):
                user_name = f"@{username}" if username else f"ID:{tgid}"
                date_str = used_at.strftime("%d.%m.%Y %H:%M") if used_at else "—"
                text += f"  {i}. {user_name} — {date_str}\n"
            if len(usages) > 10:
                text += f"  <i>...и ещё {len(usages) - 10}</i>\n"

        kb = InlineKeyboardBuilder()
        if usage_count > 10:
            kb.button(
                text=f"📄 Скачать полный список ({usage_count})",
                callback_data=PromocodeAction(id_promo=promo.id, action='stats')
            )
        kb.button(
            text="🗑 Удалить",
            callback_data=PromocodeAction(id_promo=promo.id, action='delete')
        )
        kb.button(
            text="⬅️ К списку",
            callback_data='show_promo'
        )
        kb.adjust(1)

        await call.message.edit_text(text, reply_markup=kb.as_markup())
        await call.answer()

    elif action == 'delete':
        # Спрашиваем подтверждение
        text = (
            f"❓ <b>Удалить промокод?</b>\n\n"
            f"<code>{promo.text}</code>\n"
            f"Дней: {promo.add_days}\n\n"
            f"⚠️ Это действие нельзя отменить"
        )

        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Да, удалить",
            callback_data=PromocodeAction(id_promo=promo.id, action='confirm_delete')
        )
        kb.button(
            text="❌ Отмена",
            callback_data=PromocodeAction(id_promo=promo.id, action='view')
        )
        kb.adjust(2)

        await call.message.edit_text(text, reply_markup=kb.as_markup())
        await call.answer()

    elif action == 'confirm_delete':
        # Удаляем промокод
        try:
            promo_text = promo.text
            await delete_promo_code(promo_id)
            await call.answer(f"✅ Промокод {promo_text} удалён", show_alert=True)
            # Возвращаемся к списку
            await callback_show_promo(call, state)
        except Exception as e:
            log.error(f"Error deleting promo: {e}")
            await call.answer("❌ Ошибка удаления", show_alert=True)

    elif action == 'stats':
        # Формируем файл со статистикой с датами
        usages = await get_promo_usage_with_dates(promo.id)
        if not usages:
            await call.answer("❌ Нет данных об использовании", show_alert=True)
            return

        str_stats = f"Промокод: {promo.text}\n"
        str_stats += f"Дней: {promo.add_days}\n"
        str_stats += f"Использований: {len(usages)}\n"
        str_stats += "=" * 40 + "\n\n"
        str_stats += "Кто использовал:\n\n"

        for i, (tgid, username, fullname, used_at) in enumerate(usages, 1):
            date_str = used_at.strftime("%d.%m.%Y %H:%M") if used_at else "—"
            str_stats += (
                f"{i}. @{username or 'N/A'}\n"
                f"   ID: {tgid}\n"
                f"   Имя: {fullname or 'N/A'}\n"
                f"   Дата: {date_str}\n\n"
            )

        file_stream = io.BytesIO(str_stats.encode()).getvalue()
        input_file = BufferedInputFile(file_stream, f'promo_{promo.text}_stats.txt')

        await call.message.answer_document(
            input_file,
            caption=f"📊 Статистика промокода <code>{promo.text}</code>"
        )
        await call.answer()


@referral_router.callback_query(PromocodeDelete.filter())
async def callback_delete_promo(
        call: CallbackQuery,
        callback_data: PromocodeDelete,
        state: FSMContext
):
    lang = await get_lang(call.from_user.id, state)
    try:
        id_promo = callback_data.id_promo
        await delete_promo_code(id_promo)
        await call.message.answer(_('promo_delete_text', lang))
    except Exception as e:
        await call.message.answer(_('error_promo_delete_text', lang))
        log.error(e, 'error delete promo code')
    try:
        mes_id = callback_data.mes_id
        # await call.message.edit_text(_('promo_delete_text', lang), str(mes_id))
    except Exception as e:
        log.error(e, 'error edit message')
    await call.answer()


@referral_router.callback_query(ApplicationSuccess.filter())
async def callback_success_application(
        call: CallbackQuery,
        callback_data: ApplicationSuccess,
        state: FSMContext
):
    lang = await get_lang(call.from_user.id, state)
    try:
        await succes_aplication(callback_data.id_application)
        await call.message.answer(_('application_paid', lang))
    except Exception as e:
        await call.message.answer(_('application_error_save', lang))
        log.error(e, 'error save application')
    try:
        mes_id = callback_data.mes_id
        await call.message.edit_text(
            _('application_success_text', lang),
            str(mes_id)
        )
    except Exception as e:
        log.error(e, 'error edit message')
    await call.answer()
