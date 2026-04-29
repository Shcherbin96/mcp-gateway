"""Middleware pipeline abstraction — sequential async steps with error short-circuit."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class CallContext:
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    token: str | None = None
    tenant_id: UUID | None = None
    agent_id: UUID | None = None
    role_name: str | None = None
    tool: str | None = None
    params: dict = field(default_factory=dict)
    redacted_params: dict = field(default_factory=dict)
    decision: str | None = None  # Decision.value set by authorize, consumed by approve
    approval_id: UUID | None = None
    result: dict | None = None
    result_status: str = "unknown"  # success|denied|rejected|timeout|error|auth_failed|...
    error: Exception | None = None


Handler = Callable[[CallContext], Awaitable[None]]


@dataclass
class Pipeline:
    steps: list[Handler]

    async def run(self, ctx: CallContext) -> CallContext:
        for step in self.steps:
            await step(ctx)
            if ctx.error is not None:
                break
        return ctx
