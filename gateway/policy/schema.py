from enum import Enum

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class ToolRule(BaseModel):
    tool: str
    requires_approval: bool = False


class RolePolicy(BaseModel):
    name: str
    tools: list[ToolRule] = Field(default_factory=list)


class PolicyDocument(BaseModel):
    version: int = 1
    roles: list[RolePolicy]
