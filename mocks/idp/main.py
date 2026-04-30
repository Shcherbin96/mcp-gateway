"""Mock OAuth 2.1 IdP with Dynamic Client Registration for local dev/tests.

Key material is inlined here (rather than a sibling ``keys.py``) so the
module is self-contained — the Dockerfile copies just ``main.py`` into the
container and the import works without preserving a package layout.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

# --- Inline key material (was mocks/idp/keys.py) ---------------------------

KID = "mock-idp-key-1"

KEY: rsa.RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PUBLIC_PEM: str = (
    KEY.public_key()
    .public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)

PRIVATE_PEM: bytes = KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)


ISSUER = os.environ.get("MOCK_IDP_ISSUER", "http://localhost:9000")
DEFAULT_AUDIENCE = os.environ.get("MOCK_IDP_AUDIENCE", "mcp-gateway")


# Hardcoded users for the mock authorization_code flow. Real backends would
# look these up in a directory; here we just want deterministic test fixtures.
USERS: dict[str, dict[str, str]] = {
    "alice": {
        "password": "wonderland",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "role": "support_agent",
    },
    "bob": {
        "password": "thebuilder",
        "tenant_id": "00000000-0000-0000-0000-000000000002",
        "role": "finance_admin",
    },
}


# In-memory client + agent registry
CLIENTS: dict[str, dict[str, Any]] = {}
AGENTS: dict[str, dict[str, Any]] = {}  # client_id -> agent metadata

# In-memory authorization code store. Each entry is single-use and pops on
# token exchange.
AUTH_CODES: dict[str, dict[str, Any]] = {}

AUTH_CODE_TTL_SECONDS = 600  # 10 minutes


app = FastAPI(title="Mock OAuth IdP")


# --- HTML login form -------------------------------------------------------

LOGIN_FORM_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Mock IdP — Sign in</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 380px;
        margin: 4rem auto; padding: 0 1rem; color: #222; }}
 h1 {{ font-size: 1.25rem; }}
 label {{ display: block; margin-top: 0.75rem; font-size: 0.9rem; }}
 input[type=text], input[type=password] {{ width: 100%; padding: 0.5rem;
        font-size: 1rem; box-sizing: border-box; }}
 button {{ margin-top: 1rem; padding: 0.6rem 1.2rem; font-size: 1rem;
          background: #2b6cb0; color: white; border: 0; border-radius: 4px;
          cursor: pointer; }}
 .error {{ color: #b00020; margin-top: 0.75rem; font-size: 0.9rem; }}
 .hint {{ color: #666; margin-top: 1.5rem; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>Mock IdP — Sign in</h1>
<form method="post" action="/authorize">
 <label>Username <input type="text" name="username" autofocus required></label>
 <label>Password <input type="password" name="password" required></label>
 {hidden_inputs}
 {error_block}
 <button type="submit">Sign in</button>
</form>
<p class="hint">Try <code>alice / wonderland</code> or <code>bob / thebuilder</code>.</p>
</body>
</html>
"""


def _render_login_form(params: dict[str, str], error: str | None = None) -> str:
    """Render the login HTML with hidden OAuth params and optional error."""
    hidden = "\n ".join(
        f'<input type="hidden" name="{_html_escape(k)}" value="{_html_escape(v)}">'
        for k, v in params.items()
    )
    error_block = f'<div class="error">{_html_escape(error)}</div>' if error else ""
    return LOGIN_FORM_TEMPLATE.format(hidden_inputs=hidden, error_block=error_block)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# --- Standard endpoints ----------------------------------------------------


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
        "code_challenge_methods_supported": ["S256"],
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
        "redirect_uris": list(req.redirect_uris),
    }
    AGENTS[client_id] = {"agent_id": req.agent_id or str(uuid.uuid4())}
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": req.redirect_uris,
        "grant_types": ["client_credentials", "authorization_code"],
    }


# --- Authorization code flow (OAuth 2.1 + PKCE) ----------------------------


def _validate_authorize_params(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> dict[str, Any]:
    """Validate /authorize query params; raise HTTPException(400) on failure.

    Returns the resolved client record on success.
    """
    if response_type != "code":
        raise HTTPException(400, {"error": "unsupported_response_type"})
    client = CLIENTS.get(client_id)
    if client is None:
        raise HTTPException(400, {"error": "invalid_client", "detail": "unknown client_id"})
    registered = client.get("redirect_uris") or []
    if redirect_uri not in registered:
        raise HTTPException(
            400,
            {"error": "invalid_request", "detail": "redirect_uri not registered"},
        )
    if not code_challenge:
        raise HTTPException(
            400,
            {"error": "invalid_request", "detail": "code_challenge required (PKCE)"},
        )
    if code_challenge_method != "S256":
        raise HTTPException(
            400,
            {"error": "invalid_request", "detail": "code_challenge_method must be S256"},
        )
    return client


@app.get("/authorize", response_class=HTMLResponse)
def authorize_get(
    response_type: str = "",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
) -> HTMLResponse:
    _validate_authorize_params(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge or None,
        code_challenge_method=code_challenge_method or None,
    )
    params = {
        "response_type": response_type,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }
    return HTMLResponse(_render_login_form(params))


@app.post("/authorize")
async def authorize_post(request: Request) -> Any:
    form = await request.form()

    def _f(name: str) -> str:
        v = form.get(name, "")
        return v if isinstance(v, str) else ""

    response_type = _f("response_type")
    client_id = _f("client_id")
    redirect_uri = _f("redirect_uri")
    scope = _f("scope")
    state = _f("state")
    code_challenge = _f("code_challenge")
    code_challenge_method = _f("code_challenge_method")
    username = _f("username")
    password = _f("password")

    _validate_authorize_params(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge or None,
        code_challenge_method=code_challenge_method or None,
    )

    user = USERS.get(username)
    if user is None or user["password"] != password:
        params = {
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        html = _render_login_form(params, error="Invalid username or password")
        return HTMLResponse(html, status_code=401)

    auth_code = secrets.token_urlsafe(32)
    AUTH_CODES[auth_code] = {
        "expires_at": int(time.time()) + AUTH_CODE_TTL_SECONDS,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "username": username,
        "scopes": scope.split() if scope else [],
    }

    redirect_qs = urlencode({"code": auth_code, "state": state} if state else {"code": auth_code})
    return RedirectResponse(url=f"{redirect_uri}?{redirect_qs}", status_code=302)


# --- Token endpoint --------------------------------------------------------


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, code_challenge)


def _issue_token(*, sub: str, tenant_id: str, scopes: list[str]) -> dict[str, Any]:
    now = int(time.time())
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "scopes": scopes,
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
        "scope": " ".join(scopes),
    }


@app.post("/token")
def token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(""),
    scope: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    code_verifier: str = Form(""),
) -> dict[str, Any]:
    client = CLIENTS.get(client_id)
    if not client:
        raise HTTPException(401, "invalid_client")

    if grant_type == "client_credentials":
        if client["secret"] != client_secret:
            raise HTTPException(401, "invalid_client")
        requested_scopes = scope.split() if scope else client["scopes"]
        granted_scopes = [s for s in requested_scopes if s in client["scopes"]] or client["scopes"]
        return _issue_token(
            sub=AGENTS[client_id]["agent_id"],
            tenant_id=client["tenant_id"],
            scopes=granted_scopes,
        )

    if grant_type == "authorization_code":
        # Confidential clients still authenticate; allow either basic or post.
        if client["secret"] != client_secret:
            raise HTTPException(401, "invalid_client")
        if not code:
            raise HTTPException(400, "invalid_request: code required")
        record = AUTH_CODES.pop(code, None)
        if record is None:
            raise HTTPException(400, "invalid_grant: unknown or already-used code")
        if record["expires_at"] < int(time.time()):
            raise HTTPException(400, "invalid_grant: code expired")
        if record["client_id"] != client_id:
            raise HTTPException(400, "invalid_grant: client_id mismatch")
        if record["redirect_uri"] != redirect_uri:
            raise HTTPException(400, "invalid_grant: redirect_uri mismatch")
        if not code_verifier or not _verify_pkce(code_verifier, record["code_challenge"]):
            raise HTTPException(400, "invalid_grant: PKCE verification failed")

        user = USERS[record["username"]]
        scopes = list(record["scopes"]) + [f"role:{user['role']}"]
        return _issue_token(
            sub=record["username"],
            tenant_id=user["tenant_id"],
            scopes=scopes,
        )

    raise HTTPException(400, "unsupported_grant_type")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
