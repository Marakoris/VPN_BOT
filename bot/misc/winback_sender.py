"""
Win-back автоматическая рассылка промокодов.
Запускается раз в день, отправляет персональные промокоды
пользователям без подписки в соответствующих сегментах.
"""
import asyncio
import logging
from typing import Optional

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.methods.winback import (
    get_all_winback_promos,
    get_churned_users_by_segment,
    get_new_users_for_welcome_promo,
    create_promo_usage,
    get_promo_statistics
)
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)


async def mark_user_bot_blocked(user_tgid: int):
    """Пометить пользователя как заблокировавшего бота"""
    try:
        from datetime import datetime, timezone
        from bot.database.main import engine
        from bot.database.models.main import Persons
        from sqlalchemy import update
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(autoflush=False, bind=engine()) as db:
            await db.execute(
                update(Persons).where(Persons.tgid == user_tgid).values(
                    bot_blocked=True,
                    bot_blocked_at=datetime.now(timezone.utc)
                )
            )
            await db.commit()
            log.info(f"[Winback] Marked user {user_tgid} as bot_blocked")
    except Exception as e:
        log.error(f"[Winback] Failed to mark user {user_tgid} as bot_blocked: {e}")


async def send_winback_promo_to_user(
    bot: Bot,
    user_tgid: int,
    promo_code: str,
    discount_percent: int,
    valid_days: int,
    message_template: Optional[str] = None,
    promo_type: str = 'winback'
) -> bool:
    """
    Отправить промокод одному пользователю.
    promo_type: 'winback' для ушедших, 'welcome' для новых.
    Возвращает True если сообщение отправлено успешно.
    """
    try:
        # Формируем сообщение
        if message_template:
            message = message_template.format(
                code=promo_code,
                discount=discount_percent,
                valid_days=valid_days
            )
        elif promo_type == 'welcome':
            # Рассчитываем цены со скидкой
            prices = CONFIG.month_cost  # [150, 400, 750, 1400]
            p1 = int(int(prices[0]) * (100 - discount_percent) / 100)
            p3 = int(int(prices[1]) * (100 - discount_percent) / 100)
            p6 = int(int(prices[2]) * (100 - discount_percent) / 100)
            p12 = int(int(prices[3]) * (100 - discount_percent) / 100)

            # Текст для новых пользователей
            message = (
                f"🎁 <b>Персональная скидка для вас!</b>\n\n"
                f"Вы зарегистрировались в нашем VPN-сервисе, "
                f"но ещё не попробовали его в деле.\n\n"
                f"Специально для вас — скидка <b>{discount_percent}%</b> на первую покупку!\n\n"
                f"<b>💰 Цены со скидкой:</b>\n"
                f"├ 1 мес: <s>{prices[0]}₽</s> → <b>{p1}₽</b>\n"
                f"├ 3 мес: <s>{prices[1]}₽</s> → <b>{p3}₽</b>\n"
                f"├ 6 мес: <s>{prices[2]}₽</s> → <b>{p6}₽</b>\n"
                f"└ 12 мес: <s>{prices[3]}₽</s> → <b>{p12}₽</b>\n\n"
                f"⏰ Скидка действует <b>{valid_days} дней</b>\n\n"
                f"<b>Что вы получите:</b>\n"
                f"✅ 500 ГБ трафика в месяц\n"
                f"✅ Безлимит устройств\n"
                f"✅ 10+ серверов в разных странах\n"
                f"✅ Работает в России и за рубежом\n"
                f"✅ Обход белых списков мобильных операторов\n"
                f"✅ Поддержка 24/7\n\n"
                f"👇 <b>Нажмите кнопку чтобы применить скидку</b>"
            )
        else:
            # Рассчитываем цены со скидкой
            prices = CONFIG.month_cost
            p1 = int(int(prices[0]) * (100 - discount_percent) / 100)
            p3 = int(int(prices[1]) * (100 - discount_percent) / 100)
            p6 = int(int(prices[2]) * (100 - discount_percent) / 100)
            p12 = int(int(prices[3]) * (100 - discount_percent) / 100)

            # Текст для ушедших пользователей (winback)
            message = (
                f"🎁 <b>Мы скучаем по вам!</b>\n\n"
                f"Давно не виделись! Специально для вас — скидка <b>{discount_percent}%</b> на продление:\n\n"
                f"<b>💰 Цены со скидкой:</b>\n"
                f"├ 1 мес: <s>{prices[0]}₽</s> → <b>{p1}₽</b>\n"
                f"├ 3 мес: <s>{prices[1]}₽</s> → <b>{p3}₽</b>\n"
                f"├ 6 мес: <s>{prices[2]}₽</s> → <b>{p6}₽</b>\n"
                f"└ 12 мес: <s>{prices[3]}₽</s> → <b>{p12}₽</b>\n\n"
                f"⏰ Скидка действует <b>{valid_days} дней</b>\n\n"
                f"<b>Напоминаем что входит:</b>\n"
                f"✅ 500 ГБ трафика в месяц\n"
                f"✅ Безлимит устройств\n"
                f"✅ 10+ серверов в разных странах\n"
                f"✅ Работает в России и за рубежом\n"
                f"✅ Обход белых списков мобильных операторов\n\n"
                f"👇 <b>Нажмите кнопку чтобы применить скидку</b>"
            )

        # Кнопка для автоматического применения промокода
        from bot.misc.callbackData import ApplyPromoCode
        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Применить скидку {discount_percent}%", callback_data=ApplyPromoCode(code=promo_code))
        kb.adjust(1)

        await bot.send_message(
            chat_id=user_tgid,
            text=message,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        return True

    except Exception as e:
        error_str = str(e).lower()
        # Пометить пользователя как заблокировавшего бота
        if 'bot was blocked by the user' in error_str or 'user is deactivated' in error_str:
            await mark_user_bot_blocked(user_tgid)
        log.warning(f"[Winback] Failed to send promo to user {user_tgid}: {e}")
        return False


async def winback_autosend(bot: Bot):
    """
    Автоматическая рассылка win-back промокодов.
    Вызывается по расписанию (например, раз в день).
    """
    log.info("[Winback] Starting automatic promo code distribution...")

    try:
        # Получить все активные промокоды с включённой автоотправкой
        all_promos = await get_all_winback_promos(active_only=True)
        auto_promos = [p for p in all_promos if p.auto_send]

        if not auto_promos:
            log.info("[Winback] No promos with auto_send enabled")
            return

        log.info(f"[Winback] Found {len(auto_promos)} promos with auto_send enabled")

        total_sent = 0
        total_errors = 0
        results_by_promo = {}

        for promo in auto_promos:
            promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'

            if promo_type == 'welcome':
                delay_days = getattr(promo, 'delay_days', 0) or 0
                log.info(f"[Winback] Processing WELCOME promo '{promo.code}' "
                         f"(discount: {promo.discount_percent}%, delay: {delay_days} days)")
                # Для welcome - новые пользователи (retention=0)
                users = await get_new_users_for_welcome_promo(
                    exclude_already_sent_promo_id=promo.id,
                    delay_days=delay_days
                )
            else:
                log.info(f"[Winback] Processing promo '{promo.code}' "
                         f"(segment: {promo.min_days_expired}-{promo.max_days_expired} days, "
                         f"discount: {promo.discount_percent}%)")
                # Для winback - ушедшие пользователи
                users = await get_churned_users_by_segment(
                    min_days=promo.min_days_expired,
                    max_days=promo.max_days_expired,
                    exclude_already_sent_promo_id=promo.id
                )

            if not users:
                log.info(f"[Winback] No users for promo '{promo.code}'")
                results_by_promo[promo.code] = {'sent': 0, 'errors': 0, 'users_in_segment': 0}
                continue

            log.info(f"[Winback] Found {len(users)} users for promo '{promo.code}'")

            sent_count = 0
            error_count = 0

            for user in users:
                # Создать запись об отправке
                usage = await create_promo_usage(
                    promo_id=promo.id,
                    user_tgid=user.tgid,
                    valid_days=promo.valid_days
                )

                if not usage:
                    # Уже отправляли этому пользователю
                    continue

                # Отправить сообщение
                success = await send_winback_promo_to_user(
                    bot=bot,
                    user_tgid=user.tgid,
                    promo_code=promo.code,
                    discount_percent=promo.discount_percent,
                    valid_days=promo.valid_days,
                    message_template=promo.message_template,
                    promo_type=promo_type
                )

                if success:
                    sent_count += 1
                    total_sent += 1
                else:
                    error_count += 1
                    total_errors += 1

                # Небольшая задержка между отправками
                await asyncio.sleep(0.05)

            results_by_promo[promo.code] = {
                'sent': sent_count,
                'errors': error_count,
                'users_in_segment': len(users)
            }
            log.info(f"[Winback] Promo '{promo.code}': sent {sent_count}, errors {error_count}")

        # Итоговый лог
        log.info(f"[Winback] Automatic distribution completed: "
                 f"total sent {total_sent}, total errors {total_errors}")

        # Отправить отчёт администраторам (если есть что отправлять)
        if total_sent > 0 or total_errors > 0:
            await send_winback_report_to_admins(bot, results_by_promo, total_sent, total_errors)

    except Exception as e:
        log.error(f"[Winback] Error in automatic distribution: {e}")


async def send_winback_report_to_admins(
    bot: Bot,
    results_by_promo: dict,
    total_sent: int,
    total_errors: int
):
    """Отправить отчёт о рассылке администраторам"""
    try:
        report_lines = ["📊 <b>Отчёт Win-back рассылки</b>\n"]

        for code, stats in results_by_promo.items():
            if stats['sent'] > 0 or stats['errors'] > 0:
                report_lines.append(
                    f"🏷 <code>{code}</code>: "
                    f"✅ {stats['sent']} | ❌ {stats['errors']} | "
                    f"👥 {stats['users_in_segment']} в сегменте"
                )

        report_lines.append(f"\n<b>Итого:</b> ✅ {total_sent} отправлено | ❌ {total_errors} ошибок")

        report_text = "\n".join(report_lines)

        from bot.misc.alerts import send_admin_alert
        await send_admin_alert(report_text)

    except Exception as e:
        log.error(f"[Winback] Error sending report to admins: {e}")


async def manual_send_promo_to_segment(
    bot: Bot,
    promo_id: int,
    admin_tgid: int
) -> dict:
    """
    Ручная отправка промокода сегменту (вызывается из админки).
    Возвращает статистику отправки.
    """
    from bot.database.methods.winback import get_winback_promo

    promo = await get_winback_promo(promo_id)
    if not promo:
        return {'success': False, 'error': 'Промокод не найден'}

    # Получить пользователей в сегменте
    users = await get_churned_users_by_segment(
        min_days=promo.min_days_expired,
        max_days=promo.max_days_expired,
        exclude_already_sent_promo_id=promo.id
    )

    if not users:
        return {'success': True, 'sent': 0, 'errors': 0, 'message': 'Нет пользователей в сегменте'}

    # Отправить уведомление о начале
    try:
        await bot.send_message(
            admin_tgid,
            f"🚀 Начинаю рассылку промокода <code>{promo.code}</code>...\n"
            f"👥 Пользователей в сегменте: {len(users)}",
            parse_mode="HTML"
        )
    except:
        pass

    sent_count = 0
    error_count = 0

    for user in users:
        # Создать запись об отправке
        usage = await create_promo_usage(
            promo_id=promo.id,
            user_tgid=user.tgid,
            valid_days=promo.valid_days
        )

        if not usage:
            continue

        # Отправить сообщение
        success = await send_winback_promo_to_user(
            bot=bot,
            user_tgid=user.tgid,
            promo_code=promo.code,
            discount_percent=promo.discount_percent,
            valid_days=promo.valid_days,
            message_template=promo.message_template
        )

        if success:
            sent_count += 1
        else:
            error_count += 1

        await asyncio.sleep(0.05)

    return {
        'success': True,
        'sent': sent_count,
        'errors': error_count,
        'total_users': len(users)
    }
