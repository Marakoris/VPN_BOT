import asyncio
import logging
import uuid
from math import ceil

from aiogram import Bot
from yookassa import Configuration, Payment

from bot.database.methods.get import get_person
from bot.database.methods.update import add_last_payment_data_person
from bot.keyboards.inline.user_inline import pay_and_check
from bot.misc.Payment.payment_systems import PaymentSystem
from bot.misc.language import Localization, get_lang

log = logging.getLogger(__name__)

_ = Localization.text


class KassaSmart(PaymentSystem):
    CHECK_ID: str = None
    ID: str = None
    EMAIL: str

    def __init__(self,
                 config,
                 message,
                 user_id,
                 fullname,
                 price,
                 months_count,
                 price_on_db,
                 email=None):
        super().__init__(message, user_id, fullname, price, months_count, price_on_db)
        self.fullname = fullname
        self.payment_method_id = None
        self.ACCOUNT_ID = int(config.yookassa_shop_id)
        self.SECRET_KEY = config.yookassa_secret_key
        self.EMAIL = email
        self.message = message

    async def create(self):
        self.ID = str(uuid.uuid4())

    async def check_payment(self):
        Configuration.account_id = self.ACCOUNT_ID
        Configuration.secret_key = self.SECRET_KEY
        tic = 0
        while tic < self.CHECK_PERIOD:
            res = await Payment.find_one(self.ID)
            log.debug(f'Payment status for ID {self.ID}: {res.status}')
            if res.status == 'succeeded':
                self.payment_method_id = res.payment_method.id
                await add_last_payment_data_person(self.user_id, self.payment_method_id, ceil(self.days_count/31), self.price_on_db)
                await self.successful_payment(
                    self.price,
                    'YooKassaSmart',
                )
                return
            tic += self.STEP
            await asyncio.sleep(self.STEP)
        return

    async def invoice(self, lang_user):
        payment = await Payment.create({
            "amount": {
                "value": f"{self.price:.2f}",
                "currency": "RUB"
            },
            "receipt": {
                "customer": {
                    "full_name": self.fullname,
                    "email": self.EMAIL or 'default@mail.ru',
                },
                "items": [
                    {
                        "description": _('description_payment', lang_user),
                        "quantity": 1,  # Количество как число
                        "amount": {
                            "value": f"{self.price:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,  # Например, без НДС
                        "payment_mode": "full_payment",
                    },
                ]
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/"
            },
            "capture": True,
            "description": _('description_payment', lang_user),
            "save_payment_method": True,
        }, self.ID)
        self.ID = payment.id
        return payment.confirmation.confirmation_url

    async def to_pay(self):
        await self.message.delete()
        await self.create()
        Configuration.account_id = self.ACCOUNT_ID
        Configuration.secret_key = self.SECRET_KEY
        lang_user = await get_lang(self.user_id)
        link_invoice = await self.invoice(lang_user)
        # Сохраняем сообщение о пополнении для удаления после успешной оплаты
        self.payment_message = await self.message.answer(
            _('payment_balance_text', lang_user).format(price=self.price),
            reply_markup=await pay_and_check(link_invoice, lang_user)
        )
        log.info(
            f'Create payment link YooKassaSmart '
            f'User: (ID: {self.user_id}'
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
        return 'YooKassaSmart payment system'

    async def create_autopayment(self, price, bot: Bot):
        Configuration.account_id = self.ACCOUNT_ID
        Configuration.secret_key = self.SECRET_KEY

        lang_user = await get_lang(self.user_id)

        # Получаем сохраненный payment_method_id
        person = await get_person(self.user_id)
        self.payment_method_id = person.payment_method_id
        if not self.payment_method_id:
            # await bot.send_message(
            #     chat_id=self.user_id,
            #     text=_("Не удалось найти сохраненный метод оплаты. Пожалуйста, обновите данные.")
            # )
            return False

        # Формируем запрос для автоплатежа
        payment = await Payment.create({
            "amount": {
                "value": f"{price:.2f}",
                "currency": "RUB"
            },
            "payment_method_id": self.payment_method_id,
            "capture": True,
            "description": _('description_payment', lang_user),
            "receipt": {
                "customer": {
                    "full_name": self.fullname,
                    "email": self.EMAIL or 'default@mail.ru',
                },
                "items": [
                    {
                        "description": _('description_payment', lang_user),
                        "quantity": 1,
                        "amount": {
                            "value": f"{price:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                    },
                ]
            },
            "metadata": {
                "user_id": self.user_id,
                "days_count": self.days_count
            }
        })
        self.ID = payment.id

        # Проверяем статус платежа
        return await self.check_auto_payment()

    async def check_auto_payment(self):
        tic = 0
        while tic < self.CHECK_PERIOD:
            try:
                payment = await Payment.find_one(self.ID)
                log.debug(f'Payment status for ID {self.ID}: {payment.status}')
                if payment.status == 'succeeded':
                    return True
                elif payment.status == 'canceled':
                    log.info(f'Платеж {self.ID} был отменен.')
                    return False
                else:
                    await asyncio.sleep(self.STEP)
                    tic += self.STEP
            except Exception as e:
                log.error(f"Ошибка при проверке статуса платежа {self.ID}: {e}")
                await asyncio.sleep(self.STEP)
                tic += self.STEP
        log.warning(f'Время ожидания платежа {self.ID} истекло.')
        return False