"""
Security middleware and utilities for Subscription API

Stage 6: Security implementation
- Rate limiting per IP
- Brute-force protection
- Suspicious activity monitoring
"""
import time
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


# ==================== CONFIGURATION ====================

class SecurityConfig:
    """Security configuration"""

    # Rate limiting
    RATE_LIMIT_REQUESTS = 60  # requests per window
    RATE_LIMIT_WINDOW = 60  # seconds (1 minute)

    # Brute-force protection
    BRUTE_FORCE_THRESHOLD = 10  # failed attempts
    BRUTE_FORCE_WINDOW = 300  # seconds (5 minutes)
    BRUTE_FORCE_BAN_DURATION = 3600  # seconds (1 hour)

    # Suspicious activity
    SUSPICIOUS_THRESHOLD = 100  # requests per hour
    SUSPICIOUS_WINDOW = 3600  # seconds (1 hour)

    # IP whitelist (optional - empty means no whitelist)
    IP_WHITELIST = []

    # Cleanup interval
    CLEANUP_INTERVAL = 300  # seconds (5 minutes)


# ==================== DATA STRUCTURES ====================

@dataclass
class IPStats:
    """Statistics for a single IP address"""
    ip: str
    requests: deque = field(default_factory=deque)  # Timestamps of requests
    failed_attempts: deque = field(default_factory=deque)  # Failed token attempts
    banned_until: Optional[float] = None  # Unix timestamp
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    total_requests: int = 0
    total_failed: int = 0

    def is_banned(self) -> bool:
        """Check if IP is currently banned"""
        if self.banned_until is None:
            return False
        if time.time() < self.banned_until:
            return True
        # Ban expired, reset
        self.banned_until = None
        return False


class SecurityManager:
    """
    Security manager for subscription API

    Implements:
    - Rate limiting per IP
    - Brute-force protection
    - Suspicious activity detection
    """

    def __init__(self, config: SecurityConfig = None):
        self.config = config or SecurityConfig()
        self.ip_stats: Dict[str, IPStats] = {}
        self.last_cleanup = time.time()

    def _get_ip_stats(self, ip: str) -> IPStats:
        """Get or create IP statistics"""
        if ip not in self.ip_stats:
            self.ip_stats[ip] = IPStats(ip=ip)
        return self.ip_stats[ip]

    def _cleanup_old_data(self):
        """Remove old data to prevent memory leaks"""
        now = time.time()

        # Only cleanup every CLEANUP_INTERVAL seconds
        if now - self.last_cleanup < self.config.CLEANUP_INTERVAL:
            return

        self.last_cleanup = now

        # Remove IPs that haven't been seen in 24 hours
        inactive_threshold = now - 86400
        inactive_ips = [
            ip for ip, stats in self.ip_stats.items()
            if stats.last_seen < inactive_threshold and not stats.is_banned()
        ]

        for ip in inactive_ips:
            del self.ip_stats[ip]

        if inactive_ips:
            log.info(f"[Security] Cleaned up {len(inactive_ips)} inactive IPs")

        # Clean old timestamps from active IPs
        for stats in self.ip_stats.values():
            # Remove requests older than rate limit window
            cutoff = now - self.config.RATE_LIMIT_WINDOW
            while stats.requests and stats.requests[0] < cutoff:
                stats.requests.popleft()

            # Remove failed attempts older than brute force window
            cutoff = now - self.config.BRUTE_FORCE_WINDOW
            while stats.failed_attempts and stats.failed_attempts[0] < cutoff:
                stats.failed_attempts.popleft()

    def check_rate_limit(self, ip: str) -> Tuple[bool, Optional[str]]:
        """
        Check if IP is within rate limits

        Args:
            ip: IP address to check

        Returns:
            (allowed, error_message)
        """
        # Whitelist check
        if ip in self.config.IP_WHITELIST:
            return True, None

        stats = self._get_ip_stats(ip)
        stats.last_seen = time.time()

        # Check if banned
        if stats.is_banned():
            remaining = int(stats.banned_until - time.time())
            log.warning(f"[Security] Banned IP attempted access: {ip} ({remaining}s remaining)")
            return False, f"IP banned. Try again in {remaining} seconds"

        # Clean old requests
        now = time.time()
        cutoff = now - self.config.RATE_LIMIT_WINDOW
        while stats.requests and stats.requests[0] < cutoff:
            stats.requests.popleft()

        # Check rate limit
        if len(stats.requests) >= self.config.RATE_LIMIT_REQUESTS:
            log.warning(
                f"[Security] Rate limit exceeded for IP: {ip} "
                f"({len(stats.requests)} requests in {self.config.RATE_LIMIT_WINDOW}s)"
            )
            return False, "Rate limit exceeded. Please try again later"

        # Record request
        stats.requests.append(now)
        stats.total_requests += 1

        # Cleanup old data periodically
        self._cleanup_old_data()

        return True, None

    def record_failed_attempt(self, ip: str, reason: str = "invalid_token"):
        """
        Record failed authentication attempt

        Args:
            ip: IP address
            reason: Reason for failure (invalid_token, etc.)
        """
        stats = self._get_ip_stats(ip)
        now = time.time()

        # Record failed attempt
        stats.failed_attempts.append(now)
        stats.total_failed += 1

        # Clean old failed attempts
        cutoff = now - self.config.BRUTE_FORCE_WINDOW
        while stats.failed_attempts and stats.failed_attempts[0] < cutoff:
            stats.failed_attempts.popleft()

        # Check if threshold exceeded
        if len(stats.failed_attempts) >= self.config.BRUTE_FORCE_THRESHOLD:
            stats.banned_until = now + self.config.BRUTE_FORCE_BAN_DURATION
            log.warning(
                f"[Security] ⚠️  IP BANNED for brute-force: {ip} "
                f"({len(stats.failed_attempts)} failed attempts in {self.config.BRUTE_FORCE_WINDOW}s)"
            )

    def check_suspicious_activity(self, ip: str) -> bool:
        """
        Check if IP shows suspicious activity patterns

        Args:
            ip: IP address

        Returns:
            True if suspicious, False otherwise
        """
        stats = self._get_ip_stats(ip)
        now = time.time()

        # Count requests in last hour
        cutoff = now - self.config.SUSPICIOUS_WINDOW
        recent_requests = sum(1 for ts in stats.requests if ts > cutoff)

        if recent_requests >= self.config.SUSPICIOUS_THRESHOLD:
            log.warning(
                f"[Security] 🚨 Suspicious activity detected: {ip} "
                f"({recent_requests} requests in {self.config.SUSPICIOUS_WINDOW}s)"
            )
            return True

        return False

    def get_stats(self, ip: Optional[str] = None) -> Dict:
        """
        Get security statistics

        Args:
            ip: Optional - get stats for specific IP, or all IPs if None

        Returns:
            Statistics dictionary
        """
        if ip:
            if ip not in self.ip_stats:
                return {"error": "IP not found"}

            stats = self.ip_stats[ip]
            return {
                "ip": ip,
                "total_requests": stats.total_requests,
                "total_failed": stats.total_failed,
                "recent_requests": len(stats.requests),
                "recent_failed": len(stats.failed_attempts),
                "is_banned": stats.is_banned(),
                "banned_until": stats.banned_until,
                "first_seen": datetime.fromtimestamp(stats.first_seen).isoformat(),
                "last_seen": datetime.fromtimestamp(stats.last_seen).isoformat()
            }

        # Global stats
        total_ips = len(self.ip_stats)
        banned_ips = sum(1 for stats in self.ip_stats.values() if stats.is_banned())
        total_requests = sum(stats.total_requests for stats in self.ip_stats.values())
        total_failed = sum(stats.total_failed for stats in self.ip_stats.values())

        return {
            "total_ips": total_ips,
            "banned_ips": banned_ips,
            "total_requests": total_requests,
            "total_failed": total_failed,
            "config": {
                "rate_limit": f"{self.config.RATE_LIMIT_REQUESTS} req/{self.config.RATE_LIMIT_WINDOW}s",
                "brute_force_threshold": self.config.BRUTE_FORCE_THRESHOLD,
                "brute_force_ban_duration": f"{self.config.BRUTE_FORCE_BAN_DURATION}s",
            }
        }

    def unban_ip(self, ip: str) -> bool:
        """
        Manually unban an IP address

        Args:
            ip: IP address to unban

        Returns:
            True if IP was banned and is now unbanned, False otherwise
        """
        if ip not in self.ip_stats:
            return False

        stats = self.ip_stats[ip]
        if stats.banned_until is None:
            return False

        stats.banned_until = None
        log.info(f"[Security] IP manually unbanned: {ip}")
        return True


# ==================== GLOBAL INSTANCE ====================

# Create global security manager instance
security_manager = SecurityManager()


# ==================== HELPER FUNCTIONS ====================

def check_rate_limit(ip: str) -> Tuple[bool, Optional[str]]:
    """Helper: Check rate limit for IP"""
    return security_manager.check_rate_limit(ip)


def record_failed_attempt(ip: str, reason: str = "invalid_token"):
    """Helper: Record failed attempt"""
    security_manager.record_failed_attempt(ip, reason)


def check_suspicious_activity(ip: str) -> bool:
    """Helper: Check for suspicious activity"""
    return security_manager.check_suspicious_activity(ip)


def get_security_stats(ip: Optional[str] = None) -> Dict:
    """Helper: Get security statistics"""
    return security_manager.get_stats(ip)


def unban_ip(ip: str) -> bool:
    """Helper: Unban IP address"""
    return security_manager.unban_ip(ip)


# ==================== YOOKASSA IP WHITELIST ====================

import ipaddress

# Official YooKassa IP addresses for webhook notifications
# Source: https://yookassa.ru/developers/using-api/webhooks
YOOKASSA_IP_WHITELIST = [
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.128/25",
]


def is_yookassa_ip(ip: str) -> bool:
    """
    Check if IP address belongs to YooKassa webhook servers.

    Args:
        ip: IP address to check

    Returns:
        True if IP is in YooKassa whitelist, False otherwise
    """
    try:
        check_ip = ipaddress.ip_address(ip)

        for allowed in YOOKASSA_IP_WHITELIST:
            if '/' in allowed:
                # CIDR notation
                if check_ip in ipaddress.ip_network(allowed, strict=False):
                    return True
            else:
                # Single IP
                if check_ip == ipaddress.ip_address(allowed):
                    return True

        return False
    except ValueError:
        log.error(f"[Security] Invalid IP address format: {ip}")
        return False
