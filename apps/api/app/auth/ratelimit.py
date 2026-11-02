"""Login rate limit (NFR-6; D10 M-7, L-3).

Three limits, all checked **before** any password work and identically for known and unknown
emails:
- per (normalised email, client IP): 5 per minute — the NFR-6 limit;
- per normalised email across IPs: 20 per hour (429, never an account lock);
- per client IP across emails: 30 per minute (password spraying).

Counters live in a shared store (Postgres `auth_attempts`), so the limits hold across workers and
instances. Bucket keys are SHA-256 digests, so no email or IP is stored in clear. Rejected attempts
are not recorded, so a window always drains.

Client IP: the socket peer, unless the peer is in `TRUSTED_PROXIES` (the BFF or platform LB), in
which case the right-most `X-Forwarded-For` entry that is not itself a trusted proxy.
"""

import hashlib
import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.contract.common import ErrorCode
from app.core.errors import ApiError


@dataclass(frozen=True)
class Limit:
    name: str
    limit: int
    window: timedelta


PER_EMAIL_IP = Limit("email_ip", 5, timedelta(minutes=1))
PER_EMAIL = Limit("email", 20, timedelta(hours=1))
PER_IP = Limit("ip", 30, timedelta(minutes=1))


@dataclass(frozen=True)
class Bucket:
    key: str
    limit: Limit


class AttemptStore(Protocol):
    def try_record(self, buckets: Sequence[Bucket], now: datetime) -> bool:
        """Atomically: if every bucket is under its limit, record one attempt in each and return
        True; otherwise record nothing and return False."""
        ...


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def login_buckets(email: str, ip: str) -> list[Bucket]:
    """`email` must already be normalised."""
    return [
        Bucket(_digest(PER_EMAIL_IP.name, email, ip), PER_EMAIL_IP),
        Bucket(_digest(PER_EMAIL.name, email), PER_EMAIL),
        Bucket(_digest(PER_IP.name, ip), PER_IP),
    ]


RATE_LIMITED_HEADERS = {"Retry-After": "60"}


def enforce_login_limit(store: AttemptStore, email: str, ip: str, now: datetime) -> None:
    if not store.try_record(login_buckets(email, ip), now):
        raise ApiError(429, ErrorCode.RATE_LIMITED, headers=RATE_LIMITED_HEADERS)


class MemoryAttemptStore:
    """Process-local store for unit tests only (not shared across workers)."""

    def __init__(self) -> None:
        self.hits: dict[str, list[datetime]] = {}

    def try_record(self, buckets: Sequence[Bucket], now: datetime) -> bool:
        for b in buckets:
            recent = [t for t in self.hits.get(b.key, []) if t > now - b.limit.window]
            if len(recent) >= b.limit.limit:
                return False
        for b in buckets:
            self.hits.setdefault(b.key, []).append(now)
        return True


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_trusted_proxies(values: Sequence[str]) -> list[Network]:
    return [ipaddress.ip_network(v, strict=False) for v in values]


def _is_trusted(ip: str, trusted: Sequence[Network]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in trusted)


def client_ip(peer: str | None, forwarded_for: str | None, trusted: Sequence[Network]) -> str:
    peer = peer or "unknown"
    if not forwarded_for or not _is_trusted(peer, trusted):
        return peer
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, trusted):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer
    return peer
