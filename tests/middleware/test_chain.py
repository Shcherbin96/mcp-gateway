"""Pipeline short-circuit semantics + per-step failure mapping."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from gateway.auth.exceptions import TokenError
from gateway.middleware.audit import make_audit
from gateway.middleware.authenticate import make_authenticate
from gateway.middleware.authorize import make_authorize
from gateway.middleware.chain import CallContext, Pipeline
from gateway.middleware.execute import make_execute
from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.schema import PolicyDocument
from gateway.tools.exceptions import UpstreamUnavailable

pytestmark = pytest.mark.unit


async def test_pipeline_short_circuits_on_error():
    step1 = AsyncMock()

    async def fail(ctx: CallContext) -> None:
        ctx.error = ValueError("nope")
        ctx.result_status = "denied"

    step3 = AsyncMock()

    p = Pipeline(steps=[step1, fail, step3])
    ctx = CallContext()
    await p.run(ctx)

    assert step1.called
    assert not step3.called
    assert ctx.result_status == "denied"
    assert isinstance(ctx.error, ValueError)


async def test_authenticate_missing_token_sets_auth_failed():
    validator = AsyncMock()
    step = make_authenticate(validator)
    ctx = CallContext()  # no token

    await step(ctx)

    assert ctx.result_status == "auth_failed"
    assert isinstance(ctx.error, TokenError)
    validator.verify.assert_not_called()


async def test_authenticate_invalid_token_sets_auth_failed():
    validator = AsyncMock()
    validator.verify.side_effect = TokenError("bad signature")
    step = make_authenticate(validator)
    ctx = CallContext(token="bogus")

    await step(ctx)

    assert ctx.result_status == "auth_failed"
    assert isinstance(ctx.error, TokenError)
    assert "bad signature" in str(ctx.error)


async def test_authorize_unknown_role_sets_denied():
    # Evaluator with empty role set
    evaluator = PolicyEvaluator(PolicyDocument(roles=[]))
    session_factory = AsyncMock()  # never called when role_name is preset
    step = make_authorize(evaluator, session_factory)
    ctx = CallContext(role_name="nonexistent", tool="any_tool", agent_id=uuid4())

    await step(ctx)

    assert ctx.result_status == "denied"
    assert isinstance(ctx.error, PermissionError)


async def test_execute_unknown_tool_sets_error():
    registry = AsyncMock()
    registry.get = lambda name: None  # registry empty
    step = make_execute(registry)
    ctx = CallContext(tool="missing")

    await step(ctx)

    assert ctx.result_status == "error"
    assert ctx.error is not None
    assert "unknown tool" in str(ctx.error)


async def test_execute_upstream_unavailable_maps():
    handler = AsyncMock(side_effect=UpstreamUnavailable("circuit open"))

    class FakeRT:
        def __init__(self, h):
            self.handler = h

    registry = AsyncMock()
    registry.get = lambda name: FakeRT(handler)
    step = make_execute(registry)
    ctx = CallContext(tool="some_tool", params={})

    await step(ctx)

    assert ctx.result_status == "upstream_unavailable"
    assert isinstance(ctx.error, UpstreamUnavailable)


async def test_audit_writes_on_any_outcome():
    writer = AsyncMock()
    step = make_audit(writer)
    ctx = CallContext(
        tenant_id=uuid4(),
        agent_id=uuid4(),
        tool="some_tool",
        params={"k": "v"},
    )
    ctx.error = PermissionError("denied")
    ctx.result_status = "denied"

    await step(ctx)

    writer.write.assert_awaited_once()
    kwargs = writer.write.await_args.kwargs
    assert kwargs["result_status"] == "denied"
    assert kwargs["tool"] == "some_tool"
    assert kwargs["result"] == {"error": "denied"}
