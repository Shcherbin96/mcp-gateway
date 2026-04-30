"""Shared tool-invocation helper used by both the legacy REST endpoint
(``POST /mcp/call/{tool_name}``) and the MCP Streamable HTTP endpoint
(``POST /mcp/rpc``).

The helper runs the standard 5-layer pipeline (authenticate → authorize →
approve → execute → audit) and returns a transport-neutral :class:`InvokeOutcome`
that each transport renders into its own response shape (HTTP status codes for
REST, JSON-RPC envelopes for MCP).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from gateway.middleware.chain import CallContext, Pipeline
from gateway.middleware.rate_limit import RateLimiter
from gateway.observability.logging import get_logger
from gateway.observability.metrics import REQUEST_DURATION, REQUESTS_TOTAL

log = get_logger(__name__)


@dataclass
class InvokeOutcome:
    """Transport-neutral result of running a tool through the pipeline.

    ``body`` is always a dict ready to serialise. ``http_status`` reflects the
    REST-style status code so the legacy endpoint can keep its public contract;
    the MCP transport ignores it (always 200) and uses ``is_error`` instead.
    """

    body: dict
    http_status: int
    is_error: bool
    trace_id: str
    result_status: str
    rate_limited: bool = False
    retry_after: float = 0.0


async def invoke_tool(
    *,
    app_state: Any,
    tool_name: str,
    payload: dict,
    token: str | None,
    client_ip: str | None,
) -> InvokeOutcome:
    """Run ``tool_name`` through the pipeline.

    Pulls everything it needs off ``app_state`` so callers don't have to know
    about the rate limiter, registry, pipeline, or audit step separately. This
    is the single chokepoint both transports go through.
    """
    limiter: RateLimiter = app_state.rate_limiter
    rl_key = RateLimiter.key_from_token(token, client_ip)
    allowed, retry_after = await limiter.check(rl_key)
    if not allowed:
        log.info("rate_limit_exceeded", key=rl_key, tool=tool_name, retry_after=retry_after)
        return InvokeOutcome(
            body={"error": "rate_limit_exceeded", "retry_after": retry_after},
            http_status=429,
            is_error=True,
            trace_id="",
            result_status="rate_limited",
            rate_limited=True,
            retry_after=retry_after,
        )

    # Redact BEFORE the pipeline runs so audit always has redacted_params,
    # even when authentication or other early steps fail.
    rt = app_state.registry.get(tool_name)
    redact_fn = rt.meta.redact if rt else (lambda p: dict(p))
    redacted = redact_fn(payload)

    ctx = CallContext(
        token=token,
        tool=tool_name,
        params=dict(payload),
        redacted_params=redacted,
    )

    pipeline: Pipeline = app_state.pipeline
    audit_step = app_state.audit_step

    started = time.monotonic()
    try:
        await pipeline.run(ctx)
    finally:
        try:
            await audit_step(ctx)
        except Exception as e:  # noqa: BLE001
            log.error("audit_failed", error=str(e), trace_id=ctx.trace_id)
            return InvokeOutcome(
                body={"error": "audit_failure", "trace_id": ctx.trace_id},
                http_status=500,
                is_error=True,
                trace_id=ctx.trace_id,
                result_status="audit_failure",
            )
        duration = time.monotonic() - started
        REQUEST_DURATION.labels(tool=tool_name).observe(duration)
        REQUESTS_TOTAL.labels(
            tool=tool_name,
            status=ctx.result_status,
            tenant=str(ctx.tenant_id) if ctx.tenant_id else "none",
        ).inc()

    status = ctx.result_status
    if status == "auth_failed":
        return InvokeOutcome(
            body={"error": str(ctx.error)},
            http_status=401,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status == "denied":
        return InvokeOutcome(
            body={"error": str(ctx.error)},
            http_status=403,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status == "rejected":
        return InvokeOutcome(
            body={"error": "approval rejected"},
            http_status=403,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status == "timeout":
        return InvokeOutcome(
            body={"error": "approval timeout"},
            http_status=408,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status == "upstream_unavailable":
        return InvokeOutcome(
            body={"error": str(ctx.error)},
            http_status=502,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status.startswith("upstream_4xx_"):
        try:
            code = int(status[len("upstream_4xx_") :])
        except ValueError:
            code = 502
        return InvokeOutcome(
            body={"error": str(ctx.error)},
            http_status=code,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status == "upstream_5xx":
        return InvokeOutcome(
            body={"error": str(ctx.error)},
            http_status=502,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )
    if status == "error":
        return InvokeOutcome(
            body={"error": str(ctx.error), "trace_id": ctx.trace_id},
            http_status=500,
            is_error=True,
            trace_id=ctx.trace_id,
            result_status=status,
        )

    return InvokeOutcome(
        body=ctx.result or {},
        http_status=200,
        is_error=False,
        trace_id=ctx.trace_id,
        result_status=status,
    )
