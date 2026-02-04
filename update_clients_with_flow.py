#!/usr/bin/env python3
"""
Обновление существующих VLESS клиентов - добавление flow
"""

import asyncio
import sys
sys.path.insert(0, '/app')

from bot.misc.VPN.ServerManager import ServerManager
from bot.database.main import engine
from bot.database.models.main import Servers
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def update_vless_clients_with_flow(user_id: int):
    """Обновить VLESS клиентов добавив flow=xtls-rprx-vision"""

    print(f"\n{'='*80}")
    print(f"🔄 ОБНОВЛЕНИЕ VLESS КЛИЕНТОВ - ДОБАВЛЕНИЕ FLOW")
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

                # Проверяем существование клиента
                client = await server_manager.get_user(user_id)

                if client == 'User not found':
                    print(f"   ℹ️  Клиент не найден")
                    continue

                print(f"   ✅ Клиент найден (UUID: {client.get('id', 'N/A')[:8]}...)")
                print(f"      Current flow: '{client.get('flow', '')}'")

                # Обновляем с flow
                print(f"   🔄 Обновляем клиента добавляя flow=xtls-rprx-vision...")

                result = await server_manager.client.update_client_flow(user_id)

                if result:
                    print(f"   ✅ Обновлено успешно!")

                    # Проверяем что flow добавился
                    await asyncio.sleep(2)
                    updated_client = await server_manager.get_user(user_id)

                    if isinstance(updated_client, dict):
                        flow = updated_client.get('flow', '')
                        if flow == 'xtls-rprx-vision':
                            print(f"   🎉 FLOW ПОДТВЕРЖДЁН: {flow}")
                        elif flow:
                            print(f"   ⚠️  Flow: {flow} (неожиданное значение)")
                        else:
                            print(f"   ❌ Flow всё ещё пустой")
                else:
                    print(f"   ❌ Ошибка обновления")

            except Exception as e:
                print(f"   ❌ Ошибка: {e}")

            print()

    print(f"{'='*80}\n")


if __name__ == "__main__":
    user_id = 870499087
    asyncio.run(update_vless_clients_with_flow(user_id))
