from __future__ import annotations

from typing import Any

from gateway.policy.schema import Condition, Decision, PolicyDocument, ToolRule

_OPS: dict[str, Any] = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def _condition_matches(cond: Condition, params: dict | None) -> bool:
    if not params or cond.param not in params:
        return False
    actual = params[cond.param]
    op = _OPS.get(cond.op)
    if op is None:
        return False
    try:
        return bool(op(actual, cond.value))
    except TypeError:
        # Comparing incompatible types (e.g. str vs int with `gt`) — treat
        # as no match rather than crashing the gateway on bad params.
        return False


class PolicyEvaluator:
    def __init__(self, document: PolicyDocument):
        # Build O(1) lookup: role -> tool -> ToolRule
        self._index: dict[str, dict[str, ToolRule]] = {
            role.name: {t.tool: t for t in role.tools} for role in document.roles
        }

    def evaluate(self, role: str, tool: str, params: dict | None = None) -> Decision:
        role_tools = self._index.get(role)
        if role_tools is None:
            return Decision.DENY
        rule = role_tools.get(tool)
        if rule is None:
            return Decision.DENY

        ra = rule.requires_approval
        if ra is True:
            return Decision.REQUIRES_APPROVAL
        if ra is False:
            return Decision.ALLOW
        # ra is a list[Condition]: any-match → REQUIRES_APPROVAL, else ALLOW.
        for cond in ra:
            if _condition_matches(cond, params):
                return Decision.REQUIRES_APPROVAL
        return Decision.ALLOW
