import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
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

# Thread pool для изоляции sync HTTP вызовов YooKassa
# YooKassa библиотека использует sync httpx.Client внутри async методов,
# что нарушает greenlet контекст SQLAlchemy при использовании в APScheduler
_yookassa_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="yookassa")


def _sync_payment_create(params, idempotency_key=None):
    """
    Синхронная обёртка для Payment.create.
    Вызывается в отдельном потоке через run_in_executor.

    ВАЖНО: НЕ используем set_event_loop() чтобы не нарушать greenlet контекст основного потока!
    """
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(Payment.create(params, idempotency_key))
        return result
    finally:
        loop.close()


def _sync_payment_find_one(payment_id):
    """
    Синхронная обёртка для Payment.find_one.
    Вызывается в отдельном потоке через run_in_executor.

    ВАЖНО: НЕ используем set_event_loop() чтобы не нарушать greenlet контекст основного потока!
    """
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(Payment.find_one(payment_id))
        return result
    finally:
        loop.close()


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
                 promo_code=None,
                 email=None):
        super().__init__(message, user_id, fullname, price, months_count, price_on_db, promo_code)
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

    async def create_autopayment(self, price, bot: Bot, lang_user: str = 'ru'):
        """
        Создание автоплатежа с изоляцией sync YooKassa вызовов.

        ВАЖНО: YooKassa библиотека использует sync httpx.Client внутри async методов,
        что нарушает greenlet контекст SQLAlchemy при вызове из APScheduler.
        Решение: запускаем YooKassa вызовы в отдельном потоке через run_in_executor.

        ВАЖНО #2: НЕ делаем вызовы к БД внутри этого метода!
        payment_method_id должен быть установлен снаружи через self.payment_method_id

        Returns:
            dict: {'success': bool, 'reason': str|None, 'card_last4': str|None}
        """
        Configuration.account_id = self.ACCOUNT_ID
        Configuration.secret_key = self.SECRET_KEY

        # Используем payment_method_id который был установлен снаружи
        # НЕ делаем вызов к БД здесь!
        if not self.payment_method_id:
            return {'success': False, 'reason': 'no_payment_method', 'card_last4': None}

        # Формируем запрос для автоплатежа
        payment_params = {
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
        }

        # Запускаем YooKassa в отдельном потоке чтобы не нарушить greenlet контекст
        loop = asyncio.get_event_loop()
        try:
            payment = await loop.run_in_executor(
                _yookassa_executor,
                partial(_sync_payment_create, payment_params)
            )
            self.ID = payment.id
            log.info(f"[Autopay] Payment created: {self.ID} for user {self.user_id}")
        except Exception as e:
            log.error(f"[Autopay] Failed to create payment for user {self.user_id}: {e}")
            return {'success': False, 'reason': str(e), 'card_last4': None}

        # Проверяем статус платежа (также в отдельном потоке)
        return await self.check_auto_payment()

    async def check_auto_payment(self):
        """
        Проверка статуса автоплатежа с изоляцией sync YooKassa вызовов.

        Returns:
            dict: {'success': bool, 'reason': str|None, 'card_last4': str|None}
        """
        tic = 0
        loop = asyncio.get_event_loop()
        card_last4 = None

        while tic < self.CHECK_PERIOD:
            try:
                # Запускаем YooKassa в отдельном потоке
                payment = await loop.run_in_executor(
                    _yookassa_executor,
                    partial(_sync_payment_find_one, self.ID)
                )
                log.debug(f'Payment status for ID {self.ID}: {payment.status}')

                # Попробуем получить последние 4 цифры карты
                try:
                    if payment.payment_method and hasattr(payment.payment_method, 'card'):
                        card_last4 = payment.payment_method.card.last4
                except Exception:
                    pass

                if payment.status == 'succeeded':
                    return {'success': True, 'reason': None, 'card_last4': card_last4}
                elif payment.status == 'canceled':
                    # Пытаемся получить причину отмены
                    reason = None
                    if hasattr(payment, 'cancellation_details') and payment.cancellation_details:
                        reason = payment.cancellation_details.reason
                    log.info(f'Платеж {self.ID} был отменен. Причина: {reason}')
                    return {'success': False, 'reason': reason, 'card_last4': card_last4}
                else:
                    await asyncio.sleep(self.STEP)
                    tic += self.STEP
            except Exception as e:
                log.error(f"Ошибка при проверке статуса платежа {self.ID}: {e}")
                await asyncio.sleep(self.STEP)
                tic += self.STEP

        log.warning(f'Время ожидания платежа {self.ID} истекло.')
        return {'success': False, 'reason': 'timeout', 'card_last4': card_last4}