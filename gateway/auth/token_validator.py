"""JWT token validation against a JWKS provider."""

from collections.abc import Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

import jwt
from jwt import PyJWKClient

from gateway.auth.exceptions import (
    TokenAudienceMismatch,
    TokenInvalid,
    TokenIssuerMismatch,
    TokenExpired,
)
from gateway.auth.oauth_models import TokenClaims


JWKSProvider = Callable[[], Sequence[tuple[str, Any]]]


class TokenValidator(Protocol):
    async def verify(self, token: str) -> TokenClaims: ...


class JWKSTokenValidator:
    """Validates JWTs against a callable that yields (kid, public_key) pairs."""

    def __init__(self, jwks_provider: JWKSProvider, issuer: str, audience: str) -> None:
        self._jwks_provider = jwks_provider
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> TokenClaims:
        try:
            unverified = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise TokenInvalid(str(e)) from e

        if unverified.get("alg") not in ("RS256", "ES256"):
            raise TokenInvalid("unsupported algorithm")

        kid = unverified.get("kid")
        pub_key: Any = None
        for k, key in self._jwks_provider():
            if k == kid:
                pub_key = key
                break
        if pub_key is None:
            raise TokenInvalid(f"unknown kid {kid}")

        try:
            payload = jwt.decode(
                token,
                pub_key,
                algorithms=["RS256", "ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise TokenExpired(str(e)) from e
        except jwt.InvalidAudienceError as e:
            raise TokenAudienceMismatch(str(e)) from e
        except jwt.InvalidIssuerError as e:
            raise TokenIssuerMismatch(str(e)) from e
        except jwt.PyJWTError as e:
            raise TokenInvalid(str(e)) from e

        aud_claim = payload["aud"]
        return TokenClaims(
            sub=payload["sub"],
            tenant_id=UUID(payload["tenant_id"]),
            scopes=frozenset(payload.get("scopes", [])),
            exp=payload["exp"],
            iss=payload["iss"],
            aud=aud_claim if isinstance(aud_claim, str) else aud_claim[0],
        )


class HTTPJWKSProvider:
    """Production: fetches and caches JWKS from URL."""

    def __init__(self, url: str) -> None:
        self._client = PyJWKClient(url, cache_keys=True, lifespan=600)

    def __call__(self) -> list[tuple[str, Any]]:
        return [(k.key_id, k.key) for k in self._client.get_signing_keys()]
