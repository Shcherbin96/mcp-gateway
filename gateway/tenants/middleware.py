"""ContextVar-based tenant scoping for per-request tenant isolation."""

from contextvars import ContextVar
from uuid import UUID

_tenant_ctx: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)


def set_tenant(tenant_id: UUID | None) -> None:
    _tenant_ctx.set(tenant_id)


def current_tenant() -> UUID | None:
    return _tenant_ctx.get()


def require_tenant() -> UUID:
    tid = current_tenant()
    if tid is None:
        raise RuntimeError("tenant context not set")
    return tid
