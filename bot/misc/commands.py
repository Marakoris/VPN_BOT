from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault


async def set_commands(bot: Bot):
    commands = [
        BotCommand(
            command='start',
            description='Главное меню'
        ),
        BotCommand(
            command='pay',
            description='Оплатить VPN'
        ),
        BotCommand(
            command='connect',
            description='Подключить VPN'
        ),
        BotCommand(
            command='help',
            description='Помощь и поддержка'
        ),
    ]

    await bot.set_my_commands(commands, BotCommandScopeDefault())
