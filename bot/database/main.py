from sqlalchemy.ext.asyncio import create_async_engine

from bot.misc.util import CONFIG


if CONFIG.debug:
    ENGINE = "sqlite+aiosqlite:///bot/database/DatabaseVPN.db"
else:
    ENGINE = (
        f'postgresql+asyncpg://'
        f'{CONFIG.postgres_user}:'
        f'{CONFIG.postgres_password}'
        f'@postgres_db_container/{CONFIG.postgres_db}'
    )


def engine():
    engine = create_async_engine(ENGINE)
    return engine
