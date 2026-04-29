import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.audit.reader import AuditFilter, AuditReader
from gateway.audit.writer import AuditWriter
from gateway.db.models import Tenant


pytestmark = pytest.mark.integration


async def test_tenant_isolation(db_engine):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        a = Tenant(name=f"a-{uuid4()}")
        b = Tenant(name=f"b-{uuid4()}")
        s.add_all([a, b])
        await s.commit()
        a_id, b_id = a.id, b.id

    w = AuditWriter(sf)
    await w.write(
        tenant_id=a_id, agent_id=None, tool="x", params={}, result_status="success"
    )
    await w.write(
        tenant_id=b_id, agent_id=None, tool="x", params={}, result_status="success"
    )

    r = AuditReader(sf)
    page_a = await r.query(AuditFilter(tenant_id=a_id))
    assert page_a.total == 1
    assert all(e.tenant_id == a_id for e in page_a.entries)
