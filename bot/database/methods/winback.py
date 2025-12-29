"""
Win-back промокоды - методы для работы с БД
Возврат ушедших клиентов через персональные скидки
"""
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.main import engine
from bot.database.models.main import WinbackPromo, WinbackPromoUsage, Persons


# ============================================
# CRUD для WinbackPromo
# ============================================

async def create_winback_promo(
    code: str,
    discount_percent: int,
    min_days_expired: int = 0,
    max_days_expired: int = 365,
    valid_days: int = 7,
    auto_send: bool = False,
    message_template: Optional[str] = None
) -> Optional[WinbackPromo]:
    """Создать новый win-back промокод"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Проверить уникальность кода
        existing = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.code == code.upper())
        )
        if existing.scalar_one_or_none():
            return None  # Код уже существует

        promo = WinbackPromo(
            code=code.upper(),
            discount_percent=discount_percent,
            min_days_expired=min_days_expired,
            max_days_expired=max_days_expired,
            valid_days=valid_days,
            auto_send=auto_send,
            message_template=message_template,
            is_active=True
        )
        db.add(promo)
        await db.commit()
        await db.refresh(promo)
        return promo


async def get_winback_promo(promo_id: int) -> Optional[WinbackPromo]:
    """Получить промокод по ID"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.id == promo_id)
        )
        return result.scalar_one_or_none()


async def get_winback_promo_by_code(code: str) -> Optional[WinbackPromo]:
    """Получить промокод по коду"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.code == code.upper())
        )
        return result.scalar_one_or_none()


async def get_all_winback_promos(active_only: bool = False) -> List[WinbackPromo]:
    """Получить все win-back промокоды"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(WinbackPromo).order_by(WinbackPromo.min_days_expired)
        if active_only:
            stmt = stmt.filter(WinbackPromo.is_active == True)
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def update_winback_promo(
    promo_id: int,
    **kwargs
) -> bool:
    """Обновить win-back промокод"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.id == promo_id)
        )
        promo = result.scalar_one_or_none()
        if not promo:
            return False

        for key, value in kwargs.items():
            if hasattr(promo, key):
                if key == 'code':
                    value = value.upper()
                setattr(promo, key, value)

        await db.commit()
        return True


async def delete_winback_promo(promo_id: int) -> bool:
    """Удалить win-back промокод"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.id == promo_id)
        )
        promo = result.scalar_one_or_none()
        if not promo:
            return False

        await db.delete(promo)
        await db.commit()
        return True


async def toggle_winback_promo(promo_id: int) -> Optional[bool]:
    """Переключить активность промокода. Возвращает новое состояние."""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.id == promo_id)
        )
        promo = result.scalar_one_or_none()
        if not promo:
            return None

        promo.is_active = not promo.is_active
        await db.commit()
        return promo.is_active


# ============================================
# Работа с использованием промокодов
# ============================================

async def create_promo_usage(
    promo_id: int,
    user_tgid: int,
    valid_days: int
) -> Optional[WinbackPromoUsage]:
    """Создать запись об отправке промокода пользователю"""
    moscow_tz = ZoneInfo("Europe/Moscow")
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Проверить, не отправляли ли уже этот промокод этому пользователю
        existing = await db.execute(
            select(WinbackPromoUsage).filter(
                WinbackPromoUsage.promo_id == promo_id,
                WinbackPromoUsage.user_tgid == user_tgid
            )
        )
        if existing.scalar_one_or_none():
            return None  # Уже отправляли

        expires_at = datetime.now(moscow_tz) + timedelta(days=valid_days)
        usage = WinbackPromoUsage(
            promo_id=promo_id,
            user_tgid=user_tgid,
            expires_at=expires_at
        )
        db.add(usage)
        await db.commit()
        await db.refresh(usage)
        return usage


async def get_active_promo_for_user(user_tgid: int) -> Optional[Dict]:
    """
    Получить активный (неиспользованный, не истёкший) промокод для пользователя.
    Возвращает dict с promo и usage.
    """
    moscow_tz = ZoneInfo("Europe/Moscow")
    now = datetime.now(moscow_tz)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromoUsage)
            .options(selectinload(WinbackPromoUsage.promo))
            .filter(
                WinbackPromoUsage.user_tgid == user_tgid,
                WinbackPromoUsage.used_at.is_(None),  # Не использован
                WinbackPromoUsage.expires_at > now  # Не истёк
            )
            .order_by(WinbackPromoUsage.sent_at.desc())
        )
        usage = result.scalar_one_or_none()
        if not usage:
            return None

        return {
            'usage': usage,
            'promo': usage.promo,
            'code': usage.promo.code,
            'discount_percent': usage.promo.discount_percent,
            'expires_at': usage.expires_at
        }


async def apply_promo_discount(
    user_tgid: int,
    code: str,
    original_price: int
) -> Optional[Dict]:
    """
    Применить промокод и получить скидку.
    Возвращает dict с информацией о скидке или None если промокод недействителен.
    """
    moscow_tz = ZoneInfo("Europe/Moscow")
    now = datetime.now(moscow_tz)

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Найти активный промокод для пользователя
        result = await db.execute(
            select(WinbackPromoUsage)
            .options(selectinload(WinbackPromoUsage.promo))
            .filter(
                WinbackPromoUsage.user_tgid == user_tgid,
                WinbackPromoUsage.used_at.is_(None),
                WinbackPromoUsage.expires_at > now
            )
            .join(WinbackPromo)
            .filter(WinbackPromo.code == code.upper())
        )
        usage = result.scalar_one_or_none()
        if not usage:
            return None

        # Рассчитать скидку
        discount_percent = usage.promo.discount_percent
        discount_amount = int(original_price * discount_percent / 100)
        final_price = original_price - discount_amount

        # Обновить запись использования
        usage.used_at = now
        usage.original_price = original_price
        usage.discount_amount = discount_amount
        usage.final_price = final_price

        await db.commit()

        return {
            'code': usage.promo.code,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'original_price': original_price,
            'final_price': final_price
        }


async def check_promo_code(user_tgid: int, code: str) -> Optional[Dict]:
    """
    Проверить промокод для пользователя (без применения).
    Возвращает информацию о скидке если промокод действителен.
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromoUsage)
            .options(selectinload(WinbackPromoUsage.promo))
            .filter(
                WinbackPromoUsage.user_tgid == user_tgid,
                WinbackPromoUsage.used_at.is_(None),
                WinbackPromoUsage.expires_at > func.now()
            )
            .join(WinbackPromo)
            .filter(WinbackPromo.code == code.upper())
        )
        usage = result.scalar_one_or_none()
        if not usage:
            return None

        return {
            'code': usage.promo.code,
            'discount_percent': usage.promo.discount_percent,
            'expires_at': usage.expires_at,
            'valid': True
        }


# ============================================
# Сегментация пользователей
# ============================================

async def get_churned_users_by_segment(
    min_days: int,
    max_days: int,
    exclude_already_sent_promo_id: Optional[int] = None
) -> List[Persons]:
    """
    Получить пользователей без подписки в указанном диапазоне дней.
    Исключает тех, кому уже отправлен указанный промокод.
    Исключает тех, кто заблокировал бота (bot_blocked=true).
    """
    current_time = int(time.time())
    min_timestamp = current_time - (max_days * 86400)  # Подписка истекла max_days назад
    max_timestamp = current_time - (min_days * 86400)  # Подписка истекла min_days назад

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(
            Persons.subscription.isnot(None),
            Persons.subscription < current_time,  # Подписка истекла
            Persons.subscription >= min_timestamp,  # Не раньше max_days назад
            Persons.subscription <= max_timestamp,  # Не позже min_days назад
            Persons.banned == False,  # Не забанен
            or_(Persons.bot_blocked == False, Persons.bot_blocked.is_(None)),  # Не заблокировал бота
            Persons.retention > 0  # Хотя бы раз покупал
        )

        # Исключить тех, кому уже отправлен этот промокод
        if exclude_already_sent_promo_id:
            subq = select(WinbackPromoUsage.user_tgid).filter(
                WinbackPromoUsage.promo_id == exclude_already_sent_promo_id
            )
            stmt = stmt.filter(Persons.tgid.notin_(subq))

        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_user_days_without_subscription(user_tgid: int) -> Optional[int]:
    """Получить количество дней без подписки для пользователя"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(Persons).filter(Persons.tgid == user_tgid)
        )
        person = result.scalar_one_or_none()
        if not person or not person.subscription:
            return None

        current_time = int(time.time())
        if person.subscription >= current_time:
            return 0  # Подписка активна

        days = (current_time - person.subscription) // 86400
        return days


async def get_churned_users_stats() -> dict:
    """
    Получить статистику пользователей без активной подписки.
    Возвращает количество по сегментам.
    Исключает заблокировавших бота (bot_blocked=true).
    """
    current_time = int(time.time())

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Общее количество пользователей без подписки (хотя бы раз покупали)
        total_churned = await db.execute(
            select(func.count(Persons.id)).filter(
                Persons.subscription.isnot(None),
                Persons.subscription < current_time,
                Persons.banned == False,
                or_(Persons.bot_blocked == False, Persons.bot_blocked.is_(None)),
                Persons.retention > 0
            )
        )
        total = total_churned.scalar() or 0

        # По сегментам
        segments = {
            "0-7": (0, 7),
            "7-30": (7, 30),
            "30-90": (30, 90),
            "90+": (90, 365*10)
        }

        stats = {"total": total}
        for name, (min_days, max_days) in segments.items():
            min_timestamp = current_time - (max_days * 86400)
            max_timestamp = current_time - (min_days * 86400)

            result = await db.execute(
                select(func.count(Persons.id)).filter(
                    Persons.subscription.isnot(None),
                    Persons.subscription < current_time,
                    Persons.subscription >= min_timestamp,
                    Persons.subscription <= max_timestamp,
                    Persons.banned == False,
                    or_(Persons.bot_blocked == False, Persons.bot_blocked.is_(None)),
                    Persons.retention > 0
                )
            )
            stats[name] = result.scalar() or 0

        return stats


async def find_matching_promo_for_user(user_tgid: int) -> Optional[WinbackPromo]:
    """Найти подходящий промокод для пользователя по его сегменту"""
    days = await get_user_days_without_subscription(user_tgid)
    if days is None or days == 0:
        return None  # Подписка активна или пользователь не найден

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        result = await db.execute(
            select(WinbackPromo).filter(
                WinbackPromo.is_active == True,
                WinbackPromo.min_days_expired <= days,
                WinbackPromo.max_days_expired >= days
            ).order_by(WinbackPromo.discount_percent.desc())  # Сначала с большей скидкой
        )
        return result.scalar_one_or_none()


# ============================================
# Статистика
# ============================================

async def get_promo_statistics(promo_id: int) -> Dict:
    """Получить статистику по промокоду"""
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        promo = await db.execute(
            select(WinbackPromo).filter(WinbackPromo.id == promo_id)
        )
        promo = promo.scalar_one_or_none()
        if not promo:
            return {}

        # Общее количество отправленных
        sent_count = await db.execute(
            select(func.count(WinbackPromoUsage.id)).filter(
                WinbackPromoUsage.promo_id == promo_id
            )
        )
        sent_count = sent_count.scalar() or 0

        # Количество использованных
        used_count = await db.execute(
            select(func.count(WinbackPromoUsage.id)).filter(
                WinbackPromoUsage.promo_id == promo_id,
                WinbackPromoUsage.used_at.isnot(None)
            )
        )
        used_count = used_count.scalar() or 0

        # Сумма скидок
        total_discount = await db.execute(
            select(func.sum(WinbackPromoUsage.discount_amount)).filter(
                WinbackPromoUsage.promo_id == promo_id,
                WinbackPromoUsage.used_at.isnot(None)
            )
        )
        total_discount = total_discount.scalar() or 0

        # Сумма оплат со скидкой
        total_revenue = await db.execute(
            select(func.sum(WinbackPromoUsage.final_price)).filter(
                WinbackPromoUsage.promo_id == promo_id,
                WinbackPromoUsage.used_at.isnot(None)
            )
        )
        total_revenue = total_revenue.scalar() or 0

        # Конверсия
        conversion_rate = (used_count / sent_count * 100) if sent_count > 0 else 0

        return {
            'promo': promo,
            'code': promo.code,
            'discount_percent': promo.discount_percent,
            'segment': f"{promo.min_days_expired}-{promo.max_days_expired} дней",
            'sent_count': sent_count,
            'used_count': used_count,
            'conversion_rate': round(conversion_rate, 1),
            'total_discount': total_discount,
            'total_revenue': total_revenue
        }


async def get_all_promos_statistics() -> List[Dict]:
    """Получить статистику по всем промокодам"""
    promos = await get_all_winback_promos()
    stats = []
    for promo in promos:
        stat = await get_promo_statistics(promo.id)
        stats.append(stat)
    return stats


async def get_new_users_for_welcome_promo(
    exclude_already_sent_promo_id: Optional[int] = None,
    delay_days: int = 0
) -> List[Persons]:
    """
    Получить новых пользователей (retention=0) для welcome промокодов.
    Исключает тех, кому уже отправлен промокод и заблокировавших бота.

    delay_days: задержка в днях после регистрации (0 = отправлять сразу)
    """
    moscow_tz = ZoneInfo("Europe/Moscow")
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(
            Persons.retention == 0,  # Никогда не покупали
            Persons.banned == False,  # Не забанен
            or_(Persons.bot_blocked == False, Persons.bot_blocked.is_(None)),  # Не заблокировал бота
        )

        # Фильтр по задержке после регистрации
        if delay_days > 0:
            # Выбираем пользователей, которые зарегистрировались минимум delay_days дней назад
            cutoff_date = datetime.now(moscow_tz) - timedelta(days=delay_days)
            stmt = stmt.filter(
                Persons.first_interaction.isnot(None),
                Persons.first_interaction <= cutoff_date
            )

        # Исключить тех, кому уже отправлен этот промокод
        if exclude_already_sent_promo_id:
            subq = select(WinbackPromoUsage.user_tgid).filter(
                WinbackPromoUsage.promo_id == exclude_already_sent_promo_id
            )
            stmt = stmt.filter(Persons.tgid.notin_(subq))

        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_users_for_autosend() -> Dict[int, List[Persons]]:
    """
    Получить пользователей для автоматической рассылки промокодов.
    Поддерживает оба типа: 'winback' (ушедшие) и 'welcome' (новые).
    Возвращает dict: {promo_id: [users]}
    """
    result = {}

    # Получить все активные промокоды с автоотправкой
    promos = await get_all_winback_promos(active_only=True)
    auto_promos = [p for p in promos if p.auto_send]

    for promo in auto_promos:
        promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'

        if promo_type == 'welcome':
            # Для welcome промокодов - новые пользователи (retention=0)
            delay_days = getattr(promo, 'delay_days', 0) or 0
            users = await get_new_users_for_welcome_promo(
                exclude_already_sent_promo_id=promo.id,
                delay_days=delay_days
            )
        else:
            # Для winback промокодов - ушедшие пользователи
            users = await get_churned_users_by_segment(
                min_days=promo.min_days_expired,
                max_days=promo.max_days_expired,
                exclude_already_sent_promo_id=promo.id
            )

        if users:
            result[promo.id] = users

    return result
