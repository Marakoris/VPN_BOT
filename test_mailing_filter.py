"""
Скрипт для тестирования фильтрации пользователей для рассылки
"""
import asyncio
from bot.database.methods.get import (
    get_users_by_server_and_vpn_type,
    get_all_server
)


async def test_filtering():
    print("=" * 60)
    print("ТЕСТ ФИЛЬТРАЦИИ ПОЛЬЗОВАТЕЛЕЙ ДЛЯ РАССЫЛКИ")
    print("=" * 60)

    # Получаем все серверы
    servers = await get_all_server()
    print(f"\n📊 Всего серверов в БД: {len(servers)}")

    if not servers:
        print("❌ Нет серверов в базе данных!")
        return

    # Показываем информацию о серверах
    print("\n🌍 Список серверов:")
    for server in servers:
        vpn_types = {0: 'Outline 🪐', 1: 'Vless 🐊', 2: 'Shadowsocks 🦈'}
        print(f"  - ID: {server.id} | Имя: {server.name} | "
              f"Тип: {vpn_types.get(server.type_vpn, 'Неизвестный')}")

    print("\n" + "=" * 60)
    print("ТЕСТ 1: Фильтрация по типу VPN")
    print("=" * 60)

    # Тестируем фильтрацию по типам VPN
    for vpn_type in [0, 1, 2]:
        vpn_names = {0: 'Outline 🪐', 1: 'Vless 🐊', 2: 'Shadowsocks 🦈'}
        users = await get_users_by_server_and_vpn_type(vpn_type=vpn_type)
        print(f"\n📡 {vpn_names[vpn_type]}: {len(users)} пользователей")

        if users:
            print("   Примеры пользователей:")
            for user in users[:5]:  # Показываем первых 5
                print(f"   - ID: {user.tgid} | Имя: {user.fullname} | "
                      f"Сервер ID: {user.server}")

    print("\n" + "=" * 60)
    print("ТЕСТ 2: Фильтрация по серверу")
    print("=" * 60)

    # Тестируем фильтрацию по серверам
    for server in servers[:3]:  # Тестируем первые 3 сервера
        users = await get_users_by_server_and_vpn_type(server_id=server.id)
        print(f"\n🌍 Сервер '{server.name}': {len(users)} пользователей")

        if users:
            print("   Примеры пользователей:")
            for user in users[:5]:
                print(f"   - ID: {user.tgid} | Имя: {user.fullname}")

    print("\n" + "=" * 60)
    print("ТЕСТ 3: Комбинированная фильтрация")
    print("=" * 60)

    # Тестируем комбинированную фильтрацию
    if servers:
        test_server = servers[0]
        vpn_type = test_server.type_vpn
        users = await get_users_by_server_and_vpn_type(
            server_id=test_server.id,
            vpn_type=vpn_type
        )
        vpn_names = {0: 'Outline 🪐', 1: 'Vless 🐊', 2: 'Shadowsocks 🦈'}
        print(f"\n🎯 Сервер '{test_server.name}' + "
              f"Тип {vpn_names.get(vpn_type, 'Неизвестный')}: "
              f"{len(users)} пользователей")

    print("\n" + "=" * 60)
    print("✅ ТЕСТ ЗАВЕРШЕН")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(test_filtering())
