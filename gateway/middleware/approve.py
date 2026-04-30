"""Approve step — when policy says REQUIRES_APPROVAL, create + wait for decision."""

from gateway.approval.notifier import ApprovalNotifier
from gateway.approval.store import APPROVED, REJECTED, TIMEOUT, ApprovalStore
from gateway.config import get_settings
from gateway.middleware.chain import CallContext
from gateway.observability.metrics import APPROVALS_PENDING, APPROVALS_TOTAL
from gateway.policy.schema import Decision


def make_approve(store: ApprovalStore, notifier: ApprovalNotifier, settings=None):
    settings = settings or get_settings()

    async def step(ctx: CallContext) -> None:
        if ctx.decision != Decision.REQUIRES_APPROVAL.value:
            return

        if ctx.tenant_id is None or ctx.agent_id is None or ctx.tool is None:
            return  # nothing to approve without context

        approval_id = await store.create(
            tenant_id=ctx.tenant_id,
            agent_id=ctx.agent_id,
            tool=ctx.tool,
            params=ctx.redacted_params or ctx.params,
        )
        ctx.approval_id = approval_id

        APPROVALS_PENDING.labels(tenant=str(ctx.tenant_id)).inc()
        try:
            await notifier.notify_pending(
                approval_id=approval_id,
                agent_id=ctx.agent_id,
                tool=ctx.tool,
                params=ctx.redacted_params or ctx.params,
            )
            status = await store.wait_for_decision(
                approval_id,
                timeout=settings.approval_timeout_seconds,
                poll_interval=settings.approval_poll_interval_seconds,
            )
        finally:
            APPROVALS_PENDING.labels(tenant=str(ctx.tenant_id)).dec()

        APPROVALS_TOTAL.labels(decision=status).inc()
        if status == APPROVED:
            return
        if status == REJECTED:
            ctx.error = PermissionError("approval rejected")
            ctx.result_status = "rejected"
        elif status == TIMEOUT:
            ctx.error = TimeoutError("approval timeout")
            ctx.result_status = "timeout"

    return step
