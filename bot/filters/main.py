from aiogram.filters import Filter
from aiogram.types import Message
from bot.misc.util import CONFIG


class IsAdmin(Filter):
    def __init__(self):
        config = CONFIG
        self.admins_ids = config.admins_ids

    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in self.admins_ids
