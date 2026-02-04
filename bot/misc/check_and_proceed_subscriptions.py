import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.utils.formatting import Text

from bot.database.methods.get import (
    get_server_id, get_subscriptions_needing_action,
    get_daily_statistics_aggregated, MAX_AUTOPAY_RETRY, AUTOPAY_RETRY_HOURS
)
from bot.database.methods.insert import crate_or_update_stats, add_payment
from bot.database.methods.update import (
    add_time_person, server_space_update, person_one_day_false,
    person_one_day_true, add_retention_person, person_subscription_expired_true,
    person_subscription_expired_false, increment_autopay_retry, reset_autopay_retry
)
from bot.misc.subscription import activate_subscription
from bot.misc.traffic_monitor import reset_user_traffic, reset_bypass_traffic
from bot.database.models.main import Persons
from bot.keyboards.reply.user_reply import user_menu
from bot.misc.Payment.KassaSmart import KassaSmart
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

# Executor для изоляции async операций с БД после YooKassa
# Нужен потому что YooKassa нарушает greenlet контекст SQLAlchemy
_db_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="db_ops")


def _sync_increment_autopay_retry(tgid: int) -> int:
    """Синхронная версия increment_autopay_retry для использования после YooKassa.

    Использует psycopg2 напрямую чтобы избежать greenlet_spawn error.
    """
    import psycopg2
    import os

    conn = psycopg2.connect(
        dbname=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        host='db_postgres'
    )
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
            SET autopay_retry_count = COALESCE(autopay_retry_count, 0) + 1,
                autopay_last_attempt = NOW()
            WHERE tgid = %s
            RETURNING autopay_retry_count
        """, (tgid,))
        result = cur.fetchone()
        conn.commit()
        return result[0] if result else 1
    finally:
        conn.close()


def _sync_person_subscription_expired_true(tgid: int) -> bool:
    """Синхронная версия person_subscription_expired_true."""
    import psycopg2
    import os

    conn = psycopg2.connect(
        dbname=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        host='db_postgres'
    )
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
            SET subscription_expired = true
            WHERE tgid = %s
        """, (tgid,))
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_do_success_ops(tgid: int, months: int, price: int, count_second_month: int) -> bool:
    """Синхронная версия всех success операций после автоплатежа."""
    import psycopg2
    import os
    from datetime import datetime

    conn = psycopg2.connect(
        dbname=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        host='db_postgres'
    )
    try:
        cur = conn.cursor()
        # Добавляем время подписки
        cur.execute("""
            UPDATE users
            SET subscription = COALESCE(subscription, 0) + %s,
                subscription_expired = false,
                notion_oneday = true,
                autopay_retry_count = 0,
                autopay_last_attempt = NULL,
                retention = COALESCE(retention, 0) + 1
            WHERE tgid = %s
        """, (months * count_second_month, tgid))

        # Добавляем запись о платеже
        cur.execute("""
            INSERT INTO payments ("user", payment_system, amount, data)
            SELECT id, 'Autopayment by YooKassa', %s, NOW()
            FROM users WHERE tgid = %s
        """, (price, tgid))

        conn.commit()
        return True
    finally:
        conn.close()

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
    """Оптимизированная версия - один SQL запрос вместо итерации по всем юзерам"""
    stats = await get_daily_statistics_aggregated()
    log.info(f"Daily stats (optimized SQL): active_today={stats['today_active_persons_count']}, active_subs={stats['active_subscriptions_count']}")

    await crate_or_update_stats(
        date.today(),
        stats['today_active_persons_count'],
        stats['active_subscriptions_count'],
        stats['active_subscriptions_sum'],
        stats['active_autopay_subscriptions_count'],
        stats['active_autopay_subscriptions_sum'],
        stats['referral_balance_persons_count'],
        stats['referral_balance_sum']
    )


async def process_subscriptions(bot: Bot, config):
    """
    Функция для проверки и обработки подписок пользователей.
    Предназначена для использования в планировщике задач (например, APScheduler).

    СХЕМА АВТОПЛАТЕЖА:
    - За 1 день до истечения: первая попытка автоплатежа
    - Каждые 4 часа: retry до 5 попыток (всего ~20 часов)
    - Уведомления клиенту: только при первой и последней неудаче

    ОПТИМИЗИРОВАНО: Получаем только пользователей, требующих действия.
    """
    log.info("process_subscriptions started")
    try:
        current_time = int(time.time())
        one_day_later = current_time + 86400  # +1 день
        moscow_tz = ZoneInfo("Europe/Moscow")
        now = datetime.now(moscow_tz)

        # ОПТИМИЗАЦИЯ: получаем только тех, кому нужно действие (вместо всех 3000+)
        all_persons = await get_subscriptions_needing_action()
        log.info(f"Found {len(all_persons)} users needing action (optimized query)")

        for person in all_persons:
            lang_user = await get_lang(person.tgid)
            current_retry = person.autopay_retry_count or 0

            # Определяем тип обработки
            has_autopay = person.payment_method_id is not None
            subscription_expires_soon = (
                person.subscription and
                person.subscription <= one_day_later and
                person.subscription > current_time
            )
            subscription_expired = person.subscription and person.subscription < current_time

            # 1. ПРЕВЕНТИВНЫЙ АВТОПЛАТЁЖ: подписка истекает в ближайшие 24ч, есть autopay
            # 2. RETRY АВТОПЛАТЁЖ: уже были попытки, нужен следующий retry
            needs_autopay = (
                has_autopay and
                (subscription_expires_soon or subscription_expired) and
                current_retry < MAX_AUTOPAY_RETRY
            )

            if needs_autopay:
                current_tariff_cost = await get_current_tariff(person.subscription_months)

                # Проверка изменения тарифа (только для первой попытки)
                if current_retry == 0 and current_tariff_cost != person.subscription_price:
                    # Тариф изменился - отменяем автоплатёж
                    log.info(f"[Autopay] Tariff changed for user {person.tgid}, canceling autopay")
                    if subscription_expired:
                        if person.server is not None:
                            try:
                                await delete_key(person)
                            except Exception as e:
                                log.warning(f"Failed to delete key for user {person.tgid}: {e}")
                        await person_subscription_expired_true(person.tgid)
                    try:
                        await bot.send_photo(
                            chat_id=person.tgid,
                            photo=FSInputFile('bot/img/ended_subscribe.jpg'),
                            caption=_('tariff_cost_changed', lang_user)
                        )
                    except Exception as e:
                        log.error(f"Failed to send tariff change notification to {person.tgid}: {e}")
                    continue

                # Попытка автоплатежа
                attempt_type = "preventive" if subscription_expires_soon else "retry"
                log.info(f"[Autopay] {attempt_type.upper()} attempt for user {person.tgid} (attempt {current_retry + 1}/{MAX_AUTOPAY_RETRY})")

                kassa_smart = KassaSmart(
                    config=config,
                    message=None,
                    user_id=person.tgid,
                    fullname=person.fullname,
                    price=current_tariff_cost,
                    months_count=person.subscription_months,
                    price_on_db=current_tariff_cost
                )
                kassa_smart.payment_method_id = person.payment_method_id
                autopay_result = {'success': False, 'reason': None, 'card_last4': None}

                try:
                    autopay_result = await kassa_smart.create_autopayment(current_tariff_cost, bot, lang_user)
                except Exception as e:
                    log.error(f"[Autopay] Exception during payment for user {person.tgid}: {e}")
                    autopay_result = {'success': False, 'reason': str(e), 'card_last4': None}

                # После вызова YooKassa greenlet контекст нарушен
                # Запускаем ВСЕ БД операции в отдельном event loop через executor
                loop = asyncio.get_event_loop()

                if autopay_result.get('success'):
                    # УСПЕХ! Продление подписки
                    # БД операции через sync psycopg2 (избегаем greenlet_spawn)
                    try:
                        await loop.run_in_executor(
                            _db_executor,
                            _sync_do_success_ops,
                            person.tgid,
                            person.subscription_months,
                            current_tariff_cost,
                            CONFIG.COUNT_SECOND_MOTH
                        )
                    except Exception as e:
                        log.error(f"[Autopay] Error in success DB ops for user {person.tgid}: {e}")

                    # Активация подписки и сброс трафика (эти используют VPN API, не только БД)
                    try:
                        await activate_subscription(person.tgid)
                        log.info(f"[Autopay] Subscription activated for user {person.tgid}")
                    except Exception as e:
                        log.error(f"[Autopay] Failed to activate subscription for user {person.tgid}: {e}")

                    try:
                        await reset_user_traffic(person.tgid)
                        await reset_bypass_traffic(person.tgid)
                        log.info(f"[Autopay] Traffic reset for user {person.tgid}")
                    except Exception as e:
                        log.error(f"[Autopay] Failed to reset traffic for user {person.tgid}: {e}")

                    # Уведомление пользователю
                    try:
                        await bot.send_message(
                            chat_id=person.tgid,
                            text=_('payment_success', lang_user).format(
                                months_count=person.subscription_months
                            )
                        )
                    except Exception as e:
                        log.error(f"Failed to send success notification to {person.tgid}: {e}")

                    log.info(f"[Autopay] SUCCESS for user {person.tgid} on attempt {current_retry + 1}")

                    # Уведомление админам
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
                            await bot.send_message(admin_id, **text.as_kwargs())
                        except Exception as e:
                            log.error(f"Can't send message to admin {admin_id}: {e}")
                        await asyncio.sleep(0.01)
                else:
                    # НЕУДАЧА автоплатежа - sync DB операции через psycopg2
                    try:
                        new_retry_count = await loop.run_in_executor(
                            _db_executor, _sync_increment_autopay_retry, person.tgid)
                    except Exception as e:
                        log.error(f"[Autopay] Error incrementing retry for user {person.tgid}: {e}")
                        new_retry_count = 1  # Assume first failure if can't increment

                    log.info(f"[Autopay] FAILED for user {person.tgid} (attempt {new_retry_count}/{MAX_AUTOPAY_RETRY})")

                    # Проверяем исчерпаны ли попытки
                    if new_retry_count >= MAX_AUTOPAY_RETRY:
                        # Все попытки исчерпаны - финальное отключение
                        log.info(f"[Autopay] All retries exhausted for user {person.tgid}, disabling keys")

                        try:
                            await loop.run_in_executor(
                                _db_executor, _sync_person_subscription_expired_true, person.tgid)
                        except Exception as e:
                            log.error(f"[Autopay] Error in final failure ops for user {person.tgid}: {e}")

                        if person.server is not None:
                            try:
                                await delete_key(person)
                            except Exception as e:
                                log.warning(f"Failed to delete key for user {person.tgid}: {e}")

                        # ФИНАЛЬНОЕ УВЕДОМЛЕНИЕ (последняя неудача)
                        reason = autopay_result.get('reason')
                        card_last4 = autopay_result.get('card_last4')
                        reason_texts = {
                            'insufficient_funds': 'недостаточно средств на карте',
                            'card_expired': 'срок действия карты истёк',
                            'payment_method_restricted': 'способ оплаты ограничен',
                            'fraud_suspected': 'подозрение на мошенничество',
                            'general_decline': 'банк отклонил платёж',
                            'issuer_unavailable': 'банк недоступен',
                            'timeout': 'превышено время ожидания',
                        }
                        reason_text = reason_texts.get(reason, reason or 'неизвестная ошибка')
                        card_info = f" с карты **** {card_last4}" if card_last4 else ""

                        from aiogram.utils.keyboard import InlineKeyboardBuilder
                        from aiogram.types import InlineKeyboardButton
                        from bot.misc.callbackData import MainMenuAction

                        kb = InlineKeyboardBuilder()
                        kb.row(InlineKeyboardButton(
                            text="💳 Оплатить вручную",
                            callback_data="buy_subscription_no_image"
                        ))
                        kb.row(InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data=MainMenuAction(action='back_to_menu').pack()
                        ))

                        try:
                            await bot.send_message(
                                chat_id=person.tgid,
                                text=(
                                    f"❌ <b>Автоплатёж отменён</b>\n\n"
                                    f"Не удалось списать {current_tariff_cost}₽{card_info} "
                                    f"после {MAX_AUTOPAY_RETRY} попыток.\n\n"
                                    f"Последняя причина: {reason_text}\n\n"
                                    f"Ваша подписка отключена. Оплатите вручную, чтобы продолжить."
                                ),
                                reply_markup=kb.as_markup(),
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            log.error(f"Failed to send final autopay failure notification to {person.tgid}: {e}")

                    elif new_retry_count == 1:
                        # ПЕРВАЯ НЕУДАЧА - отправляем уведомление
                        attempts_left = MAX_AUTOPAY_RETRY - new_retry_count
                        reason = autopay_result.get('reason')
                        card_last4 = autopay_result.get('card_last4')
                        reason_texts = {
                            'insufficient_funds': 'недостаточно средств на карте',
                            'card_expired': 'срок действия карты истёк',
                            'payment_method_restricted': 'способ оплаты ограничен',
                            'fraud_suspected': 'подозрение на мошенничество',
                            'general_decline': 'банк отклонил платёж',
                            'issuer_unavailable': 'банк недоступен',
                            'timeout': 'превышено время ожидания',
                        }
                        reason_text = reason_texts.get(reason, reason or 'неизвестная ошибка')
                        card_info = f" с карты **** {card_last4}" if card_last4 else ""

                        from aiogram.utils.keyboard import InlineKeyboardBuilder
                        from aiogram.types import InlineKeyboardButton
                        from bot.misc.callbackData import MainMenuAction

                        kb = InlineKeyboardBuilder()
                        kb.row(InlineKeyboardButton(
                            text="💳 Оплатить сейчас",
                            callback_data="buy_subscription_no_image"
                        ))
                        kb.row(InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data=MainMenuAction(action='back_to_menu').pack()
                        ))

                        try:
                            await bot.send_message(
                                chat_id=person.tgid,
                                text=(
                                    f"⚠️ <b>Не удалось списать {current_tariff_cost}₽{card_info}</b>\n\n"
                                    f"Причина: {reason_text}\n\n"
                                    f"🔄 Повторные попытки каждые {AUTOPAY_RETRY_HOURS} часа "
                                    f"(осталось попыток: {attempts_left})\n\n"
                                    f"Вы можете оплатить вручную прямо сейчас."
                                ),
                                reply_markup=kb.as_markup(),
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            log.error(f"Failed to send first autopay failure notification to {person.tgid}: {e}")
                    else:
                        # ПРОМЕЖУТОЧНАЯ НЕУДАЧА - НЕ отправляем уведомление (тихая попытка)
                        log.info(f"[Autopay] Silent retry for user {person.tgid}, attempt {new_retry_count}/{MAX_AUTOPAY_RETRY}")

            # 3. ИСТЕЧЕНИЕ БЕЗ AUTOPAY: подписка истекла, нет автоплатежа
            elif subscription_expired and not has_autopay and not person.subscription_expired:
                log.info(f"Subscription expired for user {person.tgid} (no autopay)")
                if person.server is not None:
                    try:
                        await delete_key(person)
                    except Exception as e:
                        log.warning(f"Failed to delete key for user {person.tgid}: {e}")
                await person_subscription_expired_true(person.tgid)

            # 4. УВЕДОМЛЕНИЕ за день до истечения (для тех без автоплатежа)
            elif (subscription_expires_soon and
                  not has_autopay and
                  person.notion_oneday):
                try:
                    await bot.send_message(
                        chat_id=person.tgid,
                        text=_('alert_to_renew_sub', lang_user)
                    )
                except Exception as e:
                    log.error(f"Failed to send renewal reminder to {person.tgid}: {e}")
                await person_one_day_false(person.tgid)
                log.info(f"Sent renewal reminder to user {person.tgid}")

    except Exception as e:
        log.error(f"Error in process_subscriptions: {e}")

    try:
        await update_daily_statistics()
    except Exception as e:
        log.error(f'Error updating daily statistics: {e}')


async def get_current_tariff(months_count):
    """
    Функция для получения актуального тарифа.
    """
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
