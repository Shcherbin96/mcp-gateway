"""Schema invariants: append-only audit_log, tenant uniqueness."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gateway.db.models import AuditLog, Tenant

pytestmark = pytest.mark.integration


async def test_audit_log_blocks_update(db_session):
    db_session.add(AuditLog(result_status="success"))
    await db_session.flush()
    log_id = (await db_session.execute(text("SELECT id FROM audit_log LIMIT 1"))).scalar()
    with pytest.raises(Exception, match="append-only"):
        await db_session.execute(
            text("UPDATE audit_log SET result_status='x' WHERE id = :i"), {"i": log_id}
        )


async def test_audit_log_blocks_delete(db_session):
    db_session.add(AuditLog(result_status="success"))
    await db_session.flush()
    with pytest.raises(Exception, match="append-only"):
        await db_session.execute(text("DELETE FROM audit_log"))


async def test_tenant_unique_name(db_session):
    db_session.add(Tenant(name="acme"))
    await db_session.flush()
    db_session.add(Tenant(name="acme"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
