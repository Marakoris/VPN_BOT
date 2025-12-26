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
    get_promo_code
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
    from bot.keyboards.inline.admin_inline import admin_main_inline_menu, promocode_menu
    try:
        try:
            promo_code = int(message.text.strip())
        except Exception as e:
            await message.answer(_('error_input_number_add_days', lang))
            log.info(e)
            return
        data = await state.get_data()
        await add_promo(data['text_promo'], promo_code)
        await message.answer(
            _('new_promo_success', lang),
            reply_markup=await promocode_menu(lang)
        )
    except Exception as e:
        await message.answer(
            _('error_new_promo_text', lang),
            reply_markup=await promocode_menu(lang)
        )
        log.info(e, 'referal_admin.py Line 131')
    await state.clear()


@referral_router.callback_query(F.data == 'show_promo')
async def callback_show_promo(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(call.from_user.id, state)
    all_promo = await get_all_promo_code()
    if len(all_promo) == 0:
        await call.message.edit_text(
            "❌ Нет промокодов",
            reply_markup=await admin_back_inline_menu('promo', lang)
        )
        await call.answer()
        return

    # Формируем компактный список промокодов
    text = "🎟 <b>Промокоды:</b>\n\n"
    for promo in all_promo:
        usage_count = len(promo.person) if promo.person else 0
        text += (
            f"<code>{promo.text}</code> — "
            f"{promo.add_days} дн. — "
            f"исп. {usage_count} раз\n"
        )

    text += "\n<i>Нажмите на промокод для деталей:</i>"

    # Кнопки для перехода в детали каждого промокода
    kb = InlineKeyboardBuilder()
    for promo in all_promo:
        usage_count = len(promo.person) if promo.person else 0
        kb.button(
            text=f"{promo.text} ({usage_count})",
            callback_data=PromocodeAction(id_promo=promo.id, action='view')
        )
    kb.adjust(2)
    kb.row()
    kb.button(
        text='⬅️ Назад',
        callback_data=AdminMenuNav(menu='promo').pack()
    )

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
        # Показываем детали промокода
        usage_count = len(promo.person) if promo.person else 0
        text = (
            f"🎟 <b>Промокод:</b> <code>{promo.text}</code>\n\n"
            f"📅 Дней: <b>{promo.add_days}</b>\n"
            f"👥 Использован: <b>{usage_count}</b> раз\n"
        )

        # Показываем кто использовал (до 10 пользователей в сообщении)
        if promo.person:
            text += "\n<b>Использовали:</b>\n"
            for i, user in enumerate(promo.person[:10], 1):
                username = f"@{user.username}" if user.username else f"ID:{user.tgid}"
                text += f"  {i}. {username}\n"
            if len(promo.person) > 10:
                text += f"  <i>...и ещё {len(promo.person) - 10}</i>\n"

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
        # Формируем файл со статистикой
        if not promo.person:
            await call.answer("❌ Нет данных об использовании", show_alert=True)
            return

        str_stats = f"Промокод: {promo.text}\n"
        str_stats += f"Дней: {promo.add_days}\n"
        str_stats += f"Использований: {len(promo.person)}\n"
        str_stats += "=" * 40 + "\n\n"
        str_stats += "Кто использовал:\n\n"

        for i, user in enumerate(promo.person, 1):
            str_stats += (
                f"{i}. @{user.username or 'N/A'}\n"
                f"   ID: {user.tgid}\n"
                f"   Имя: {user.fullname or 'N/A'}\n\n"
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
