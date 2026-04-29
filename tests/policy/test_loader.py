from pathlib import Path

import pytest

from gateway.policy.loader import load_policies

pytestmark = pytest.mark.unit


def test_loads_yaml(tmp_path: Path):
    p = tmp_path / "p.yaml"
    p.write_text(
        """
version: 1
roles:
  - name: support
    tools:
      - tool: get_customer
      - tool: refund_payment
        requires_approval: true
"""
    )
    doc = load_policies(p)
    assert len(doc.roles) == 1
    assert doc.roles[0].tools[1].requires_approval is True
