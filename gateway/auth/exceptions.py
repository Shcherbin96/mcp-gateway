"""Token validation exception hierarchy."""


class TokenError(Exception):
    """Base class for all token-related errors."""


class TokenExpired(TokenError):
    """Token's exp claim is in the past."""


class TokenInvalid(TokenError):
    """Token is structurally invalid, has bad signature, unsupported alg, etc."""


class TokenAudienceMismatch(TokenError):
    """Token's aud claim does not match expected audience."""


class TokenIssuerMismatch(TokenError):
    """Token's iss claim does not match expected issuer."""
