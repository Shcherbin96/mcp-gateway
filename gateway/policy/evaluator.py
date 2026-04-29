from gateway.policy.schema import Decision, PolicyDocument, ToolRule


class PolicyEvaluator:
    def __init__(self, document: PolicyDocument):
        # Build O(1) lookup: role -> tool -> ToolRule
        self._index: dict[str, dict[str, ToolRule]] = {
            role.name: {t.tool: t for t in role.tools} for role in document.roles
        }

    def evaluate(self, role: str, tool: str) -> Decision:
        role_tools = self._index.get(role)
        if role_tools is None:
            return Decision.DENY
        rule = role_tools.get(tool)
        if rule is None:
            return Decision.DENY
        return Decision.REQUIRES_APPROVAL if rule.requires_approval else Decision.ALLOW
