"""Security test verifying append-only enforcement of the audit log.

The ``mcp_app`` Postgres role (created in alembic migration 0001) is granted
INSERT/SELECT only on ``audit_log``. Append-only triggers and revoked
UPDATE/DELETE privileges should cause both statements to raise
``InsufficientPrivilegeError`` for this user.

Requires a running Postgres with migrations applied; tagged as integration.
"""

from urllib.parse import urlparse

import asyncpg
import pytest

pytestmark = [pytest.mark.security, pytest.mark.integration]


async def test_app_user_cannot_update_audit(pg_url: str) -> None:
    """Verify GRANTs prevent the application user from mutating audit_log rows."""
    parsed = urlparse(pg_url.replace("postgresql+asyncpg://", "postgresql://"))
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user="mcp_app",
        password="mcp_app",
        database=parsed.path.lstrip("/"),
    )
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("UPDATE audit_log SET tool='hacked'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM audit_log")
    finally:
        await conn.close()
