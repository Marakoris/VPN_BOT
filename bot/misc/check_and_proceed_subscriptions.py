import asyncio
import logging
import time
from datetime import date

from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.utils.formatting import Text

from bot.database.methods.get import get_all_subscription, get_server_id, get_all_user
from bot.database.methods.insert import crate_or_update_stats, add_payment
from bot.database.methods.update import add_time_person, server_space_update, person_banned_true, person_one_day_false, \
    person_one_day_true, add_retention_person
from bot.database.models.main import Persons
from bot.keyboards.reply.user_reply import user_menu
from bot.misc.Payment.KassaSmart import KassaSmart
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

_ = Localization.text

COUNT_SECOND_DAY = 86400  # Количество секунд в одном дне

# Маппинг цен на количество месяцев
month_count = {
    CONFIG.month_cost[3]: 12,
    CONFIG.month_cost[2]: 6,
    CONFIG.month_cost[1]: 3,
    CONFIG.month_cost[0]: 1,
}


async def update_daily_statistics():
    persons: list[Persons] = await get_all_user()
    today_active_persons_count = 0
    active_subscriptions_count = 0
    active_subscriptions_sum = 0
    active_autopay_subscriptions_count = 0
    active_autopay_subscriptions_sum = 0
    referral_balance_persons_count = 0
    referral_balance_sum = 0
    log.info(f"Checking {len(persons)} persons")
    for person in persons:
        if person.last_interaction is not None and person.last_interaction.date() == date.today():
            today_active_persons_count += 1
        if person.subscription is not None and person.subscription >= int(
                time.time()) and person.subscription_price is not None or person.subscription_months is not None:
            active_subscriptions_count += 1
            active_subscriptions_sum += person.subscription_price if person.subscription_price is not None else 0
        if person.payment_method_id is not None:
            active_autopay_subscriptions_count += 1
            active_autopay_subscriptions_sum += person.subscription_price if person.subscription_price is not None else 0
        if person.referral_balance is not None and person.referral_balance > 0:
            referral_balance_persons_count += 1
            referral_balance_sum += person.referral_balance

    await crate_or_update_stats(date.today(), today_active_persons_count, active_subscriptions_count,
                                active_subscriptions_sum, active_autopay_subscriptions_count,
                                active_autopay_subscriptions_sum, referral_balance_persons_count,
                                referral_balance_sum)


async def process_subscriptions(bot: Bot, config):
    """
    Функция для проверки и обработки подписок пользователей.
    Предназначена для использования в планировщике задач (например, APScheduler).
    """
    log.info("process_subscriptions started")
    try:
        current_time = int(time.time())
        all_persons = await get_all_subscription()

        for person in all_persons:
            lang_user = await get_lang(person.tgid)

            # Проверяем, истекла ли подписка
            if person.subscription and person.subscription < current_time:
                if person.payment_method_id:
                    # Автоплатеж возможен
                    current_tariff_cost = await get_current_tariff(person.subscription_months)
                    if current_tariff_cost != person.subscription_price:
                        # Тариф изменился
                        if person.server is not None:
                            try:
                                await delete_key(person)
                            except Exception as e:
                                log.error(e)
                        await person_banned_true(person.tgid)
                        await bot.send_photo(
                            chat_id=person.tgid,
                            photo=FSInputFile('bot/img/ended_subscribe.jpg'),
                            caption=_('tariff_cost_changed', lang_user),
                            reply_markup=await user_menu(person, person.lang)
                        )
                        continue
                    # Попытка автоплатежа
                    kassa_smart = KassaSmart(
                        config=config,
                        message=None,  # Нет сообщения, так как функция запускается по расписанию
                        user_id=person.tgid,
                        fullname=person.fullname,
                        price=current_tariff_cost,
                        months_count=person.subscription_months,
                        price_on_db=current_tariff_cost
                    )
                    kassa_smart.payment_method_id = person.payment_method_id
                    success = False
                    try:
                        success = await kassa_smart.create_autopayment(current_tariff_cost, bot)

                        if success:
                            # Продление подписки
                            await add_time_person(person.tgid, person.subscription_months * CONFIG.COUNT_SECOND_MOTH)
                            await person_one_day_true(person.tgid)
                            await bot.send_message(
                                chat_id=person.tgid,
                                text=_('payment_success', lang_user).format(
                                    months_count=person.subscription_months
                                ),
                                reply_markup=await user_menu(person, lang_user)
                            )
                            await add_retention_person(person.tgid, 1)
                            await add_payment(
                                person.tgid,
                                current_tariff_cost,
                                'Autopayment by YooKassa'
                            )
                            log.info(f"Автоплатеж успешно выполнен для пользователя {person.tgid}")
                            for admin_id in CONFIG.admins_ids:
                                text = Text(
                                    _(
                                        'success_auto_payment_exist_admin',
                                        await get_lang(admin_id)
                                    ).format(
                                        full_name=person.fullname,
                                        user_id=person.tgid,
                                        count_m=person.subscription_months
                                    )
                                )
                                try:
                                    await bot.send_message(
                                        admin_id,
                                        **text.as_kwargs(),
                                    )
                                except Exception as e:
                                    log.error(f"{e} Can't send message to the admin with tg_id {admin_id}")
                                await asyncio.sleep(0.01)
                    finally:
                        if not success:
                            log.info(f"User with id {person.tgid} can't auto pay")
                            # Автоплатеж неуспешен
                            if person.server is not None:
                                try:
                                    await delete_key(person)
                                except Exception as e:
                                    log.error(e)
                            await person_banned_true(person.tgid)
                            await bot.send_photo(
                                chat_id=person.tgid,
                                photo=FSInputFile('bot/img/ended_subscribe.jpg'),
                                caption=_('ended_sub_message', person.lang),
                                reply_markup=await user_menu(person, person.lang)
                            )
                else:
                    log.info("Can't pay")
                    # Автоплатеж невозможен, предлагаем обновить подписку вручную
                    if person.server is not None:
                        try:
                            await delete_key(person)
                        except Exception as e:
                            log.error(e)
                    await person_banned_true(person.tgid)
                    await bot.send_photo(
                        chat_id=person.tgid,
                        photo=FSInputFile('bot/img/ended_subscribe.jpg'),
                        caption=_('ended_sub_message', person.lang),
                        reply_markup=await user_menu(person, person.lang)
                    )
            elif (person.subscription and
                  person.subscription <= (current_time + COUNT_SECOND_DAY) and
                  person.payment_method_id is None and person.notion_oneday):
                # Подписка истекает в ближайший день и пользователь еще не уведомлен
                await bot.send_message(
                    chat_id=person.tgid,
                    text=_('alert_to_renew_sub', lang_user)
                )
                await person_one_day_false(person.tgid)
                log.info(f"Пользователю {person.tgid} отправлено напоминание о продлении подписки")
    except Exception as e:
        log.error(f"Ошибка в процессе проверки подписок: {e}")

    try:
        await update_daily_statistics()
    except Exception as e:
        log.error(f'Ошибка в процессе обновления ежедневной статистики: {e}')


async def get_current_tariff(months_count):
    """
    Функция для получения актуального тарифа.
    Предполагается, что тарифы хранятся в конфигурации или в базе данных.
    """
    # Пример получения тарифов из конфигурации
    tariffs = {
        1: int(CONFIG.month_cost[0]),
        3: int(CONFIG.month_cost[1]),
        6: int(CONFIG.month_cost[2]),
        12: int(CONFIG.month_cost[3]),
    }
    if months_count in tariffs:
        tariff = tariffs.get(months_count)
    else:
        tariff = tariffs.get(1)
    return tariff


async def delete_key(person):
    server = await get_server_id(person.server)
    if server is None:
        return
    server_manager = ServerManager(server)
    await server_manager.login()
    try:
        if await server_manager.delete_client(person.tgid):
            all_client = await server_manager.get_all_user()
        else:
            raise Exception("Couldn't delete it")
    except Exception as e:
        log.error(f"Failed to connect to the server: {e}")
        raise e
    space = len(all_client)
    if not await server_space_update(server.name, space):
        raise "Failed to update data about free space on the server"
