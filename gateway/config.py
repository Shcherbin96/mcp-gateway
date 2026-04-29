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
    approval_poll_interval_seconds: float = 1.0

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

    # Server
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
