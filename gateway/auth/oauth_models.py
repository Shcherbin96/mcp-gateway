"""OAuth-related data models."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TokenClaims:
    """Validated OAuth token claims."""

    sub: str  # agent_id
    tenant_id: UUID
    scopes: frozenset[str]
    exp: int
    iss: str
    aud: str
