import sqlite3 as sq
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.main import engine
from bot.database.models.main import Persons, Servers, Payments, StaticPersons


async def import_all():
    await import_servers()
    await import_users()
    await import_payments()
    await import_static_person()


async def import_users():
    try:
        with sq.connect('bot/database/importBD/DatabaseVPN.db') as con:
            cur = con.cursor()
            qyt = ('''
            SELECT * FROM users
            ''')
            output = cur.execute(qyt)
    except Exception as e:
        print('Не удалось получить доступ к базе '
              'данных она должна называться DatabaseVPN.db', e)
    list_users = []
    for user in output:
        user_orm = Persons(
            tgid=int(user[1]),
            banned=user[2],
            notion_oneday=user[3],
            subscription=user[4],
            balance=user[5],
            username=user[6],
            fullname=user[7],
            referral_user_tgid=user[8],
            referral_balance=user[9],
            lang=user[10],
            server=user[11],
        )
        list_users.append(user_orm)
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        for user in list_users:
            db.add(user)
            await db.commit()


async def import_servers():
    try:
        with sq.connect('bot/database/importBD/DatabaseVPN.db') as con:
            cur = con.cursor()
            qyt = ('''
            SELECT * FROM servers
            ''')
            output = cur.execute(qyt)
    except Exception as e:
        print('Не удалось получить доступ к базе '
              'данных она должна называться DatabaseVPN.db', e)
    list_server = []
    for server in output:
        server_orm = Servers(
            name=server[1],
            type_vpn=server[2],
            outline_link=server[3],
            ip=server[4],
            connection_method=server[5],
            panel=server[6],
            inbound_id=server[7],
            password=server[8],
            vds_password=server[9],
            login=server[10],
            work=server[11],
            space=server[12],
        )
        list_server.append(server_orm)
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        for server in list_server:
            db.add(server)
        await db.commit()


async def import_payments():
    try:
        with sq.connect('bot/database/importBD/DatabaseVPN.db') as con:
            cur = con.cursor()
            qyt = ('''
            SELECT * FROM payments
            ''')
            output = cur.execute(qyt)
    except Exception as e:
        print('Не удалось получить доступ к базе '
              'данных она должна называться DatabaseVPN.db', e)
    list_payments = []
    for server in output:
        payment_orm = Payments(
            user=server[1],
            payment_system=server[2],
            amount=server[3],
            data=datetime.strptime(server[4], '%Y-%m-%d %H:%M:%S.%f'),
        )
        list_payments.append(payment_orm)
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        for payment in list_payments:
            db.add(payment)
        await db.commit()


async def import_static_person():
    try:
        with sq.connect('bot/database/importBD/DatabaseVPN.db') as con:
            cur = con.cursor()
            qyt = ('''
            SELECT * FROM static_persons
            ''')
            output = cur.execute(qyt)
    except Exception as e:
        print('Не удалось получить доступ к базе '
              'данных она должна называться DatabaseVPN.db', e)
    list_static = []
    for server in output:
        static_orm = StaticPersons(
            name=server[1],
            server=server[2],
        )
        list_static.append(static_orm)
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        for static in list_static:
            db.add(static)
        await db.commit()


