import logging
import sys
from logging.handlers import RotatingFileHandler


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(filename)s:%(lineno)d "
           "[%(asctime)s] - %(name)s - %(message)s",
    handlers=[
        RotatingFileHandler(
            filename='logs/all.log',
            maxBytes=1024 * 1024 * 50,  # 50 MB per file
            backupCount=5,  # Keep 5 backup files (total ~250 MB)
            encoding='UTF-8',
        ),
        RotatingFileHandler(
            filename='logs/errors.log',
            maxBytes=1024 * 1024 * 25,  # 25 MB per file
            backupCount=3,  # Keep 3 backup files
            encoding='UTF-8',
        ),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.getLogger().handlers[1].setLevel(logging.ERROR)

from bot.main import start_bot
import asyncio

if __name__ == '__main__':
    asyncio.run(start_bot())
