import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_refund_idempotent():
    from mocks.payments.main import app
    c = TestClient(app)
    h = {"x-api-key": "dev-payments-key", "idempotency-key": "key-1"}
    r1 = c.post("/refunds", json={"customer_id": "C001", "amount": 100}, headers=h)
    r2 = c.post("/refunds", json={"customer_id": "C001", "amount": 999}, headers=h)
    assert r1.json() == r2.json()
