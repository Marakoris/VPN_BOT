import asyncio
import logging

from aiocryptopay import AioCryptoPay, Networks

from bot.keyboards.inline.user_inline import pay_and_check
from bot.misc.Payment.payment_systems import PaymentSystem
from bot.misc.language import get_lang, Localization

log = logging.getLogger(__name__)

_ = Localization.text


class CryptoBot(PaymentSystem):
    CRYPTO: type(AioCryptoPay)

    def __init__(self, config, message, user_id, price, months_count, data=None):
        super().__init__(message, user_id, price, months_count)
        self.CRYPTO = AioCryptoPay(
            token=config.crypto_bot_api,
            network=Networks.MAIN_NET
        )

    async def check_pay_wallet(self, order):
        tic = 0
        while tic < self.CHECK_PERIOD:
            order_preview = await self.CRYPTO.get_invoices(
                invoice_ids=order.invoice_id
            )
            if order_preview.status == "paid":
                await self.successful_payment(
                    self.price,
                    'CryptoBot'
                )
                return
            tic += self.STEP
            await asyncio.sleep(self.STEP)
        await self.CRYPTO.delete_invoice(
            invoice_id=order.invoice_id
        )
        return

    async def to_pay(self):
        lang_user = await get_lang(self.user_id)
        await self.message.delete()
        order = await self.CRYPTO.create_invoice(
            amount=self.price,
            fiat='RUB',
            currency_type='fiat'
        )
        await self.message.answer(
            _('payment_balance_text', lang_user).format(price=self.price),
            reply_markup=await pay_and_check(order.bot_invoice_url, lang_user)
        )
        log.info(
            f'Create payment link CryptoBot '
            f'User: ID: {self.user_id}'
        )
        try:
            await self.check_pay_wallet(order)
        except Exception as e:
            log.error(e, 'The payment period has expired')

    def __str__(self):
        return 'Платежная система CryptoBot'
