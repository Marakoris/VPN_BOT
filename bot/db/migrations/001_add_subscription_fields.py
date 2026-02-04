"""
Migration: Add subscription fields to database
Date: 2025-11-26
Author: Claude Code
"""
import asyncio
import asyncpg
import logging
import sys
import os

# Add bot path
sys.path.insert(0, '/root/github_repos/VPN_BOT')

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def run_migration():
    """
    Добавить поля для subscription системы
    """
    log.info("="*60)
    log.info("Starting migration: add_subscription_fields")
    log.info("="*60)

    # Подключение к БД (тестовая)
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='postgres',
        database='VPNHubBotDB_TEST'
    )

    try:
        # 1. Добавить поля в users
        log.info("1. Adding subscription fields to users table...")
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS subscription_token VARCHAR(255),
            ADD COLUMN IF NOT EXISTS subscription_created_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS subscription_updated_at TIMESTAMP;
        """)
        log.info("   ✅ Added subscription fields to users table")

        # 2. Создать индекс
        log.info("2. Creating index on subscription_token...")
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_subscription_token
            ON users(subscription_token) WHERE subscription_token IS NOT NULL;
        """)
        log.info("   ✅ Created index on subscription_token")

        # 3. Создать таблицу логов
        log.info("3. Creating subscription_logs table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                ip_address VARCHAR(45),
                user_agent VARCHAR(255),
                servers_count INTEGER,
                accessed_at TIMESTAMP DEFAULT NOW()
            );
        """)
        log.info("   ✅ Created subscription_logs table")

        # 4. Индексы для логов
        log.info("4. Creating indexes on subscription_logs...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subscription_logs_user
            ON subscription_logs(user_id);

            CREATE INDEX IF NOT EXISTS idx_subscription_logs_time
            ON subscription_logs(accessed_at);
        """)
        log.info("   ✅ Created indexes on subscription_logs")

        # 5. Добавить поля в user_keys (опционально)
        log.info("5. Adding fields to user_keys table...")
        await conn.execute("""
            ALTER TABLE user_keys
            ADD COLUMN IF NOT EXISTS created_on_demand BOOLEAN DEFAULT false,
            ADD COLUMN IF NOT EXISTS key_type INTEGER DEFAULT 1;
        """)
        log.info("   ✅ Added fields to user_keys table")
        log.info("   Note: key_type: 0=Outline, 1=VLESS, 2=Shadowsocks")

        log.info("="*60)
        log.info("✅ Migration completed successfully!")
        log.info("="*60)

    except Exception as e:
        log.error(f"❌ Migration failed: {e}")
        raise
    finally:
        await conn.close()


async def verify_migration():
    """
    Проверить что миграция выполнена
    """
    log.info("\n" + "="*60)
    log.info("Verifying migration...")
    log.info("="*60)

    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='postgres',
        database='VPNHubBotDB_TEST'
    )

    try:
        # Проверить поля в users
        result = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name IN ('subscription_token', 'subscription_created_at', 'subscription_updated_at')
            ORDER BY column_name;
        """)

        log.info("1. Fields in users table:")
        for row in result:
            log.info(f"   ✅ {row['column_name']}: {row['data_type']}")

        # Проверить таблицу subscription_logs
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'subscription_logs'
            );
        """)

        if exists:
            log.info("2. Table subscription_logs:")
            log.info(f"   ✅ EXISTS")
        else:
            log.error("2. Table subscription_logs:")
            log.error(f"   ❌ NOT EXISTS")

        # Проверить индексы
        indexes = await conn.fetch("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename IN ('users', 'subscription_logs')
            AND indexname LIKE '%subscription%'
            ORDER BY indexname;
        """)

        log.info("3. Indexes:")
        for idx in indexes:
            log.info(f"   ✅ {idx['indexname']}")

        # Проверить поля в user_keys
        result = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'user_keys'
            AND column_name IN ('created_on_demand', 'key_type')
            ORDER BY column_name;
        """)

        log.info("4. Fields in user_keys table:")
        for row in result:
            log.info(f"   ✅ {row['column_name']}: {row['data_type']}")

        log.info("="*60)
        log.info("✅ Verification completed!")
        log.info("="*60)

    finally:
        await conn.close()


async def rollback_migration():
    """
    Откат миграции (для тестов)
    """
    log.info("="*60)
    log.info("Rolling back migration: add_subscription_fields")
    log.info("="*60)

    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='postgres',
        database='VPNHubBotDB_TEST'
    )

    try:
        await conn.execute("DROP TABLE IF EXISTS subscription_logs;")
        log.info("✅ Dropped subscription_logs table")

        await conn.execute("""
            ALTER TABLE users
            DROP COLUMN IF EXISTS subscription_token,
            DROP COLUMN IF EXISTS subscription_created_at,
            DROP COLUMN IF EXISTS subscription_updated_at;
        """)
        log.info("✅ Dropped subscription fields from users")

        await conn.execute("""
            ALTER TABLE user_keys
            DROP COLUMN IF EXISTS created_on_demand,
            DROP COLUMN IF EXISTS key_type;
        """)
        log.info("✅ Dropped fields from user_keys")

        log.info("="*60)
        log.info("✅ Rollback completed")
        log.info("="*60)

    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback_migration())
    elif len(sys.argv) > 1 and sys.argv[1] == "verify":
        asyncio.run(verify_migration())
    else:
        asyncio.run(run_migration())
        asyncio.run(verify_migration())
