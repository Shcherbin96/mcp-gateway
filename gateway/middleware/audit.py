"""Audit step — append outcome to AuditLog (success or error)."""

from gateway.audit.writer import AuditWriter
from gateway.middleware.chain import CallContext


def make_audit(writer: AuditWriter):
    async def step(ctx: CallContext) -> None:
        params_for_audit = ctx.redacted_params or {
            k: v for k, v in ctx.params.items() if not k.startswith("__")
        }
        result_for_audit: dict = {}
        if ctx.result_status == "success":
            result_for_audit = ctx.result or {}
        elif ctx.error:
            result_for_audit = {"error": str(ctx.error)}

        await writer.write(
            tenant_id=ctx.tenant_id,
            agent_id=ctx.agent_id,
            tool=ctx.tool,
            params=params_for_audit,
            result_status=ctx.result_status,
            result=result_for_audit,
            approval_id=ctx.approval_id,
            trace_id=ctx.trace_id,
        )

    return step
