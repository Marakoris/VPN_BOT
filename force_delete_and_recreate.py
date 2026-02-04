#!/usr/bin/env python3
"""
Полное удаление и пересоздание ключей с flow
"""

import asyncio
import sys
sys.path.insert(0, '/app')

from bot.misc.VPN.ServerManager import get_server_by_id
from bot.misc.subscription import activate_subscription
from bot.database.main import engine
from bot.database.models import Servers
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def force_delete_user_keys(user_id: int):
    """Полностью удалить все ключи пользователя"""

    print(f"\n{'='*80}")
    print(f"🗑️  ПОЛНОЕ УДАЛЕНИЕ КЛЮЧЕЙ ПОЛЬЗОВАТЕЛЯ {user_id}")
    print(f"{'='*80}\n")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Получаем все серверы
        statement = select(Servers).filter(Servers.work == True)
        result = await db.execute(statement)
        servers = result.scalars().all()

        for server in servers:
            try:
                print(f"📍 Server {server.id} ({server.name})...")
                server_manager = await get_server_by_id(server.id)

                # Проверяем есть ли клиент
                client = await server_manager.get_user(user_id)

                if not client:
                    print(f"   ℹ️  Клиент не найден")
                    continue

                # Полное удаление
                if server.type_vpn == 0:  # Outline
                    # Для Outline используем специальный метод
                    result = await server_manager.client.delete_key(user_id)
                    if result:
                        print(f"   ✅ Outline ключ удалён")
                    else:
                        print(f"   ⚠️  Не удалось удалить Outline ключ")

                elif server.type_vpn in [1, 2]:  # VLESS or Shadowsocks
                    # Используем метод delete_client (если есть)
                    # Если нет - сначала disable, потом recreate сделает своё дело
                    await server_manager.disable_client(user_id)
                    print(f"   ✅ Ключ отключен (будет пересоздан)")

            except Exception as e:
                print(f"   ❌ Ошибка: {e}")

    print(f"\n{'='*80}\n")


async def main():
    user_id = 870499087

    # Шаг 1: Удалить все ключи
    await force_delete_user_keys(user_id)

    # Пауза
    await asyncio.sleep(2)

    # Шаг 2: Создать новые с flow
    print(f"\n{'='*80}")
    print(f"🔧 СОЗДАНИЕ НОВЫХ КЛЮЧЕЙ С FLOW")
    print(f"{'='*80}\n")

    token = await activate_subscription(user_id, include_outline=True)

    print(f"\n✅ Новый subscription token: {token[:50]}...")
    print(f"📲 URL: http://185.58.204.196:8003/sub/{token}")
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
