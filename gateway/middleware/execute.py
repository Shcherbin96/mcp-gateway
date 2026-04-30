"""Execute step — invokes the registered tool handler with mapped errors."""

from gateway.middleware.chain import CallContext
from gateway.tools.exceptions import (
    ToolError,
    UpstreamClientError,
    UpstreamServerError,
    UpstreamUnavailable,
)
from gateway.tools.registry import ToolRegistry


def make_execute(registry: ToolRegistry):
    async def step(ctx: CallContext) -> None:
        if ctx.tool is None:
            ctx.error = ToolError("missing tool")
            ctx.result_status = "error"
            return
        rt = registry.get(ctx.tool)
        if not rt:
            ctx.error = ToolError(f"unknown tool: {ctx.tool}")
            ctx.result_status = "error"
            return
        try:
            result = await rt.handler(
                **{k: v for k, v in ctx.params.items() if not k.startswith("__")}
            )
            ctx.result = result
            ctx.result_status = "success"
        except UpstreamUnavailable as e:
            ctx.error = e
            ctx.result_status = "upstream_unavailable"
        except UpstreamClientError as e:
            ctx.error = e
            ctx.result_status = f"upstream_4xx_{e.status}"
        except UpstreamServerError as e:
            ctx.error = e
            ctx.result_status = "upstream_5xx"
        except Exception as e:
            ctx.error = e
            ctx.result_status = "error"

    return step
