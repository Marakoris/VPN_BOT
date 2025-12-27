#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, "/app")

async def run():
    from bot.misc.traffic_monitor import update_all_users_traffic
    from aiogram import Bot

    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 870499087
    bot = Bot(token="7501968261:AAFFQhRO8YLWB71rrm4zmCiixJgzy1zqwvU")

    try:
        await bot.send_message(user_id, "🔄 Начинаю обновление трафика...")
        stats = await update_all_users_traffic()

        updated = stats.get('updated', 0)
        active = stats.get('active', 0)
        exceeded = stats.get('exceeded', 0)
        errors = stats.get('errors', 0)

        msg = f"✅ Обновление трафика завершено!\n\nUpdated: {updated}\nActive: {active}\nExceeded: {exceeded}\nErrors: {errors}"
        await bot.send_message(user_id, msg)
    except Exception as e:
        await bot.send_message(user_id, f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(run())
