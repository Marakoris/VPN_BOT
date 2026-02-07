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
from bot.misc.winback_sender import winback_autosend
from bot.misc.traffic_monitor import update_all_users_traffic, check_and_block_exceeded_users, reset_monthly_traffic, send_setup_reminders, send_reengagement_reminders, send_daily_stats, snapshot_daily_traffic, check_servers_health, check_servers_speed, reset_monthly_bypass_traffic
from bot.misc.util import CONFIG


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

    # Добавляем задачу для обработки подписок (увеличен интервал с 15с до 60с для снижения нагрузки)
    scheduler.add_job(process_subscriptions, "interval", seconds=60, args=(bot, CONFIG,))

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

    # Добавляем задачу для бэкапа БД (ежедневно в 14:00 MSK)
    # SFTP загрузка управляется через SFTP_ENABLED в .env
    scheduler.add_job(
        backup_and_upload_task,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=14, minute=0),
        args=(bot,),
        id='backup_and_upload_task',
        replace_existing=True
    )

    # Добавляем задачу мониторинга трафика (каждый час)
    # UNIFIED: обновляет main + bypass трафик + отправляет уведомления bypass
    async def traffic_monitor_job():
        await update_all_users_traffic(bot)  # Передаём bot для bypass уведомлений
        await check_and_block_exceeded_users(bot)

    scheduler.add_job(
        traffic_monitor_job,
        trigger=CronTrigger(minute=0),  # Каждый час в :00
        id='traffic_monitor',
        replace_existing=True
    )

    # Добавляем задачу ежемесячного сброса трафика (каждый день в 00:05)
    scheduler.add_job(
        reset_monthly_traffic,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=0, minute=5),
        id='monthly_traffic_reset',
        replace_existing=True
    )

    # Ежемесячный сброс bypass трафика (каждый день в 00:10)
    scheduler.add_job(
        reset_monthly_bypass_traffic,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=0, minute=10),
        id='monthly_bypass_traffic_reset',
        replace_existing=True
    )


    # Напоминание о настройке VPN для неактивных пользователей (каждый день в 10:00)
    async def setup_reminder_job():
        await send_setup_reminders(bot)

    scheduler.add_job(
        setup_reminder_job,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=10, minute=0),
        id='setup_reminder',
        replace_existing=True
    )

    # Re-engagement напоминания (каждый день в 11:00)
    async def reengagement_job():
        await send_reengagement_reminders(bot)

    scheduler.add_job(
        reengagement_job,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=11, minute=0),
        id='reengagement_reminder',
        replace_existing=True
    )

    # Ежедневная статистика для админов (каждый день в 09:00)
    async def daily_stats_job():
        await send_daily_stats(bot)

    scheduler.add_job(
        daily_stats_job,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=9, minute=0),
        id='daily_stats',
        replace_existing=True
    )

    # Win-back автоматическая рассылка (каждый день в 12:00 MSK)
    async def winback_job():
        await winback_autosend(bot)

    scheduler.add_job(
        winback_job,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=12, minute=0),
        id='winback_autosend',
        replace_existing=True
    )

    # Ежедневный snapshot трафика (в полночь)
    scheduler.add_job(
        snapshot_daily_traffic,
        trigger=CronTrigger(timezone=ZoneInfo("Europe/Moscow"), hour=0, minute=1),
        id="traffic_snapshot",
        replace_existing=True
    )

    # Health check серверов (каждые 5 минут)
    async def server_health_check_job():
        await check_servers_health(bot)

    scheduler.add_job(
        server_health_check_job,
        trigger=IntervalTrigger(minutes=5),
        id='server_health_check',
        replace_existing=True
    )

    # Speed check серверов (каждый час в :05, после того как VPN серверы отправят метрики в :00)
    async def server_speed_check_job():
        await check_servers_speed(bot)

    scheduler.add_job(
        server_speed_check_job,
        trigger=CronTrigger(minute=5),  # Every hour at :05
        id='server_speed_check',
        replace_existing=True
    )

    logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
    scheduler.start()
    await asyncio.gather(
        dp.start_polling(bot),
    )
