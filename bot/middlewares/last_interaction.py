from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, Update

from bot.database.methods.update import update_interaction_person


class LastInteractionMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        # Инициализация tgid
        tgid = None

        # Проверяем тип события Update и извлекаем вложенные данные
        if isinstance(event, Update):
            if event.message:  # Обработка обычных сообщений
                tgid = event.message.from_user.id
            elif event.callback_query:  # Обработка CallbackQuery
                tgid = event.callback_query.from_user.id

        # Если удалось извлечь tgid, обновляем взаимодействие
        if tgid:
            await update_interaction_person(tgid)

        # Передаем управление следующему обработчику
        return await handler(event, data)
