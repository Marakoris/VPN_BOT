#!/usr/bin/env python3
"""
MTProto Proxy Stats Collector

Collects stats from multiple MTProto proxy servers via SSH,
parses logs, writes metrics to PostgreSQL.
Runs every MTPROTO_COLLECT_INTERVAL seconds (default: 300).

Supported servers:
  - Frankfurt (Docker-based, password SSH)
  - Bypass-1 (systemd-based, key-based SSH)
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Database config
POSTGRES_DB = os.getenv('POSTGRES_DB', '')
POSTGRES_USER = os.getenv('POSTGRES_USER', '')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
DB_HOST = 'postgres_db_container'

# Regex patterns
# "vpnhub: 192 connects (6 current), 5.05 MB, 1860 msgs"
STATS_RE = re.compile(
    r'(\w+): (\d+) connects \((\d+) current\), ([\d.]+) MB, (\d+) msgs'
)
# "New IPs:" followed by IP lines (supports journalctl prefix)
NEW_IPS_HEADER_RE = re.compile(r'New IPs:\s*$')
IP_RE = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*$')


def get_db_url():
    return (
        f'postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}'
        f'@{DB_HOST}/{POSTGRES_DB}'
    )


# ── Server configurations ──────────────────────────────────────────

def build_server_list():
    """Build list of servers to collect from based on env vars."""
    servers = []

    # Server 1: Frankfurt (Docker, password SSH)
    host1 = os.getenv('MTPROTO_SSH_HOST', '')
    if host1:
        servers.append({
            'name': 'Frankfurt',
            'host': host1,
            'fetch_fn': _fetch_docker_password,
            'ssh_user': os.getenv('MTPROTO_SSH_USER', 'root'),
            'ssh_password': os.getenv('MTPROTO_SSH_PASSWORD', ''),
            'docker_container': os.getenv('MTPROTO_DOCKER_CONTAINER', 'mtproto-proxy'),
            'log_tail': int(os.getenv('MTPROTO_LOG_TAIL', '200')),
        })

    # Server 2: Bypass-1 (systemd, key-based SSH)
    host2 = os.getenv('MTPROTO_BYPASS1_HOST', '')
    if host2:
        servers.append({
            'name': 'Bypass-1',
            'host': host2,
            'fetch_fn': _fetch_journalctl_key,
            'ssh_user': os.getenv('MTPROTO_BYPASS1_SSH_USER', 'root'),
            'ssh_key': os.getenv('MTPROTO_BYPASS1_SSH_KEY', '/root/.ssh/id_ed25519'),
            'service_name': os.getenv('MTPROTO_BYPASS1_SERVICE', 'mtproto-proxy'),
        })

    return servers


def _fetch_docker_password(server: dict) -> str:
    """Fetch logs from Docker container via password-based SSH."""
    cmd = [
        'sshpass', '-p', server['ssh_password'],
        'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
        f"{server['ssh_user']}@{server['host']}",
        f"docker logs --tail={server['log_tail']} {server['docker_container']} 2>&1"
    ]
    return _run_ssh(cmd, server['name'])


def _fetch_journalctl_key(server: dict) -> str:
    """Fetch logs from journalctl via key-based SSH."""
    cmd = [
        'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
        '-i', server['ssh_key'],
        f"{server['ssh_user']}@{server['host']}",
        f"journalctl -u {server['service_name']} -n 500 --no-pager 2>&1"
    ]
    return _run_ssh(cmd, server['name'])


def _run_ssh(cmd: list, server_name: str) -> str:
    """Execute SSH command and return stdout."""
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


# ── Log parsing ─────────────────────────────────────────────────────

def parse_logs(raw: str):
    """Parse logs, return (latest_stats_per_proxy, new_ips)."""
    lines = raw.strip().split('\n')
    latest_stats = {}  # proxy_name -> (total, current, traffic, msgs)
    new_ips = set()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Parse stats line
        m = STATS_RE.search(line)
        if m:
            proxy_name = m.group(1)
            total = int(m.group(2))
            current = int(m.group(3))
            traffic = float(m.group(4))
            msgs = int(m.group(5))
            latest_stats[proxy_name] = (total, current, traffic, msgs)

        # Parse New IPs block
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


# ── Database ────────────────────────────────────────────────────────

async def save_to_db(server_host: str, server_name: str, latest_stats: dict, new_ips: set):
    """Insert stats and upsert IPs into PostgreSQL."""
    engine = create_async_engine(get_db_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            # Insert stats rows
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

            # Upsert IPs
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
                logger.info(f"[{server_name}] New IPs: {', '.join(sorted(new_ips))}")

    await engine.dispose()


# ── Main collection ─────────────────────────────────────────────────

async def collect():
    """Single collection cycle — iterate over all configured servers."""
    servers = build_server_list()
    if not servers:
        logger.warning("No servers configured, skipping cycle")
        return

    logger.info(f"Collecting from {len(servers)} server(s): {', '.join(s['name'] for s in servers)}")

    for server in servers:
        name = server['name']
        host = server['host']

        logger.info(f"[{name}] Fetching logs from {host}...")
        raw = server['fetch_fn'](server)
        if not raw:
            logger.warning(f"[{name}] No logs fetched, skipping")
            continue

        latest_stats, new_ips = parse_logs(raw)

        if not latest_stats:
            logger.warning(f"[{name}] No stats found in logs, skipping")
            continue

        logger.info(f"[{name}] Parsed: {len(latest_stats)} proxy(s), {len(new_ips)} new IP(s)")
        await save_to_db(host, name, latest_stats, new_ips)
        logger.info(f"[{name}] Done")

    logger.info("Collection cycle complete")


def main():
    asyncio.run(collect())


if __name__ == '__main__':
    main()
