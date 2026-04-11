#!/usr/bin/env python3
"""
Device Stats Collector

Reads xray access logs from all VPN servers, extracts (user_id, source_ip) pairs,
and stores unique IPs per user per day in user_device_ips table.

Log format:
  2026/04/11 13:40:08 176.214.176.234:46068 accepted tcp:... email: 383655912_vless
"""
import asyncio
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

POSTGRES_DB = os.getenv('POSTGRES_DB', '')
POSTGRES_USER = os.getenv('POSTGRES_USER', '')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
DB_HOST = 'postgres_db_container'

# Two xray log formats:
# Old: "2026/04/11 13:40:08 1.2.3.4:56789 accepted ... email: 123456789_vless"
# New: "2026/04/11 13:40:08.123456 from 1.2.3.4:56789 accepted ... email: 123456789_vless"
LOG_RE = re.compile(
    r'^(\d{4}/\d{2}/\d{2}) \d{2}:\d{2}:\d{2}(?:\.\d+)? '  # date + time (optional microseconds)
    r'(?:from )?'              # optional "from " keyword
    r'([\d.]+):\d+ '          # source IPv4
    r'accepted .+ '
    r'email: (\S+)$'
)

LOG_TAIL = int(os.getenv('DEVICE_LOG_TAIL', '5000'))


def get_db_url():
    return (
        f'postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}'
        f'@{DB_HOST}/{POSTGRES_DB}'
    )


def _ssh(cmd: list, name: str) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            logger.error(f'[{name}] SSH failed (rc={r.returncode}): {r.stderr[:200]}')
            return ''
        return r.stdout
    except subprocess.TimeoutExpired:
        logger.error(f'[{name}] SSH timeout')
        return ''
    except Exception as e:
        logger.error(f'[{name}] SSH error: {e}')
        return ''


def fetch_log(server: dict) -> str:
    remote_cmd = f'tail -n {LOG_TAIL} /var/log/xray/access.log 2>/dev/null || echo ""'
    if server.get('ssh_key'):
        cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
            '-i', server['ssh_key'],
            f"{server['ssh_user']}@{server['host']}",
            remote_cmd,
        ]
    else:
        cmd = [
            'sshpass', '-p', server['ssh_password'],
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
            f"{server['ssh_user']}@{server['host']}",
            remote_cmd,
        ]
    return _ssh(cmd, server['name'])


def parse_log(raw: str) -> dict[tuple, set]:
    """Returns {(log_date, user_id): {ip, ...}}"""
    result: dict[tuple, set] = {}
    for line in raw.splitlines():
        m = LOG_RE.match(line.strip())
        if not m:
            continue
        log_date_str, src_ip, email = m.group(1), m.group(2), m.group(3)
        # email like "383655912_vless" or "383655912_ss" or just "383655912"
        tgid_str = email.split('_')[0]
        if not tgid_str.isdigit():
            continue
        user_id = int(tgid_str)
        log_date = date.fromisoformat(log_date_str.replace('/', '-'))
        key = (log_date, user_id)
        result.setdefault(key, set()).add(src_ip)
    return result


async def save_to_db(server_id: int, data: dict[tuple, set]):
    if not data:
        return
    engine = create_async_engine(get_db_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    total = 0
    async with async_session() as session:
        async with session.begin():
            for (log_date, user_id), ips in data.items():
                for ip in ips:
                    await session.execute(
                        text("""
                            INSERT INTO user_device_ips (date, user_id, server_id, ip_address)
                            VALUES (:date, :uid, :sid, :ip)
                            ON CONFLICT (date, user_id, server_id, ip_address) DO NOTHING
                        """),
                        {'date': log_date, 'uid': user_id, 'sid': server_id, 'ip': ip},
                    )
                    total += 1
    await engine.dispose()
    return total


def build_server_list() -> list[dict]:
    """Build server list from environment or hardcode from DB query logic."""
    servers_env = os.getenv('DEVICE_SERVERS', '')
    if not servers_env:
        return []
    servers = []
    for entry in servers_env.split(';'):
        entry = entry.strip()
        if not entry:
            continue
        # Format: server_id,host,ssh_user,ssh_password_or_key
        # If password starts with '/', it's treated as a key path
        parts = entry.split(',', 3)
        if len(parts) < 3:
            continue
        sid, host, user = parts[0], parts[1], parts[2]
        auth = parts[3] if len(parts) > 3 else ''
        srv = {
            'server_id': int(sid),
            'name': f'server-{sid}',
            'host': host,
            'ssh_user': user,
        }
        if auth.startswith('/'):
            srv['ssh_key'] = auth
            srv['ssh_password'] = ''
        else:
            srv['ssh_key'] = ''
            srv['ssh_password'] = auth
        servers.append(srv)
    return servers


async def collect():
    servers = build_server_list()
    if not servers:
        logger.warning('No servers configured via DEVICE_SERVERS env var')
        return

    logger.info(f'Collecting device stats from {len(servers)} server(s)')
    today = date.today()

    for srv in servers:
        name = srv['name']
        logger.info(f'[{name}] Fetching access log from {srv["host"]}...')
        raw = fetch_log(srv)
        if not raw.strip():
            logger.warning(f'[{name}] Empty log')
            continue

        data = parse_log(raw)
        if not data:
            logger.warning(f'[{name}] No parseable entries')
            continue

        unique_users = len(data)
        unique_ips = sum(len(v) for v in data.values())
        logger.info(f'[{name}] Parsed: {unique_users} users, {unique_ips} IP entries')

        saved = await save_to_db(srv['server_id'], data)
        logger.info(f'[{name}] Saved {saved} records to DB')


def main():
    asyncio.run(collect())


if __name__ == '__main__':
    main()
