import pytest

from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.schema import Decision, PolicyDocument, RolePolicy, ToolRule

pytestmark = pytest.mark.unit


@pytest.fixture
def doc():
    return PolicyDocument(
        roles=[
            RolePolicy(
                name="support",
                tools=[
                    ToolRule(tool="get_customer"),
                    ToolRule(tool="refund_payment", requires_approval=True),
                ],
            ),
            RolePolicy(name="readonly", tools=[ToolRule(tool="get_customer")]),
        ]
    )


def test_allow_for_permitted_tool(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("support", "get_customer") == Decision.ALLOW


def test_requires_approval(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("support", "refund_payment") == Decision.REQUIRES_APPROVAL


def test_deny_unknown_tool(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("support", "delete_everything") == Decision.DENY


def test_deny_unknown_role(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("admin", "get_customer") == Decision.DENY


def test_deny_for_role_without_tool(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("readonly", "refund_payment") == Decision.DENY
