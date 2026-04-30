"""Param-condition evaluation in PolicyEvaluator (any-match semantics)."""

import pytest

from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.schema import Condition, Decision, PolicyDocument, RolePolicy, ToolRule

pytestmark = pytest.mark.unit


@pytest.fixture
def doc_with_conditions() -> PolicyDocument:
    return PolicyDocument(
        roles=[
            RolePolicy(
                name="support_agent",
                tools=[
                    ToolRule(tool="get_customer"),
                    ToolRule(
                        tool="refund_payment",
                        requires_approval=[
                            Condition(param="amount", op="gt", value=1000),
                        ],
                    ),
                ],
            ),
        ]
    )


def test_amount_under_threshold_allows(doc_with_conditions):
    """Refund of $500 is under the gt-1000 threshold → ALLOW (no approval)."""
    e = PolicyEvaluator(doc_with_conditions)
    decision = e.evaluate("support_agent", "refund_payment", {"amount": 500})
    assert decision == Decision.ALLOW


def test_amount_over_threshold_requires_approval(doc_with_conditions):
    """Refund of $5000 trips the gt-1000 condition → REQUIRES_APPROVAL."""
    e = PolicyEvaluator(doc_with_conditions)
    decision = e.evaluate("support_agent", "refund_payment", {"amount": 5000})
    assert decision == Decision.REQUIRES_APPROVAL


def test_multiple_conditions_any_match_semantics():
    """Any matching condition triggers approval; none matching → ALLOW."""
    doc = PolicyDocument(
        roles=[
            RolePolicy(
                name="ops",
                tools=[
                    ToolRule(
                        tool="execute_query",
                        requires_approval=[
                            Condition(param="rows", op="gt", value=10000),
                            Condition(param="table", op="eq", value="users"),
                        ],
                    ),
                ],
            ),
        ]
    )
    e = PolicyEvaluator(doc)

    # Neither condition matches → ALLOW.
    assert e.evaluate("ops", "execute_query", {"rows": 5, "table": "products"}) == Decision.ALLOW
    # First matches (large rows), second doesn't → REQUIRES_APPROVAL.
    assert (
        e.evaluate("ops", "execute_query", {"rows": 50000, "table": "products"})
        == Decision.REQUIRES_APPROVAL
    )
    # Second matches (sensitive table), first doesn't → REQUIRES_APPROVAL.
    assert (
        e.evaluate("ops", "execute_query", {"rows": 5, "table": "users"})
        == Decision.REQUIRES_APPROVAL
    )


def test_missing_param_does_not_match():
    """A condition cannot match when the param is absent → ALLOW."""
    doc = PolicyDocument(
        roles=[
            RolePolicy(
                name="r",
                tools=[
                    ToolRule(
                        tool="t",
                        requires_approval=[Condition(param="amount", op="gt", value=10)],
                    )
                ],
            ),
        ]
    )
    e = PolicyEvaluator(doc)
    assert e.evaluate("r", "t", {}) == Decision.ALLOW
    assert e.evaluate("r", "t", None) == Decision.ALLOW


def test_legacy_bool_true_still_requires_approval():
    """Backward compatibility: bare ``requires_approval: true`` still works."""
    doc = PolicyDocument(
        roles=[
            RolePolicy(
                name="r",
                tools=[ToolRule(tool="t", requires_approval=True)],
            )
        ]
    )
    e = PolicyEvaluator(doc)
    assert e.evaluate("r", "t", {"amount": 0}) == Decision.REQUIRES_APPROVAL
    assert e.evaluate("r", "t", None) == Decision.REQUIRES_APPROVAL


def test_incompatible_type_comparison_does_not_crash():
    """Comparing str to int with `gt` must not raise — treated as no match."""
    doc = PolicyDocument(
        roles=[
            RolePolicy(
                name="r",
                tools=[
                    ToolRule(
                        tool="t",
                        requires_approval=[Condition(param="x", op="gt", value=10)],
                    )
                ],
            ),
        ]
    )
    e = PolicyEvaluator(doc)
    # str > int raises TypeError in Python 3; evaluator must swallow it.
    assert e.evaluate("r", "t", {"x": "not-a-number"}) == Decision.ALLOW
