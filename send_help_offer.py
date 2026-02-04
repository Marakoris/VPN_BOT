import asyncio
import sys
sys.path.insert(0, '/app')

from aiogram import Bot
from bot.misc.util import CONFIG

# 11 пользователей без трафика
USERS = [
    5613158215,  # @Anniaaaaaaaaaaaaa
    411747047,   # @Svetlana_tea
    1008227176,  # @alexandr_kgb
    7947524114,  # @None
    5836757793,  # @None
    778072676,   # @None
    5116129785,  # @None
    6191960852,  # @QMmktHlyv
    918098455,   # @None
    8100173056,  # @None
    546012005,   # @RED0GAME
]

MESSAGE = '''Привет! 👋

У тебя активная подписка VPN, но мы заметили что ты ещё не подключался.

Может нужна помощь с настройкой? Это займёт всего пару минут:
• Поможем выбрать приложение для твоего устройства
• Настроим подключение
• Проверим что всё работает

Напиши в поддержку — разберёмся:
👉 @VPN_YouSupport_bot'''

async def main():
    bot = Bot(token=CONFIG.tg_token)
    
    success = 0
    errors = 0
    
    for tgid in USERS:
        try:
            await bot.send_message(tgid, MESSAGE)
            print(f'✅ Sent to {tgid}')
            success += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f'❌ Error {tgid}: {e}')
            errors += 1
    
    await bot.session.close()
    print(f'\nDone: {success} sent, {errors} errors')

asyncio.run(main())
