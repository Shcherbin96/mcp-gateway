from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class Condition(BaseModel):
    """Conditions evaluate against the tool's params dict.

    A list of conditions on ``ToolRule.requires_approval`` triggers approval if
    *any* condition matches (logical OR).
    """

    param: str  # e.g. "amount" — looked up in ctx.params
    op: Literal["gt", "gte", "lt", "lte", "eq", "ne"]
    value: int | float | str | bool


class ToolRule(BaseModel):
    tool: str
    # bool: legacy semantics (always requires approval if True).
    # list[Condition]: requires approval if any condition matches.
    requires_approval: bool | list[Condition] = False


class RolePolicy(BaseModel):
    name: str
    tools: list[ToolRule] = Field(default_factory=list)


class PolicyDocument(BaseModel):
    version: int = 1
    roles: list[RolePolicy]
