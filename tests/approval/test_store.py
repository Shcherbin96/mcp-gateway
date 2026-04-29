"""Integration tests for ApprovalStore against a real Postgres testcontainer."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.approval.store import APPROVED, TIMEOUT, ApprovalStore
from gateway.db.models import Agent, Role, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
async def seeded_ids(db_session):
    t = Tenant(name="t1")
    db_session.add(t)
    await db_session.flush()
    r = Role(tenant_id=t.id, name="support")
    db_session.add(r)
    await db_session.flush()
    a = Agent(tenant_id=t.id, name="a1", role_id=r.id)
    db_session.add(a)
    await db_session.commit()
    return t.id, a.id


async def test_create_and_decide(db_engine, seeded_ids):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})
    ok = await store.decide(rid, decision=APPROVED, decided_by="me")
    assert ok is True
    req = await store.get(rid)
    assert req.status == APPROVED


async def test_concurrent_decide_only_one_wins(db_engine, seeded_ids):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})
    results = await asyncio.gather(
        store.decide(rid, decision="approved", decided_by="a"),
        store.decide(rid, decision="rejected", decided_by="b"),
    )
    assert results.count(True) == 1
    assert results.count(False) == 1


async def test_wait_for_decision_returns_when_decided(db_engine, seeded_ids):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})

    async def decide_later():
        await asyncio.sleep(0.5)
        await store.decide(rid, decision=APPROVED, decided_by="x")

    asyncio.create_task(decide_later())
    status = await store.wait_for_decision(rid, timeout=5, poll_interval=0.2)
    assert status == APPROVED


async def test_wait_for_decision_times_out(db_engine, seeded_ids):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})
    status = await store.wait_for_decision(rid, timeout=0.5, poll_interval=0.1)
    assert status == TIMEOUT


async def test_decide_with_tenant_filter(db_engine, seeded_ids):
    """Cross-tenant decide must fail when tenant_id filter is enforced."""
    from uuid import uuid4

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})

    # Wrong tenant_id: update must not match.
    wrong_tid = uuid4()
    ok = await store.decide(
        rid, decision=APPROVED, decided_by="attacker", tenant_id=wrong_tid
    )
    assert ok is False
    req = await store.get(rid)
    assert req.status == "pending"
    assert req.decided_by is None

    # Correct tenant_id: update succeeds.
    ok = await store.decide(
        rid, decision=APPROVED, decided_by="legit", tenant_id=tid
    )
    assert ok is True
    req = await store.get(rid)
    assert req.status == APPROVED
    assert req.decided_by == "legit"
