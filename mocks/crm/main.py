import os

from fastapi import FastAPI, Header, HTTPException

API_KEY = os.environ.get("MOCK_CRM_API_KEY", "dev-crm-key")

CUSTOMERS = {
    "C001": {
        "id": "C001",
        "name": "Иванов Иван",
        "email": "ivanov@example.com",
        "balance": 12500.0,
        "tier": "gold",
    },
    "C002": {
        "id": "C002",
        "name": "Петров Пётр",
        "email": "petrov@example.com",
        "balance": 0.0,
        "tier": "standard",
    },
    "C003": {
        "id": "C003",
        "name": "Сидорова Анна",
        "email": "sidorova@example.com",
        "balance": 4980.0,
        "tier": "silver",
    },
    "C004": {
        "id": "C004",
        "name": "Кузнецов Дмитрий",
        "email": "kuznetsov@example.com",
        "balance": 89500.0,
        "tier": "platinum",
    },
    "C005": {
        "id": "C005",
        "name": "Морозова Елена",
        "email": "morozova@example.com",
        "balance": 250.0,
        "tier": "standard",
    },
    "C006": {
        "id": "C006",
        "name": "Smith John",
        "email": "j.smith@example.com",
        "balance": 33200.0,
        "tier": "gold",
    },
}
ORDERS = {
    "O1234": {
        "id": "O1234",
        "customer_id": "C001",
        "amount": 50000.0,
        "status": "completed",
        "items": ["Premium subscription, 12 mo"],
    },
    "O1235": {
        "id": "O1235",
        "customer_id": "C002",
        "amount": 1200.0,
        "status": "pending",
        "items": ["Trial activation"],
    },
    "O1236": {
        "id": "O1236",
        "customer_id": "C003",
        "amount": 7800.0,
        "status": "completed",
        "items": ["Hardware bundle"],
    },
    "O1237": {
        "id": "O1237",
        "customer_id": "C004",
        "amount": 145000.0,
        "status": "completed",
        "items": ["Enterprise license, 24 mo", "Onboarding"],
    },
    "O1238": {
        "id": "O1238",
        "customer_id": "C001",
        "amount": 350.0,
        "status": "shipped",
        "items": ["Add-on: SSO module"],
    },
    "O1239": {
        "id": "O1239",
        "customer_id": "C006",
        "amount": 24500.0,
        "status": "pending",
        "items": ["Annual renewal"],
    },
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
