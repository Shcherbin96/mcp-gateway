"""Security test verifying append-only enforcement of the audit log.

The ``mcp_app`` Postgres role (created in alembic migration 0001) is granted
INSERT/SELECT only on ``audit_log``. Append-only triggers and revoked
UPDATE/DELETE privileges should cause both statements to raise
``InsufficientPrivilegeError`` for this user.

Requires a running Postgres with migrations applied; tagged as integration.
"""

import asyncpg
import pytest

pytestmark = [pytest.mark.security, pytest.mark.integration]


async def test_app_user_cannot_update_audit() -> None:
    conn = await asyncpg.connect(
        "postgresql://mcp_app:mcp_app@localhost:5432/mcp_gateway"
    )
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("UPDATE audit_log SET tool='hacked'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM audit_log")
    finally:
        await conn.close()
