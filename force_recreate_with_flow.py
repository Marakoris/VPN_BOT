#!/usr/bin/env python3
"""
Принудительное пересоздание клиентов с flow
"""

import asyncio
import sys
sys.path.insert(0, '/app')

from bot.misc.VPN.ServerManager import ServerManager
from bot.database.main import engine
from bot.database.models.main import Servers
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def force_recreate_vless_clients(user_id: int):
    """Удалить и пересоздать VLESS клиентов с flow"""

    print(f"\n{'='*80}")
    print(f"🔄 ПРИНУДИТЕЛЬНОЕ ПЕРЕСОЗДАНИЕ VLESS КЛЮЧЕЙ С FLOW")
    print(f"📱 Пользователь: {user_id}")
    print(f"{'='*80}\n")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Получаем только VLESS серверы (type_vpn=1)
        statement = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn == 1  # VLESS only
        )
        result = await db.execute(statement)
        servers = result.scalars().all()

        print(f"Found {len(servers)} VLESS servers\n")

        for server in servers:
            print(f"📍 Server {server.id}: {server.name}")

            try:
                server_manager = ServerManager(server)
                await server_manager.login()

                # Шаг 1: Проверяем существование клиента
                client = await server_manager.get_user(user_id)

                if client == 'User not found':
                    print(f"   ℹ️  Клиент не существует")
                    client_exists = False
                else:
                    print(f"   ✅ Клиент найден (UUID: {client.get('id', 'N/A')[:8]}...)")
                    print(f"      Current flow: {client.get('flow', 'NOT SET')}")
                    client_exists = True

                # Шаг 2: Удаляем если существует
                if client_exists:
                    print(f"   🗑️  Удаляем старого клиента...")
                    delete_result = await server_manager.delete_client(user_id)

                    if delete_result:
                        print(f"   ✅ Удалён успешно")
                    else:
                        print(f"   ⚠️  Не удалось удалить (продолжаем)")

                    # Ждём больше времени для обновления панели
                    print(f"   ⏳ Ожидание 10 секунд...")
                    await asyncio.sleep(10)

                    # Проверяем что клиент действительно удалился
                    check = await server_manager.get_user(user_id)
                    if check != 'User not found':
                        print(f"   ⚠️  Клиент всё ещё существует после удаления!")
                    else:
                        print(f"   ✅ Клиент подтверждён удалённым")

                # Шаг 3: Создаём нового с flow
                print(f"   ➕ Создаём нового клиента с flow=xtls-rprx-vision...")

                try:
                    add_result = await server_manager.add_client(user_id)

                    if add_result:
                        print(f"   ✅ Создан успешно!")
                    elif add_result is False:
                        print(f"   ❌ Ошибка создания (add_client вернул False)")
                        continue
                    else:
                        print(f"   ⚠️  Неожиданный результат: {add_result}")
                        continue
                except Exception as e:
                    print(f"   ❌ Exception при создании: {e}")
                    continue

                await asyncio.sleep(1)

                # Шаг 4: Проверяем что flow добавился
                new_client = await server_manager.get_user(user_id)

                if isinstance(new_client, dict):
                    flow = new_client.get('flow', '')
                    if flow == 'xtls-rprx-vision':
                        print(f"   🎉 FLOW ДОБАВЛЕН: {flow}")
                    elif flow:
                        print(f"   ⚠️  Flow: {flow} (не тот что ожидали)")
                    else:
                        print(f"   ❌ Flow НЕ УСТАНОВЛЕН")
                else:
                    print(f"   ⚠️  Не удалось проверить клиента")

            except Exception as e:
                print(f"   ❌ Ошибка: {e}")

            print()

    print(f"{'='*80}\n")


if __name__ == "__main__":
    user_id = 870499087
    asyncio.run(force_recreate_vless_clients(user_id))
