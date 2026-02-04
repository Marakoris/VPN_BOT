import datetime
import time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.methods.get import _get_person
from bot.database.models.main import (
    Persons,
    Payments,
    StaticPersons,
    PromoCode,
    WithdrawalRequests, Groups, SuperOffer, DailyStatistics, AffiliateStatistics
)


async def add_new_person(from_user, username, subscription, ref_user, client_id):
    moscow_tz = ZoneInfo("Europe/Moscow")
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Если subscription > 0 - добавляем к текущему времени
        # Если subscription == 0 - оставляем 0 (пробный период активируется отдельно)
        subscription_time = int(time.time()) + subscription if subscription > 0 else 0
        tom = Persons(
            tgid=from_user.id,
            username=username,
            fullname=from_user.full_name,
            subscription=subscription_time,
            lang_tg=from_user.language_code or None,
            referral_user_tgid=ref_user or None,
            client_id=client_id,
            first_interaction=datetime.datetime.now(moscow_tz),
            banned=False  # Новый пользователь не забанен
        )
        db.add(tom)
        await db.commit()


async def add_payment(tgid: int, deposit: float, payment_system: str):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        person = await _get_person(db, tgid)
        if person is not None:
            payment = Payments(
                amount=deposit,
                data=datetime.datetime.now(),
                payment_system=payment_system
            )
            payment.user = person.id
            db.add(payment)
            await db.commit()


async def add_server(server):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        db.add(server)
        await db.commit()


async def add_static_user(name, server):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        static_user = StaticPersons(
            name=name,
            server=server
        )
        db.add(static_user)
        await db.commit()


async def add_promo(text_promo, add_days, expires_at=None):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        promo_code = PromoCode(
            text=text_promo,
            add_days=add_days,
            expires_at=expires_at
        )
        db.add(promo_code)
        await db.commit()


async def add_withdrawal(tgid, amount, payment_info, communication):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        withdrawal = WithdrawalRequests(
            amount=amount,
            payment_info=payment_info,
            user_tgid=tgid,
            communication=communication
        )
        db.add(withdrawal)
        await db.commit()


async def add_group(group_name):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        group = Groups(
            name=group_name
        )
        db.add(group)
        await db.commit()


async def add_super_offer(days: int, price: int):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        super_offer = SuperOffer(
            days=days,
            price=price
        )
        db.add(super_offer)
        await db.commit()


async def crate_or_update_stats(day, today_active_persons_count: int, active_subscriptions_count: int,
                                active_subscriptions_sum: int, active_autopay_subscriptions_count: int,
                                active_autopay_subscriptions_sum: int, referral_balance_persons_count: int,
                                referral_balance_sum):
    async with AsyncSession(autoflush=False, bind=engine()) as session:
        # Попытка получить запись за текущий день
        stats: DailyStatistics = (
            await session.execute(select(DailyStatistics).where(DailyStatistics.date == day))).scalars().first()
        if stats:
            stats.today_active_persons_count = today_active_persons_count
            stats.active_subscriptions_count = active_subscriptions_count
            stats.active_subscriptions_sum = active_subscriptions_sum
            stats.active_autopay_subscriptions_count = active_autopay_subscriptions_count
            stats.active_autopay_subscriptions_sum = active_autopay_subscriptions_sum
            stats.referral_balance_persons_count = referral_balance_persons_count
            stats.referral_balance_sum = referral_balance_sum
            await session.commit()
            return True

        stats = DailyStatistics()
        stats.date = day
        stats.today_active_persons_count = today_active_persons_count
        stats.active_subscriptions_count = active_subscriptions_count
        stats.active_subscriptions_sum = active_subscriptions_sum
        stats.active_autopay_subscriptions_count = active_autopay_subscriptions_count
        stats.active_autopay_subscriptions_sum = active_autopay_subscriptions_sum
        stats.referral_balance_persons_count = referral_balance_persons_count
        stats.referral_balance_sum = referral_balance_sum
        session.add(stats)
        await session.commit()
        return False


async def create_affiliate_statistics(client_fullname: str, client_tg_id: int, referral_tg_id: int, payment_amount: int,
                                      reward_percent: int, reward_amount: int):
    async with AsyncSession(autoflush=False, bind=engine()) as session:
        stat = AffiliateStatistics(
            client_fullname=client_fullname,
            client_tg_id=client_tg_id,
            referral_tg_id=referral_tg_id,
            payment_amount=payment_amount,
            reward_percent=reward_percent,
            reward_amount=reward_amount,
        )

        session.add(stat)
        await session.commit()
