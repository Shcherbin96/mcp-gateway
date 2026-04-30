import os
import random
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

API_KEY = os.environ.get("MOCK_PAYMENTS_API_KEY", "dev-payments-key")
FAILURE_RATE = float(os.environ.get("MOCK_PAYMENTS_FAILURE_RATE", "0"))  # for testing retries

PAYMENTS: dict[str, dict] = {}


app = FastAPI(title="Mock Payments")


def auth(x_api_key: str | None):
    if x_api_key != API_KEY:
        raise HTTPException(401, "invalid_api_key")


def maybe_fail():
    # Non-cryptographic: only used to inject synthetic transient failures in
    # the mock service for retry/backoff tests.
    if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:  # noqa: S311
        raise HTTPException(503, "transient_failure")


class RefundRequest(BaseModel):
    customer_id: str
    amount: float
    reason: str | None = None


@app.post("/refunds")
def refund(
    req: RefundRequest,
    x_api_key: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
):
    auth(x_api_key)
    maybe_fail()
    key = idempotency_key or str(uuid.uuid4())
    if key in PAYMENTS:
        return PAYMENTS[key]
    pid = f"P-{uuid.uuid4().hex[:10]}"
    rec = {
        "id": pid,
        "customer_id": req.customer_id,
        "amount": req.amount,
        "type": "refund",
        "status": "completed",
        "reason": req.reason,
        "created_at": datetime.now(UTC).isoformat(),
    }
    PAYMENTS[key] = rec
    return rec


class ChargeRequest(BaseModel):
    card_number: str
    amount: float
    customer_id: str | None = None


@app.post("/charges")
def charge(
    req: ChargeRequest,
    x_api_key: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
):
    auth(x_api_key)
    maybe_fail()
    key = idempotency_key or str(uuid.uuid4())
    if key in PAYMENTS:
        return PAYMENTS[key]
    pid = f"P-{uuid.uuid4().hex[:10]}"
    rec = {
        "id": pid,
        "customer_id": req.customer_id,
        "amount": req.amount,
        "type": "charge",
        "status": "completed",
        "card_last4": req.card_number[-4:] if len(req.card_number) >= 4 else "****",
        "created_at": datetime.now(UTC).isoformat(),
    }
    PAYMENTS[key] = rec
    return rec


@app.get("/healthz")
def hz():
    return {"ok": True}
