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


@callback_user.callback_query(ChoosingMonths.filter())
async def deposit_balance(
        call: CallbackQuery,
        callback_data: ChoosingMonths,
        state: FSMContext
) -> None:
    # Выбор способа пополнения
    await call.message.delete()
    lang = await get_lang(call.from_user.id, state)
    await call.message.answer(
        _('method_replenishment', lang),
        reply_markup=await choosing_payment_option_keyboard(CONFIG, lang, price=callback_data.price,
                                                            days_count=callback_data.days_count, price_on_db=callback_data.price_on_db)
    )


@callback_user.callback_query(ChoosingPayment.filter())
async def callback_payment(
        call: CallbackQuery,
        callback_data: ChoosingPayment,
        state: FSMContext
):
    await state.clear()
    if types_of_payments.get(callback_data.payment):
        await pay_payment(
            callback_data.payment,
            call.message,
            call.from_user,
            callback_data.price,
            callback_data.days_count,
            callback_data.price_on_db
        )
    else:
        raise NameError(callback_data.payment)


async def pay_payment(payment, message, from_user, price, days_count, price_on_db):
    payment = types_of_payments[payment](
        CONFIG,
        message,
        from_user.id,
        from_user.full_name,
        int(price),
        days_count,
        int(price_on_db)
    )
    await payment.to_pay()
