import asyncio
import logging
import time

from aiogram import Bot
from aiogram.types import FSInputFile, ReplyKeyboardRemove

from bot.keyboards.reply.user_reply import user_menu
from bot.database.methods.get import (
    get_all_subscription,
    get_server_id,
    get_person
)
from bot.database.methods.update import (
    person_subscription_expired_true,
    person_one_day_true,
    person_two_days_true,
    person_three_days_true,
    update_last_expiry_notification,
    server_space_update, add_time_person, reduce_balance_person
)
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.subscription import activate_subscription
from bot.misc.traffic_monitor import reset_user_traffic, reset_bypass_traffic
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG
from bot.keyboards.inline.user_inline import renew

log = logging.getLogger(__name__)

_ = Localization.text

COUNT_SECOND_DAY = 86400

month_count = {
    CONFIG.month_cost[3]: 12,
    CONFIG.month_cost[2]: 6,
    CONFIG.month_cost[1]: 3,
    CONFIG.month_cost[0]: 1,
}



async def loop(bot: Bot):
    try:
        all_persons = await get_all_subscription()
        for person in all_persons:
            await check_date(person, bot)
    except Exception as e:
        log.error(e)


async def check_date(person, bot: Bot):
    try:
        current_time = int(time.time())

        if person.subscription <= current_time:
            # Subscription has expired
            if await check_auto_renewal(
                    person,
                    bot,
                    _('loop_autopay_text', person.lang)
            ):
                return

            # Check if we need to send daily reminder
            last_notification = person.last_expiry_notification or 0
            time_since_last = current_time - last_notification

            # Send reminder if it's the first time OR if 24 hours have passed
            if time_since_last >= COUNT_SECOND_DAY:
                # Delete keys only on first expiration
                if last_notification == 0 and person.server is not None:
                    await delete_key(person)

                await person_subscription_expired_true(person.tgid)

                # Build full payment keyboard (with super offer + prices + oferta)
                kb = await renew(CONFIG, person.lang, person.tgid, person.payment_method_id)

                # Determine message based on how long subscription has been expired
                days_expired = (current_time - person.subscription) // COUNT_SECOND_DAY

                if days_expired == 0:
                    # Just expired
                    await bot.send_photo(
                        chat_id=person.tgid,
                        photo=FSInputFile('bot/img/ended_subscribe.jpg'),
                        caption=_('ended_sub_message', person.lang),
                        reply_markup=kb
                    )
                else:
                    # Daily reminder
                    await bot.send_message(
                        chat_id=person.tgid,
                        text=f"⏰ Напоминание: Ваша подписка истекла {days_expired} дн. назад\n\n" +
                             _('ended_sub_message', person.lang),
                        reply_markup=kb
                    )

                # Update last notification timestamp
                await update_last_expiry_notification(person.tgid)
        # Check for 3-day reminder
        elif (person.subscription <= int(time.time()) + COUNT_SECOND_DAY * 3
              and person.subscription > int(time.time()) + COUNT_SECOND_DAY * 2
              and not person.notion_threedays):
            await person_three_days_true(person.tgid)

            # Send 3-day reminder with full payment keyboard
            kb = await renew(CONFIG, person.lang, person.tgid, person.payment_method_id)

            await bot.send_message(
                person.tgid,
                _('alert_to_renew_sub', person.lang) + "\n\n⏰ Осталось 3 дня",
                reply_markup=kb
            )

        # Check for 2-day reminder
        elif (person.subscription <= int(time.time()) + COUNT_SECOND_DAY * 2
              and person.subscription > int(time.time()) + COUNT_SECOND_DAY
              and not person.notion_twodays):
            await person_two_days_true(person.tgid)

            # Send 2-day reminder with full payment keyboard
            kb = await renew(CONFIG, person.lang, person.tgid, person.payment_method_id)

            await bot.send_message(
                person.tgid,
                _('alert_to_renew_sub', person.lang) + "\n\n⏰ Осталось 2 дня",
                reply_markup=kb
            )

        # Check for 1-day reminder
        elif (person.subscription <= int(time.time()) + COUNT_SECOND_DAY
              and not person.notion_oneday):
            await person_one_day_true(person.tgid)

            # Send 1-day reminder with full payment keyboard
            kb = await renew(CONFIG, person.lang, person.tgid, person.payment_method_id)

            await bot.send_message(
                person.tgid,
                _('alert_to_renew_sub', person.lang) + "\n\n⏰ Остался 1 день",
                reply_markup=kb
            )
        return
    except Exception as e:
        log.error(f"Error in the user date verification cycle {e}")
        return


async def delete_key(person):
    server = await get_server_id(person.server)
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


async def check_auto_renewal(person, bot, text):
    try:
        for price, mount_count in month_count.items():
            price = int(price)
            if person.balance >= price:
                if await add_time_person(
                        person.tgid,
                        mount_count * CONFIG.COUNT_SECOND_MOTH
                ):
                    await reduce_balance_person(
                        price,
                        person.tgid
                    )

                    # Активируем ключи на всех серверах (ВАЖНО!)
                    try:
                        await activate_subscription(person.tgid)
                        log.info(f"[Balance Autopay] Subscription activated for user {person.tgid}")
                    except Exception as e:
                        log.error(f"[Balance Autopay] Failed to activate subscription for user {person.tgid}: {e}")

                    # Сброс счётчика трафика при продлении через баланс
                    try:
                        await reset_user_traffic(person.tgid)
                        await reset_bypass_traffic(person.tgid)
                        log.info(f"[Balance Autopay] Traffic reset for user {person.tgid}")
                    except Exception as e:
                        log.error(f"[Balance Autopay] Failed to reset traffic for user {person.tgid}: {e}")

                    person_new = await get_person(person.tgid)

                    # Send autopay notification with "My keys" button
                    from bot.misc.callbackData import MainMenuAction
                    from aiogram.utils.keyboard import InlineKeyboardBuilder
                    from aiogram.types import InlineKeyboardButton

                    kb = InlineKeyboardBuilder()
                    kb.row(
                        InlineKeyboardButton(
                            text="🔑 Мои ключи",
                            callback_data=MainMenuAction(action='my_keys').pack()
                        )
                    )

                    await bot.send_message(
                        person_new.tgid,
                        _('loop_autopay', person_new.lang).format(
                            text=text,
                            mount_count=mount_count
                        ),
                        reply_markup=kb.as_markup()
                    )
                    return True
                else:
                    for admin_id in CONFIG.admins_ids:
                        try:
                            await bot.send_message(
                                CONFIG.admin_tg_id,
                                _(
                                    'loop_autopay_error',
                                    await get_lang(CONFIG.admin_tg_id)
                                ).format(telegram_id=person.tgid)
                            )
                        except Exception as e:
                            log.error(f"Can't send message to the admin with tg_id {admin_id}: {e}")

                        await asyncio.sleep(0.01)


    except Exception as e:
        log.error(
            f'{e} Error when trying '
            f'to auto-renew a subscription to '
            f'a client {person.username} {person.tgid}'
        )
    return False
