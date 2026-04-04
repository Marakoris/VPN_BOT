#!/usr/bin/env python3
"""
MTProto Proxy Stats Collector v2

Collects stats from multiple MTProto proxy servers:
  - Frankfurt: Docker-based (alexdoesh/mtproto-proxy), password SSH
  - Bypass-1/ES-1: mtg v2 (JSON logs), key-based SSH via Madrid or direct

Runs every MTPROTO_COLLECT_INTERVAL seconds (default: 300).
"""
import asyncio
import json as json_lib
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

# Regex for old format: "vpnhub: 192 connects (6 current), 5.05 MB, 1860 msgs"
STATS_RE = re.compile(
    r'(\w+): (\d+) connects \((\d+) current\), ([\d.]+) MB, (\d+) msgs'
)
NEW_IPS_HEADER_RE = re.compile(r'New IPs:\s*$')
IP_RE = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*$')


def get_db_url():
    return (
        f'postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}'
        f'@{DB_HOST}/{POSTGRES_DB}'
    )


def _run_ssh(cmd: list, server_name: str) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"[{server_name}] SSH failed (rc={result.returncode}): {result.stderr}")
            return ""
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.error(f"[{server_name}] SSH timed out")
        return ""
    except Exception as e:
        logger.error(f"[{server_name}] SSH error: {e}")
        return ""


# ── Server configurations ──

def build_server_list():
    servers = []

    # Server 1: Frankfurt (Docker, password SSH) - old format
    host1 = os.getenv('MTPROTO_SSH_HOST', '')
    if host1:
        servers.append({
            'name': 'Frankfurt',
            'host': host1,
            'format': 'docker',
            'ssh_user': os.getenv('MTPROTO_SSH_USER', 'root'),
            'ssh_password': os.getenv('MTPROTO_SSH_PASSWORD', ''),
            'docker_container': os.getenv('MTPROTO_DOCKER_CONTAINER', 'mtproto-proxy'),
            'log_tail': int(os.getenv('MTPROTO_LOG_TAIL', '200')),
        })

    # Server 2: Bypass-1/ES-1 (mtg v2, JSON logs)
    host2 = os.getenv('MTPROTO_BYPASS1_HOST', '')
    if host2:
        servers.append({
            'name': 'Bypass-1',
            'host': host2,
            'format': 'mtg',
            'ssh_user': os.getenv('MTPROTO_BYPASS1_SSH_USER', 'root'),
            'ssh_password': os.getenv('MTPROTO_BYPASS1_SSH_PASSWORD', ''),
            'ssh_key': os.getenv('MTPROTO_BYPASS1_SSH_KEY', ''),
            'service_name': os.getenv('MTPROTO_BYPASS1_SERVICE', 'mtg'),
        })

    return servers


def fetch_docker_logs(server: dict) -> str:
    cmd = [
        'sshpass', '-p', server['ssh_password'],
        'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
        f"{server['ssh_user']}@{server['host']}",
        f"docker logs --tail={server['log_tail']} {server['docker_container']} 2>&1"
    ]
    return _run_ssh(cmd, server['name'])


def fetch_mtg_logs(server: dict) -> str:
    if server.get('ssh_key'):
        cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
            '-i', server['ssh_key'],
            f"{server['ssh_user']}@{server['host']}",
            f"journalctl -u {server['service_name']} -n 500 --no-pager --since '5 minutes ago' 2>&1"
        ]
    else:
        cmd = [
            'sshpass', '-p', server['ssh_password'],
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
            f"{server['ssh_user']}@{server['host']}",
            f"journalctl -u {server['service_name']} -n 500 --no-pager --since '5 minutes ago' 2>&1"
        ]
    return _run_ssh(cmd, server['name'])


# ── Log parsing ──

def parse_docker_logs(raw: str):
    """Parse old Docker mtproto-proxy format."""
    lines = raw.strip().split('\n')
    latest_stats = {}
    new_ips = set()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = STATS_RE.search(line)
        if m:
            proxy_name = m.group(1)
            total = int(m.group(2))
            current = int(m.group(3))
            traffic = float(m.group(4))
            msgs = int(m.group(5))
            latest_stats[proxy_name] = (total, current, traffic, msgs)

        if NEW_IPS_HEADER_RE.search(line):
            i += 1
            while i < len(lines):
                ip_line = lines[i].strip()
                ip_m = IP_RE.search(ip_line)
                if ip_m:
                    new_ips.add(ip_m.group(1))
                    i += 1
                else:
                    break
            continue
        i += 1

    return latest_stats, new_ips


def parse_mtg_logs(raw: str):
    """Parse mtg v2 JSON debug logs. Count streams and unique IPs."""
    lines = raw.strip().split('\n')
    total_connects = 0
    current_connects = 0
    unique_ips = set()

    for line in lines:
        # Extract JSON from journalctl line
        json_start = line.find('{')
        if json_start == -1:
            continue
        try:
            entry = json_lib.loads(line[json_start:])
        except json_lib.JSONDecodeError:
            continue

        msg = entry.get('message', '')
        client_ip = entry.get('client-ip', '')

        if msg == 'Stream has been finished':
            total_connects += 1
            if client_ip:
                unique_ips.add(client_ip)
        elif msg == 'Stream has been created':
            current_connects += 1
            if client_ip:
                unique_ips.add(client_ip)

    # proxy_name = "bypass" to distinguish from "vpnhub" on Frankfurt
    stats = {}
    if total_connects > 0 or current_connects > 0:
        stats['bypass'] = (total_connects, current_connects, 0.0, 0)

    return stats, unique_ips


# ── Database ──

async def save_to_db(server_host: str, server_name: str, latest_stats: dict, new_ips: set):
    engine = create_async_engine(get_db_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            for proxy_name, (total, current, traffic, msgs) in latest_stats.items():
                await session.execute(
                    text("""
                        INSERT INTO mtproto_proxy_stats
                            (collected_at, server_host, proxy_name, total_connects, current_connects, traffic_mb, total_msgs)
                        VALUES (now(), :host, :name, :total, :current, :traffic, :msgs)
                    """),
                    {
                        'host': server_host,
                        'name': proxy_name,
                        'total': total,
                        'current': current,
                        'traffic': traffic,
                        'msgs': msgs,
                    }
                )
                logger.info(
                    f"[{server_name}/{proxy_name}] connects={total} (current={current}), "
                    f"traffic={traffic}MB, msgs={msgs}"
                )

            today = date.today()
            for ip in new_ips:
                await session.execute(
                    text("""
                        INSERT INTO mtproto_proxy_ips (first_seen_at, date, server_host, ip_address)
                        VALUES (now(), :date, :host, :ip)
                        ON CONFLICT (date, server_host, ip_address) DO NOTHING
                    """),
                    {'date': today, 'host': server_host, 'ip': ip}
                )
            if new_ips:
                logger.info(f"[{server_name}] IPs: {', '.join(sorted(new_ips))}")

    await engine.dispose()


# ── Main ──

async def collect():
    servers = build_server_list()
    if not servers:
        logger.warning("No servers configured, skipping cycle")
        return

    logger.info(f"Collecting from {len(servers)} server(s): {', '.join(s['name'] for s in servers)}")

    for server in servers:
        name = server['name']
        host = server['host']
        fmt = server['format']

        logger.info(f"[{name}] Fetching logs from {host} (format={fmt})...")

        if fmt == 'docker':
            raw = fetch_docker_logs(server)
            if not raw:
                continue
            latest_stats, new_ips = parse_docker_logs(raw)
        elif fmt == 'mtg':
            raw = fetch_mtg_logs(server)
            if not raw:
                continue
            latest_stats, new_ips = parse_mtg_logs(raw)
        else:
            logger.warning(f"[{name}] Unknown format: {fmt}")
            continue

        if not latest_stats:
            logger.warning(f"[{name}] No stats found in logs")
            continue

        logger.info(f"[{name}] Parsed: {len(latest_stats)} proxy(s), {len(new_ips)} IP(s)")
        await save_to_db(host, name, latest_stats, new_ips)
        logger.info(f"[{name}] Done")

    logger.info("Collection cycle complete")


def main():
    asyncio.run(collect())


if __name__ == '__main__':
    main()
