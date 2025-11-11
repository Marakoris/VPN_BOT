import asyncio
import logging
import time

from aiogram import Bot
from aiogram.types import FSInputFile

from bot.keyboards.reply.user_reply import user_menu
from bot.database.methods.get import (
    get_all_subscription,
    get_server_id,
    get_person
)
from bot.database.methods.update import (
    person_banned_true,
    person_one_day_true,
    server_space_update, add_time_person, reduce_balance_person
)
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

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
        if person.subscription <= int(time.time()):
            if await check_auto_renewal(
                    person,
                    bot,
                    _('loop_autopay_text', person.lang)
            ):
                return
            if person.server is not None:
                await delete_key(person)
            await person_banned_true(person.tgid)
            await bot.send_photo(
                chat_id=person.tgid,
                photo=FSInputFile('bot/img/ended_subscribe.jpg'),
                caption=_('ended_sub_message', person.lang),
                reply_markup=await user_menu(person, person.lang)
            )
        elif (person.subscription <= int(time.time()) + COUNT_SECOND_DAY
              and not person.notion_oneday):
            await person_one_day_true(person.tgid)
            await bot.send_message(
                person.tgid,
                _('alert_to_renew_sub', person.lang)
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
                    person_new = await get_person(person.tgid)
                    await bot.send_message(
                        person_new.tgid,
                        _('loop_autopay', person_new.lang).format(
                            text=text,
                            mount_count=mount_count
                        ),
                        reply_markup=await user_menu(
                            person_new,
                            person_new.lang
                        )
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
