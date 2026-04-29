"""Pipeline short-circuit semantics."""

from unittest.mock import AsyncMock

import pytest

from gateway.middleware.chain import CallContext, Pipeline


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
