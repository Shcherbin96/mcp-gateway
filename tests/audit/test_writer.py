from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.audit.writer import AuditWriter
from gateway.db.models import Tenant

pytestmark = pytest.mark.integration


async def test_write_appends(db_engine):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}")
        s.add(t)
        await s.commit()
        tid = t.id

    w = AuditWriter(sf)
    await w.write(
        tenant_id=tid,
        agent_id=None,
        tool="get_customer",
        params={"id": "1"},
        result_status="success",
        result={"ok": True},
    )

    from sqlalchemy import func, select

    from gateway.db.models import AuditLog

    async with sf() as s:
        cnt = (
            await s.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tid)
            )
        ).scalar()
        assert cnt == 1
