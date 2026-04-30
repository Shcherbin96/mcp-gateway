"""In-memory token-bucket rate limiter keyed by JWT subject (agent_id) or client IP.

Bespoke ~50-LOC limiter chosen over slowapi (Flask-flavored, heavyweight).
Buckets are pruned periodically when idle > 5 minutes.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

import jwt

from gateway.observability.logging import get_logger

log = get_logger(__name__)

_PRUNE_IDLE_SECONDS = 300.0


@dataclass
class _Bucket:
    tokens: float
    last_refill: float
    last_seen: float


class RateLimiter:
    """Token-bucket limiter: ``rate`` tokens/min plus ``burst`` extra capacity.

    Capacity = ``rate + burst``; refill happens at ``rate / 60`` tokens per second.
    Returns ``(allowed, retry_after_seconds)`` from :meth:`check`.
    """

    def __init__(self, *, rate_per_minute: int = 60, burst: int = 10) -> None:
        self.rate_per_minute = rate_per_minute
        self.burst = burst
        self.capacity = float(rate_per_minute + burst)
        self.refill_per_sec = rate_per_minute / 60.0
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def key_from_token(token: str | None, fallback_ip: str | None) -> str:
        """Return ``sub:<agent_id>`` or ``ip:<addr>``; never raises.

        Signature is intentionally NOT verified here — the token has not yet
        been validated by the authenticate step, and we only need a stable
        key for rate limiting. Forging a sub merely changes which bucket the
        attacker drains; it cannot bypass the limit.
        """
        if token:
            with contextlib.suppress(Exception):
                claims = jwt.decode(token, options={"verify_signature": False})
                sub = claims.get("sub")
                if sub:
                    return f"sub:{sub}"
        return f"ip:{fallback_ip or 'unknown'}"

    async def check(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        async with self._lock:
            self._prune_locked(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, last_refill=now, last_seen=now)
                self._buckets[key] = bucket
            else:
                elapsed = now - bucket.last_refill
                bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_sec)
                bucket.last_refill = now
            bucket.last_seen = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            # Wait time for one full token to refill.
            retry_after = max(1.0, (1.0 - bucket.tokens) / self.refill_per_sec)
            return False, retry_after

    def _prune_locked(self, now: float) -> None:
        stale = [k for k, b in self._buckets.items() if now - b.last_seen > _PRUNE_IDLE_SECONDS]
        for k in stale:
            del self._buckets[k]
