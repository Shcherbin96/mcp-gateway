"""Unit tests for the in-memory token-bucket rate limiter."""

import asyncio

import pytest

from gateway.middleware.rate_limit import RateLimiter

pytestmark = pytest.mark.unit


async def test_under_limit_all_pass():
    """All calls within capacity (rate + burst) succeed."""
    limiter = RateLimiter(rate_per_minute=60, burst=10)
    key = "sub:agent-a"
    for _ in range(60):
        allowed, retry = await limiter.check(key)
        assert allowed is True
        assert retry == 0.0


async def test_61st_call_within_60s_returns_429():
    """Past full bucket capacity (rate + burst), the next call is denied."""
    # Rate=60, burst=10 → capacity 70. Drain 70 then expect denial.
    limiter = RateLimiter(rate_per_minute=60, burst=10)
    key = "sub:agent-b"
    for _ in range(70):
        allowed, _ = await limiter.check(key)
        assert allowed is True
    allowed, retry_after = await limiter.check(key)
    assert allowed is False
    assert retry_after >= 1.0


async def test_different_agents_have_independent_buckets():
    """Two different keys must not share state — one being rate-limited
    must not affect the other.
    """
    limiter = RateLimiter(rate_per_minute=60, burst=10)
    a, b = "sub:agent-a", "sub:agent-b"
    # Drain a entirely
    for _ in range(70):
        allowed, _ = await limiter.check(a)
        assert allowed is True
    allowed_a, _ = await limiter.check(a)
    assert allowed_a is False
    # b still has full capacity
    allowed_b, _ = await limiter.check(b)
    assert allowed_b is True


async def test_key_from_token_falls_back_to_ip():
    """Without a token, key by IP; with malformed token, also fall back to IP."""
    assert RateLimiter.key_from_token(None, "1.2.3.4") == "ip:1.2.3.4"
    assert RateLimiter.key_from_token("not-a-jwt", "5.6.7.8") == "ip:5.6.7.8"


async def test_key_from_token_uses_sub():
    """Valid JWT (signature unverified for keying) yields sub-keyed bucket."""
    import jwt

    token = jwt.encode({"sub": "agent-xyz"}, "secret", algorithm="HS256")
    assert RateLimiter.key_from_token(token, "1.2.3.4") == "sub:agent-xyz"


async def test_concurrent_check_is_thread_safe():
    """Concurrent checks on the same key must not race past capacity."""
    limiter = RateLimiter(rate_per_minute=60, burst=10)  # capacity 70
    results = await asyncio.gather(*(limiter.check("sub:c") for _ in range(100)))
    allowed_count = sum(1 for ok, _ in results if ok)
    assert allowed_count == 70
