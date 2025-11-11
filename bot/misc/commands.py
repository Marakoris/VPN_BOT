from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault


async def set_commands(bot: Bot):
    commands = [
        BotCommand(
            command='start',
            description='Start bot'
        ),
        BotCommand(
            command='subscription',
            description='Приобрести подписку'
        ),
        BotCommand(
            command='partnership',
            description='Партнёрская программа'
        ),
        BotCommand(
            command='bonus',
            description='Получить бонус'
        ),
    ]

    await bot.set_my_commands(commands, BotCommandScopeDefault())
