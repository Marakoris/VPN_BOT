import asyncio
import logging
from datetime import datetime
from math import ceil

import requests
import csv
import io

from aiogram.utils.formatting import Text
from aiohttp.log import client_logger

from bot.database.methods.get import get_person
from bot.database.methods.insert import add_payment, create_affiliate_statistics
from bot.database.methods.update import (
    add_balance_person,
    add_referral_balance_person, add_time_person, person_one_day_true, add_retention_person
)

from bot.keyboards.reply.user_reply import balance_menu, back_menu
from bot.misc.language import Localization, get_lang
from bot.misc.loop import check_auto_renewal
from bot.misc.traffic_monitor import reset_user_traffic, reset_bypass_traffic
from bot.misc.util import CONFIG
from bot.misc.yandex_metrika import YandexMetrikaAPI

log = logging.getLogger(__name__)

_ = Localization.text


class PaymentSystem:
    TOKEN: str
    CHECK_PERIOD = 60 * 30
    STEP = 5

    def __init__(self, message, user_id, full_name, price=None, days_count: int = 0, price_on_db=None):
        self.message = message
        self.user_id = user_id
        self.user_full_name = full_name
        self.price = price
        self.price_on_db = price_on_db
        self.days_count = days_count

    async def to_pay(self):
        raise NotImplementedError()

    async def successful_payment(self, total_amount, name_payment):
        log.info(
            f'user ID: {self.user_id}'
            f' success payment {total_amount} RUB for {self.days_count} days. Payment - {name_payment}'
        )
        # Оплата прошла успешно на сумму total_amount через систему name_payment
        # Здесь нужно выполнять отправку оф конверсии в ЯМ
        person = await get_person(self.user_id)
        # log.info(f"Был получен пользователь по {self.user_id} его данные {person}")
        # Если у пользователя есть client_id, то оправляем офлайн конверсию
        if person is not None and person.client_id is not None:
            client_id = person.client_id
            ym_api = YandexMetrikaAPI(counter_id=CONFIG.ym_counter, oauth_token=CONFIG.ym_oauth_token)
            # Отправка офлайн-конверсии
            upload_id = ym_api.send_offline_conversion_payment(client_id, datetime.now().astimezone(),
                                                               ceil(self.days_count / 31),
                                                               total_amount,
                                                               'RUB', 'SubscriptionPurchase')
            # log.info(f"Uload_id {upload_id}")
            # Проверка статуса загрузки (если загрузка прошла успешно)
            if upload_id:
                log.info(ym_api.check_conversion_status(upload_id))
        # else:
        #     log.info("У вас нет client_id")

        lang_user = await get_lang(self.user_id)
        if not await add_time_person(
                self.user_id,
                self.days_count * CONFIG.COUNT_SECOND_DAY):
            await self.message.answer(_('error_send_admin', lang_user))

        # Сброс счётчика трафика при оплате
        await reset_user_traffic(self.user_id)
        await reset_bypass_traffic(self.user_id)

        await add_retention_person(self.user_id, 1)

        log.info(
            f"Adding payment with fields user_id {self.user_id}, total_amount {total_amount}, name_payment {name_payment}")
        try:
            await add_payment(
                self.user_id,
                total_amount,
                name_payment
            )
        except Exception:
            log.error(Exception)

        try:
            # Удаляем предыдущее сообщение о пополнении (если есть)
            if hasattr(self, 'payment_message') and self.payment_message:
                try:
                    await self.payment_message.delete()
                except Exception:
                    pass  # Сообщение могло быть уже удалено

            # Получаем обновлённые данные для показа даты окончания и автоподписки
            person_after_payment = await get_person(self.user_id)
            subscription_end = datetime.fromtimestamp(person_after_payment.subscription).strftime('%d.%m.%Y')

            # Формируем сообщение с периодом
            success_message = _('payment_success', lang_user) + f"\n\n📅 Подписка активна до: <b>{subscription_end}</b>"

            # Добавляем информацию об автоподписке если она подключена
            if person_after_payment.payment_method_id:
                success_message += "\n🔄 Автоподписка подключена"

            # Подсказка что ничего делать не нужно
            success_message += "\n\nℹ️ Если VPN уже настроен — ничего делать не нужно, всё работает"

            # Кнопка перехода к VPN подключению - сразу на лендинг
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            from urllib.parse import quote
            kb = InlineKeyboardBuilder()

            # Если есть токен - сразу URL на лендинг
            if person_after_payment.subscription_token:
                add_link_url = f"{CONFIG.subscription_api_url}/connect/{quote(person_after_payment.subscription_token, safe='')}"
                kb.row(InlineKeyboardButton(text="🔑 Подключиться к VPN", url=add_link_url))
            else:
                # Fallback на callback если токена нет
                from bot.misc.callbackData import MainMenuAction
                kb.button(text="🔑 Подключиться к VPN", callback_data=MainMenuAction(action='my_keys'))
            kb.adjust(1)

            await self.message.answer(
                success_message,
                reply_markup=kb.as_markup()
            )
        except Exception as e:
            log.error(f"Error sending success message: {e}")

        if CONFIG.auto_extension:
            await check_auto_renewal(
                person,
                self.message.bot,
                _('payment_autopay_text', lang_user)
            )
        if person.referral_user_tgid is not None:
            referral_user = person.referral_user_tgid
            referral_balance = max(1, round(total_amount * (CONFIG.referral_percent * 0.01)))
            await add_referral_balance_person(
                referral_balance,
                referral_user
            )
            await create_affiliate_statistics(self.user_full_name,
                                              self.user_id,
                                              referral_user,
                                              total_amount,
                                              CONFIG.referral_percent,
                                              referral_balance)
            await self.message.bot.send_message(
                referral_user,
                _('reff_add_balance', await get_lang(referral_user)).format(
                    referral_balance=referral_balance
                )
            )
        await person_one_day_true(self.user_id)

        for admin_id in CONFIG.admins_ids:
            # Формируем сообщение с UTM-меткой
            utm_info = ""
            if person and person.client_id:
                utm_info = f"\n📊 UTM: {person.client_id}"

            admin_message = _(
                'success_payment_exist_admin',
                await get_lang(admin_id)
            ).format(
                full_name=self.user_full_name,
                user_id=self.user_id,
                count_m=self.days_count
            ) + utm_info

            text = Text(admin_message)
            try:
                await self.message.bot.send_message(
                    admin_id,
                    **text.as_kwargs(),
                )
            except:
                log.error(f"Can't send message to the admin with tg_id {admin_id}")
            await asyncio.sleep(0.01)
