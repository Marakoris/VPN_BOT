import asyncio
import logging
import uuid

from aiolava import LavaBusinessClient

from bot.keyboards.inline.user_inline import pay_and_check
from bot.misc.Payment.payment_systems import PaymentSystem
from bot.misc.language import Localization, get_lang

log = logging.getLogger(__name__)

_ = Localization.text


class Lava(PaymentSystem):
    CHECK_ID: str = None
    ID: str = None

    def __init__(self, config, message, user_id, price, months_count, check_id=None):
        super().__init__(message, user_id, price, months_count)
        self.CHECK_ID = check_id
        self.CLIENT = LavaBusinessClient(
            private_key=config.lava_token_secret,
            shop_id=config.lava_id_project
        )

    async def create_id(self):
        self.ID = str(uuid.uuid4())

    async def create_invoice(self):
        invoice = await self.CLIENT.create_invoice(
            sum_=self.price,
            order_id=self.ID
        )
        return invoice

    async def check_payment(self):
        tic = 0
        while tic < self.CHECK_PERIOD:
            status = await self.CLIENT.check_invoice_status(order_id=self.ID)
            if status.data.status == 'success':
                await self.successful_payment(self.price, 'Lava')
                return
            tic += self.STEP
            await asyncio.sleep(self.STEP)
        return

    async def to_pay(self):
        lang_user = await get_lang(self.user_id)
        await self.message.delete()
        await self.create_id()
        invoice = await self.create_invoice()
        await self.message.answer(
            _('payment_balance_text', lang_user).format(price=self.price),
            reply_markup=await pay_and_check(invoice.data.url, lang_user)
        )
        log.info(
            f'Create payment link Lava '
            f'User: ID: {self.user_id}'
        )
        try:
            await self.check_payment()
        except Exception as e:
            log.error(e, 'The payment period has expired')

    def __str__(self):
        return 'Lava payment system'
