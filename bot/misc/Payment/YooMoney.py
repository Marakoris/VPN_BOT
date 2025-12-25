import asyncio
import logging
import random
import uuid

from aiohttp import client_exceptions
from yoomoney_async import Quickpay, Client

from bot.keyboards.inline.user_inline import pay_and_check
from bot.misc.Payment.payment_systems import PaymentSystem
from bot.misc.language import get_lang, Localization

log = logging.getLogger(__name__)

_ = Localization.text


class YooMoney(PaymentSystem):
    CHECK_ID: str = None
    ID: str = None

    def __init__(self, config, message, user_id, fullname, price, months_count, price_on_db, check_id=None):
        super().__init__(message, user_id, fullname, price, months_count, price_on_db)
        self.TOKEN = config.yoomoney_token
        self.TOKEN_WALLET = config.yoomoney_wallet_token

    async def create(self):
        self.ID = str(uuid.uuid4())

    async def check_payment(self):
        client = Client(self.TOKEN)
        tic = 0
        while tic < self.CHECK_PERIOD:
            try:
                history = await client.operation_history(label=self.ID)
                for operation in history.operations:
                    await self.successful_payment(self.price, 'YooMoney')
                    return
            except client_exceptions.ClientOSError as e:
                await asyncio.sleep(self.STEP + random.randint(0, 3))
                log.info('Error 104  YooMoney -- OK')
                continue
            tic += self.STEP
            await asyncio.sleep(self.STEP)
        return

    async def invoice(self):
        quick_pay = await Quickpay(
            receiver=self.TOKEN_WALLET,
            quickpay_form="shop",
            targets='Deposit balance',
            paymentType="SB",
            sum=self.price,
            label=self.ID
        ).start()
        return quick_pay.base_url

    async def to_pay(self):
        lang_user = await get_lang(self.user_id)
        await self.message.delete()
        await self.create()
        link_invoice = await self.invoice()
        await self.message.answer(
            _('payment_balance_text', lang_user).format(price=self.price),
            reply_markup=await pay_and_check(link_invoice, lang_user)
        )
        log.info(
            f'Create payment link YooMoney '
            f'User: {self.user_id}'
        )
        # Запускаем проверку оплаты как background task чтобы не блокировать бота
        asyncio.create_task(self._check_payment_background())

    async def _check_payment_background(self):
        """Background task wrapper for check_payment with exception handling"""
        try:
            await self.check_payment()
        except Exception as e:
            log.error(f'The payment period has expired: {e}')

    def __str__(self):
        return 'Платежная система YooMoney'
