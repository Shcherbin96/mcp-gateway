"""Tool registry: maps tool names to metadata + async handlers."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from gateway.audit.redaction import IDENTITY, RedactFn


@dataclass(frozen=True)
class ToolMeta:
    name: str
    description: str
    input_schema: dict[str, Any]
    destructive: bool
    redact: RedactFn = IDENTITY


@dataclass
class RegisteredTool:
    meta: ToolMeta
    handler: Callable[..., Awaitable[dict]]


@dataclass
class ToolRegistry:
    tools: dict[str, RegisteredTool] = field(default_factory=dict)

    def register(self, meta: ToolMeta, handler: Callable[..., Awaitable[dict]]) -> None:
        self.tools[meta.name] = RegisteredTool(meta=meta, handler=handler)

    def get(self, name: str) -> RegisteredTool | None:
        return self.tools.get(name)

    def list(self) -> list[ToolMeta]:
        return [t.meta for t in self.tools.values()]
