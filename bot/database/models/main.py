from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, ForeignKey, Table, \
    UniqueConstraint, BigInteger, TIMESTAMP, DateTime, func, Date
from sqlalchemy import Float, Boolean

from bot.database.main import engine
from bot.misc.util import CONFIG


class Base(DeclarativeBase):
    pass


class SuperOffer(Base):
    __tablename__ = 'super_offer'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    days = Column(Integer, default=31)
    price = Column(Integer, default=CONFIG.month_cost[0])


class Groups(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True)
    servers = relationship('Servers', back_populates="group_tabel")
    users = relationship('Persons', back_populates="group_tabel")


class Persons(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    tgid = Column(BigInteger, unique=True)
    client_id = Column(String, nullable=True)  # Добавил поле с ClientID
    banned = Column(Boolean, default=False)
    bot_blocked = Column(Boolean, default=False)  # Пользователь заблокировал бота
    notion_oneday = Column(Boolean, default=False)
    subscription = Column(BigInteger)
    subscription_months = Column(Integer, nullable=True)  # На сколько месяцев пользователь оформил последнюю подписку
    subscription_price = Column(Integer, nullable=True)  # По какой цене пользователь оформил последнюю подписку
    payment_method_id = Column(String, nullable=True)  # ID по которому проводится автооплата
    balance = Column(Integer, default=0)
    username = Column(String)
    fullname = Column(String)
    retention = Column(Integer, default=0)  # Сколько раз покупал подписку
    first_interaction = Column(TIMESTAMP(timezone=True), nullable=True)  # Дата первого взаимодействия
    last_interaction = Column(TIMESTAMP(timezone=True), nullable=True)  # Дата последнего взаимодействия
    referral_user_tgid = Column(BigInteger, nullable=True)
    referral_balance = Column(Integer, default=0)
    lang = Column(String, default=CONFIG.languages)
    lang_tg = Column(String, nullable=True)
    # Subscription system fields
    subscription_active = Column(Boolean, default=False)  # Активна ли subscription подписка
    subscription_token = Column(String(255), nullable=True, unique=True, index=True)  # HMAC токен для subscription URL
    subscription_created_at = Column(TIMESTAMP(timezone=True), nullable=True)  # Когда создан токен
    subscription_updated_at = Column(TIMESTAMP(timezone=True), nullable=True)  # Когда обновлен токен
    free_trial_used = Column(Boolean, default=False)  # Использовал ли пользователь бесплатный пробный период
    subscription_expired = Column(Boolean, default=False)  # Истекла ли подписка (мягкое ограничение, не бан)
    # Traffic monitoring fields
    total_traffic_bytes = Column(BigInteger, default=0)  # Суммарный трафик со всех серверов
    traffic_offset_bytes = Column(BigInteger, default=0)  # Offset для сброса трафика (при оплате)
    traffic_reset_date = Column(TIMESTAMP(timezone=True), nullable=True)  # Дата последнего сброса трафика
    traffic_limit_bytes = Column(BigInteger, default=536870912000)  # Лимит трафика (500GB по умолчанию)
    previous_traffic_bytes = Column(BigInteger, default=0)  # Предыдущее значение трафика (для отслеживания активности)
    traffic_last_change = Column(TIMESTAMP(timezone=True), nullable=True)  # Когда последний раз менялся трафик
    traffic_warning_sent = Column(Boolean, default=False)  # Отправлено ли предупреждение о 90% трафика
    setup_reminder_sent = Column(Boolean, default=False)  # Отправлено ли напоминание о настройке VPN
    server = Column(
        Integer,
        ForeignKey("servers.id", ondelete='SET NULL'),
        nullable=True)
    server_table = relationship("Servers", back_populates="users")
    group = Column(
        String,
        ForeignKey("groups.name", ondelete='SET NULL'),
        nullable=True)
    group_tabel = relationship(Groups, back_populates="users")
    payment = relationship('Payments', back_populates='payment_id')
    promocode = relationship(
        'PromoCode',
        secondary='person_promocode_association',
        back_populates='person'
    )
    withdrawal_requests = relationship(
        'WithdrawalRequests',
        back_populates='person'
    )
    subscription_logs = relationship('SubscriptionLogs', back_populates='user')


class Servers(Base):
    __tablename__ = 'servers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    type_vpn = Column(Integer, nullable=False)
    outline_link = Column(String, unique=True)
    ip = Column(String, nullable=False)
    connection_method = Column(Boolean)
    panel = Column(String)
    inbound_id = Column(Integer)
    password = Column(String)
    vds_password = Column(String)
    login = Column(String)
    work = Column(Boolean, default=True)
    space = Column(Integer, default=0)
    group = Column(
        String,
        ForeignKey("groups.name", ondelete='SET NULL'),
        nullable=True)
    group_tabel = relationship(Groups, back_populates="servers")
    users = relationship(Persons, back_populates="server_table")
    static = relationship("StaticPersons", back_populates="server_table")

    @classmethod
    def create_server(cls, data):
        return cls(**data)


class Payments(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True, index=True)
    user = Column(Integer, ForeignKey("users.id"))
    payment_id = relationship(Persons, back_populates="payment")
    payment_system = Column(String)
    amount = Column(Float)
    data = Column(DateTime)


class StaticPersons(Base):
    __tablename__ = 'static_persons'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    server = Column(Integer, ForeignKey("servers.id", ondelete='SET NULL'))
    server_table = relationship("Servers", back_populates="static")


class PromoCode(Base):
    __tablename__ = 'promocode'
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, unique=True, nullable=False)
    add_balance = Column(Integer, nullable=True)
    add_days = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # Срок действия промокода
    created_at = Column(DateTime, server_default=func.now())  # Дата создания
    person = relationship(
        'Persons',
        secondary='person_promocode_association',
        back_populates='promocode',
    )


message_button_association = Table(
    'person_promocode_association',
    Base.metadata,
    Column('promocode_id', Integer, ForeignKey(
        'promocode.id', ondelete='CASCADE'
    )),
    Column('users_id', Integer, ForeignKey(
        'users.id', ondelete='CASCADE'
    )),
    Column('used_at', DateTime, server_default=func.now()),
    UniqueConstraint('promocode_id', 'users_id', name='uq_users_promocode')
)


class WithdrawalRequests(Base):
    __tablename__ = 'withdrawal_requests'
    id = Column(Integer, primary_key=True, index=True)
    request_date = Column(TIMESTAMP(timezone=True), nullable=True, unique=True, default=func.now())
    payment_date = Column(TIMESTAMP(timezone=True), nullable=True)
    amount = Column(Integer, nullable=False)
    payment_info = Column(String, nullable=False)
    communication = Column(String)
    check_payment = Column(Boolean, default=False)
    user_tgid = Column(BigInteger, ForeignKey("users.tgid"))
    person = relationship("Persons", back_populates="withdrawal_requests")




class DailyStatistics(Base):
    __tablename__ = "daily_statistics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True, default=func.current_date())
    today_active_persons_count = Column(Integer, nullable=False, default=0)
    active_subscriptions_count = Column(Integer, nullable=False, default=0)
    active_subscriptions_sum = Column(BigInteger, nullable=False, default=0)
    active_autopay_subscriptions_count = Column(Integer, nullable=False, default=0)
    active_autopay_subscriptions_sum = Column(BigInteger, nullable=False, default=0)
    referral_balance_persons_count = Column(Integer, nullable=False, default=0)
    referral_balance_sum = Column(BigInteger, nullable=False, default=0)


class AffiliateStatistics(Base):
    __tablename__ = "affiliate_statistics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attraction_date = Column(TIMESTAMP(timezone=True), nullable=True)
    client_fullname = Column(String)
    client_tg_id = Column(BigInteger)
    referral_tg_id = Column(BigInteger)

    payment_date = Column(TIMESTAMP(timezone=True), nullable=True, default=func.now())
    payment_amount = Column(Integer, nullable=False)
    reward_percent = Column(Integer, nullable=False)
    reward_amount = Column(Integer, nullable=False)


class SubscriptionLogs(Base):
    __tablename__ = "subscription_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete='CASCADE'), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)
    servers_count = Column(Integer, nullable=True)  # Сколько серверов было в ответе
    accessed_at = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now(), index=True)

    user = relationship("Persons", back_populates="subscription_logs")


class WinbackPromo(Base):
    """
    Win-back промокоды для возврата ушедших клиентов.
    Процентная скидка на подписку в зависимости от сегмента (дней без подписки).
    promo_type: 'winback' - для ушедших клиентов, 'welcome' - для новых (не покупавших)
    """
    __tablename__ = "winback_promos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # Промокод (HOT10, WARM20, COLD30)
    discount_percent = Column(Integer, nullable=False)  # Процент скидки (10, 20, 30)
    min_days_expired = Column(Integer, nullable=False, default=0)  # Мин. дней без подписки (для winback)
    max_days_expired = Column(Integer, nullable=False, default=365)  # Макс. дней без подписки (для winback)
    valid_days = Column(Integer, nullable=False, default=7)  # Сколько дней действует промокод после отправки
    is_active = Column(Boolean, default=True)  # Активен ли промокод
    auto_send = Column(Boolean, default=False)  # Автоматическая рассылка
    promo_type = Column(String(20), default='winback')  # 'winback' или 'welcome'
    delay_days = Column(Integer, default=0)  # Задержка в днях после регистрации (для welcome промокодов)
    message_template = Column(String(1000), nullable=True)  # Шаблон сообщения (опционально)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    # Связь с использованиями
    usages = relationship("WinbackPromoUsage", back_populates="promo", cascade="all, delete-orphan")


class WinbackPromoUsage(Base):
    """
    Использование win-back промокодов пользователями.
    Отслеживает отправку и применение промокодов.
    """
    __tablename__ = "winback_promo_usages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    promo_id = Column(Integer, ForeignKey("winback_promos.id", ondelete='CASCADE'), nullable=False)
    user_tgid = Column(BigInteger, nullable=False, index=True)  # Telegram ID пользователя
    sent_at = Column(TIMESTAMP(timezone=True), server_default=func.now())  # Когда отправлен
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)  # Когда истекает
    used_at = Column(TIMESTAMP(timezone=True), nullable=True)  # Когда использован (NULL = не использован)
    discount_amount = Column(Integer, nullable=True)  # Сумма скидки в рублях (при использовании)
    original_price = Column(Integer, nullable=True)  # Оригинальная цена
    final_price = Column(Integer, nullable=True)  # Финальная цена со скидкой

    # Связь с промокодом
    promo = relationship("WinbackPromo", back_populates="usages")


async def create_all_table():
    async_engine = engine()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
