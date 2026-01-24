#!/usr/bin/env python3
"""
Скрипт для проверки и удаления старых VPN ключей.
Запускается по cron раз в неделю.

Старые ключи - это ключи без суффиксов _vless/_ss,
которые не контролируются системой подписки.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Tuple
import subprocess
import asyncpg
import aiohttp

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/check_old_keys.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Конфигурация серверов
SERVERS = [
    {
        "name": "Германия",
        "ip": "185.233.81.238",
        "ssh_password": "Dkjfew@3er#$1331",
        "method": "ssh"
    },
    {
        "name": "Нидерланды-1",
        "ip": "194.113.153.106",
        "ssh_password": "lb[VR'X[y_0M",
        "method": "ssh"
    },
    {
        "name": "Нидерланды-2",
        "ip": "194.113.153.192",
        "ssh_password": "2fy3X42cYio9i6UKJS",
        "method": "ssh"
    },
    {
        "name": "Россия",
        "ip": "185.239.50.235",
        "ssh_password": "TFO]E2FBadf",
        "method": "ssh_regex"  # Нестандартный JSON
    },
    {
        "name": "Испания",
        "ip": "159.255.34.42",
        "ssh_password": "gt23i0m4kI6f",
        "method": "ssh"
    },
    {
        "name": "США",
        "ip": "64.23.178.134",
        "ssh_password": "Dmiofwe@#mfpoir1!#@#3",
        "method": "ssh"
    },
    {
        "name": "Bypass-1",
        "ip": "178.154.221.172",
        "panel_port": 2053,
        "panel_user": "admin",
        "panel_password": "po7SQZEgIDaIBf",
        "method": "api"
    },
    {
        "name": "Bypass-2",
        "ip": "51.250.83.138",
        "panel_port": 2053,
        "panel_user": "admin",
        "panel_password": "4qza06HuOnXCYT",
        "method": "api"
    }
]

# Telegram настройки
TG_BOT_TOKEN = os.getenv("TG_TOKEN", "")
TG_ADMIN_IDS = [870499087]  # ID админов для уведомлений

# База данных
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("POSTGRES_USER", "marakoris"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "database": os.getenv("POSTGRES_DB", "VPNHubBotDB")
}


def run_ssh_command(ip: str, password: str, command: str) -> str:
    """Выполнить команду через SSH"""
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
        f"root@{ip}", command
    ]
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        log.error(f"SSH error for {ip}: {e}")
        return ""


def get_old_keys_ssh(server: Dict) -> List[Tuple[int, str]]:
    """Получить старые ключи через SSH"""
    python_script = '''
import sqlite3, json
conn = sqlite3.connect("/etc/x-ui/x-ui.db")
cursor = conn.cursor()
cursor.execute("SELECT id, settings FROM inbounds")
for row in cursor.fetchall():
    if row[1]:
        try:
            for c in json.loads(row[1]).get("clients", []):
                email = c["email"]
                if not email.endswith("_vless") and not email.endswith("_ss"):
                    print(f"{row[0]}|{email}")
        except: pass
conn.close()
'''
    output = run_ssh_command(server["ip"], server["ssh_password"], f"python3 -c '{python_script}'")

    keys = []
    for line in output.strip().split('\n'):
        if '|' in line:
            parts = line.split('|')
            keys.append((int(parts[0]), parts[1]))
    return keys


def get_old_keys_ssh_regex(server: Dict) -> List[Tuple[int, str]]:
    """Получить старые ключи через SSH с regex парсингом (для России)"""
    import re
    output = run_ssh_command(
        server["ip"],
        server["ssh_password"],
        'sqlite3 /etc/x-ui/x-ui.db "SELECT settings FROM inbounds;"'
    )

    emails = re.findall(r'email: ([^,}\s]+)', output)
    keys = []
    for email in emails:
        if not email.endswith('_vless') and not email.endswith('_ss') and not email.endswith('_vle'):
            keys.append((1, email))  # Предполагаем inbound 1
    return keys


async def get_old_keys_api(server: Dict) -> List[Tuple[int, str]]:
    """Получить старые ключи через API панели"""
    base_url = f"http://{server['ip']}:{server['panel_port']}"

    async with aiohttp.ClientSession() as session:
        # Login
        async with session.post(
            f"{base_url}/login",
            data={"username": server["panel_user"], "password": server["panel_password"]}
        ) as resp:
            if resp.status != 200:
                return []

        # Get inbounds
        async with session.get(f"{base_url}/panel/api/inbounds/list") as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

    keys = []
    for inb in data.get('obj', []):
        inbound_id = inb.get('id')
        settings = json.loads(inb.get('settings', '{}'))
        for c in settings.get('clients', []):
            email = c['email']
            if not email.endswith('_vless') and not email.endswith('_ss'):
                keys.append((inbound_id, email))
    return keys


def delete_key_ssh(server: Dict, inbound_id: int, email: str) -> bool:
    """Удалить ключ через SSH"""
    python_script = f'''
import sqlite3, json
conn = sqlite3.connect("/etc/x-ui/x-ui.db")
conn.text_factory = str
cursor = conn.cursor()
cursor.execute("SELECT settings FROM inbounds WHERE id=?", ({inbound_id},))
row = cursor.fetchone()
if row:
    settings = json.loads(row[0])
    original = len(settings.get("clients", []))
    settings["clients"] = [c for c in settings.get("clients", []) if c["email"] != "{email}"]
    if len(settings["clients"]) < original:
        cursor.execute("UPDATE inbounds SET settings=? WHERE id=?", (json.dumps(settings, ensure_ascii=False), {inbound_id}))
        conn.commit()
        print("deleted")
conn.close()
'''
    output = run_ssh_command(server["ip"], server["ssh_password"], f"python3 -c '{python_script}'")
    return "deleted" in output


async def delete_key_api(server: Dict, inbound_id: int, email: str) -> bool:
    """Удалить ключ через API"""
    base_url = f"http://{server['ip']}:{server['panel_port']}"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/login",
            data={"username": server["panel_user"], "password": server["panel_password"]}
        ) as resp:
            if resp.status != 200:
                return False

        async with session.post(f"{base_url}/panel/api/inbounds/{inbound_id}/delClient/{email}") as resp:
            data = await resp.json()
            return data.get("success", False)


async def check_subscription(pool: asyncpg.Pool, telegram_id: str) -> Dict:
    """Проверить статус подписки пользователя"""
    try:
        tg_id = int(telegram_id)
    except ValueError:
        return {"exists": False, "active": False, "expired": False}

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription, subscription_active FROM users WHERE tgid = $1",
            tg_id
        )

    if not row:
        return {"exists": False, "active": False, "expired": False}

    subscription = row['subscription'] or 0
    now = datetime.now().timestamp()

    return {
        "exists": True,
        "active": row['subscription_active'] and subscription > now,
        "expired": subscription > 0 and subscription <= now
    }


async def send_telegram_report(report: str):
    """Отправить отчёт в Telegram"""
    if not TG_BOT_TOKEN:
        log.warning("TG_TOKEN not set, skipping Telegram notification")
        return

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"

    async with aiohttp.ClientSession() as session:
        for admin_id in TG_ADMIN_IDS:
            try:
                await session.post(url, json={
                    "chat_id": admin_id,
                    "text": report,
                    "parse_mode": "HTML"
                })
            except Exception as e:
                log.error(f"Failed to send Telegram message: {e}")


async def main():
    log.info("Starting old keys check...")

    # Подключение к БД
    try:
        pool = await asyncpg.create_pool(**DB_CONFIG)
    except Exception as e:
        log.error(f"Database connection failed: {e}")
        return

    total_found = 0
    total_deleted = 0
    report_lines = ["<b>🔑 Проверка старых VPN ключей</b>\n"]

    for server in SERVERS:
        log.info(f"Checking {server['name']}...")

        # Получить старые ключи
        if server["method"] == "ssh":
            old_keys = get_old_keys_ssh(server)
        elif server["method"] == "ssh_regex":
            old_keys = get_old_keys_ssh_regex(server)
        elif server["method"] == "api":
            old_keys = await get_old_keys_api(server)
        else:
            continue

        if not old_keys:
            continue

        server_deleted = 0
        expired_users = []

        for inbound_id, email in old_keys:
            total_found += 1

            # Проверить подписку
            sub_status = await check_subscription(pool, email)

            # Удалять только если подписка истекла
            if sub_status["expired"]:
                log.info(f"Deleting expired key: {email} on {server['name']}")

                if server["method"] in ["ssh", "ssh_regex"]:
                    success = delete_key_ssh(server, inbound_id, email)
                else:
                    success = await delete_key_api(server, inbound_id, email)

                if success:
                    server_deleted += 1
                    total_deleted += 1
                    expired_users.append(email)

        if server_deleted > 0:
            report_lines.append(f"🗑 <b>{server['name']}</b>: удалено {server_deleted}")
            for user in expired_users[:5]:
                report_lines.append(f"   - {user}")
            if len(expired_users) > 5:
                report_lines.append(f"   - ... и ещё {len(expired_users) - 5}")

    await pool.close()

    # Формируем отчёт
    report_lines.append(f"\n📊 <b>Итого:</b>")
    report_lines.append(f"   Найдено старых ключей: {total_found}")
    report_lines.append(f"   Удалено (истёкшие): {total_deleted}")
    report_lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    report = "\n".join(report_lines)
    log.info(report)

    # Отправляем в Telegram только если были удаления или много старых ключей
    if total_deleted > 0 or total_found > 30:
        await send_telegram_report(report)

    log.info(f"Check completed. Found: {total_found}, Deleted: {total_deleted}")


if __name__ == "__main__":
    asyncio.run(main())
