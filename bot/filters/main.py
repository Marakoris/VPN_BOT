from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from typing import Union
from bot.misc.util import CONFIG


class IsAdmin(Filter):
    def __init__(self):
        config = CONFIG
        self.admins_ids = config.admins_ids

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        return event.from_user.id in self.admins_ids
