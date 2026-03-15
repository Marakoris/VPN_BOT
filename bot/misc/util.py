import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    admins_ids: list[int]
    month_cost: list
    deposit: list
    auto_extension: bool = False
    trial_period: int
    UTC_time: int
    max_people_server: int
    limit_ip: int
    limit_GB: int
    tg_token: str
    yoomoney_token: str
    yoomoney_wallet_token: str
    tg_wallet_token: str = ''
    lava_token_secret: str
    lava_id_project: str
    yookassa_shop_id: str
    yookassa_secret_key: str
    cryptomus_key: str
    cryptomus_uuid: str
    referral_day: int
    referral_percent: int
    minimum_withdrawal_amount: int
    COUNT_SECOND_DAY: int = 86400
    COUNT_SECOND_MOTH: int = 2678400
    languages: str
    name: str
    id_channel: int = 1
    link_channel: str = ''
    crypto_bot_api: str = ''
    debug: bool = False
    postgres_db: str
    postgres_user: str
    postgres_password: str
    max_count_groups: int = 100
    import_bd: int = 0
    token_stars: str
    ym_counter: str
    ym_oauth_token: str
    offer_url: str
    BACKUP_INTERVAL: int
    UPLOAD_INTERVAL: int
    SFTP_ENABLED: bool
    SFTP_HOST: str
    SFTP_USER: str
    subscription_api_url: str
    SFTP_PASS: str
    SFTP_DIR: str
    BACKUP_DIR: str
    DB_CONTAINER_NAME: str
    # LINK_

    def __init__(self):
        self.read_evn()

    def read_evn(self):
        admins_ids = os.getenv('ADMINS_IDS')
        if admins_ids == '' or admins_ids is None:
            raise ValueError('Write your ID Telegram to ADMINS_IDS')

        self.admins_ids = [int(admin_id.strip()) for admin_id in admins_ids.split(',')]

        self.tg_token = os.getenv('TG_TOKEN')
        if self.tg_token is None:
            raise ValueError('Write your TOKEN TelegramBot to TG_TOKEN')

        self.name = os.getenv('NAME')
        if self.name is None:
            raise ValueError('Write your name bot to NAME')

        self.languages = os.getenv('LANGUAGES')
        if self.languages is None:
            raise ValueError('Write your languages bot to LANGUAGES')

        try:
            self.month_cost = os.getenv('MONTH_COST').split(',')
            if self.month_cost is None:
                raise ValueError('Write your price month to MONTH_COST')
        except Exception as e:
            raise ValueError(
                'You filled in the MONTH_COST field incorrectly', e
            )

        try:
            self.deposit = os.getenv('DEPOSIT').split(',')
            if self.deposit is None:
                raise ValueError('Write your price to DEPOSIT')
        except Exception as e:
            raise ValueError(
                'You filled in the DEPOSIT field incorrectly', e
            )

        trial_period = os.getenv('TRIAL_PERIOD')
        if trial_period == '':
            raise ValueError(
                'Write your time trial period sec to TRIAL_PERIOD'
            )
        self.trial_period = int(trial_period)

        max_people_server = os.getenv('MAX_PEOPLE_SERVER')
        if max_people_server == '':
            raise ValueError(
                'Write your maximum people one server to MAX_PEOPLE_SERVER'
            )
        self.max_people_server = int(max_people_server)

        utc_time = os.getenv('UTC_TIME')
        if utc_time == '':
            raise ValueError('Write your UTC TIME to UTC_TIME')
        self.UTC_time = int(utc_time)

        referral_day = os.getenv('REFERRAL_DAY')
        if referral_day == '':
            raise ValueError('Write your day per referral to REFERRAL_DAY')
        self.referral_day = int(referral_day)

        referral_percent = os.getenv('REFERRAL_PERCENT')
        if referral_percent == '':
            raise ValueError(
                'Write your percent per referral to REFERRAL_PERCENT'
            )
        self.referral_percent = int(referral_percent)

        minimum_withdrawal_amount = os.getenv('MINIMUM_WITHDRAWAL_AMOUNT')
        if minimum_withdrawal_amount == '':
            raise ValueError(
                'Write your minimum withdrawal amount to '
                'MINIMUM_WITHDRAWAL_AMOUNT'
            )
        self.minimum_withdrawal_amount = int(minimum_withdrawal_amount)

        limit_ip = os.getenv('LIMIT_IP')
        self.limit_ip = int(limit_ip if limit_ip != '' else 0)

        limit_gb = os.getenv('LIMIT_GB')
        self.limit_GB = int(limit_gb if limit_gb != '' else 0)

        import_bd = os.getenv('IMPORT_DB')
        self.import_bd = int(import_bd if import_bd != '' else 0)

        token_stars = os.getenv('TG_STARS')
        self.token_stars = '' if token_stars != 'off' else token_stars
        token_stars = os.getenv('TG_STARS_DEV')
        self.token_stars = '' if token_stars == 'run' else self.token_stars

        self.yoomoney_token = os.getenv('YOOMONEY_TOKEN', '')
        self.yoomoney_wallet_token = os.getenv('YOOMONEY_WALLET', '')
        self.lava_token_secret = os.getenv('LAVA_TOKEN_SECRET', '')
        self.lava_id_project = os.getenv('LAVA_ID_PROJECT', '')
        self.yookassa_shop_id = os.getenv('YOOKASSA_SHOP_ID', '')
        self.yookassa_secret_key = os.getenv('YOOKASSA_SECRET_KEY', '')
        self.cryptomus_key = os.getenv('CRYPTOMUS_KEY', '')
        self.cryptomus_uuid = os.getenv('CRYPTOMUS_UUID', '')
        self.crypto_bot_api = os.getenv('CRYPTO_BOT_API', '')
        self.debug = os.getenv('DEBUG') == 'True'
        self.postgres_db = os.getenv('POSTGRES_DB', '')
        if self.postgres_db == '':
            raise ValueError('Write your name DB to POSTGRES_DB')
        self.postgres_user = os.getenv('POSTGRES_USER', '')
        if self.postgres_user == '':
            raise ValueError('Write your login DB to POSTGRES_USER')
        self.postgres_password = os.getenv('POSTGRES_PASSWORD', '')
        if self.postgres_password == '':
            raise ValueError('Write your password DB to POSTGRES_PASSWORD')
        pg_email = os.getenv('PGADMIN_DEFAULT_EMAIL', '')
        if pg_email == '':
            raise ValueError('Write your email to PGADMIN_DEFAULT_EMAIL')
        pg_password = os.getenv('PGADMIN_DEFAULT_PASSWORD', '')
        if pg_password == '':
            raise ValueError('Write your password to PGADMIN_DEFAULT_PASSWORD')
        self.ym_counter = os.getenv("YM_COUNTER", "")
        # YM Counter is optional for test environment
        self.ym_oauth_token = os.getenv('YM_AUTH_TOKEN', '')
        # YM OAuth token is optional for test environment
        self.offer_url = os.getenv('OFFER_URL', '')
        # Offer URL is optional for test environment

        self.BACKUP_INTERVAL = int(os.getenv('BACKUP_INTERVAL', 3))
        self.UPLOAD_INTERVAL = int(os.getenv('UPLOAD_INTERVAL', 90))
        self.SFTP_ENABLED = os.getenv('SFTP_ENABLED', 'false').lower() in ('true', '1', 'yes')
        self.SFTP_HOST = os.getenv('SFTP_HOST', '')
        # SFTP is optional for test environment
        self.SFTP_USER = os.getenv('SFTP_USER', '')
        # SFTP User is optional for test environment
        self.SFTP_PASS = os.getenv('SFTP_PASS', '')
        # SFTP Pass is optional for test environment
        self.SFTP_DIR = os.getenv('SFTP_DIR', '/')
        # SFTP Dir is optional for test environment
        self.BACKUP_DIR = '/app/backups'
        self.DB_CONTAINER_NAME = 'postgres_db_container'  # Имя контейнера с PostgreSQL

        # Subscription API URL
        self.subscription_api_url = os.getenv('SUBSCRIPTION_API_URL', 'http://localhost:8003')

        # Alerts bot (separate bot for technical alerts)
        self.alerts_bot_token = os.getenv('ALERTS_BOT_TOKEN', '')
        self.alerts_chat_id = os.getenv('ALERTS_CHAT_ID', '')


CONFIG = Config()
