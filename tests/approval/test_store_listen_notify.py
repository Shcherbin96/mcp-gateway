"""Integration test for LISTEN/NOTIFY-driven wait_for_decision.

Verifies that decide() on one connection wakes wait_for_decision on
another within ~100ms, much faster than the 5s poll fallback.
"""

import asyncio
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.approval.store import APPROVED, ApprovalStore
from gateway.db.models import Agent, Role, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
async def seeded_ids(db_engine):
    """Seed a tenant + role + agent via a real (committed) session, then clean up."""
    from uuid import uuid4

    from sqlalchemy import delete

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}")
        s.add(t)
        await s.flush()
        r = Role(tenant_id=t.id, name="support")
        s.add(r)
        await s.flush()
        a = Agent(tenant_id=t.id, name="a1", role_id=r.id)
        s.add(a)
        await s.commit()
        tid, aid, rid_role = t.id, a.id, r.id

    yield tid, aid

    from gateway.db.models import ApprovalRequest

    async with sf() as s:
        await s.execute(delete(ApprovalRequest).where(ApprovalRequest.tenant_id == tid))
        await s.execute(delete(Agent).where(Agent.id == aid))
        await s.execute(delete(Role).where(Role.id == rid_role))
        await s.execute(delete(Tenant).where(Tenant.id == tid))
        await s.commit()


async def test_notify_wakes_waiter_within_100ms(db_engine, pg_url, seeded_ids):
    """A decide() call on one connection wakes a wait_for_decision() on another
    much faster than the 5s poll fallback would allow.
    """
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf, database_url=pg_url)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})

    async def decide_after_short_delay():
        # Long enough for the listener to attach, short enough to prove NOTIFY
        # (not the 5s poll fallback) drove the wake-up.
        await asyncio.sleep(0.1)
        await store.decide(rid, decision=APPROVED, decided_by="me")

    asyncio.create_task(decide_after_short_delay())

    started = time.monotonic()
    # Long timeout, but a 5s poll fallback — we expect NOTIFY to wake us in well
    # under 1s (decide fires after ~100ms; NOTIFY adds tens of ms at most).
    status = await store.wait_for_decision(rid, timeout=10.0, poll_interval=5.0)
    elapsed = time.monotonic() - started

    assert status == APPROVED
    # Generous bound — must beat the 5s poll fallback.
    assert elapsed < 2.0, f"NOTIFY path too slow: took {elapsed:.2f}s"
