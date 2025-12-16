#!/usr/bin/env python3
"""
Скрипт миграции пользователя на новые ключи с flow=xtls-rprx-vision
"""

import asyncio
import sys
sys.path.insert(0, '/root/github_repos/VPN_BOT')

from bot.misc.subscription import expire_subscription, activate_subscription


async def migrate_user_to_flow(user_id: int):
    """Пересоздать ключи пользователя с flow"""

    print(f"\n{'='*80}")
    print(f"🔄 МИГРАЦИЯ ПОЛЬЗОВАТЕЛЯ {user_id} НА КЛЮЧИ С FLOW")
    print(f"{'='*80}\n")

    # Шаг 1: Отключаем старые ключи
    print(f"\n📍 Шаг 1/2: Отключаем старые ключи...")
    try:
        result = await expire_subscription(user_id)
        print(f"   ✅ Старые ключи отключены")
    except Exception as e:
        print(f"   ⚠️  Ошибка отключения: {e}")

    # Небольшая пауза
    await asyncio.sleep(2)

    # Шаг 2: Создаём новые ключи с flow
    print(f"\n📍 Шаг 2/2: Создаём новые ключи с flow=xtls-rprx-vision...")
    try:
        new_token = await activate_subscription(user_id, include_outline=True)
        print(f"   ✅ Новые ключи созданы!")
        print(f"   Token: {new_token[:50]}...")
    except Exception as e:
        print(f"   ❌ Ошибка создания: {e}")
        return False

    print(f"\n{'='*80}")
    print(f"✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
    print(f"{'='*80}\n")

    print(f"📲 Новый Subscription URL:")
    print(f"http://185.58.204.196:8003/sub/{new_token}")
    print(f"\n{'='*80}\n")

    return True


if __name__ == "__main__":
    user_id = 870499087  # Тестовый пользователь

    result = asyncio.run(migrate_user_to_flow(user_id))

    if result:
        print("🎉 Готово! Теперь все ключи имеют flow=xtls-rprx-vision")
        sys.exit(0)
    else:
        print("❌ Миграция не удалась")
        sys.exit(1)
