import asyncio
import logging
import uuid

from cryptomus import Client
from cryptomus.payments import Payment
from cryptomus.payouts import Payout

from bot.keyboards.inline.user_inline import pay_and_check
from bot.misc.Payment.payment_systems import PaymentSystem
from bot.misc.language import get_lang, Localization

log = logging.getLogger(__name__)

_ = Localization.text


class Cryptomus(PaymentSystem):
    PAYMENT: Payment
    ID: str

    def __init__(self, config, message, user_id, fullname, price, months_count, price_on_db, data=None):
        super().__init__(message, user_id, fullname, price, months_count, price_on_db)
        self.PAYMENT = Client.payment(
            config.cryptomus_key,
            config.cryptomus_uuid
        )

    async def create_id(self):
        self.ID = str(uuid.uuid4())

    async def new_payment(self):
        return {
            'amount': str(self.price),
            'currency': 'RUB',
            'order_id': self.ID,
            'lifetime': self.CHECK_PERIOD - 30,
        }

    async def check_pay_wallet(self, uuid_order):
        tic = 0
        while tic < self.CHECK_PERIOD:
            order_info = self.PAYMENT.info(
                {'uuid': uuid_order}
            )
            if order_info['status'] == "paid":
                await self.successful_payment(
                    self.price,
                    'Cryptomus'
                )
                return
            tic += self.STEP
            await asyncio.sleep(self.STEP)
        return

    async def to_pay(self):
        lang_user = await get_lang(self.user_id)
        await self.message.delete()
        await self.create_id()
        data = await self.new_payment()
        result = self.PAYMENT.create(data)
        await self.message.answer(
            _('payment_balance_text', lang_user).format(price=self.price),
            reply_markup=await pay_and_check(
                result['url'],
                lang_user
            )
        )
        log.info(
            f'Create payment link Cryptomus '
            f'User: ID: {self.user_id}'
        )
        # Запускаем проверку оплаты как background task чтобы не блокировать бота
        asyncio.create_task(self._check_payment_background(result['uuid']))

    async def _check_payment_background(self, uuid_order):
        """Background task wrapper for check_pay_wallet with exception handling"""
        try:
            await self.check_pay_wallet(uuid_order)
        except Exception as e:
            log.error(f'The payment period has expired: {e}')

    def __str__(self):
        return 'Платежная система Cryptomus'
