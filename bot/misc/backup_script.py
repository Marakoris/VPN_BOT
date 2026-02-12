import asyncio
import os
import shutil
from datetime import datetime
import logging
import asyncssh
import docker
from aiogram import Bot

from bot.misc.util import CONFIG

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def mail_admins(bot: Bot, text: str):
    """Send backup alerts via alerts bot"""
    from bot.misc.alerts import send_admin_alert
    await send_admin_alert(text)

async def create_backup():
    try:
        # Используем более читаемый формат даты
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file = f'{CONFIG.BACKUP_DIR}/backup_{timestamp}.sql'  # Путь внутри контейнера с PostgreSQL
        os.makedirs(CONFIG.BACKUP_DIR, exist_ok=True)

        # Использование Docker SDK для выполнения pg_dump внутри контейнера
        client = docker.from_env()
        container = client.containers.get(CONFIG.DB_CONTAINER_NAME)

        # Команда для создания бэкапа
        command = (f'pg_dump --dbname=postgresql://'
                   f'{CONFIG.postgres_user}:'
                   f'{CONFIG.postgres_password}@localhost:5432/'
                   f'{CONFIG.postgres_db} --file='
                   f'{backup_file}')

        exit_code, output = container.exec_run(command)

        if exit_code != 0:
            raise Exception(f'Failed to create backup: {output.decode()}')

        # Копирование файла .env в папку backup с новым именем
        env_file_path = '/app/.env'  # Убедитесь, что путь правильный
        env_backup_file = f'{CONFIG.BACKUP_DIR}/.env.{datetime.now().strftime("%Y.%m.%d.%H.%M.%S")}'

        if os.path.exists(env_file_path):
            shutil.copy2(env_file_path, env_backup_file)
            logger.info(f'Created .env backup: {env_backup_file}')
        else:
            env_backup_file = ''
            logger.warning(f'File {env_file_path} not found, skipping .env backup')

        # Бэкап Metabase H2 базы
        metabase_backup_file = ''
        try:
            metabase_src = '/app/metabase-data/metabase.db/metabase.db.mv.db'
            metabase_dst = f'{CONFIG.BACKUP_DIR}/metabase_{timestamp}.mv.db'
            if os.path.exists(metabase_src):
                shutil.copy2(metabase_src, metabase_dst)
                metabase_backup_file = metabase_dst
                logger.info(f'Created Metabase backup: {metabase_dst}')
            else:
                logger.warning(f'Metabase DB not found at {metabase_src}, skipping')
        except Exception as e:
            logger.error(f'Error backing up Metabase: {e}')

        logger.info(f'Created backup: {backup_file}, {env_backup_file}, {metabase_backup_file}')
        return backup_file, env_backup_file
    except Exception as e:
        logger.error(f'Error creating backup: {e}')
        raise e

async def upload_to_sftp(file_path):
    try:
        if not os.path.exists(file_path):
            logger.error(f"File {file_path} does not exist locally.")
            raise FileNotFoundError(f"File {file_path} does not exist locally.")

        async with asyncssh.connect(
            host=CONFIG.SFTP_HOST,
            username=CONFIG.SFTP_USER,
            password=CONFIG.SFTP_PASS,
            known_hosts=None  # Отключаем проверку известных хостов (не рекомендуется для production)
        ) as conn:
            async with conn.start_sftp_client() as sftp:
                remote_path = f'{CONFIG.SFTP_DIR}/{os.path.basename(file_path)}'
                await sftp.put(file_path, remote_path)
        logger.info(f'Uploaded backup to SFTP: {file_path}')
    except Exception as e:
        logger.error(f'Error uploading to SFTP: {e}')
        raise e

async def backup_and_upload_task(bot: Bot):
    try:
        # Создаём бэкап
        db_backup, config_backup = await create_backup()

        # Загружаем на SFTP только если включено в .env
        if not CONFIG.SFTP_ENABLED:
            logger.info('SFTP disabled (SFTP_ENABLED != true), skipping upload')
            return

        # Загружаем бэкап БД на SFTP
        if db_backup:
            try:
                await upload_to_sftp(db_backup)
            except Exception as e:
                await mail_admins(bot, f'Не получилось загрузить бэкап БД {db_backup} на сервер: {e}')

        # Загружаем бэкап конфигурационных файлов на SFTP
        if config_backup:
            try:
                await upload_to_sftp(config_backup)
            except Exception as e:
                await mail_admins(bot, f'Не получилось загрузить бэкап конфиг-файла {config_backup} на сервер: {e}')

    except Exception as e:
        await mail_admins(bot, f'Ошибка при создании или загрузке бэкапа: {e}')

async def backup_task(bot: Bot):
    try:
        db_backup, config_backup = await create_backup()
        return db_backup, config_backup
    except Exception as e:
        await mail_admins(bot, f'Не получилось создать бэкап: {e}')
        return None, None