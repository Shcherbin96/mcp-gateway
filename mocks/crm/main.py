import os
from fastapi import FastAPI, HTTPException, Header

API_KEY = os.environ.get("MOCK_CRM_API_KEY", "dev-crm-key")

CUSTOMERS = {
    "C001": {"id": "C001", "name": "Иванов Иван", "email": "ivanov@example.com", "balance": 12500.0},
    "C002": {"id": "C002", "name": "Петров Петр", "email": "petrov@example.com", "balance": 0.0},
    "C003": {"id": "C003", "name": "Сидорова Анна", "email": "sidorova@example.com", "balance": 4980.0},
}
ORDERS = {
    "O1234": {"id": "O1234", "customer_id": "C001", "amount": 50000.0, "status": "completed"},
    "O1235": {"id": "O1235", "customer_id": "C002", "amount": 1200.0, "status": "pending"},
}

app = FastAPI(title="Mock CRM")


def auth(x_api_key: str | None):
    if x_api_key != API_KEY:
        raise HTTPException(401, "invalid_api_key")


@app.get("/customers/{cid}")
def get_customer(cid: str, x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    c = CUSTOMERS.get(cid)
    if not c:
        raise HTTPException(404, "not_found")
    return c


@app.get("/orders")
def list_orders(customer_id: str, x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    return {"orders": [o for o in ORDERS.values() if o["customer_id"] == customer_id]}


@app.patch("/orders/{oid}")
def update_order(oid: str, body: dict, x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    if oid not in ORDERS:
        raise HTTPException(404, "not_found")
    ORDERS[oid].update({k: v for k, v in body.items() if k in ("status",)})
    return ORDERS[oid]


@app.get("/healthz")
def hz():
    return {"ok": True}
