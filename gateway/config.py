"""Centralized application configuration via Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MCP_", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://mcp:mcp@localhost:5432/mcp_gateway"
    database_app_user: str = "mcp_app"

    # OAuth
    oauth_issuer: str = "http://localhost:9000"
    oauth_jwks_url: str = "http://localhost:9000/jwks"
    oauth_audience: str = "mcp-gateway"

    # Approval
    approval_timeout_seconds: int = 300
    # Poll interval is the safety-net fallback for LISTEN/NOTIFY (raised from 1.0 → 5.0
    # since NOTIFY usually wakes us in ms; polling only matters during failover gaps).
    approval_poll_interval_seconds: float = 5.0

    # Rate limiting (per JWT subject / agent_id; falls back to client IP when no token).
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10  # extra capacity for short bursts

    # Telegram (optional — gateway works without it via WS-only notifications)
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None

    # Upstream services
    crm_base_url: str = "http://localhost:9001"
    crm_api_key: str = "dev-crm-key"
    payments_base_url: str = "http://localhost:9002"
    payments_api_key: str = "dev-payments-key"

    # Observability
    log_level: str = "INFO"
    otel_endpoint: str | None = None
    otel_service_name: str = "mcp-gateway"

    # Policy
    policy_file: str = "config/policies.yaml"

    # Server — bind all interfaces is intentional inside the container.
    host: str = "0.0.0.0"  # nosec B104
    port: int = 8000

    # Web admin auth (shared-secret bearer for /approvals/decide, audit, ws).
    # MVP: single shared secret + identity. Replace with SSO later.
    web_admin_token: str | None = None
    web_admin_user: str = "web-admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
