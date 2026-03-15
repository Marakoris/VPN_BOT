import asyncio

from bot.database.main import engine
from bot.database.methods.delete import drop_all
from bot.database.models.main import Base

if __name__ == "__main__":
    asyncio.run(drop_all(engine(), Base))
