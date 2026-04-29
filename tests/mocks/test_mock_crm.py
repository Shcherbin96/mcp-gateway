import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_get_customer_requires_key():
    from mocks.crm.main import app
    c = TestClient(app)
    assert c.get("/customers/C001").status_code == 401
    r = c.get("/customers/C001", headers={"x-api-key": "dev-crm-key"})
    assert r.status_code == 200
    assert r.json()["name"] == "Иванов Иван"


def test_unknown_customer_404():
    from mocks.crm.main import app
    c = TestClient(app)
    r = c.get("/customers/XXX", headers={"x-api-key": "dev-crm-key"})
    assert r.status_code == 404
