"""Unit tests for JWKSTokenValidator."""

import base64
import json
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from gateway.auth.exceptions import TokenAudienceMismatch, TokenExpired, TokenInvalid
from gateway.auth.token_validator import JWKSTokenValidator

pytestmark = pytest.mark.unit


@pytest.fixture
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_priv, pub_pem, "test-kid"


def make_token(priv: bytes, kid: str, **overrides) -> str:
    now = int(time.time())
    payload = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "scopes": ["tool:get_customer"],
        "exp": now + 3600,
        "iat": now,
        "iss": "http://idp.test",
        "aud": "mcp-gateway",
    }
    payload.update(overrides)
    return jwt.encode(payload, priv, algorithm="RS256", headers={"kid": kid})


async def test_valid_token_parses(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(
        jwks_provider=lambda: [(kid, pub)],
        issuer="http://idp.test",
        audience="mcp-gateway",
    )
    tok = make_token(priv, kid)
    claims = await validator.verify(tok)
    assert "tool:get_customer" in claims.scopes


async def test_expired_token_rejected(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(
        jwks_provider=lambda: [(kid, pub)],
        issuer="http://idp.test",
        audience="mcp-gateway",
    )
    tok = make_token(priv, kid, exp=int(time.time()) - 10)
    with pytest.raises(TokenExpired):
        await validator.verify(tok)


async def test_wrong_audience_rejected(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(
        jwks_provider=lambda: [(kid, pub)],
        issuer="http://idp.test",
        audience="mcp-gateway",
    )
    tok = make_token(priv, kid, aud="other-app")
    with pytest.raises(TokenAudienceMismatch):
        await validator.verify(tok)


async def test_none_algorithm_rejected(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(
        jwks_provider=lambda: [(kid, pub)],
        issuer="http://idp.test",
        audience="mcp-gateway",
    )
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "x",
                    "tenant_id": "x",
                    "scopes": [],
                    "exp": 9999999999,
                    "aud": "mcp-gateway",
                    "iss": "http://idp.test",
                }
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    tok = f"{header}.{payload}."
    with pytest.raises(TokenInvalid):
        await validator.verify(tok)
