import logging
import re

from aiogram import F
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import Text

from bot.keyboards.reply.user_reply import back_menu_balance, balance_menu
from bot.misc.Payment.CryptoBot import CryptoBot
from bot.misc.Payment.Cryptomus import Cryptomus
from bot.misc.Payment.KassaSmart import KassaSmart
from bot.misc.Payment.Lava import Lava
from bot.misc.Payment.Stars import Stars, stars_router
#from bot.misc.Payment.YooMoney import YooMoney
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG
from bot.misc.callbackData import (
    ChoosingMonths,
    ChoosingPayment,
    ChoosingPrise, ChoosedSuperOffer,
    ApplyPromoCode,
)

from bot.keyboards.inline.user_inline import price_menu, choosing_payment_option_keyboard

from bot.database.methods.update import (
    add_time_person,
    reduce_balance_person
)
from bot.database.methods.get import get_person

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

callback_user = Router()
callback_user.include_router(stars_router)
CONVERT_PANY_RUBLS = 100

types_of_payments = {
    'KassaSmart': KassaSmart,
#    'YooMoney': YooMoney,
    'Lava': Lava,
    'Cryptomus': Cryptomus,
    'CryptoBot': CryptoBot,
    'Stars': Stars
}


class Email(StatesGroup):
    input_email = State()


class PromoCodeState(StatesGroup):
    waiting_for_code = State()


# ============================================
# Промокод - ввод и применение скидки
# ============================================

@callback_user.callback_query(F.data == 'enter_promo_code')
async def enter_promo_code_start(call: CallbackQuery, state: FSMContext):
    """Начало ввода промокода"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    await state.set_state(PromoCodeState.waiting_for_code)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_promo_input"))

    await call.message.edit_text(
        "🏷 <b>Введите промокод</b>\n\n"
        "Если у вас есть персональный промокод на скидку, введите его ниже:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await call.answer()


@callback_user.callback_query(F.data == 'cancel_promo_input')
async def cancel_promo_input(call: CallbackQuery, state: FSMContext):
    """Отмена ввода промокода"""
    from bot.keyboards.inline.user_inline import renew
    from bot.misc.callbackData import MainMenuAction
    from aiogram.types import InlineKeyboardButton

    await state.clear()
    lang = await get_lang(call.from_user.id, state)
    person = await get_person(call.from_user.id)

    kb = await renew(CONFIG, lang, call.from_user.id, person.payment_method_id)
    # Добавляем кнопку "Главное меню"
    kb.inline_keyboard.append([InlineKeyboardButton(
        text="🏠 Главное меню",
        callback_data=MainMenuAction(action='back_to_menu').pack()
    )])

    await call.message.edit_text(
        _('choosing_month_sub', lang),
        reply_markup=kb,
        parse_mode="HTML"
    )
    await call.answer()


@callback_user.message(PromoCodeState.waiting_for_code)
async def process_promo_code(message: Message, state: FSMContext):
    """Обработка введённого промокода"""
    from bot.database.methods.winback import check_promo_code, get_active_promo_for_user
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    code = message.text.strip().upper()
    user_id = message.from_user.id
    lang = await get_lang(user_id, state)

    # Проверяем промокод
    promo_info = await check_promo_code(user_id, code)

    if not promo_info:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔄 Попробовать ещё", callback_data="enter_promo_code"))
        kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_promo_input"))

        await message.answer(
            "❌ <b>Промокод недействителен</b>\n\n"
            "Возможные причины:\n"
            "• Промокод не существует\n"
            "• Промокод не был вам отправлен\n"
            "• Срок действия промокода истёк\n"
            "• Промокод уже использован",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        return

    # Промокод действителен - показываем цены со скидкой
    await state.clear()
    discount_percent = promo_info['discount_percent']

    # Сохраняем промокод в state для использования при оплате
    await state.update_data(active_promo_code=code, promo_discount=discount_percent)

    # Формируем клавиатуру с ценами со скидкой
    kb = InlineKeyboardBuilder()

    months_map = {1: 0, 3: 1, 6: 2, 12: 3}
    for month, price_idx in months_map.items():
        original_price = int(CONFIG.month_cost[price_idx])
        discounted_price = int(original_price * (100 - discount_percent) / 100)

        kb.button(
            text=f"{month} мес: {discounted_price}₽ (было {original_price}₽)",
            callback_data=ChoosingMonths(
                price=discounted_price,
                days_count=month * 31,
                price_on_db=original_price  # Сохраняем оригинальную цену для БД
            )
        )

    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_promo_input"))
    kb.adjust(1)

    await message.answer(
        f"✅ <b>Промокод {code} применён!</b>\n\n"
        f"🏷 Скидка: <b>{discount_percent}%</b>\n\n"
        f"Выберите тариф со скидкой:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@callback_user.callback_query(ApplyPromoCode.filter())
async def auto_apply_promo_code(call: CallbackQuery, callback_data: ApplyPromoCode, state: FSMContext):
    """Автоматическое применение промокода из кнопки в сообщении"""
    from bot.database.methods.winback import check_promo_code
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    code = callback_data.code.upper()
    user_id = call.from_user.id
    lang = await get_lang(user_id, state)

    # Проверяем промокод
    promo_info = await check_promo_code(user_id, code)

    if not promo_info:
        await call.answer("❌ Промокод недействителен или истёк", show_alert=True)
        return

    # Промокод действителен - показываем цены со скидкой
    discount_percent = promo_info['discount_percent']

    # Сохраняем промокод в state для использования при оплате
    await state.update_data(active_promo_code=code, promo_discount=discount_percent)

    # Формируем клавиатуру с ценами со скидкой
    kb = InlineKeyboardBuilder()

    months_map = {1: 0, 3: 1, 6: 2, 12: 3}
    for month, price_idx in months_map.items():
        original_price = int(CONFIG.month_cost[price_idx])
        discounted_price = int(original_price * (100 - discount_percent) / 100)

        kb.button(
            text=f"{month} мес: {discounted_price}₽ (было {original_price}₽)",
            callback_data=ChoosingMonths(
                price=discounted_price,
                days_count=month * 31,
                price_on_db=original_price
            )
        )

    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_promo_input"))
    kb.adjust(1)

    await call.message.edit_text(
        f"✅ <b>Промокод {code} применён!</b>\n\n"
        f"🏷 Скидка: <b>{discount_percent}%</b>\n\n"
        f"Выберите тариф со скидкой:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await call.answer()


@callback_user.callback_query(ChoosingMonths.filter())
async def deposit_balance(
        call: CallbackQuery,
        callback_data: ChoosingMonths,
        state: FSMContext
) -> None:
    # Выбор способа пополнения
    await call.message.delete()
    lang = await get_lang(call.from_user.id, state)

    # Формируем информацию о тарифе
    months = callback_data.days_count // 31  # Приблизительное количество месяцев
    if months == 1:
        period_text = "1 месяц"
    elif months in [2, 3, 4]:
        period_text = f"{months} месяца"
    else:
        period_text = f"{months} месяцев"

    message_text = (
        f"💳 <b>Оплата подписки</b>\n\n"
        f"📅 <b>Тариф:</b> {period_text}\n"
        f"💰 <b>Сумма:</b> {callback_data.price} ₽\n\n"
        f"Выберите способ оплаты:"
    )

    await call.message.answer(
        message_text,
        reply_markup=await choosing_payment_option_keyboard(CONFIG, lang, price=callback_data.price,
                                                            days_count=callback_data.days_count, price_on_db=callback_data.price_on_db),
        parse_mode="HTML"
    )


@callback_user.callback_query(ChoosingPayment.filter())
async def callback_payment(
        call: CallbackQuery,
        callback_data: ChoosingPayment,
        state: FSMContext
):
    # Получаем промокод до очистки state
    state_data = await state.get_data()
    promo_code = state_data.get('active_promo_code')

    await state.clear()
    if types_of_payments.get(callback_data.payment):
        await pay_payment(
            callback_data.payment,
            call.message,
            call.from_user,
            callback_data.price,
            callback_data.days_count,
            callback_data.price_on_db,
            promo_code
        )
    else:
        raise NameError(callback_data.payment)


async def pay_payment(payment, message, from_user, price, days_count, price_on_db, promo_code=None):
    payment = types_of_payments[payment](
        CONFIG,
        message,
        from_user.id,
        from_user.full_name,
        int(price),
        days_count,
        int(price_on_db),
        promo_code
    )
    await payment.to_pay()
