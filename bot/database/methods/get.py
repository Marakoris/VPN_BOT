from sqlalchemy.orm import joinedload
from io import BytesIO
from zoneinfo import ZoneInfo
import xlsxwriter
import pandas as pd
from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from bot.database.main import engine
from bot.database.models.main import (
    Persons,
    Servers,
    Payments,
    StaticPersons,
    PromoCode,
    WithdrawalRequests, Groups, SuperOffer, AffiliateStatistics
)
from bot.misc.util import CONFIG


async def get_person(telegram_id: int):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.tgid == telegram_id)
        result = await db.execute(statement)
        person = result.scalar_one_or_none()
        return person


async def get_person_id(list_input):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.tgid.in_(list_input))
        result = await db.execute(statement)
        persons = result.scalars().all()
        return persons


async def _get_person(db, tgid):
    statement = select(Persons).filter(Persons.tgid == tgid)
    result = await db.execute(statement)
    person = result.scalar_one_or_none()
    return person


async def _get_server(db, name):
    statement = select(Servers).filter(Servers.name == name)
    result = await db.execute(statement)
    server = result.scalar_one_or_none()
    return server


async def get_all_user():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons)
        result = await db.execute(statement)
        persons = result.scalars().all()
        return persons


async def get_all_subscription():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.banned == False)
        result = await db.execute(statement)
        persons = result.scalars().all()
        return persons


async def get_no_subscription():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.banned == True)
        result = await db.execute(statement)
        persons = result.scalars().all()
        return persons


async def get_payments():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Payments).options(
            joinedload(Payments.payment_id)
        )
        result = await db.execute(statement)
        payments = result.scalars().all()

        for payment in payments:
            payment.user = payment.payment_id.username

        return payments


async def get_all_server():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Servers)
        result = await db.execute(statement)
        servers = result.scalars().all()
        return servers


async def get_server(name):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        return await _get_server(db, name)


async def get_server_id(id_server):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Servers).filter(Servers.id == id_server)
        result = await db.execute(statement)
        server = result.scalar_one_or_none()
        return server


async def get_free_servers(group_name, type_vpn):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Servers).filter(
            and_(
                Servers.space < int(CONFIG.max_people_server),
                Servers.work,
                Servers.group == group_name,
                Servers.type_vpn == type_vpn
            )
        )
        result = await db.execute(statement)
        servers = result.scalars().all()
        if not servers:
            raise FileNotFoundError('Server not found')
        return servers


async def get_all_static_user():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(StaticPersons).options(
            joinedload(StaticPersons.server_table)
        )
        result = await db.execute(statement)
        all_static_user = result.scalars().all()
        return all_static_user


async def get_all_promo_code():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(PromoCode)
        result = await db.execute(statement)
        promo_code = result.scalars().all()
        return promo_code


async def get_promo_code(text_promo):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(PromoCode).options(
            joinedload(PromoCode.person)
        ).filter(
            PromoCode.text == text_promo
        )
        result = await db.execute(statement)
        promo_code = result.unique().scalar_one_or_none()
        return promo_code


async def get_count_referral_user(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(func.count(Persons.id)).filter(
            Persons.referral_user_tgid == tgid
        )
        result = await db.execute(statement)
        return result.scalar()


async def get_referral_balance(tgid):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.tgid == tgid)
        result = await db.execute(statement)
        person = result.scalar_one_or_none()
        return person.referral_balance


async def get_all_application_referral():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(WithdrawalRequests)
        result = await db.execute(statement)
        return result.scalars().all()


async def get_application_referral_check_false():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(WithdrawalRequests).filter(
            WithdrawalRequests.check_payment == False
        )
        result = await db.execute(statement)
        return result.scalars().all()


async def get_person_lang(telegram_id):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).filter(Persons.tgid == telegram_id)
        result = await db.execute(statement)
        person = result.scalar_one_or_none()
        if person is None:
            return CONFIG.languages
        return person.lang


async def get_all_groups():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(
            Groups, func.count(Groups.users), func.count(Groups.servers)). \
            outerjoin(Groups.users). \
            outerjoin(Groups.servers). \
            group_by(Groups.id). \
            order_by(Groups.id)
        result = await db.execute(statement)
        rows = result.all()
        groups_with_counts = []
        for row in rows:
            group = row[0]
            count_user = row[1]
            count_server = row[2]
            groups_with_counts.append(
                {"group": group, "count_user": count_user,
                 "count_server": count_server})
        return groups_with_counts


async def get_group(group_id):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Groups).filter(Groups.id == group_id)
        result = await db.execute(statement)
        return result.scalar_one_or_none()


async def get_group_name(group_name):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Groups).filter(Groups.name == group_name)
        result = await db.execute(statement)
        return result.scalar_one_or_none()


async def get_users_group(group_id):
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Groups).filter(Groups.id == group_id)
        result = await db.execute(statement)
        group = result.scalar_one_or_none()
        statement = select(Persons).filter(Persons.group == group.name)
        result = await db.execute(statement)
        return result.scalars().all()


async def get_count_groups():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(func.count(Groups.id))
        result = await db.execute(statement)
        count = result.scalar_one()
        return count


async def get_users_by_server_and_vpn_type(server_id: int = None, vpn_type: int = None):
    """
    Получить пользователей по серверу и/или типу VPN
    :param server_id: ID сервера (опционально)
    :param vpn_type: Тип VPN: 0=Outline, 1=Vless, 2=Shadowsocks (опционально)
    :return: Список пользователей
    """
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Persons).join(
            Servers, Persons.server == Servers.id
        )

        # Добавляем фильтры если указаны
        conditions = []
        if server_id is not None:
            conditions.append(Persons.server == server_id)
        if vpn_type is not None:
            conditions.append(Servers.type_vpn == vpn_type)

        if conditions:
            statement = statement.filter(and_(*conditions))

        result = await db.execute(statement)
        persons = result.scalars().all()
        return persons

async def get_super_offer():
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(SuperOffer)
        result = await db.execute(stmt)
        super_offer = result.scalars().first()
        return super_offer


async def export_affiliate_statistics_to_excel(tg_id: int):
    moscow_tz = ZoneInfo("Europe/Moscow")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(AffiliateStatistics).where(tg_id == AffiliateStatistics.referral_tg_id)
        result = await db.execute(stmt)
        data = result.scalars().all()

    df = pd.DataFrame([
        {
            "№": i + 1,
            "Дата перехода": record.attraction_date.astimezone(moscow_tz).strftime('%d.%m.%Y') if record.attraction_date else '',
            "Имя клиента": record.client_fullname,
            "ID клиента": record.client_tg_id,
            "Дата оплаты": record.payment_date.astimezone(moscow_tz).strftime('%d.%m.%Y') if record.payment_date else '',
            "Сумма оплаты, ₽": record.payment_amount,
            "Процент вознаграждения": f"{record.reward_percent}%",
            "Вознаграждение, ₽": record.reward_amount,
        }
        for i, record in enumerate(data)
    ])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name="Привлечённые клиенты", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Привлечённые клиенты"]

        # Форматы
        currency_format = workbook.add_format({"num_format": "#,##0 ₽", "align": "right"})
        percent_format = workbook.add_format({"align": "right"})
        header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "border": 1})

        # Автоширина колонок
        for col_num, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).map(len).max(), len(col)) + 5
            worksheet.set_column(col_num, col_num, max_length)

            # Устанавливаем формат для числовых колонок
            if "Сумма оплаты" in col or "Вознаграждение" in col:
                worksheet.set_column(col_num, col_num, max_length, currency_format)
            elif "Процент вознаграждения" in col:
                worksheet.set_column(col_num, col_num, max_length, percent_format)

        # Стиль заголовков
        for col_num, value in enumerate(df.columns):
            worksheet.write(0, col_num, value, header_format)

    buffer.seek(0)
    return buffer


async def export_withdrawal_statistics_to_excel(tg_id: int):
    moscow_tz = ZoneInfo("Europe/Moscow")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(WithdrawalRequests).where(tg_id == WithdrawalRequests.user_tgid)
        result = await db.execute(stmt)
        data = result.scalars().all()

    df = pd.DataFrame([
        {
            "№": i + 1,
            "Дата заявки": record.request_date.astimezone(moscow_tz).strftime('%d.%m.%Y') if record.request_date else '',
            "Дата выплаты": record.payment_date.astimezone(moscow_tz).strftime('%d.%m.%Y') if record.payment_date else '—',
            "Сумма выплаты, ₽": record.amount,
            "Статус": "Выплачено" if record.check_payment else "Ожидает"
        }
        for i, record in enumerate(data)
    ])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name="Выплаты", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Выплаты"]

        # Форматы
        currency_format = workbook.add_format({"num_format": "#,##0 ₽", "align": "right"})
        header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "border": 1})

        # Автоширина колонок
        for col_num, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).map(len).max(), len(col)) + 5
            worksheet.set_column(col_num, col_num, max_length)

            # Форматирование числовых данных
            if "Сумма выплаты" in col:
                worksheet.set_column(col_num, col_num, max_length, currency_format)

        # Стиль заголовков
        for col_num, value in enumerate(df.columns):
            worksheet.write(0, col_num, value, header_format)

    buffer.seek(0)
    return buffer

