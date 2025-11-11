import logging

from aiogram import F, Router
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery

from bot.misc.Payment.payment_systems import PaymentSystem
from bot.misc.language import get_lang, Localization

stars_router = Router()
log = logging.getLogger(__name__)

_ = Localization.text


class Stars(PaymentSystem):

    def __init__(self, config, message, user_id, fullname, price, months_count, data=None):
        super().__init__(message, user_id, fullname, price, months_count)
        self.TOKEN = config.token_stars

    async def to_pay(self):
        lang_user = await get_lang(self.user_id)
        await self.message.delete()
        amount = self.price // 2
        title = _('description_payment', lang_user)
        description = (
            _('payment_balance_text2', lang_user).format(price=self.price)
        )
        prices = [LabeledPrice(label="XTR", amount=amount)]
        await self.message.answer_invoice(
            title=title,
            description=description,
            prices=prices,
            provider_token=self.TOKEN,
            payload=f'{self.price}',
            currency="XTR"
        )
        log.info(
            f'Create payment Stars '
            f'User: ID: {self.user_id}'
        )
        return self.price

    def __str__(self):
        return 'Платежная система Telegram Stars'


@stars_router.pre_checkout_query()
async def on_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@stars_router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    price = int(message.successful_payment.invoice_payload)
    payment_system = PaymentSystem(
        message,
        message.from_user.id,
        price=price
    )
    await payment_system.successful_payment(price, 'Telegram Stars')
