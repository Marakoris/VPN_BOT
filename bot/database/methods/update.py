import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bot.database.main import engine
from bot.database.methods.get import _get_person, _get_server, get_super_offer
from bot.database.methods.insert import add_super_offer
from bot.database.models.main import Persons, WithdrawalRequests


async def add_balance_person(tgid, deposit):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.balance += int(deposit)
            await db.commit()
            return True
        return False


async def add_client_id_person(tgid, client_id):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.client_id = client_id
            await db.commit()
            return True
        return False


async def add_last_payment_data_person(tgid, payment_method_id, months, price):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person: Persons = await _get_person(db, tgid)
        if person is not None:
            person.payment_method_id = payment_method_id
            person.subscription_months = months
            person.subscription_price = price
            await db.commit()
            return True
        return False

async def delete_payment_method_id_person(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person: Persons = await _get_person(db, tgid)
        if person is not None:
            person.payment_method_id = None
            await db.commit()
            return True
        return False

async def reduce_balance_person(deposit, tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.balance -= int(deposit)
            await db.commit()
            return True
        return False


async def reduce_referral_balance_person(amount, tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.referral_balance -= int(amount)
            if person.referral_balance < 0:
                return False
            await db.commit()
            return True
        return False


async def update_balance_person(amount, tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.balance = int(amount)
            if person.balance < 0:
                return False
            await db.commit()
            return True
        return False


async def add_referral_balance_person(amount, tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.referral_balance += int(amount)
            await db.commit()
            return True
        return False


async def add_time_person(tgid, count_time):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            now_time = int(time.time()) + count_time
            if person.banned or int(time.time()) >= person.subscription:
                person.subscription = int(now_time)
                person.banned = False
                person.subscription_expired = False  # Сброс флага истечения
                # Reset notification flags when renewing subscription
                person.notion_threedays = False
                person.notion_twodays = False
                person.notion_oneday = False
                person.last_expiry_notification = 0  # Сброс timestamp ежедневных уведомлений
            else:
                person.subscription += count_time
                person.subscription_expired = False  # Сброс флага истечения
                # Reset notification flags when renewing subscription
                person.notion_threedays = False
                person.notion_twodays = False
                person.notion_oneday = False
                person.last_expiry_notification = 0  # Сброс timestamp ежедневных уведомлений
            await db.commit()

            # Автоматически активировать единую подписку при продлении
            # include_outline=True to activate ALL protocols (VLESS, Shadowsocks, Outline)
            try:
                from bot.misc.subscription import activate_subscription
                await activate_subscription(tgid, include_outline=True)
            except Exception as e:
                # Логируем ошибку, но не прерываем процесс продления
                import logging
                log = logging.getLogger(__name__)
                log.error(f"Failed to auto-activate subscription for {tgid}: {e}")

            return True
        return False


async def add_retention_person(tgid: int, retention: int):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person.retention is None:
            person.retention = retention
        else:
            person.retention += retention
        await db.commit()

async def update_interaction_person(tgid: int):
    moscow_tz = ZoneInfo("Europe/Moscow")
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person: Persons = await _get_person(db, tgid)
        if person is None:
            return
        data = datetime.now(moscow_tz)
        person.last_interaction = data
        if person.first_interaction is None:
            person.first_interaction = data
        await db.commit()

async def person_banned_true(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.server = None
            person.banned = True
            person.notion_oneday = False
            person.subscription = int(time.time())
            await db.commit()
            return True
        return False


async def person_one_day_true(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.notion_oneday = True
            await db.commit()
            return True
        return False

async def person_one_day_false(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.notion_oneday = False
            await db.commit()
            return True
        return False

async def person_three_days_true(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.notion_threedays = True
            await db.commit()
            return True
        return False

async def person_two_days_true(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.notion_twodays = True
            await db.commit()
            return True
        return False

async def reset_all_notification_flags(tgid):
    """Reset all notification flags when subscription is renewed"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.notion_threedays = False
            person.notion_twodays = False
            person.notion_oneday = False
            await db.commit()
            return True
        return False

async def update_last_expiry_notification(tgid):
    """Update timestamp of last expiry notification"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.last_expiry_notification = int(time.time())
            await db.commit()
            return True
        return False

async def person_subscription_expired_true(tgid):
    """Set subscription_expired to True (soft limit for expired subscriptions)"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.subscription_expired = True
            await db.commit()
            return True
        return False

async def person_subscription_expired_false(tgid):
    """Set subscription_expired to False (subscription renewed/active)"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.subscription_expired = False
            await db.commit()
            return True
        return False

async def person_delete_server(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.server = None
            await db.commit()
            return True
        return False


async def server_work_update(name, work):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        server = await _get_server(db, name)
        if server is not None:
            server.work = work
            await db.commit()
            return True
        return False


async def server_space_update(name, new_space):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        server = await _get_server(db, name)
        if server is not None:
            server.space = new_space
            await db.commit()
            return True
        return False


async def add_user_in_server(telegram_id, server):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await db.execute(
            select(Persons).filter(Persons.tgid == telegram_id)
        )
        person = person.scalar_one_or_none()
        person.server = server.id
        await db.commit()


async def add_pomo_code_person(tgid, promo_code):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        async with db.begin():
            statement = select(Persons).options(
                joinedload(Persons.promocode)).filter(Persons.tgid == tgid)
            result = await db.execute(statement)
            person = result.unique().scalar_one_or_none()

            if person is not None:
                # person.balance += int(promo_code.add_balance)
                person.promocode.append(promo_code)
                await db.commit()
                return True
            return False


async def succes_aplication(id_application):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        application = await db.execute(
            select(WithdrawalRequests)
            .filter(WithdrawalRequests.id == id_application)
        )
        application_instance = application.scalar_one_or_none()
        if application_instance is not None:
            application_instance.check_payment = True
            application_instance.payment_date = datetime.now().astimezone()
            await db.commit()
            return True
        return False


async def update_delete_users_server(server):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        await db.execute(
            update(Persons)
            .where(Persons.server == server.id)
            .values({"server": None})
        )
        await db.commit()


async def update_lang(lang, tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.lang = lang
            await db.commit()
            return True
        return False


async def persons_add_group(list_input, name_group=None):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.tgid.in_(list_input))
        result = await db.execute(statement)
        persons = result.scalars().all()
        if persons is not None:
            for person in persons:
                person.group = name_group
                person.server = None
            await db.commit()
            return len(persons)
        return 0

async def update_super_offer(days: int, price: int):
    super_offer = await get_super_offer()
    if super_offer is None:
        await add_super_offer(days, price)
    else:
        super_offer.days = days
        super_offer.price = price
        async with AsyncSession(autoflush=False, bind=engine()) as db:
            db.add(super_offer)
            await db.commit()


async def set_free_trial_used(tgid: int, used: bool = True):
    """Set free_trial_used flag for user"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.free_trial_used = used
            await db.commit()
            return True
        return False


async def set_traffic_source(tgid: int, source: str):
    """Set traffic_source for user (where user came from)"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.traffic_source = source
            await db.commit()
            return True
        return False


async def increment_autopay_retry(tgid: int) -> int:
    """
    Увеличить счётчик попыток автооплаты и установить время последней попытки.
    Возвращает новое значение счётчика.
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.autopay_retry_count = (person.autopay_retry_count or 0) + 1
            person.autopay_last_attempt = datetime.now(ZoneInfo("Europe/Moscow"))
            await db.commit()
            return person.autopay_retry_count
        return 0


async def reset_autopay_retry(tgid: int):
    """
    Сбросить счётчик попыток автооплаты (при успешной оплате или отмене автооплаты).
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            person.autopay_retry_count = 0
            person.autopay_last_attempt = None
            await db.commit()
            return True
        return False
