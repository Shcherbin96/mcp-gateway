"""Mock OAuth 2.1 IdP with Dynamic Client Registration for local dev/tests.

Key material is inlined here (rather than a sibling ``keys.py``) so the
module is self-contained — the Dockerfile copies just ``main.py`` into the
container and the import works without preserving a package layout.
"""

import json
import secrets
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel


# --- Inline key material (was mocks/idp/keys.py) ---------------------------

KID = "mock-idp-key-1"

KEY: rsa.RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PUBLIC_PEM: str = KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

PRIVATE_PEM: bytes = KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)


ISSUER = "http://localhost:9000"
DEFAULT_AUDIENCE = "mcp-gateway"


# In-memory client + agent registry
CLIENTS: dict[str, dict[str, Any]] = {}
AGENTS: dict[str, dict[str, Any]] = {}  # client_id -> agent metadata


app = FastAPI(title="Mock OAuth IdP")


@app.get("/.well-known/oauth-authorization-server")
def metadata() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "registration_endpoint": f"{ISSUER}/register",
        "jwks_uri": f"{ISSUER}/jwks",
        "response_types_supported": ["code"],
        "grant_types_supported": ["client_credentials", "authorization_code"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "scopes_supported": ["tool:*"],
    }


@app.get("/jwks")
def jwks() -> dict[str, Any]:
    raw = RSAAlgorithm.to_jwk(KEY.public_key())
    jwk = json.loads(raw) if isinstance(raw, str) else dict(raw)
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


class RegisterReq(BaseModel):
    client_name: str
    tenant_id: str
    agent_id: str | None = None
    scopes: list[str] = []
    redirect_uris: list[str] = []


@app.post("/register")
def register(req: RegisterReq) -> dict[str, Any]:
    client_id = f"client-{uuid.uuid4().hex[:12]}"
    client_secret = secrets.token_urlsafe(32)
    CLIENTS[client_id] = {
        "secret": client_secret,
        "tenant_id": req.tenant_id,
        "scopes": req.scopes,
    }
    AGENTS[client_id] = {"agent_id": req.agent_id or str(uuid.uuid4())}
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": req.redirect_uris,
        "grant_types": ["client_credentials"],
    }


@app.post("/token")
def token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form(""),
) -> dict[str, Any]:
    client = CLIENTS.get(client_id)
    if not client or client["secret"] != client_secret:
        raise HTTPException(401, "invalid_client")
    if grant_type != "client_credentials":
        raise HTTPException(400, "unsupported_grant_type")

    requested_scopes = scope.split() if scope else client["scopes"]
    granted_scopes = [s for s in requested_scopes if s in client["scopes"]] or client["scopes"]

    now = int(time.time())
    payload = {
        "sub": AGENTS[client_id]["agent_id"],
        "tenant_id": client["tenant_id"],
        "scopes": granted_scopes,
        "iat": now,
        "exp": now + 3600,
        "iss": ISSUER,
        "aud": DEFAULT_AUDIENCE,
    }
    tok = jwt.encode(payload, PRIVATE_PEM, algorithm="RS256", headers={"kid": KID})
    return {
        "access_token": tok,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": " ".join(granted_scopes),
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
