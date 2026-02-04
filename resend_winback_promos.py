#!/usr/bin/env python3
"""
Повторная рассылка winback промокодов тем, кто получил но не использовал.
"""
import asyncio
import os
import sys
import time

# Добавляем путь к проекту
sys.path.insert(0, '/root/VPNHubBot')

from aiogram import Bot
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import WinbackPromo, WinbackPromoUsage, Persons
from bot.misc.winback_sender import send_winback_promo_to_user


async def resend_unused_promos():
    """Повторная отправка промокодов тем, кто не использовал"""

    # Инициализация бота
    bot_token = os.getenv('TG_TOKEN')
    if not bot_token:
        from dotenv import load_dotenv
        load_dotenv('/root/VPNHubBot/.env')
        bot_token = os.getenv('TG_TOKEN')

    bot = Bot(token=bot_token)

    promo_codes = ['COMEBACK30', 'MISSYOU40', 'SPECIAL50', 'WELCOME70']

    total_sent = 0
    total_errors = 0
    results = {}

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        for code in promo_codes:
            # Получаем промокод
            promo_result = await db.execute(
                select(WinbackPromo).filter(WinbackPromo.code == code)
            )
            promo = promo_result.scalar_one_or_none()
            if not promo:
                print(f"❌ Промокод {code} не найден")
                continue

            # Получаем пользователей: получили, но не использовали, не заблокировали бота
            # И подписка ИСТЕКЛА (не отправляем тем, у кого активная подписка)
            current_time = int(time.time())
            stmt = select(WinbackPromoUsage, Persons).join(
                Persons, WinbackPromoUsage.user_tgid == Persons.tgid
            ).filter(
                WinbackPromoUsage.promo_id == promo.id,
                WinbackPromoUsage.used_at.is_(None),  # Не использовали
                or_(Persons.bot_blocked == False, Persons.bot_blocked.is_(None)),
                or_(Persons.banned == False, Persons.banned.is_(None)),
                # ИСПРАВЛЕНИЕ: только с истёкшей подпиской
                or_(Persons.subscription.is_(None), Persons.subscription < current_time)
            )

            result = await db.execute(stmt)
            users_data = result.all()

            if not users_data:
                print(f"📭 {code}: нет пользователей для рассылки")
                results[code] = {'sent': 0, 'errors': 0}
                continue

            print(f"\n📤 {code} ({promo.discount_percent}%): отправка {len(users_data)} пользователям...")

            sent_count = 0
            error_count = 0

            for usage, person in users_data:
                success = await send_winback_promo_to_user(
                    bot=bot,
                    user_tgid=person.tgid,
                    promo_code=promo.code,
                    discount_percent=promo.discount_percent,
                    valid_days=promo.valid_days,
                    message_template=promo.message_template,
                    promo_type='winback'
                )

                if success:
                    sent_count += 1
                    total_sent += 1
                    print(f"  ✅ {person.tgid} (@{person.username or 'no_username'})")
                else:
                    error_count += 1
                    total_errors += 1
                    print(f"  ❌ {person.tgid} (@{person.username or 'no_username'})")

                # Задержка между отправками
                await asyncio.sleep(0.05)

            results[code] = {'sent': sent_count, 'errors': error_count}
            print(f"  Итого {code}: ✅ {sent_count} | ❌ {error_count}")

    await bot.session.close()

    # Финальный отчёт
    print("\n" + "="*50)
    print("📊 ИТОГОВЫЙ ОТЧЁТ")
    print("="*50)
    for code, stats in results.items():
        print(f"{code}: ✅ {stats['sent']} отправлено | ❌ {stats['errors']} ошибок")
    print(f"\nВСЕГО: ✅ {total_sent} отправлено | ❌ {total_errors} ошибок")

    return total_sent, total_errors


if __name__ == '__main__':
    print("🚀 Запуск повторной рассылки winback промокодов...")
    print("="*50)
    asyncio.run(resend_unused_promos())
