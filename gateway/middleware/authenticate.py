"""Authenticate step — verifies bearer token and populates ctx with claims."""

from uuid import UUID

from gateway.auth.exceptions import TokenError
from gateway.auth.token_validator import TokenValidator
from gateway.middleware.chain import CallContext
from gateway.observability.logging import get_logger
from gateway.tenants.middleware import set_tenant

log = get_logger(__name__)


def make_authenticate(validator: TokenValidator):
    async def step(ctx: CallContext) -> None:
        if not ctx.token:
            ctx.error = TokenError("missing token")
            ctx.result_status = "auth_failed"
            return
        try:
            claims = await validator.verify(ctx.token)
        except TokenError as e:
            ctx.error = e
            ctx.result_status = "auth_failed"
            log.warning("auth_failed", error=str(e), trace_id=ctx.trace_id)
            return
        ctx.tenant_id = claims.tenant_id
        ctx.agent_id = UUID(claims.sub)
        ctx.role_name = next(
            (s.split(":", 1)[1] for s in claims.scopes if s.startswith("role:")),
            None,
        )
        set_tenant(claims.tenant_id)

    return step
