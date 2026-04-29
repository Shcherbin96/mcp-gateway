"""Authorize step — resolves role (DB fallback) and evaluates policy decision."""

from sqlalchemy import select

from gateway.db.models import Agent, Role
from gateway.middleware.chain import CallContext
from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.schema import Decision


def make_authorize(evaluator: PolicyEvaluator, session_factory):
    async def step(ctx: CallContext) -> None:
        # Resolve role from DB if not in token
        if not ctx.role_name and ctx.agent_id is not None:
            async with session_factory() as s:
                res = await s.execute(
                    select(Role.name)
                    .join(Agent, Agent.role_id == Role.id)
                    .where(Agent.id == ctx.agent_id)
                )
                ctx.role_name = res.scalar_one_or_none()

        if not ctx.role_name:
            ctx.error = PermissionError("no role")
            ctx.result_status = "denied"
            return

        decision = evaluator.evaluate(ctx.role_name, ctx.tool)
        ctx.decision = decision.value
        if decision == Decision.DENY:
            ctx.error = PermissionError(
                f"role {ctx.role_name} denied for tool {ctx.tool}"
            )
            ctx.result_status = "denied"

    return step
