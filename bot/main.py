import logging
import asyncio
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.enums import ParseMode
from aiogram_dialog import setup_dialogs
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.handlers.admin.super_offer_dialog import dialog
from bot.handlers.user.main import user_router
from bot.handlers.admin.main import admin_router
from bot.database.models.main import create_all_table
from bot.database.importBD.import_BD import import_all
from bot.middlewares.last_interaction import LastInteractionMiddleware
from bot.misc.backup_script import backup_and_upload_task, backup_task
from bot.misc.check_and_proceed_subscriptions import process_subscriptions
from bot.misc.commands import set_commands
from bot.misc.loop import loop
from bot.misc.notification_script import notify
from bot.misc.traffic_monitor import update_all_users_traffic, check_and_block_exceeded_users
from bot.misc.util import CONFIG
from bot.misc.winback_sender import winback_autosend


async def start_bot():
    dp = Dispatcher(
        storage=MemoryStorage(),
        fsm_strategy=FSMStrategy.USER_IN_CHAT
    )

    # Setup dialogs middleware BEFORE routers
    setup_dialogs(dp)

    # Register all the routers from handlers package
    dp.include_routers(
        user_router,
        admin_router,
        dialog
    )

    dp.update.outer_middleware(LastInteractionMiddleware())

    await create_all_table()
    if CONFIG.import_bd:
        await import_all()
        logging.info('Import BD successfully -- OK')
        return

    scheduler = AsyncIOScheduler()
    bot = Bot(token=CONFIG.tg_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await set_commands(bot)

    # Настройка хранилища задач в БД
    # database_url = f"postgresql://{CONFIG.postgres_user}:{CONFIG.postgres_password}@db_postgres:5432/{CONFIG.postgres_db}"
    database_url = (
        f'postgresql+asyncpg://'
        f'{CONFIG.postgres_user}:'
        f'{CONFIG.postgres_password}'
        f'@postgres_db_container/{CONFIG.postgres_db}'
    )
    jobstores = {
        'default': SQLAlchemyJobStore(url=database_url)
    }

    # Добавляем задачу для обработки подписок
    scheduler.add_job(process_subscriptions, "interval", seconds=15, args=(bot, CONFIG,))

    # Добавляем задачу для бэкапов
    # scheduler.add_job(
    #     backup_task,
    #     trigger=CronTrigger(hour=13, minute=0),
    #     # trigger=CronTrigger(second=0),
    #     args=(bot,),
    #     id='backup_task',  # Уникальный идентификатор задачи
    #     replace_existing=True  # Заменяет задачу, если она уже существует
    # )

    scheduler.add_job(
        notify,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=9, minute=0),
        args=(bot,),
        id='notify_users_renew_subscription',
        replace_existing=True
    )

    # Win-back автоматическая рассылка промокодов (раз в день в 11:00)
    scheduler.add_job(
        winback_autosend,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=11, minute=0),
        args=(bot,),
        id='winback_autosend',
        replace_existing=True
    )

    # Добавляем задачу для загрузки на FTP (каждое число месяца)
    # ОТКЛЮЧЕНО: вызывает ошибки на тестовом сервере
    # scheduler.add_job(
    #     backup_and_upload_task,
    #     trigger=CronTrigger(hour=14, minute=0),  # 1-го числа каждого месяца в 00:00
    #     # trigger=CronTrigger(second=10),
    #     args=(bot,),
    #     id='backup_and_upload_task',  # Уникальный идентификатор задачи
    #     replace_existing=True  # Заменяет задачу, если она уже существует
    # )

    # Добавляем задачу мониторинга трафика (каждый час)
    async def traffic_monitor_job():
        await update_all_users_traffic()
        await check_and_block_exceeded_users(bot)

    scheduler.add_job(
        traffic_monitor_job,
        trigger=CronTrigger(minute=0),  # Каждый час в :00
        id='traffic_monitor',
        replace_existing=True
    )


    logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
    scheduler.start()
    await asyncio.gather(
        dp.start_polling(bot),
    )
