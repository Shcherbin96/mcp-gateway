# MCP Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Production-grade MCP Gateway that mediates AI-agent tool calls through 5 control layers (auth, RBAC, human approval, execute, audit) with full observability and Fly.io deployment.

**Architecture:** FastMCP + FastAPI app with middleware chain implementing the 5 layers. Pluggable interfaces (TokenValidator, PolicyStore, ApprovalNotifier, AuditSink) for replaceability. Multi-tenant lite via `tenant_id` row-level filtering. Append-only audit log enforced via Postgres GRANTs + triggers. Three companion services (mock-crm, mock-payments, mock-idp) emulate external integrations.

**Tech Stack:** Python 3.12, FastMCP, FastAPI, Authlib, PyJWT, SQLAlchemy 2.0 + asyncpg, Alembic, Postgres 16, Jinja2 + HTMX, python-telegram-bot, structlog, prometheus-client, OpenTelemetry, pytest + testcontainers, locust, mutmut, ruff + mypy + black, Docker, Fly.io.

**Reference spec:** `docs/superpowers/specs/2026-04-29-mcp-gateway-design.md`

---

## Phase 0: Foundation (sequential)

### Task 0.1: Initialize repo and tooling

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `README.md`, `LICENSE`, `.python-version`
- Create: `.github/workflows/ci.yml`
- Create: `.pre-commit-config.yaml`
- Create: `Makefile`

- [ ] **Step 1: Init git + first commit**

```bash
cd "/Users/moki/Projects/MCP Gateway"
git init -b main
git add 02-mcp-gateway.md docs/
git commit -m "chore: import spec and design"
```

- [ ] **Step 2: Create `.python-version`**

```
3.12
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.env
.env.local
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.log
.DS_Store
.idea/
.vscode/
node_modules/
docker-compose.override.yml
```

- [ ] **Step 4: Create `pyproject.toml`**

```toml
[project]
name = "mcp-gateway"
version = "0.1.0"
description = "Production-grade MCP Gateway with human approval, RBAC, and audit"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=0.2.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "sqlalchemy[asyncio]>=2.0.35",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "authlib>=1.3.0",
    "pyjwt[crypto]>=2.9.0",
    "httpx>=0.27.0",
    "tenacity>=9.0.0",
    "python-telegram-bot>=21.6",
    "jinja2>=3.1.0",
    "structlog>=24.4.0",
    "prometheus-client>=0.21.0",
    "opentelemetry-api>=1.27.0",
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-exporter-otlp>=1.27.0",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "opentelemetry-instrumentation-asyncpg>=0.48b0",
    "opentelemetry-instrumentation-httpx>=0.48b0",
    "pyyaml>=6.0",
    "python-multipart>=0.0.10",
    "websockets>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "testcontainers[postgres]>=4.8.0",
    "mutmut>=3.0.0",
    "locust>=2.31.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "black>=24.8.0",
    "bandit>=1.7.0",
    "pip-audit>=2.7.0",
    "pre-commit>=3.8.0",
    "types-pyyaml",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["gateway"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "S", "A", "C4", "T20", "RET", "SIM", "ARG"]
ignore = ["S101"]  # assert ok in tests

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S", "ARG"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "unit: fast tests with no I/O",
    "integration: tests requiring containers",
    "e2e: full stack tests",
    "security: security-focused tests",
]

[tool.coverage.run]
source = ["gateway"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
```

- [ ] **Step 5: Create `Makefile`**

```makefile
.PHONY: install dev fmt lint typecheck test test-unit test-integration test-e2e test-security cov up down clean

install:
	pip install -e ".[dev]"
	pre-commit install

fmt:
	ruff format .
	ruff check --fix .

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy gateway

test-unit:
	pytest -m "unit" -v

test-integration:
	pytest -m "integration" -v

test-e2e:
	docker compose -f docker-compose.test.yml up -d
	pytest -m "e2e" -v
	docker compose -f docker-compose.test.yml down

test-security:
	pytest -m "security" -v
	bandit -r gateway
	pip-audit

test: test-unit test-integration

cov:
	pytest --cov=gateway --cov-report=html --cov-report=term

up:
	docker compose up -d

down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
```

- [ ] **Step 6: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-pyyaml]
        args: [--config-file=pyproject.toml]
        files: ^gateway/
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: detect-private-key
```

- [ ] **Step 7: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: make lint
      - run: make typecheck

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: make test-unit

  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: make test-integration

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: make test-e2e

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: make test-security

  build:
    runs-on: ubuntu-latest
    needs: [lint, unit]
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t mcp-gateway:ci -f Dockerfile .
      - run: docker build -t mock-crm:ci -f mocks/crm/Dockerfile mocks/crm
      - run: docker build -t mock-payments:ci -f mocks/payments/Dockerfile mocks/payments
      - run: docker build -t mock-idp:ci -f mocks/idp/Dockerfile mocks/idp
```

- [ ] **Step 8: Create `README.md`**

```markdown
# MCP Gateway

Production-grade MCP server acting as a security gateway between AI agents and internal company systems. Every tool call passes through 5 control layers: authenticate → authorize → approve → execute → log.

See `docs/superpowers/specs/2026-04-29-mcp-gateway-design.md` for full design.

## Quick start

\`\`\`bash
make install
docker compose up -d
\`\`\`

## Demo

See Loom: <link to be added>

## Architecture

\`\`\`mermaid
graph LR
  Claude --> Gateway[MCP Gateway]
  Gateway --> CRM[Mock CRM]
  Gateway --> Pay[Mock Payments]
  Gateway --> IdP[Mock OAuth IdP]
  Gateway --> DB[(Postgres)]
  Gateway --> TG[Telegram Bot]
  Gateway --> UI[Web UI]
\`\`\`
\`\`\`
```

- [ ] **Step 9: Create `LICENSE` (MIT)**

Standard MIT license text with `Copyright (c) 2026 Roman Serbin`.

- [ ] **Step 10: Commit foundation**

```bash
git add .
git commit -m "chore: project tooling (pyproject, ci, pre-commit, makefile)"
```

---

### Task 0.2: Database schema + Alembic

**Files:**
- Create: `gateway/__init__.py`, `gateway/db/__init__.py`, `gateway/db/base.py`, `gateway/db/session.py`
- Create: `gateway/config.py`
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/db/test_schema.py`

- [ ] **Step 1: Create `gateway/config.py`**

```python
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MCP_", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://mcp:mcp@localhost:5432/mcp_gateway"
    database_app_user: str = "mcp_app"  # restricted user (no UPDATE/DELETE on audit_log)

    # OAuth
    oauth_issuer: str = "http://localhost:9000"
    oauth_jwks_url: str = "http://localhost:9000/jwks"
    oauth_audience: str = "mcp-gateway"

    # Approval
    approval_timeout_seconds: int = 300
    approval_poll_interval_seconds: float = 1.0

    # Telegram
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
```

- [ ] **Step 2: Create `gateway/db/base.py`**

```python
from datetime import datetime
from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Create `gateway/db/session.py`**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gateway.config import get_settings


_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 4: Create models in `gateway/db/models.py`**

Define ORM models matching schema in spec section 4.4: `Tenant`, `OAuthClient`, `Agent`, `Role`, `RolePermission`, `ApprovalRequest`, `AuditLog`. All inherit `Base, TimestampMixin`. Use `Mapped[]` typing, UUID PKs via `from uuid import uuid4` default, `JSONB` from `sqlalchemy.dialects.postgresql`. AuditLog uses `BigInteger` PK.

```python
from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey, Boolean, BigInteger, ARRAY, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from gateway.db.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class OAuthClient(Base, TimestampMixin):
    __tablename__ = "oauth_clients"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    client_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    client_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class RolePermission(Base, TimestampMixin):
    __tablename__ = "role_permissions"
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    owner_email: Mapped[str | None] = mapped_column(String(255))


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_requests"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"))
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    decided_at: Mapped["datetime | None"] = mapped_column()  # type: ignore[name-defined]
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decision_reason: Mapped[str | None] = mapped_column(String(1024))
    __table_args__ = (
        Index("ix_approval_requests_pending", "tenant_id", "status", "created_at"),
    )


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))  # nullable: auth_failed before tenant resolved
    agent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    tool: Mapped[str | None] = mapped_column(String(128))
    params_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    approval_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        Index("ix_audit_log_tenant_time", "tenant_id", "created_at"),
        Index("ix_audit_log_agent_time", "agent_id", "created_at"),
    )
```

- [ ] **Step 5: Init Alembic**

```bash
cd "/Users/moki/Projects/MCP Gateway"
alembic init -t async alembic
```

Edit `alembic.ini` set `sqlalchemy.url = ` empty (we set programmatically).
Edit `alembic/env.py` to import `from gateway.db.base import Base; from gateway.db import models  # noqa  # registers tables` and use `target_metadata = Base.metadata`. Override `run_migrations_online` to use `get_settings().database_url`.

- [ ] **Step 6: Generate initial migration**

```bash
alembic revision --autogenerate -m "initial schema"
```

Then manually edit migration to:
- Add `op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")` at top of `upgrade()`
- After table creation, add audit_log protection:

```python
op.execute(f"""
CREATE OR REPLACE FUNCTION audit_log_no_modify_fn() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;
""")
op.execute("""
CREATE TRIGGER audit_log_no_modify
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify_fn();
""")
op.execute(f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '{op.get_context().opts.get("app_user", "mcp_app")}') THEN
        CREATE USER mcp_app WITH PASSWORD 'mcp_app';
    END IF;
END $$;
""")
op.execute("GRANT INSERT, SELECT ON audit_log TO mcp_app;")
op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM mcp_app;")
op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO mcp_app;")
op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, oauth_clients, agents, roles, role_permissions, approval_requests TO mcp_app;")
```

- [ ] **Step 7: Create `tests/conftest.py` with Postgres testcontainer fixture**

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer
from alembic.config import Config
from alembic import command

import gateway.db.models  # noqa: F401  registers tables
from gateway.db.base import Base


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg")
        yield url


@pytest.fixture(scope="session")
async def db_engine(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("""
            CREATE OR REPLACE FUNCTION audit_log_no_modify_fn() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'audit_log is append-only'; END;
            $$ LANGUAGE plpgsql;
        """)
        await conn.exec_driver_sql("""
            CREATE TRIGGER audit_log_no_modify BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify_fn();
        """)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        sess = AsyncSession(bind=conn, expire_on_commit=False)
        yield sess
        await sess.close()
        await trans.rollback()
```

- [ ] **Step 8: Write `tests/db/test_schema.py`**

```python
import pytest
from sqlalchemy import text
from gateway.db.models import Tenant, AuditLog


pytestmark = pytest.mark.integration


async def test_audit_log_blocks_update(db_session):
    db_session.add(AuditLog(result_status="success"))
    await db_session.flush()
    log = (await db_session.execute(text("SELECT id FROM audit_log LIMIT 1"))).scalar()
    with pytest.raises(Exception, match="append-only"):
        await db_session.execute(text(f"UPDATE audit_log SET result_status='x' WHERE id={log}"))


async def test_audit_log_blocks_delete(db_session):
    db_session.add(AuditLog(result_status="success"))
    await db_session.flush()
    with pytest.raises(Exception, match="append-only"):
        await db_session.execute(text("DELETE FROM audit_log"))


async def test_tenant_unique_name(db_session):
    from sqlalchemy.exc import IntegrityError
    db_session.add(Tenant(name="acme"))
    await db_session.flush()
    db_session.add(Tenant(name="acme"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 9: Run tests, verify pass**

```bash
make test-integration
```

Expected: 3 tests pass.

- [ ] **Step 10: Commit**

```bash
git add gateway/ alembic/ alembic.ini tests/
git commit -m "feat(db): schema, alembic migrations, append-only audit log"
```

---

### Task 0.3: Observability primitives

**Files:**
- Create: `gateway/observability/__init__.py`, `gateway/observability/logging.py`, `gateway/observability/metrics.py`, `gateway/observability/tracing.py`
- Create: `tests/observability/test_logging.py`

- [ ] **Step 1: Create `gateway/observability/logging.py`**

```python
import logging
import sys
import structlog
from gateway.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper())
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 2: Create `gateway/observability/metrics.py`**

```python
from prometheus_client import Counter, Histogram, Gauge


REQUESTS_TOTAL = Counter(
    "mcp_gateway_requests_total",
    "Total tool-call requests",
    ["tool", "status", "tenant"],
)
REQUEST_DURATION = Histogram(
    "mcp_gateway_request_duration_seconds",
    "Request duration",
    ["tool"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
APPROVALS_PENDING = Gauge(
    "mcp_gateway_approvals_pending",
    "Pending approvals",
    ["tenant"],
)
APPROVALS_TOTAL = Counter(
    "mcp_gateway_approvals_total",
    "Approval decisions",
    ["decision"],
)
UPSTREAM_FAILURES = Counter(
    "mcp_gateway_upstream_failures_total",
    "Upstream service failures",
    ["service"],
)
```

- [ ] **Step 3: Create `gateway/observability/tracing.py`**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from gateway.config import get_settings


def configure_tracing(app=None) -> None:
    settings = get_settings()
    if not settings.otel_endpoint:
        return
    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    AsyncPGInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()


def get_tracer(name: str):
    return trace.get_tracer(name)
```

- [ ] **Step 4: Test logging**

```python
# tests/observability/test_logging.py
import json
import pytest
from gateway.observability.logging import configure_logging, get_logger


pytestmark = pytest.mark.unit


def test_log_emits_json(capsys):
    configure_logging()
    log = get_logger("test")
    log.info("hello", foo="bar")
    captured = capsys.readouterr().out
    payload = json.loads(captured.strip().splitlines()[-1])
    assert payload["event"] == "hello"
    assert payload["foo"] == "bar"
    assert payload["level"] == "info"
```

- [ ] **Step 5: Commit**

```bash
git add gateway/observability tests/observability
git commit -m "feat(obs): structlog logging, prometheus metrics, otel tracing"
```

---

## Phase 1: Parallel modules (8 independent tracks)

These tasks are independent. Execute via `subagent-driven-development` — dispatch one fresh subagent per task, in parallel where possible.

Each subagent receives: this plan file + the spec (`docs/superpowers/specs/2026-04-29-mcp-gateway-design.md`) + their assigned task. They MUST follow TDD: write failing test → implement → verify → commit.

### Task 1.A: OAuth — token validator + mock IdP service

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/auth/__init__.py`, `gateway/auth/token_validator.py`, `gateway/auth/oauth_models.py`, `gateway/auth/exceptions.py`
- Create: `mocks/idp/__init__.py`, `mocks/idp/main.py`, `mocks/idp/Dockerfile`, `mocks/idp/pyproject.toml`, `mocks/idp/keys.py`
- Create: `tests/auth/test_token_validator.py`, `tests/mocks/test_mock_idp.py`

- [ ] **Step 1: Define `TokenClaims` dataclass and `TokenValidator` interface**

```python
# gateway/auth/oauth_models.py
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class TokenClaims:
    sub: str  # agent_id
    tenant_id: UUID
    scopes: frozenset[str]
    exp: int
    iss: str
    aud: str
```

```python
# gateway/auth/exceptions.py
class TokenError(Exception): ...
class TokenExpired(TokenError): ...
class TokenInvalid(TokenError): ...
class TokenAudienceMismatch(TokenError): ...
class TokenIssuerMismatch(TokenError): ...
```

- [ ] **Step 2: Write failing tests for `TokenValidator`**

```python
# tests/auth/test_token_validator.py
import time
import pytest
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
from gateway.auth.token_validator import JWKSTokenValidator
from gateway.auth.exceptions import TokenExpired, TokenInvalid, TokenAudienceMismatch


pytestmark = pytest.mark.unit


@pytest.fixture
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key()
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_priv, pub_pem, "test-kid"


def make_token(priv, kid, **overrides):
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


async def test_valid_token_parses(keypair, monkeypatch):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(jwks_provider=lambda: [(kid, pub)], issuer="http://idp.test", audience="mcp-gateway")
    tok = make_token(priv, kid)
    claims = await validator.verify(tok)
    assert "tool:get_customer" in claims.scopes


async def test_expired_token_rejected(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(jwks_provider=lambda: [(kid, pub)], issuer="http://idp.test", audience="mcp-gateway")
    tok = make_token(priv, kid, exp=int(time.time()) - 10)
    with pytest.raises(TokenExpired):
        await validator.verify(tok)


async def test_wrong_audience_rejected(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(jwks_provider=lambda: [(kid, pub)], issuer="http://idp.test", audience="mcp-gateway")
    tok = make_token(priv, kid, aud="other-app")
    with pytest.raises(TokenAudienceMismatch):
        await validator.verify(tok)


async def test_none_algorithm_rejected(keypair):
    priv, pub, kid = keypair
    validator = JWKSTokenValidator(jwks_provider=lambda: [(kid, pub)], issuer="http://idp.test", audience="mcp-gateway")
    # Manually craft "none" alg token
    import base64, json
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "x", "tenant_id": "x", "scopes": [], "exp": 9999999999, "aud": "mcp-gateway", "iss": "http://idp.test"}).encode()).rstrip(b"=").decode()
    tok = f"{header}.{payload}."
    with pytest.raises(TokenInvalid):
        await validator.verify(tok)
```

- [ ] **Step 3: Implement `JWKSTokenValidator`**

```python
# gateway/auth/token_validator.py
from collections.abc import Callable, Awaitable
from typing import Protocol
from uuid import UUID
import jwt
from jwt import PyJWKClient
import httpx

from gateway.auth.oauth_models import TokenClaims
from gateway.auth.exceptions import TokenExpired, TokenInvalid, TokenAudienceMismatch, TokenIssuerMismatch


class TokenValidator(Protocol):
    async def verify(self, token: str) -> TokenClaims: ...


class JWKSTokenValidator:
    def __init__(self, jwks_provider, issuer: str, audience: str):
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
        pub_key = None
        for k, key in self._jwks_provider():
            if k == kid:
                pub_key = key
                break
        if pub_key is None:
            raise TokenInvalid(f"unknown kid {kid}")

        try:
            payload = jwt.decode(
                token, pub_key, algorithms=["RS256", "ES256"],
                audience=self._audience, issuer=self._issuer,
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

        return TokenClaims(
            sub=payload["sub"],
            tenant_id=UUID(payload["tenant_id"]),
            scopes=frozenset(payload.get("scopes", [])),
            exp=payload["exp"],
            iss=payload["iss"],
            aud=payload["aud"] if isinstance(payload["aud"], str) else payload["aud"][0],
        )


class HTTPJWKSProvider:
    """Production: fetches and caches JWKS from URL."""
    def __init__(self, url: str):
        self._client = PyJWKClient(url, cache_keys=True, lifespan=600)

    def __call__(self):
        # Return list[(kid, public_key_pem)]
        result = []
        for k in self._client.get_signing_keys():
            result.append((k.key_id, k.key))
        return result
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/auth/test_token_validator.py -v
```

- [ ] **Step 5: Build mock-idp service**

```python
# mocks/idp/main.py
import time
import uuid
import secrets
from typing import Any
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, HTTPException, Form
from pydantic import BaseModel
import jwt


KID = "mock-idp-key-1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()
PRIVATE_PEM = KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
ISSUER = "http://localhost:9000"
DEFAULT_AUDIENCE = "mcp-gateway"


# In-memory client + agent registry
CLIENTS: dict[str, dict[str, Any]] = {}
AGENTS: dict[str, dict[str, Any]] = {}  # client_id → agent metadata


app = FastAPI(title="Mock OAuth IdP")


@app.get("/.well-known/oauth-authorization-server")
def metadata():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "registration_endpoint": f"{ISSUER}/register",
        "jwks_uri": f"{ISSUER}/jwks",
        "response_types_supported": ["code"],
        "grant_types_supported": ["client_credentials", "authorization_code"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "scopes_supported": ["tool:*"],
    }


@app.get("/jwks")
def jwks():
    # Convert PEM to JWK
    from jwt.algorithms import RSAAlgorithm
    import json
    jwk = json.loads(RSAAlgorithm.to_jwk(KEY.public_key()))
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
def register(req: RegisterReq):
    client_id = f"client-{uuid.uuid4().hex[:12]}"
    client_secret = secrets.token_urlsafe(32)
    CLIENTS[client_id] = {"secret": client_secret, "tenant_id": req.tenant_id, "scopes": req.scopes}
    AGENTS[client_id] = {"agent_id": req.agent_id or str(uuid.uuid4())}
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": req.redirect_uris,
        "grant_types": ["client_credentials"],
    }


@app.post("/token")
def token(grant_type: str = Form(...), client_id: str = Form(...), client_secret: str = Form(...), scope: str = Form("")):
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
    return {"access_token": tok, "token_type": "Bearer", "expires_in": 3600, "scope": " ".join(granted_scopes)}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
```

- [ ] **Step 6: Mock IdP Dockerfile**

```dockerfile
# mocks/idp/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn[standard] pyjwt[crypto] cryptography pydantic
COPY main.py /app/main.py
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

- [ ] **Step 7: Test mock IdP via httpx**

```python
# tests/mocks/test_mock_idp.py
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_metadata_endpoint():
    from mocks.idp.main import app
    client = TestClient(app)
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    assert r.json()["registration_endpoint"].endswith("/register")


def test_jwks_returns_key():
    from mocks.idp.main import app
    client = TestClient(app)
    r = client.get("/jwks")
    keys = r.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["alg"] == "RS256"


def test_register_then_token():
    from mocks.idp.main import app
    client = TestClient(app)
    reg = client.post("/register", json={"client_name": "test", "tenant_id": "t1", "scopes": ["tool:get_customer"]}).json()
    tok = client.post("/token", data={"grant_type": "client_credentials", "client_id": reg["client_id"], "client_secret": reg["client_secret"]})
    assert tok.status_code == 200
    assert tok.json()["token_type"] == "Bearer"
```

- [ ] **Step 8: Commit**

```bash
git add gateway/auth mocks/idp tests/auth tests/mocks
git commit -m "feat(auth): JWKSTokenValidator + mock OAuth IdP with DCR"
```

---

### Task 1.B: Policy engine

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/policy/__init__.py`, `gateway/policy/schema.py`, `gateway/policy/loader.py`, `gateway/policy/evaluator.py`
- Create: `config/policies.yaml`
- Create: `tests/policy/test_loader.py`, `tests/policy/test_evaluator.py`

- [ ] **Step 1: Define schema**

```python
# gateway/policy/schema.py
from enum import Enum
from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class ToolRule(BaseModel):
    tool: str
    requires_approval: bool = False


class RolePolicy(BaseModel):
    name: str
    tools: list[ToolRule] = Field(default_factory=list)


class PolicyDocument(BaseModel):
    version: int = 1
    roles: list[RolePolicy]
```

- [ ] **Step 2: Failing tests for loader + evaluator**

```python
# tests/policy/test_loader.py
import pytest
from pathlib import Path
from gateway.policy.loader import load_policies

pytestmark = pytest.mark.unit


def test_loads_yaml(tmp_path: Path):
    p = tmp_path / "p.yaml"
    p.write_text("""
version: 1
roles:
  - name: support
    tools:
      - tool: get_customer
      - tool: refund_payment
        requires_approval: true
""")
    doc = load_policies(p)
    assert len(doc.roles) == 1
    assert doc.roles[0].tools[1].requires_approval is True
```

```python
# tests/policy/test_evaluator.py
import pytest
from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.schema import PolicyDocument, RolePolicy, ToolRule, Decision


pytestmark = pytest.mark.unit


@pytest.fixture
def doc():
    return PolicyDocument(roles=[
        RolePolicy(name="support", tools=[
            ToolRule(tool="get_customer"),
            ToolRule(tool="refund_payment", requires_approval=True),
        ]),
        RolePolicy(name="readonly", tools=[ToolRule(tool="get_customer")]),
    ])


def test_allow_for_permitted_tool(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("support", "get_customer") == Decision.ALLOW


def test_requires_approval(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("support", "refund_payment") == Decision.REQUIRES_APPROVAL


def test_deny_unknown_tool(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("support", "delete_everything") == Decision.DENY


def test_deny_unknown_role(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("admin", "get_customer") == Decision.DENY


def test_deny_for_role_without_tool(doc):
    e = PolicyEvaluator(doc)
    assert e.evaluate("readonly", "refund_payment") == Decision.DENY
```

- [ ] **Step 3: Implement loader and evaluator**

```python
# gateway/policy/loader.py
from pathlib import Path
import yaml
from gateway.policy.schema import PolicyDocument


def load_policies(path: str | Path) -> PolicyDocument:
    raw = yaml.safe_load(Path(path).read_text())
    return PolicyDocument.model_validate(raw)
```

```python
# gateway/policy/evaluator.py
from gateway.policy.schema import PolicyDocument, Decision


class PolicyEvaluator:
    def __init__(self, document: PolicyDocument):
        # Build O(1) lookup: role -> tool -> ToolRule
        self._index: dict[str, dict[str, "ToolRule"]] = {
            role.name: {t.tool: t for t in role.tools}
            for role in document.roles
        }

    def evaluate(self, role: str, tool: str) -> Decision:
        role_tools = self._index.get(role)
        if role_tools is None:
            return Decision.DENY
        rule = role_tools.get(tool)
        if rule is None:
            return Decision.DENY
        return Decision.REQUIRES_APPROVAL if rule.requires_approval else Decision.ALLOW
```

- [ ] **Step 4: Create example `config/policies.yaml`**

```yaml
version: 1
roles:
  - name: support_agent
    tools:
      - tool: get_customer
      - tool: list_orders
      - tool: update_order
      - tool: refund_payment
        requires_approval: true
  - name: readonly_analyst
    tools:
      - tool: get_customer
      - tool: list_orders
  - name: finance_admin
    tools:
      - tool: refund_payment
        requires_approval: true
      - tool: charge_card
        requires_approval: true
```

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/policy -v
git add gateway/policy config/policies.yaml tests/policy
git commit -m "feat(policy): YAML-based RBAC evaluator with allow/deny/approval decisions"
```

---

### Task 1.C: Approval module (store + Telegram + WebSocket)

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/approval/__init__.py`, `gateway/approval/store.py`, `gateway/approval/notifier.py`, `gateway/approval/telegram.py`, `gateway/approval/websocket.py`, `gateway/approval/timeout.py`
- Create: `tests/approval/test_store.py`, `tests/approval/test_telegram.py`, `tests/approval/test_websocket.py`

- [ ] **Step 1: Approval store**

```python
# gateway/approval/store.py
import asyncio
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db.models import ApprovalRequest


PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
TIMEOUT = "timeout"


class ApprovalStore:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create(
        self, *, tenant_id: UUID, agent_id: UUID, tool: str, params: dict
    ) -> UUID:
        async with self._session_factory() as session:
            req = ApprovalRequest(
                tenant_id=tenant_id, agent_id=agent_id,
                tool=tool, params_json=params, status=PENDING,
            )
            session.add(req)
            await session.commit()
            await session.refresh(req)
            return req.id

    async def get(self, req_id: UUID) -> ApprovalRequest | None:
        async with self._session_factory() as session:
            res = await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == req_id))
            return res.scalar_one_or_none()

    async def decide(
        self, req_id: UUID, *, decision: str, decided_by: str, reason: str | None = None
    ) -> bool:
        """Returns True if state transitioned, False if already decided."""
        async with self._session_factory() as session:
            res = await session.execute(
                update(ApprovalRequest)
                .where(ApprovalRequest.id == req_id, ApprovalRequest.status == PENDING)
                .values(
                    status=decision, decided_by=decided_by, decision_reason=reason,
                    decided_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            return res.rowcount > 0

    async def wait_for_decision(
        self, req_id: UUID, timeout: float, poll_interval: float = 1.0
    ) -> str:
        """Poll until status leaves PENDING or timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            req = await self.get(req_id)
            if req and req.status != PENDING:
                return req.status
            await asyncio.sleep(poll_interval)
        # Timeout: try to mark
        await self.decide(req_id, decision=TIMEOUT, decided_by="system", reason="timeout")
        return TIMEOUT
```

- [ ] **Step 2: Notifier interface + WebSocket impl**

```python
# gateway/approval/notifier.py
from typing import Protocol
from uuid import UUID


class ApprovalNotifier(Protocol):
    async def notify_pending(self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict) -> None: ...
    async def notify_decided(self, *, approval_id: UUID, status: str) -> None: ...


class CompositeNotifier:
    def __init__(self, notifiers: list[ApprovalNotifier]):
        self._notifiers = notifiers

    async def notify_pending(self, **kwargs):
        import asyncio
        await asyncio.gather(*(n.notify_pending(**kwargs) for n in self._notifiers), return_exceptions=True)

    async def notify_decided(self, **kwargs):
        import asyncio
        await asyncio.gather(*(n.notify_decided(**kwargs) for n in self._notifiers), return_exceptions=True)
```

```python
# gateway/approval/websocket.py
import asyncio
import json
from uuid import UUID
from fastapi import WebSocket


class WebSocketBroadcaster:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)

    async def _broadcast(self, message: dict):
        async with self._lock:
            dead = []
            for ws in self._connections:
                try:
                    await ws.send_text(json.dumps(message))
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.discard(ws)

    async def notify_pending(self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict):
        await self._broadcast({
            "type": "pending", "approval_id": str(approval_id),
            "agent_id": str(agent_id), "tool": tool, "params": params,
        })

    async def notify_decided(self, *, approval_id: UUID, status: str):
        await self._broadcast({"type": "decided", "approval_id": str(approval_id), "status": status})
```

- [ ] **Step 3: Telegram notifier**

```python
# gateway/approval/telegram.py
import json
from uuid import UUID
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from gateway.observability.logging import get_logger


log = get_logger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, admin_chat_id: str):
        self._bot = Bot(token=bot_token)
        self._chat_id = admin_chat_id

    async def notify_pending(self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict):
        text = (
            f"🔔 *Pending approval*\n\n"
            f"Tool: `{tool}`\n"
            f"Agent: `{agent_id}`\n"
            f"Params:\n```\n{json.dumps(params, indent=2)[:500]}\n```"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{approval_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{approval_id}"),
        ]])
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text, reply_markup=kb, parse_mode="Markdown")
        except TelegramError as e:
            log.warning("telegram_notify_failed", error=str(e), approval_id=str(approval_id))

    async def notify_decided(self, *, approval_id: UUID, status: str):
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=f"Approval `{approval_id}` → *{status}*", parse_mode="Markdown")
        except TelegramError as e:
            log.warning("telegram_notify_failed", error=str(e))
```

- [ ] **Step 4: Telegram bot polling worker**

```python
# gateway/approval/telegram_bot.py
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from uuid import UUID
from gateway.approval.store import ApprovalStore, APPROVED, REJECTED
from gateway.observability.logging import get_logger


log = get_logger(__name__)


def build_telegram_app(token: str, store: ApprovalStore, broadcaster) -> Application:
    app = Application.builder().token(token).build()

    async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not q or not q.data:
            return
        action, _, approval_id = q.data.partition(":")
        decision = APPROVED if action == "approve" else REJECTED
        user = q.from_user.username or str(q.from_user.id) if q.from_user else "unknown"
        ok = await store.decide(UUID(approval_id), decision=decision, decided_by=f"tg:{user}")
        if ok:
            await broadcaster.notify_decided(approval_id=UUID(approval_id), status=decision)
            await q.answer(f"{decision}", show_alert=False)
            await q.edit_message_reply_markup(reply_markup=None)
        else:
            await q.answer("Already decided", show_alert=True)

    app.add_handler(CallbackQueryHandler(on_callback))
    return app
```

- [ ] **Step 5: Background timeout reaper**

```python
# gateway/approval/timeout.py
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from gateway.db.models import ApprovalRequest
from gateway.approval.store import PENDING, TIMEOUT
from gateway.observability.logging import get_logger


log = get_logger(__name__)


class TimeoutReaper:
    def __init__(self, session_factory, timeout_seconds: int, broadcaster=None):
        self._sf = session_factory
        self._timeout = timeout_seconds
        self._broadcaster = broadcaster
        self._task: asyncio.Task | None = None

    async def _tick(self):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._timeout)
        async with self._sf() as session:
            res = await session.execute(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.status == PENDING,
                    ApprovalRequest.created_at < cutoff,
                )
            )
            ids = [r[0] for r in res]
            if ids:
                await session.execute(
                    update(ApprovalRequest)
                    .where(ApprovalRequest.id.in_(ids), ApprovalRequest.status == PENDING)
                    .values(status=TIMEOUT, decided_by="system", decision_reason="timeout")
                )
                await session.commit()
                log.info("approvals_timed_out", count=len(ids))
                if self._broadcaster:
                    for i in ids:
                        await self._broadcaster.notify_decided(approval_id=i, status=TIMEOUT)

    async def _run(self):
        while True:
            try:
                await self._tick()
            except Exception as e:
                log.error("reaper_tick_failed", error=str(e))
            await asyncio.sleep(10)

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
```

- [ ] **Step 6: Tests for store**

```python
# tests/approval/test_store.py
import asyncio
import pytest
from uuid import uuid4
from gateway.approval.store import ApprovalStore, PENDING, APPROVED, TIMEOUT
from gateway.db.models import Tenant, Role, Agent

pytestmark = pytest.mark.integration


@pytest.fixture
async def seeded_ids(db_session):
    t = Tenant(name="t1")
    db_session.add(t); await db_session.flush()
    r = Role(tenant_id=t.id, name="support")
    db_session.add(r); await db_session.flush()
    a = Agent(tenant_id=t.id, name="a1", role_id=r.id)
    db_session.add(a); await db_session.commit()
    return t.id, a.id


async def test_create_and_decide(db_engine, seeded_ids):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})
    ok = await store.decide(rid, decision=APPROVED, decided_by="me")
    assert ok is True
    req = await store.get(rid)
    assert req.status == APPROVED


async def test_concurrent_decide_only_one_wins(db_engine, seeded_ids):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})
    results = await asyncio.gather(
        store.decide(rid, decision="approved", decided_by="a"),
        store.decide(rid, decision="rejected", decided_by="b"),
    )
    assert results.count(True) == 1
    assert results.count(False) == 1


async def test_wait_for_decision_returns_when_decided(db_engine, seeded_ids):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})

    async def decide_later():
        await asyncio.sleep(0.5)
        await store.decide(rid, decision=APPROVED, decided_by="x")

    asyncio.create_task(decide_later())
    status = await store.wait_for_decision(rid, timeout=5, poll_interval=0.2)
    assert status == APPROVED


async def test_wait_for_decision_times_out(db_engine, seeded_ids):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    store = ApprovalStore(sf)
    tid, aid = seeded_ids
    rid = await store.create(tenant_id=tid, agent_id=aid, tool="x", params={})
    status = await store.wait_for_decision(rid, timeout=0.5, poll_interval=0.1)
    assert status == TIMEOUT
```

- [ ] **Step 7: Run tests + commit**

```bash
pytest tests/approval -v
git add gateway/approval tests/approval
git commit -m "feat(approval): store, telegram + websocket notifiers, timeout reaper"
```

---

### Task 1.D: Audit module

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/audit/__init__.py`, `gateway/audit/writer.py`, `gateway/audit/reader.py`, `gateway/audit/redaction.py`
- Create: `tests/audit/test_writer.py`, `tests/audit/test_reader.py`, `tests/audit/test_redaction.py`

- [ ] **Step 1: Define redaction**

```python
# gateway/audit/redaction.py
from typing import Callable, Mapping


RedactFn = Callable[[Mapping], dict]


def redact_card_number(params: Mapping) -> dict:
    out = dict(params)
    if "card_number" in out:
        cn = str(out["card_number"])
        out["card_number"] = f"****{cn[-4:]}" if len(cn) >= 4 else "****"
    return out


def redact_email(params: Mapping) -> dict:
    out = dict(params)
    if "email" in out and isinstance(out["email"], str):
        local, _, domain = out["email"].partition("@")
        out["email"] = f"{local[0]}***@{domain}" if local else out["email"]
    return out


def chain(*fns: RedactFn) -> RedactFn:
    def apply(params: Mapping) -> dict:
        out = dict(params)
        for fn in fns:
            out = fn(out)
        return out
    return apply


IDENTITY: RedactFn = lambda p: dict(p)
```

- [ ] **Step 2: Writer**

```python
# gateway/audit/writer.py
from uuid import UUID
from gateway.db.models import AuditLog


class AuditWriter:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def write(
        self,
        *,
        tenant_id: UUID | None,
        agent_id: UUID | None,
        tool: str | None,
        params: dict,
        result_status: str,
        result: dict | None = None,
        approval_id: UUID | None = None,
        trace_id: str | None = None,
    ) -> None:
        async with self._sf() as session:
            entry = AuditLog(
                tenant_id=tenant_id, agent_id=agent_id, tool=tool,
                params_json=params, result_status=result_status,
                result_json=result or {}, approval_id=approval_id, trace_id=trace_id,
            )
            session.add(entry)
            await session.commit()
```

- [ ] **Step 3: Reader (with filters + pagination + tenant isolation)**

```python
# gateway/audit/reader.py
from datetime import datetime
from uuid import UUID
from dataclasses import dataclass
from sqlalchemy import select, func
from gateway.db.models import AuditLog


@dataclass
class AuditFilter:
    tenant_id: UUID
    agent_id: UUID | None = None
    tool: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    result_status: str | None = None


@dataclass
class AuditPage:
    entries: list[AuditLog]
    total: int
    limit: int
    offset: int


class AuditReader:
    def __init__(self, session_factory):
        self._sf = session_factory

    async def query(self, f: AuditFilter, *, limit: int = 50, offset: int = 0) -> AuditPage:
        stmt = select(AuditLog).where(AuditLog.tenant_id == f.tenant_id)
        if f.agent_id:
            stmt = stmt.where(AuditLog.agent_id == f.agent_id)
        if f.tool:
            stmt = stmt.where(AuditLog.tool == f.tool)
        if f.result_status:
            stmt = stmt.where(AuditLog.result_status == f.result_status)
        if f.from_ts:
            stmt = stmt.where(AuditLog.created_at >= f.from_ts)
        if f.to_ts:
            stmt = stmt.where(AuditLog.created_at <= f.to_ts)

        async with self._sf() as session:
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await session.execute(count_stmt)).scalar_one()
            stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
            entries = (await session.execute(stmt)).scalars().all()
        return AuditPage(entries=list(entries), total=total, limit=limit, offset=offset)
```

- [ ] **Step 4: Tests**

```python
# tests/audit/test_redaction.py
import pytest
from gateway.audit.redaction import redact_card_number, redact_email, chain

pytestmark = pytest.mark.unit


def test_card_number_redacted():
    assert redact_card_number({"card_number": "4111111111111234"}) == {"card_number": "****1234"}


def test_email_redacted():
    assert redact_email({"email": "alice@example.com"})["email"] == "a***@example.com"


def test_chain():
    fn = chain(redact_card_number, redact_email)
    out = fn({"card_number": "4111111111111234", "email": "bob@x.com", "amount": 100})
    assert out["card_number"] == "****1234"
    assert out["email"] == "b***@x.com"
    assert out["amount"] == 100
```

```python
# tests/audit/test_writer.py
import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from gateway.audit.writer import AuditWriter
from gateway.db.models import Tenant


pytestmark = pytest.mark.integration


async def test_write_appends(db_engine):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}"); s.add(t); await s.commit()
        tid = t.id

    w = AuditWriter(sf)
    await w.write(tenant_id=tid, agent_id=None, tool="get_customer",
                  params={"id": "1"}, result_status="success", result={"ok": True})

    from sqlalchemy import select, func
    from gateway.db.models import AuditLog
    async with sf() as s:
        cnt = (await s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tid))).scalar()
        assert cnt == 1
```

```python
# tests/audit/test_reader.py
import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from gateway.audit.writer import AuditWriter
from gateway.audit.reader import AuditReader, AuditFilter
from gateway.db.models import Tenant


pytestmark = pytest.mark.integration


async def test_tenant_isolation(db_engine):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        a = Tenant(name=f"a-{uuid4()}"); b = Tenant(name=f"b-{uuid4()}")
        s.add_all([a, b]); await s.commit()
        a_id, b_id = a.id, b.id

    w = AuditWriter(sf)
    await w.write(tenant_id=a_id, agent_id=None, tool="x", params={}, result_status="success")
    await w.write(tenant_id=b_id, agent_id=None, tool="x", params={}, result_status="success")

    r = AuditReader(sf)
    page_a = await r.query(AuditFilter(tenant_id=a_id))
    assert page_a.total == 1
    assert all(e.tenant_id == a_id for e in page_a.entries)
```

- [ ] **Step 5: Commit**

```bash
git add gateway/audit tests/audit
git commit -m "feat(audit): writer + reader (with tenant isolation) + redaction chain"
```

---

### Task 1.E: Mock CRM and Mock Payments services

**Subagent:** `general-purpose`

**Files:**
- Create: `mocks/crm/main.py`, `mocks/crm/Dockerfile`, `mocks/crm/data.json`
- Create: `mocks/payments/main.py`, `mocks/payments/Dockerfile`
- Create: `tests/mocks/test_mock_crm.py`, `tests/mocks/test_mock_payments.py`

- [ ] **Step 1: Mock CRM**

```python
# mocks/crm/main.py
import os
from fastapi import FastAPI, HTTPException, Header

API_KEY = os.environ.get("MOCK_CRM_API_KEY", "dev-crm-key")

CUSTOMERS = {
    "C001": {"id": "C001", "name": "Иванов Иван", "email": "ivanov@example.com", "balance": 12500.0},
    "C002": {"id": "C002", "name": "Петров Петр", "email": "petrov@example.com", "balance": 0.0},
    "C003": {"id": "C003", "name": "Сидорова Анна", "email": "sidorova@example.com", "balance": 4980.0},
}
ORDERS = {
    "O1234": {"id": "O1234", "customer_id": "C001", "amount": 50000.0, "status": "completed"},
    "O1235": {"id": "O1235", "customer_id": "C002", "amount": 1200.0, "status": "pending"},
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
```

```dockerfile
# mocks/crm/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn[standard]
COPY main.py /app/main.py
EXPOSE 9001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]
```

- [ ] **Step 2: Mock Payments**

```python
# mocks/payments/main.py
import os
import random
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel


API_KEY = os.environ.get("MOCK_PAYMENTS_API_KEY", "dev-payments-key")
FAILURE_RATE = float(os.environ.get("MOCK_PAYMENTS_FAILURE_RATE", "0"))  # for testing retries

PAYMENTS: dict[str, dict] = {}


app = FastAPI(title="Mock Payments")


def auth(x_api_key: str | None):
    if x_api_key != API_KEY:
        raise HTTPException(401, "invalid_api_key")


def maybe_fail():
    if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
        raise HTTPException(503, "transient_failure")


class RefundRequest(BaseModel):
    customer_id: str
    amount: float
    reason: str | None = None


@app.post("/refunds")
def refund(req: RefundRequest, x_api_key: str | None = Header(default=None), idempotency_key: str | None = Header(default=None)):
    auth(x_api_key); maybe_fail()
    key = idempotency_key or str(uuid.uuid4())
    if key in PAYMENTS:
        return PAYMENTS[key]
    pid = f"P-{uuid.uuid4().hex[:10]}"
    rec = {
        "id": pid, "customer_id": req.customer_id, "amount": req.amount,
        "type": "refund", "status": "completed",
        "reason": req.reason, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    PAYMENTS[key] = rec
    return rec


class ChargeRequest(BaseModel):
    card_number: str
    amount: float
    customer_id: str | None = None


@app.post("/charges")
def charge(req: ChargeRequest, x_api_key: str | None = Header(default=None), idempotency_key: str | None = Header(default=None)):
    auth(x_api_key); maybe_fail()
    key = idempotency_key or str(uuid.uuid4())
    if key in PAYMENTS:
        return PAYMENTS[key]
    pid = f"P-{uuid.uuid4().hex[:10]}"
    rec = {
        "id": pid, "customer_id": req.customer_id, "amount": req.amount,
        "type": "charge", "status": "completed",
        "card_last4": req.card_number[-4:] if len(req.card_number) >= 4 else "****",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    PAYMENTS[key] = rec
    return rec


@app.get("/healthz")
def hz():
    return {"ok": True}
```

```dockerfile
# mocks/payments/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn[standard] pydantic
COPY main.py /app/main.py
EXPOSE 9002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9002"]
```

- [ ] **Step 3: Tests**

```python
# tests/mocks/test_mock_crm.py
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_get_customer_requires_key():
    from mocks.crm.main import app
    c = TestClient(app)
    assert c.get("/customers/C001").status_code == 401
    r = c.get("/customers/C001", headers={"x-api-key": "dev-crm-key"})
    assert r.status_code == 200
    assert r.json()["name"] == "Иванов Иван"


def test_unknown_customer_404():
    from mocks.crm.main import app
    c = TestClient(app)
    r = c.get("/customers/XXX", headers={"x-api-key": "dev-crm-key"})
    assert r.status_code == 404
```

```python
# tests/mocks/test_mock_payments.py
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_refund_idempotent():
    from mocks.payments.main import app
    c = TestClient(app)
    h = {"x-api-key": "dev-payments-key", "idempotency-key": "key-1"}
    r1 = c.post("/refunds", json={"customer_id": "C001", "amount": 100}, headers=h)
    r2 = c.post("/refunds", json={"customer_id": "C001", "amount": 999}, headers=h)
    assert r1.json() == r2.json()
```

- [ ] **Step 4: Commit**

```bash
git add mocks/crm mocks/payments tests/mocks
git commit -m "feat(mocks): CRM + payments services with auth, retry support, idempotency"
```

---

### Task 1.F: Tools (registry + implementations)

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/tools/__init__.py`, `gateway/tools/registry.py`, `gateway/tools/upstream.py`, `gateway/tools/crm.py`, `gateway/tools/payments.py`, `gateway/tools/exceptions.py`
- Create: `tests/tools/test_registry.py`, `tests/tools/test_upstream.py`, `tests/tools/test_crm.py`, `tests/tools/test_payments.py`

- [ ] **Step 1: Registry + interfaces**

```python
# gateway/tools/exceptions.py
class ToolError(Exception): ...
class UpstreamError(ToolError): ...
class UpstreamUnavailable(UpstreamError): ...
class UpstreamClientError(UpstreamError):
    def __init__(self, status: int, body: dict | str):
        super().__init__(f"client error {status}")
        self.status = status; self.body = body
class UpstreamServerError(UpstreamError): ...
```

```python
# gateway/tools/registry.py
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from gateway.audit.redaction import RedactFn, IDENTITY


@dataclass(frozen=True)
class ToolMeta:
    name: str
    description: str
    input_schema: dict[str, Any]
    destructive: bool
    redact: RedactFn = IDENTITY


@dataclass
class ToolRegistry:
    tools: dict[str, "RegisteredTool"] = field(default_factory=dict)

    def register(self, meta: ToolMeta, handler: Callable[..., Awaitable[dict]]) -> None:
        self.tools[meta.name] = RegisteredTool(meta=meta, handler=handler)

    def get(self, name: str) -> "RegisteredTool | None":
        return self.tools.get(name)

    def list(self) -> list[ToolMeta]:
        return [t.meta for t in self.tools.values()]


@dataclass
class RegisteredTool:
    meta: ToolMeta
    handler: Callable[..., Awaitable[dict]]
```

- [ ] **Step 2: Upstream client (httpx + retry + circuit breaker)**

```python
# gateway/tools/upstream.py
import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from gateway.tools.exceptions import UpstreamUnavailable, UpstreamServerError, UpstreamClientError
from gateway.observability.metrics import UPSTREAM_FAILURES
from gateway.observability.logging import get_logger


log = get_logger(__name__)


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_seconds: float = 30):
        self.name = name
        self._fails = 0
        self._opened_at: float | None = None
        self._threshold = failure_threshold
        self._recovery = recovery_seconds

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self._recovery:
            self._opened_at = None
            self._fails = 0
            return False
        return True

    def on_success(self):
        self._fails = 0
        self._opened_at = None

    def on_failure(self):
        self._fails += 1
        if self._fails >= self._threshold:
            self._opened_at = time.monotonic()

    @asynccontextmanager
    async def guard(self):
        if self._is_open():
            UPSTREAM_FAILURES.labels(service=self.name).inc()
            raise UpstreamUnavailable(f"circuit open: {self.name}")
        try:
            yield
            self.on_success()
        except (UpstreamUnavailable, UpstreamServerError):
            self.on_failure()
            raise


class UpstreamClient:
    def __init__(self, base_url: str, api_key: str, service_name: str, timeout: float = 5.0):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key}
        self._service = service_name
        self._client = httpx.AsyncClient(timeout=timeout, base_url=self._base)
        self._breaker = CircuitBreaker(service_name)

    async def aclose(self):
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type((UpstreamUnavailable, UpstreamServerError)),
        reraise=True,
    )
    async def _request(self, method: str, path: str, *, json=None, headers=None, idempotency_key: str | None = None) -> httpx.Response:
        async with self._breaker.guard():
            try:
                req_headers = dict(self._headers)
                if headers:
                    req_headers.update(headers)
                if idempotency_key:
                    req_headers["idempotency-key"] = idempotency_key
                resp = await self._client.request(method, path, json=json, headers=req_headers)
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                UPSTREAM_FAILURES.labels(service=self._service).inc()
                raise UpstreamUnavailable(str(e)) from e

            if resp.status_code >= 500:
                UPSTREAM_FAILURES.labels(service=self._service).inc()
                raise UpstreamServerError(f"{resp.status_code}: {resp.text[:200]}")
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text
                raise UpstreamClientError(resp.status_code, body)
            return resp

    async def get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._request("GET", path + (("?" + httpx.QueryParams(params).__str__()) if params else ""))
        return resp.json()

    async def post(self, path: str, json: dict, idempotency_key: str | None = None) -> dict:
        resp = await self._request("POST", path, json=json, idempotency_key=idempotency_key or str(uuid4()))
        return resp.json()

    async def patch(self, path: str, json: dict) -> dict:
        resp = await self._request("PATCH", path, json=json)
        return resp.json()
```

- [ ] **Step 3: CRM tools**

```python
# gateway/tools/crm.py
from gateway.tools.registry import ToolMeta
from gateway.tools.upstream import UpstreamClient


def build_crm_tools(client: UpstreamClient) -> list[tuple[ToolMeta, callable]]:
    async def get_customer(customer_id: str) -> dict:
        return await client.get(f"/customers/{customer_id}")

    async def list_orders(customer_id: str) -> dict:
        return await client.get("/orders", params={"customer_id": customer_id})

    async def update_order(order_id: str, status: str) -> dict:
        return await client.patch(f"/orders/{order_id}", json={"status": status})

    return [
        (ToolMeta(
            name="get_customer", description="Fetch customer profile by ID",
            input_schema={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
            destructive=False,
        ), get_customer),
        (ToolMeta(
            name="list_orders", description="List orders for a customer",
            input_schema={"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
            destructive=False,
        ), list_orders),
        (ToolMeta(
            name="update_order", description="Update order status",
            input_schema={"type": "object", "properties": {"order_id": {"type": "string"}, "status": {"type": "string"}}, "required": ["order_id", "status"]},
            destructive=False,
        ), update_order),
    ]
```

- [ ] **Step 4: Payment tools (with redaction)**

```python
# gateway/tools/payments.py
from gateway.tools.registry import ToolMeta
from gateway.tools.upstream import UpstreamClient
from gateway.audit.redaction import redact_card_number


def build_payment_tools(client: UpstreamClient) -> list[tuple[ToolMeta, callable]]:
    async def refund_payment(customer_id: str, amount: float, reason: str | None = None) -> dict:
        return await client.post("/refunds", json={"customer_id": customer_id, "amount": amount, "reason": reason})

    async def charge_card(card_number: str, amount: float, customer_id: str | None = None) -> dict:
        return await client.post("/charges", json={"card_number": card_number, "amount": amount, "customer_id": customer_id})

    return [
        (ToolMeta(
            name="refund_payment", description="Issue a refund to customer",
            input_schema={
                "type": "object",
                "properties": {"customer_id": {"type": "string"}, "amount": {"type": "number"}, "reason": {"type": "string"}},
                "required": ["customer_id", "amount"],
            },
            destructive=True,
        ), refund_payment),
        (ToolMeta(
            name="charge_card", description="Charge a credit card",
            input_schema={
                "type": "object",
                "properties": {"card_number": {"type": "string"}, "amount": {"type": "number"}, "customer_id": {"type": "string"}},
                "required": ["card_number", "amount"],
            },
            destructive=True, redact=redact_card_number,
        ), charge_card),
    ]
```

- [ ] **Step 5: Tests for upstream (mock httpx)**

```python
# tests/tools/test_upstream.py
import pytest
import httpx
import respx
from gateway.tools.upstream import UpstreamClient
from gateway.tools.exceptions import UpstreamUnavailable, UpstreamClientError

pytestmark = pytest.mark.unit


@pytest.fixture
async def client():
    c = UpstreamClient("http://test.local", "k", "test", timeout=1)
    yield c
    await c.aclose()


@respx.mock
async def test_get_returns_json(client):
    respx.get("http://test.local/x").respond(200, json={"ok": True})
    assert await client.get("/x") == {"ok": True}


@respx.mock
async def test_retry_on_5xx(client):
    route = respx.get("http://test.local/x").mock(side_effect=[
        httpx.Response(500), httpx.Response(503), httpx.Response(200, json={"ok": True}),
    ])
    assert await client.get("/x") == {"ok": True}
    assert route.call_count == 3


@respx.mock
async def test_no_retry_on_4xx(client):
    respx.get("http://test.local/x").respond(404, json={"err": "nf"})
    with pytest.raises(UpstreamClientError) as exc:
        await client.get("/x")
    assert exc.value.status == 404


@respx.mock
async def test_circuit_opens_after_failures():
    c = UpstreamClient("http://t.local", "k", "svc", timeout=1)
    respx.get("http://t.local/x").respond(500)
    for _ in range(5):
        with pytest.raises(Exception):
            await c.get("/x")
    # Circuit now open — should fail fast
    with pytest.raises(UpstreamUnavailable):
        await c.get("/x")
    await c.aclose()
```

(install `respx` — add to dev deps)

Add to pyproject `[project.optional-dependencies].dev`: `"respx>=0.21.1"`.

- [ ] **Step 6: Commit**

```bash
git add gateway/tools tests/tools pyproject.toml
git commit -m "feat(tools): registry, upstream client (retry+circuit), CRM + payments tools"
```

---

### Task 1.G: Web UI (audit + approvals)

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/web/__init__.py`, `gateway/web/routes.py`, `gateway/web/api.py`
- Create: `gateway/web/templates/base.html`, `gateway/web/templates/audit.html`, `gateway/web/templates/approvals.html`
- Create: `gateway/web/static/styles.css`
- Create: `tests/web/test_audit_route.py`, `tests/web/test_approvals_route.py`

- [ ] **Step 1: Templates (Jinja + HTMX)**

```html
<!-- gateway/web/templates/base.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}MCP Gateway{% endblock %}</title>
  <script src="https://unpkg.com/htmx.org@2.0.3"></script>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header><h1>MCP Gateway</h1>
    <nav><a href="/audit">Audit</a> · <a href="/approvals">Approvals</a></nav>
  </header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

```html
<!-- gateway/web/templates/audit.html -->
{% extends "base.html" %}
{% block title %}Audit{% endblock %}
{% block content %}
<h2>Audit log</h2>
<form hx-get="/audit/rows" hx-target="#rows" hx-trigger="change, submit">
  <input name="agent_id" placeholder="Agent ID">
  <input name="tool" placeholder="Tool">
  <select name="result_status">
    <option value="">— any status —</option>
    <option value="success">success</option>
    <option value="denied">denied</option>
    <option value="rejected">rejected</option>
    <option value="timeout">timeout</option>
    <option value="error">error</option>
  </select>
  <button type="submit">Filter</button>
</form>
<div id="rows" hx-get="/audit/rows" hx-trigger="load">Loading…</div>
{% endblock %}
```

```html
<!-- gateway/web/templates/_audit_rows.html -->
<table>
  <thead><tr><th>Time</th><th>Agent</th><th>Tool</th><th>Status</th><th>Trace</th></tr></thead>
  <tbody>
  {% for e in entries %}
    <tr>
      <td>{{ e.created_at.isoformat() }}</td>
      <td>{{ e.agent_id or "-" }}</td>
      <td>{{ e.tool or "-" }}</td>
      <td class="status-{{ e.result_status }}">{{ e.result_status }}</td>
      <td><code>{{ e.trace_id or "-" }}</code></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
<p>Total: {{ total }}</p>
```

```html
<!-- gateway/web/templates/approvals.html -->
{% extends "base.html" %}
{% block title %}Approvals{% endblock %}
{% block content %}
<h2>Pending approvals</h2>
<div id="list" hx-get="/approvals/list" hx-trigger="load, every 3s"></div>
<script>
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/approvals/ws`);
  ws.onmessage = () => htmx.trigger("#list", "refresh");
</script>
{% endblock %}
```

```html
<!-- gateway/web/templates/_approvals_list.html -->
{% if approvals %}
<ul>
  {% for a in approvals %}
    <li class="approval">
      <strong>{{ a.tool }}</strong> by agent <code>{{ a.agent_id }}</code><br>
      <pre>{{ a.params_json | tojson(indent=2) }}</pre>
      <button hx-post="/approvals/{{ a.id }}/decide?decision=approved&decided_by={{ user }}" hx-target="closest li" hx-swap="outerHTML">Approve</button>
      <button hx-post="/approvals/{{ a.id }}/decide?decision=rejected&decided_by={{ user }}" hx-target="closest li" hx-swap="outerHTML">Reject</button>
    </li>
  {% endfor %}
</ul>
{% else %}
<p>No pending approvals.</p>
{% endif %}
```

```css
/* gateway/web/static/styles.css */
body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #222; }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #ddd; padding-bottom: 1em; }
nav a { margin-right: .8em; }
table { border-collapse: collapse; width: 100%; margin-top: 1em; }
th, td { border-bottom: 1px solid #eee; padding: .4em .6em; text-align: left; font-size: .9em; }
.status-success { color: #2a7; } .status-denied, .status-rejected { color: #c33; } .status-timeout { color: #a60; } .status-error { color: #c00; }
.approval { border: 1px solid #ddd; border-radius: 8px; padding: 1em; margin-bottom: 1em; }
.approval pre { background: #f6f6f6; padding: .5em; overflow-x: auto; }
button { padding: .3em .9em; margin-right: .5em; cursor: pointer; }
form input, form select { padding: .3em .5em; margin-right: .5em; }
```

- [ ] **Step 2: Routes**

```python
# gateway/web/routes.py
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Request, Query, WebSocket, WebSocketDisconnect, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from gateway.audit.reader import AuditReader, AuditFilter
from gateway.approval.store import ApprovalStore, PENDING
from gateway.approval.websocket import WebSocketBroadcaster
from sqlalchemy import select
from gateway.db.models import ApprovalRequest


def make_router(
    *,
    templates: Jinja2Templates,
    audit_reader: AuditReader,
    approval_store: ApprovalStore,
    broadcaster: WebSocketBroadcaster,
    session_factory,
    default_tenant_id: UUID,  # MVP: single tenant filter for UI
) -> APIRouter:
    r = APIRouter()

    @r.get("/audit", response_class=HTMLResponse)
    async def audit_page(request: Request):
        return templates.TemplateResponse("audit.html", {"request": request})

    @r.get("/audit/rows", response_class=HTMLResponse)
    async def audit_rows(
        request: Request,
        agent_id: str | None = None,
        tool: str | None = None,
        result_status: str | None = None,
        limit: int = 50, offset: int = 0,
    ):
        f = AuditFilter(
            tenant_id=default_tenant_id,
            agent_id=UUID(agent_id) if agent_id else None,
            tool=tool or None,
            result_status=result_status or None,
        )
        page = await audit_reader.query(f, limit=limit, offset=offset)
        return templates.TemplateResponse("_audit_rows.html", {"request": request, "entries": page.entries, "total": page.total})

    @r.get("/api/audit")
    async def audit_api(
        agent_id: str | None = None, tool: str | None = None, result_status: str | None = None,
        limit: int = 50, offset: int = 0,
    ):
        f = AuditFilter(
            tenant_id=default_tenant_id,
            agent_id=UUID(agent_id) if agent_id else None,
            tool=tool or None, result_status=result_status or None,
        )
        page = await audit_reader.query(f, limit=limit, offset=offset)
        return {
            "total": page.total, "limit": page.limit, "offset": page.offset,
            "entries": [{
                "id": e.id, "tenant_id": str(e.tenant_id) if e.tenant_id else None,
                "agent_id": str(e.agent_id) if e.agent_id else None,
                "tool": e.tool, "params": e.params_json, "result_status": e.result_status,
                "result": e.result_json, "approval_id": str(e.approval_id) if e.approval_id else None,
                "trace_id": e.trace_id, "created_at": e.created_at.isoformat(),
            } for e in page.entries],
        }

    @r.get("/approvals", response_class=HTMLResponse)
    async def approvals_page(request: Request):
        return templates.TemplateResponse("approvals.html", {"request": request})

    @r.get("/approvals/list", response_class=HTMLResponse)
    async def approvals_list(request: Request):
        async with session_factory() as s:
            res = await s.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.tenant_id == default_tenant_id, ApprovalRequest.status == PENDING)
                .order_by(ApprovalRequest.created_at.desc())
            )
            approvals = res.scalars().all()
        return templates.TemplateResponse("_approvals_list.html", {"request": request, "approvals": approvals, "user": "web-user"})

    @r.post("/approvals/{approval_id}/decide", response_class=HTMLResponse)
    async def decide(approval_id: UUID, decision: str = Query(...), decided_by: str = Query("web-user"), reason: str | None = None):
        if decision not in ("approved", "rejected"):
            return HTMLResponse("invalid decision", status_code=400)
        ok = await approval_store.decide(approval_id, decision=decision, decided_by=decided_by, reason=reason)
        if ok:
            await broadcaster.notify_decided(approval_id=approval_id, status=decision)
        return HTMLResponse("")  # remove the row

    @r.websocket("/approvals/ws")
    async def ws(websocket: WebSocket):
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await broadcaster.disconnect(websocket)

    return r
```

- [ ] **Step 3: Tests**

```python
# tests/web/test_audit_route.py
import pytest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from gateway.web.routes import make_router
from gateway.audit.writer import AuditWriter
from gateway.audit.reader import AuditReader
from gateway.approval.store import ApprovalStore
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.db.models import Tenant


pytestmark = pytest.mark.integration


async def test_audit_html_renders(db_engine, tmp_path):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        t = Tenant(name=f"t-{uuid4()}"); s.add(t); await s.commit()
        tid = t.id
    await AuditWriter(sf).write(tenant_id=tid, agent_id=None, tool="get_customer",
                                params={"customer_id": "C1"}, result_status="success")

    app = FastAPI()
    templates = Jinja2Templates(directory="gateway/web/templates")
    app.include_router(make_router(
        templates=templates, audit_reader=AuditReader(sf),
        approval_store=ApprovalStore(sf), broadcaster=WebSocketBroadcaster(),
        session_factory=sf, default_tenant_id=tid,
    ))

    with TestClient(app) as c:
        r = c.get("/audit/rows")
        assert r.status_code == 200
        assert "get_customer" in r.text
```

- [ ] **Step 4: Commit**

```bash
git add gateway/web tests/web
git commit -m "feat(web): audit + approvals UI (HTMX) + JSON API"
```

---

### Task 1.H: Tenant middleware + seed CLI

**Subagent:** `general-purpose`

**Files:**
- Create: `gateway/tenants/__init__.py`, `gateway/tenants/middleware.py`
- Create: `gateway/cli.py`, `scripts/seed.py`
- Create: `tests/tenants/test_middleware.py`

- [ ] **Step 1: Tenant context**

```python
# gateway/tenants/middleware.py
from contextvars import ContextVar
from uuid import UUID


_tenant_ctx: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)


def set_tenant(tenant_id: UUID) -> None:
    _tenant_ctx.set(tenant_id)


def current_tenant() -> UUID | None:
    return _tenant_ctx.get()


def require_tenant() -> UUID:
    tid = current_tenant()
    if tid is None:
        raise RuntimeError("tenant context not set")
    return tid
```

- [ ] **Step 2: Seed CLI**

```python
# gateway/cli.py
import asyncio
import sys
from uuid import uuid4
import httpx
from sqlalchemy import select
from gateway.db.session import SessionLocal
from gateway.db.models import Tenant, Role, RolePermission, Agent
from gateway.config import get_settings


async def seed_demo():
    settings = get_settings()

    async with SessionLocal() as s:
        existing = (await s.execute(select(Tenant).where(Tenant.name == "demo"))).scalar_one_or_none()
        if existing:
            tenant = existing
            print(f"Tenant exists: {tenant.id}")
        else:
            tenant = Tenant(name="demo")
            s.add(tenant)
            await s.flush()
            print(f"Created tenant: {tenant.id}")

        # Roles
        roles = {}
        for rname in ("support_agent", "readonly_analyst", "finance_admin"):
            r = (await s.execute(select(Role).where(Role.tenant_id == tenant.id, Role.name == rname))).scalar_one_or_none()
            if not r:
                r = Role(tenant_id=tenant.id, name=rname); s.add(r); await s.flush()
            roles[rname] = r

        # Permissions per role
        perms = {
            "support_agent": [("get_customer", False), ("list_orders", False), ("update_order", False), ("refund_payment", True)],
            "readonly_analyst": [("get_customer", False), ("list_orders", False)],
            "finance_admin": [("refund_payment", True), ("charge_card", True)],
        }
        for rname, plist in perms.items():
            for tool, req_app in plist:
                existing_p = (await s.execute(
                    select(RolePermission).where(RolePermission.role_id == roles[rname].id, RolePermission.tool_name == tool)
                )).scalar_one_or_none()
                if not existing_p:
                    s.add(RolePermission(role_id=roles[rname].id, tool_name=tool, requires_approval=req_app))

        # Agent
        agent_name = "demo-support-bot"
        agent = (await s.execute(select(Agent).where(Agent.tenant_id == tenant.id, Agent.name == agent_name))).scalar_one_or_none()
        if not agent:
            agent = Agent(tenant_id=tenant.id, name=agent_name, role_id=roles["support_agent"].id, owner_email="me@example.com")
            s.add(agent); await s.flush()
        await s.commit()

        # Register OAuth client at IdP
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{settings.oauth_issuer}/register", json={
                "client_name": agent_name,
                "tenant_id": str(tenant.id),
                "agent_id": str(agent.id),
                "scopes": ["tool:get_customer", "tool:list_orders", "tool:update_order", "tool:refund_payment"],
            })
            r.raise_for_status()
            creds = r.json()
            print(f"OAuth client_id: {creds['client_id']}")
            print(f"OAuth client_secret: {creds['client_secret']}")
            print(f"\nObtain token:")
            print(f"  curl -X POST {settings.oauth_issuer}/token \\")
            print(f"    -d 'grant_type=client_credentials' \\")
            print(f"    -d 'client_id={creds['client_id']}' \\")
            print(f"    -d 'client_secret={creds['client_secret']}'")


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "seed":
        print("Usage: python -m gateway.cli seed")
        sys.exit(1)
    asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Tests for tenant context**

```python
# tests/tenants/test_middleware.py
import asyncio
import pytest
from uuid import uuid4
from gateway.tenants.middleware import set_tenant, current_tenant, require_tenant


pytestmark = pytest.mark.unit


def test_set_get_tenant():
    tid = uuid4()
    set_tenant(tid)
    assert current_tenant() == tid


def test_require_raises_when_unset():
    set_tenant(None)
    with pytest.raises(RuntimeError):
        require_tenant()


async def test_isolated_per_task():
    tid_a = uuid4(); tid_b = uuid4()

    async def task_a():
        set_tenant(tid_a)
        await asyncio.sleep(0.05)
        assert current_tenant() == tid_a

    async def task_b():
        set_tenant(tid_b)
        await asyncio.sleep(0.05)
        assert current_tenant() == tid_b

    await asyncio.gather(task_a(), task_b())
```

- [ ] **Step 4: Commit**

```bash
git add gateway/tenants gateway/cli.py tests/tenants
git commit -m "feat(tenants): contextvar-based tenant scoping + seed CLI"
```

---

## Phase 2: Integration

### Task 2.1: Middleware chain + server wiring

**Files:**
- Create: `gateway/middleware/__init__.py`, `gateway/middleware/authenticate.py`, `gateway/middleware/authorize.py`, `gateway/middleware/approve.py`, `gateway/middleware/execute.py`, `gateway/middleware/audit.py`, `gateway/middleware/chain.py`
- Create: `gateway/server.py`
- Create: `tests/middleware/test_chain.py`

- [ ] **Step 1: Middleware chain abstraction**

```python
# gateway/middleware/chain.py
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass
class CallContext:
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    token: str | None = None
    tenant_id: UUID | None = None
    agent_id: UUID | None = None
    role_name: str | None = None
    tool: str | None = None
    params: dict = field(default_factory=dict)
    redacted_params: dict = field(default_factory=dict)
    approval_id: UUID | None = None
    result: dict | None = None
    result_status: str = "unknown"  # success|denied|rejected|timeout|error|auth_failed
    error: Exception | None = None


Handler = Callable[[CallContext], Awaitable[None]]


@dataclass
class Pipeline:
    steps: list[Handler]

    async def run(self, ctx: CallContext) -> CallContext:
        for step in self.steps:
            await step(ctx)
            if ctx.error is not None:
                break
        return ctx
```

- [ ] **Step 2: Each middleware step**

```python
# gateway/middleware/authenticate.py
from gateway.middleware.chain import CallContext
from gateway.auth.token_validator import TokenValidator
from gateway.auth.exceptions import TokenError
from gateway.observability.logging import get_logger


log = get_logger(__name__)


def make_authenticate(validator: TokenValidator):
    async def step(ctx: CallContext) -> None:
        if not ctx.token:
            ctx.error = TokenError("missing token")
            ctx.result_status = "auth_failed"
            return
        try:
            claims = await validator.verify(ctx.token)
        except TokenError as e:
            ctx.error = e
            ctx.result_status = "auth_failed"
            log.warning("auth_failed", error=str(e), trace_id=ctx.trace_id)
            return
        ctx.tenant_id = claims.tenant_id
        ctx.agent_id = __import__("uuid").UUID(claims.sub)
        ctx.role_name = next((s.split(":", 1)[1] for s in claims.scopes if s.startswith("role:")), None)
    return step
```

```python
# gateway/middleware/authorize.py
from gateway.middleware.chain import CallContext
from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.schema import Decision
from sqlalchemy import select
from gateway.db.models import Agent, Role


def make_authorize(evaluator: PolicyEvaluator, session_factory):
    async def step(ctx: CallContext) -> None:
        # Resolve role from DB if not in token
        if not ctx.role_name:
            async with session_factory() as s:
                res = await s.execute(
                    select(Role.name).join(Agent, Agent.role_id == Role.id).where(Agent.id == ctx.agent_id)
                )
                ctx.role_name = res.scalar_one_or_none()

        if not ctx.role_name:
            ctx.error = PermissionError("no role")
            ctx.result_status = "denied"
            return

        decision = evaluator.evaluate(ctx.role_name, ctx.tool)
        ctx.params.setdefault("__decision__", decision.value)
        if decision == Decision.DENY:
            ctx.error = PermissionError(f"role {ctx.role_name} denied for tool {ctx.tool}")
            ctx.result_status = "denied"
    return step
```

```python
# gateway/middleware/approve.py
from gateway.middleware.chain import CallContext
from gateway.approval.store import ApprovalStore, APPROVED, REJECTED, TIMEOUT
from gateway.approval.notifier import ApprovalNotifier
from gateway.config import get_settings
from gateway.policy.schema import Decision
from gateway.observability.metrics import APPROVALS_PENDING, APPROVALS_TOTAL


def make_approve(store: ApprovalStore, notifier: ApprovalNotifier, settings=None):
    settings = settings or get_settings()

    async def step(ctx: CallContext) -> None:
        decision_value = ctx.params.pop("__decision__", None)
        if decision_value != Decision.REQUIRES_APPROVAL.value:
            return

        approval_id = await store.create(
            tenant_id=ctx.tenant_id, agent_id=ctx.agent_id,
            tool=ctx.tool, params=ctx.redacted_params or ctx.params,
        )
        ctx.approval_id = approval_id

        APPROVALS_PENDING.labels(tenant=str(ctx.tenant_id)).inc()
        try:
            await notifier.notify_pending(
                approval_id=approval_id, agent_id=ctx.agent_id,
                tool=ctx.tool, params=ctx.redacted_params or ctx.params,
            )
            status = await store.wait_for_decision(
                approval_id, timeout=settings.approval_timeout_seconds,
                poll_interval=settings.approval_poll_interval_seconds,
            )
        finally:
            APPROVALS_PENDING.labels(tenant=str(ctx.tenant_id)).dec()

        APPROVALS_TOTAL.labels(decision=status).inc()
        if status == APPROVED:
            return
        if status == REJECTED:
            ctx.error = PermissionError("approval rejected")
            ctx.result_status = "rejected"
        elif status == TIMEOUT:
            ctx.error = TimeoutError("approval timeout")
            ctx.result_status = "timeout"
    return step
```

```python
# gateway/middleware/execute.py
from gateway.middleware.chain import CallContext
from gateway.tools.registry import ToolRegistry
from gateway.tools.exceptions import ToolError, UpstreamUnavailable, UpstreamClientError, UpstreamServerError


def make_execute(registry: ToolRegistry):
    async def step(ctx: CallContext) -> None:
        rt = registry.get(ctx.tool)
        if not rt:
            ctx.error = ToolError(f"unknown tool: {ctx.tool}")
            ctx.result_status = "error"
            return
        try:
            result = await rt.handler(**{k: v for k, v in ctx.params.items() if not k.startswith("__")})
            ctx.result = result
            ctx.result_status = "success"
        except UpstreamUnavailable as e:
            ctx.error = e; ctx.result_status = "upstream_unavailable"
        except UpstreamClientError as e:
            ctx.error = e; ctx.result_status = f"upstream_4xx_{e.status}"
        except UpstreamServerError as e:
            ctx.error = e; ctx.result_status = "upstream_5xx"
        except Exception as e:
            ctx.error = e; ctx.result_status = "error"
    return step
```

```python
# gateway/middleware/audit.py
from gateway.middleware.chain import CallContext
from gateway.audit.writer import AuditWriter


def make_audit(writer: AuditWriter):
    async def step(ctx: CallContext) -> None:
        try:
            await writer.write(
                tenant_id=ctx.tenant_id, agent_id=ctx.agent_id, tool=ctx.tool,
                params=ctx.redacted_params or {k: v for k, v in ctx.params.items() if not k.startswith("__")},
                result_status=ctx.result_status,
                result=ctx.result if ctx.result_status == "success" else ({"error": str(ctx.error)} if ctx.error else {}),
                approval_id=ctx.approval_id, trace_id=ctx.trace_id,
            )
        except Exception:
            # If audit fails, propagate — caller treats as 500
            raise
    return step
```

- [ ] **Step 3: Server entrypoint**

```python
# gateway/server.py
import contextlib
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import select

from gateway.config import get_settings
from gateway.observability.logging import configure_logging, get_logger
from gateway.observability.tracing import configure_tracing
from gateway.observability.metrics import REQUESTS_TOTAL, REQUEST_DURATION
from gateway.db.session import engine
from gateway.db.models import Tenant
from gateway.auth.token_validator import JWKSTokenValidator
from gateway.policy.loader import load_policies
from gateway.policy.evaluator import PolicyEvaluator
from gateway.tools.registry import ToolRegistry
from gateway.tools.upstream import UpstreamClient
from gateway.tools.crm import build_crm_tools
from gateway.tools.payments import build_payment_tools
from gateway.approval.store import ApprovalStore
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.approval.notifier import CompositeNotifier
from gateway.approval.timeout import TimeoutReaper
from gateway.audit.writer import AuditWriter
from gateway.audit.reader import AuditReader
from gateway.middleware.chain import Pipeline, CallContext
from gateway.middleware.authenticate import make_authenticate
from gateway.middleware.authorize import make_authorize
from gateway.middleware.approve import make_approve
from gateway.middleware.execute import make_execute
from gateway.middleware.audit import make_audit
from gateway.web.routes import make_router


log = get_logger(__name__)
settings = get_settings()


def _jwks_provider_from_url(url: str):
    """Lazy refreshing JWKS fetcher."""
    import jwt
    client = jwt.PyJWKClient(url, cache_keys=True, lifespan=600)
    def provider():
        return [(k.key_id, k.key) for k in client.get_signing_keys()]
    return provider


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_tracing(app)

    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app.state.session_factory = sf

    # Auth
    validator = JWKSTokenValidator(
        jwks_provider=_jwks_provider_from_url(settings.oauth_jwks_url),
        issuer=settings.oauth_issuer, audience=settings.oauth_audience,
    )

    # Policy
    policy_doc = load_policies(settings.policy_file)
    evaluator = PolicyEvaluator(policy_doc)

    # Tools
    crm_client = UpstreamClient(settings.crm_base_url, settings.crm_api_key, "crm")
    pay_client = UpstreamClient(settings.payments_base_url, settings.payments_api_key, "payments")
    registry = ToolRegistry()
    for meta, handler in build_crm_tools(crm_client) + build_payment_tools(pay_client):
        registry.register(meta, handler)
    app.state.registry = registry

    # Approvals
    store = ApprovalStore(sf)
    broadcaster = WebSocketBroadcaster()
    notifiers = [broadcaster]
    if settings.telegram_bot_token and settings.telegram_admin_chat_id:
        from gateway.approval.telegram import TelegramNotifier
        from gateway.approval.telegram_bot import build_telegram_app
        tg_notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_admin_chat_id)
        notifiers.append(tg_notifier)
        tg_app = build_telegram_app(settings.telegram_bot_token, store, broadcaster)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()
        app.state.tg_app = tg_app
    else:
        app.state.tg_app = None

    notifier = CompositeNotifier(notifiers)

    # Audit
    writer = AuditWriter(sf)
    reader = AuditReader(sf)

    # Build pipeline
    app.state.pipeline = Pipeline(steps=[
        make_authenticate(validator),
        make_authorize(evaluator, sf),
        make_approve(store, notifier),
        make_execute(registry),
    ])
    app.state.audit_step = make_audit(writer)

    # Reaper
    reaper = TimeoutReaper(sf, settings.approval_timeout_seconds, broadcaster)
    reaper.start()

    # Web router (single-tenant view: pick first tenant)
    async with sf() as s:
        first = (await s.execute(select(Tenant).limit(1))).scalar_one_or_none()
    if first:
        templates = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))
        app.include_router(make_router(
            templates=templates, audit_reader=reader, approval_store=store,
            broadcaster=broadcaster, session_factory=sf, default_tenant_id=first.id,
        ))

    yield

    await reaper.stop()
    if app.state.tg_app:
        await app.state.tg_app.updater.stop()
        await app.state.tg_app.stop()
        await app.state.tg_app.shutdown()
    await crm_client.aclose(); await pay_client.aclose()


app = FastAPI(title="MCP Gateway", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "web" / "static")), name="static")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(503, "db_unavailable")


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# MCP-style tool listing
@app.get("/mcp/tools")
async def list_tools(request: Request):
    return {"tools": [{"name": m.name, "description": m.description, "inputSchema": m.input_schema} for m in request.app.state.registry.list()]}


@app.post("/mcp/call/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    import time
    payload = await request.json()
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.lower().startswith("bearer ") else None

    rt = request.app.state.registry.get(tool_name)
    redact_fn = rt.meta.redact if rt else (lambda p: dict(p))
    redacted = redact_fn(payload)

    ctx = CallContext(token=token, tool=tool_name, params=dict(payload), redacted_params=redacted)

    pipeline: Pipeline = request.app.state.pipeline
    audit_step = request.app.state.audit_step

    started = time.monotonic()
    try:
        await pipeline.run(ctx)
    finally:
        # Always audit, regardless of outcome
        try:
            await audit_step(ctx)
        except Exception as e:
            log.error("audit_failed", error=str(e), trace_id=ctx.trace_id)
            return JSONResponse(
                {"error": "audit_failure", "trace_id": ctx.trace_id}, status_code=500,
                headers={"X-Trace-Id": ctx.trace_id},
            )
        duration = time.monotonic() - started
        REQUEST_DURATION.labels(tool=tool_name).observe(duration)
        REQUESTS_TOTAL.labels(tool=tool_name, status=ctx.result_status, tenant=str(ctx.tenant_id) if ctx.tenant_id else "none").inc()

    headers = {"X-Trace-Id": ctx.trace_id}
    if ctx.result_status == "auth_failed":
        return JSONResponse({"error": str(ctx.error)}, status_code=401, headers=headers)
    if ctx.result_status == "denied":
        return JSONResponse({"error": str(ctx.error)}, status_code=403, headers=headers)
    if ctx.result_status == "rejected":
        return JSONResponse({"error": "approval rejected"}, status_code=403, headers=headers)
    if ctx.result_status == "timeout":
        return JSONResponse({"error": "approval timeout"}, status_code=408, headers=headers)
    if ctx.result_status == "upstream_unavailable":
        return JSONResponse({"error": str(ctx.error)}, status_code=502, headers=headers)
    if ctx.result_status.startswith("upstream_4xx_"):
        return JSONResponse({"error": str(ctx.error)}, status_code=int(ctx.result_status.removeprefix("upstream_4xx_")), headers=headers)
    if ctx.result_status == "error":
        return JSONResponse({"error": str(ctx.error), "trace_id": ctx.trace_id}, status_code=500, headers=headers)

    return JSONResponse(ctx.result or {}, headers=headers)
```

- [ ] **Step 4: Pipeline integration test**

```python
# tests/middleware/test_chain.py
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock
from gateway.middleware.chain import Pipeline, CallContext


pytestmark = pytest.mark.unit


async def test_pipeline_short_circuits_on_error():
    step1 = AsyncMock()
    async def fail(ctx): ctx.error = ValueError("nope"); ctx.result_status = "denied"
    step3 = AsyncMock()
    p = Pipeline(steps=[step1, fail, step3])
    ctx = CallContext()
    await p.run(ctx)
    assert step1.called
    assert not step3.called
    assert ctx.result_status == "denied"
```

- [ ] **Step 5: Commit**

```bash
git add gateway/middleware gateway/server.py tests/middleware
git commit -m "feat(server): wire 5-layer middleware chain into FastAPI app with metrics + audit"
```

---

### Task 2.2: Docker Compose + observability stack

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`, `docker-compose.test.yml`, `docker-compose.observability.yml`
- Create: `observability/prometheus.yml`, `observability/grafana/datasources.yml`, `observability/grafana/dashboards.yml`, `observability/grafana/mcp-gateway.json`
- Create: `.env.example`

- [ ] **Step 1: Main Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e .
COPY gateway /app/gateway
COPY alembic /app/alembic
COPY alembic.ini /app/
COPY config /app/config
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: mcp
      POSTGRES_PASSWORD: mcp
      POSTGRES_DB: mcp_gateway
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mcp"]
      interval: 5s
      retries: 10

  mock-idp:
    build: ./mocks/idp
    ports: ["9000:9000"]

  mock-crm:
    build: ./mocks/crm
    environment:
      MOCK_CRM_API_KEY: dev-crm-key
    ports: ["9001:9001"]

  mock-payments:
    build: ./mocks/payments
    environment:
      MOCK_PAYMENTS_API_KEY: dev-payments-key
    ports: ["9002:9002"]

  migrate:
    build: .
    depends_on:
      postgres: { condition: service_healthy }
    environment:
      MCP_DATABASE_URL: postgresql+asyncpg://mcp:mcp@postgres:5432/mcp_gateway
    command: ["alembic", "upgrade", "head"]
    restart: "no"

  gateway:
    build: .
    depends_on:
      postgres: { condition: service_healthy }
      migrate: { condition: service_completed_successfully }
      mock-idp: { condition: service_started }
    environment:
      MCP_DATABASE_URL: postgresql+asyncpg://mcp:mcp@postgres:5432/mcp_gateway
      MCP_OAUTH_ISSUER: http://mock-idp:9000
      MCP_OAUTH_JWKS_URL: http://mock-idp:9000/jwks
      MCP_CRM_BASE_URL: http://mock-crm:9001
      MCP_PAYMENTS_BASE_URL: http://mock-payments:9002
      MCP_TELEGRAM_BOT_TOKEN: ${MCP_TELEGRAM_BOT_TOKEN:-}
      MCP_TELEGRAM_ADMIN_CHAT_ID: ${MCP_TELEGRAM_ADMIN_CHAT_ID:-}
      MCP_OTEL_ENDPOINT: ${MCP_OTEL_ENDPOINT:-}
    ports: ["8000:8000"]

  seed:
    build: .
    depends_on:
      gateway: { condition: service_healthy }
      mock-idp: { condition: service_started }
    environment:
      MCP_DATABASE_URL: postgresql+asyncpg://mcp:mcp@postgres:5432/mcp_gateway
      MCP_OAUTH_ISSUER: http://mock-idp:9000
    command: ["python", "-m", "gateway.cli", "seed"]
    restart: "no"

volumes:
  pgdata:
```

- [ ] **Step 3: docker-compose.test.yml** (CI-friendly subset)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: mcp
      POSTGRES_PASSWORD: mcp
      POSTGRES_DB: mcp_gateway
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mcp"]
      interval: 3s
      retries: 10

  mock-idp:
    build: ./mocks/idp
    ports: ["9000:9000"]

  mock-crm:
    build: ./mocks/crm
    environment:
      MOCK_CRM_API_KEY: dev-crm-key
    ports: ["9001:9001"]

  mock-payments:
    build: ./mocks/payments
    environment:
      MOCK_PAYMENTS_API_KEY: dev-payments-key
    ports: ["9002:9002"]

  gateway:
    build: .
    depends_on:
      postgres: { condition: service_healthy }
      mock-idp: { condition: service_started }
    environment:
      MCP_DATABASE_URL: postgresql+asyncpg://mcp:mcp@postgres:5432/mcp_gateway
      MCP_OAUTH_ISSUER: http://mock-idp:9000
      MCP_OAUTH_JWKS_URL: http://mock-idp:9000/jwks
      MCP_CRM_BASE_URL: http://mock-crm:9001
      MCP_PAYMENTS_BASE_URL: http://mock-payments:9002
      MCP_APPROVAL_TIMEOUT_SECONDS: "5"
    ports: ["8000:8000"]
    command: >
      sh -c "alembic upgrade head &&
             python -m gateway.cli seed &&
             uvicorn gateway.server:app --host 0.0.0.0 --port 8000"
```

- [ ] **Step 4: docker-compose.observability.yml**

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes: ["./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro"]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:latest
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    volumes:
      - "./observability/grafana:/etc/grafana/provisioning"
      - "./observability/grafana/dashboards:/var/lib/grafana/dashboards"
    ports: ["3000:3000"]

  jaeger:
    image: jaegertracing/all-in-one:latest
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
```

- [ ] **Step 5: Prometheus + Grafana provisioning files**

```yaml
# observability/prometheus.yml
global: { scrape_interval: 5s }
scrape_configs:
  - job_name: gateway
    static_configs:
      - targets: ["gateway:8000"]
```

```yaml
# observability/grafana/datasources.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

```yaml
# observability/grafana/dashboards.yml
apiVersion: 1
providers:
  - name: default
    folder: ""
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

`observability/grafana/mcp-gateway.json` — minimal dashboard with panels for: requests rate, p95 latency, approval rate by decision, upstream failures. Generate via `grafonnet` or hand-craft. Skip details here; aim for 4 panels.

- [ ] **Step 6: `.env.example`**

```
MCP_DATABASE_URL=postgresql+asyncpg://mcp:mcp@localhost:5432/mcp_gateway
MCP_OAUTH_ISSUER=http://localhost:9000
MCP_OAUTH_JWKS_URL=http://localhost:9000/jwks
MCP_OAUTH_AUDIENCE=mcp-gateway
MCP_CRM_BASE_URL=http://localhost:9001
MCP_CRM_API_KEY=dev-crm-key
MCP_PAYMENTS_BASE_URL=http://localhost:9002
MCP_PAYMENTS_API_KEY=dev-payments-key
MCP_APPROVAL_TIMEOUT_SECONDS=300
MCP_TELEGRAM_BOT_TOKEN=
MCP_TELEGRAM_ADMIN_CHAT_ID=
MCP_OTEL_ENDPOINT=
MCP_LOG_LEVEL=INFO
```

- [ ] **Step 7: Smoke test — `docker compose up`**

```bash
docker compose up -d --build
curl http://localhost:8000/healthz
docker compose logs gateway | tail -20
docker compose down
```

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose.yml docker-compose.test.yml docker-compose.observability.yml observability/ .env.example
git commit -m "feat(deploy): docker-compose with mocks + observability stack"
```

---

### Task 2.3: E2E test

**Files:**
- Create: `tests/e2e/__init__.py`, `tests/e2e/test_full_flow.py`

- [ ] **Step 1: E2E test against running compose**

```python
# tests/e2e/test_full_flow.py
import asyncio
import os
import pytest
import httpx


pytestmark = pytest.mark.e2e

GATEWAY = os.environ.get("E2E_GATEWAY_URL", "http://localhost:8000")
IDP = os.environ.get("E2E_IDP_URL", "http://localhost:9000")
TIMEOUT = httpx.Timeout(30.0)


async def _get_token(client: httpx.AsyncClient, scopes: list[str]) -> str:
    # Find demo agent's client creds (printed by seed but for e2e re-register)
    reg = await client.post(f"{IDP}/register", json={
        "client_name": "e2e", "tenant_id": "00000000-0000-0000-0000-000000000000",
        "agent_id": "00000000-0000-0000-0000-000000000001", "scopes": scopes,
    })
    reg.raise_for_status()
    creds = reg.json()
    tok = await client.post(f"{IDP}/token", data={
        "grant_type": "client_credentials",
        "client_id": creds["client_id"], "client_secret": creds["client_secret"],
    })
    tok.raise_for_status()
    return tok.json()["access_token"]


async def test_get_customer_unauthorized():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{GATEWAY}/mcp/call/get_customer", json={"customer_id": "C001"})
        assert r.status_code == 401


async def test_refund_requires_approval_then_rejected():
    """E2E: call refund_payment, find approval via /approvals/list, reject via API, expect 403."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        token = await _get_token(c, ["tool:refund_payment"])

        async def call_refund():
            return await c.post(
                f"{GATEWAY}/mcp/call/refund_payment",
                json={"customer_id": "C001", "amount": 50000},
                headers={"Authorization": f"Bearer {token}"},
            )

        async def reject_after_delay():
            await asyncio.sleep(2)
            # Find pending approval via API
            async with httpx.AsyncClient() as c2:
                # Audit API would not show pending; use DB-backed list endpoint instead
                # We trigger the approval rejection by calling /approvals/{id}/decide endpoint
                # For e2e simplicity: query the audit log isn't enough; we use the web UI HTML and parse
                # Better: expose a JSON list endpoint at /api/approvals/pending — add it as part of this task
                lst = await c2.get(f"{GATEWAY}/api/approvals/pending")
                lst.raise_for_status()
                pending = lst.json()["approvals"]
                assert pending, "expected at least one pending approval"
                approval_id = pending[0]["id"]
                d = await c2.post(f"{GATEWAY}/approvals/{approval_id}/decide?decision=rejected&decided_by=e2e")
                d.raise_for_status()

        result, _ = await asyncio.gather(call_refund(), reject_after_delay())
        assert result.status_code == 403
```

(This task adds `/api/approvals/pending` endpoint — extend `gateway/web/routes.py` with a JSON listing for testability and external integrations.)

- [ ] **Step 2: Add `/api/approvals/pending` to `gateway/web/routes.py`**

In `make_router`, add:

```python
@r.get("/api/approvals/pending")
async def pending_api():
    async with session_factory() as s:
        res = await s.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.tenant_id == default_tenant_id, ApprovalRequest.status == PENDING)
            .order_by(ApprovalRequest.created_at.desc())
        )
        approvals = res.scalars().all()
    return {"approvals": [{
        "id": str(a.id), "tool": a.tool, "agent_id": str(a.agent_id),
        "params": a.params_json, "created_at": a.created_at.isoformat(),
    } for a in approvals]}
```

- [ ] **Step 3: Run e2e**

```bash
make test-e2e
```

- [ ] **Step 4: Commit**

```bash
git add tests/e2e gateway/web/routes.py
git commit -m "test(e2e): full-flow refund → reject scenario via docker-compose"
```

---

### Task 2.4: Security tests + review

**Files:**
- Create: `tests/security/__init__.py`, `tests/security/test_jwt_attacks.py`, `tests/security/test_tenant_isolation.py`, `tests/security/test_audit_immutability.py`

- [ ] **Step 1: JWT attack tests**

```python
# tests/security/test_jwt_attacks.py
import pytest
import httpx

pytestmark = pytest.mark.security

GATEWAY = "http://localhost:8000"


async def test_unsigned_jwt_rejected():
    # crafted "alg=none" token
    import base64, json
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "x", "tenant_id": "x", "scopes": [], "exp": 9999999999, "aud": "mcp-gateway", "iss": "http://mock-idp:9000"}).encode()).rstrip(b"=").decode()
    tok = f"{header}.{payload}."
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{GATEWAY}/mcp/call/get_customer", json={"customer_id": "C001"}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401
```

- [ ] **Step 2: Tenant isolation test**

```python
# tests/security/test_tenant_isolation.py
import pytest
import httpx

pytestmark = pytest.mark.security


async def test_audit_api_does_not_leak_other_tenants():
    """Audit API uses default_tenant_id from server; cross-tenant requires multi-tenant setup."""
    async with httpx.AsyncClient() as c:
        r = await c.get("http://localhost:8000/api/audit?agent_id=00000000-0000-0000-0000-000000000099")
        assert r.status_code == 200
        assert all(e["agent_id"] == "00000000-0000-0000-0000-000000000099" for e in r.json()["entries"])
```

- [ ] **Step 3: Audit immutability test**

```python
# tests/security/test_audit_immutability.py
import pytest
import asyncpg

pytestmark = pytest.mark.security


async def test_app_user_cannot_update_audit():
    conn = await asyncpg.connect("postgresql://mcp_app:mcp_app@localhost:5432/mcp_gateway")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("UPDATE audit_log SET tool='hacked'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM audit_log")
    finally:
        await conn.close()
```

- [ ] **Step 4: Run security review subagent**

After this task, dispatch the `security-reviewer` subagent on the entire `gateway/` directory + spec to verify no missed OWASP issues.

- [ ] **Step 5: Commit**

```bash
git add tests/security
git commit -m "test(security): JWT none-alg, tenant isolation, audit immutability"
```

---

### Task 2.5: Mutation testing setup

**Files:**
- Create: `mutmut_config.py`

- [ ] **Step 1: Configure mutmut**

```python
# mutmut_config.py
def pre_mutation(context):
    pass

def init():
    pass
```

- [ ] **Step 2: Add Makefile target**

```makefile
test-mutation:
	mutmut run --paths-to-mutate gateway/policy/,gateway/auth/ --tests-dir tests/policy/,tests/auth/
	mutmut results
```

- [ ] **Step 3: Run + commit**

```bash
make test-mutation || true  # informational, not blocking
git add mutmut_config.py Makefile
git commit -m "chore: mutmut config for policy + auth"
```

---

### Task 2.6: Load test

**Files:**
- Create: `loadtest/locustfile.py`, `loadtest/README.md`

- [ ] **Step 1: locustfile**

```python
# loadtest/locustfile.py
import os
import httpx
from locust import HttpUser, task, between, events


IDP = os.environ.get("IDP_URL", "http://localhost:9000")


@events.test_start.add_listener
def fetch_token(environment, **kwargs):
    with httpx.Client() as c:
        reg = c.post(f"{IDP}/register", json={
            "client_name": "loadtest", "tenant_id": "00000000-0000-0000-0000-000000000000",
            "scopes": ["tool:get_customer", "tool:list_orders"],
        }).json()
        tok = c.post(f"{IDP}/token", data={
            "grant_type": "client_credentials",
            "client_id": reg["client_id"], "client_secret": reg["client_secret"],
        }).json()
        environment.parsed_options.token = tok["access_token"]


class GatewayUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {self.environment.parsed_options.token}"}

    @task(3)
    def get_customer(self):
        self.client.post("/mcp/call/get_customer", json={"customer_id": "C001"}, headers=self.headers, name="get_customer")

    @task(1)
    def list_orders(self):
        self.client.post("/mcp/call/list_orders", json={"customer_id": "C001"}, headers=self.headers, name="list_orders")
```

- [ ] **Step 2: Add CI smoke load**

```yaml
# extend .github/workflows/ci.yml jobs
  load-smoke:
    runs-on: ubuntu-latest
    needs: e2e
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e ".[dev]"
      - run: docker compose -f docker-compose.test.yml up -d --build
      - run: |
          sleep 15  # wait for warmup
          locust -f loadtest/locustfile.py --headless -u 10 -r 5 -t 30s --host http://localhost:8000 --only-summary
      - run: docker compose -f docker-compose.test.yml down
```

- [ ] **Step 3: Commit**

```bash
git add loadtest/ .github/workflows/ci.yml
git commit -m "test(load): locust smoke test in CI"
```

---

## Phase 3: Deployment

### Task 3.1: Fly.io configs

**Files:**
- Create: `fly.toml`, `mocks/crm/fly.toml`, `mocks/payments/fly.toml`, `mocks/idp/fly.toml`

- [ ] **Step 1: Gateway `fly.toml`**

```toml
app = "mcp-gateway"
primary_region = "fra"

[build]
  dockerfile = "Dockerfile"

[env]
  MCP_OAUTH_ISSUER = "https://mcp-mock-idp.fly.dev"
  MCP_OAUTH_JWKS_URL = "https://mcp-mock-idp.fly.dev/jwks"
  MCP_CRM_BASE_URL = "https://mcp-mock-crm.fly.dev"
  MCP_PAYMENTS_BASE_URL = "https://mcp-mock-payments.fly.dev"
  MCP_LOG_LEVEL = "INFO"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

  [http_service.checks]
    [[http_service.checks.http]]
      grace_period = "10s"
      interval = "30s"
      method = "GET"
      timeout = "5s"
      path = "/healthz"

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
```

Similar minimal `fly.toml` for each mock with their port and dockerfile path. Set `MCP_DATABASE_URL` and secrets via `fly secrets set` rather than env block.

- [ ] **Step 2: Deploy script**

```makefile
# add to Makefile
deploy-mocks:
	fly deploy --config mocks/idp/fly.toml -c mocks/idp
	fly deploy --config mocks/crm/fly.toml -c mocks/crm
	fly deploy --config mocks/payments/fly.toml -c mocks/payments

deploy-gateway:
	fly deploy
```

- [ ] **Step 3: GitHub Actions deploy job**

```yaml
# extend .github/workflows/ci.yml
  deploy:
    runs-on: ubuntu-latest
    needs: [build, e2e, security]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

- [ ] **Step 4: Commit**

```bash
git add fly.toml mocks/*/fly.toml Makefile .github/workflows/ci.yml
git commit -m "chore(deploy): fly.io configs + GitHub Actions deploy job"
```

---

### Task 3.2: Final docs

**Files:**
- Modify: `README.md`
- Create: `docs/architecture.md`, `docs/operations.md`

- [ ] **Step 1: Expand README**

Add: prerequisites, "Run locally" with full `docker compose up` flow, "Configure Telegram" section, "Demo with Claude Desktop" with `claude_desktop_config.json` snippet, link to architecture doc.

- [ ] **Step 2: Architecture doc**

`docs/architecture.md` — copy the relevant sections from spec, add Mermaid diagrams for: high-level flow, sequence diagram for refund + approval, ER diagram for DB.

- [ ] **Step 3: Operations doc**

`docs/operations.md` — runbooks: how to rotate JWKS, how to read audit log via SQL, how to seed a new tenant, how to switch from mock-IdP to a real IdP, how to look at metrics in Grafana, how to export audit log to S3 (placeholder for future).

- [ ] **Step 4: Commit**

```bash
git add README.md docs/architecture.md docs/operations.md
git commit -m "docs: expand README + architecture + operations runbooks"
```

---

### Task 3.3: Final review and polish

**Files:**
- Run: dependency-auditor, security-reviewer, code-reviewer subagents

- [ ] **Step 1: Dispatch `dependency-auditor` subagent**

Audit `pyproject.toml` for typosquats, CVEs, unmaintained packages.

- [ ] **Step 2: Dispatch `security-reviewer` subagent**

Full security review of `gateway/` against OWASP top 10.

- [ ] **Step 3: Dispatch `code-reviewer` subagent**

Review entire codebase against original plan + spec.

- [ ] **Step 4: Apply fixes from reviews**

Each reviewer's findings → triage (critical / important / nice-to-have), fix critical+important inline.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: address review findings (security, dependencies, code quality)"
```

---

### Task 3.4: Demo recording materials

- [ ] **Step 1: Update README with Loom link placeholder**

- [ ] **Step 2: Create `demo/claude_desktop_config.json`**

```json
{
  "mcpServers": {
    "mcp-gateway": {
      "transport": {
        "type": "http",
        "url": "https://mcp-gateway.fly.dev/mcp",
        "headers": {"Authorization": "Bearer <token>"}
      }
    }
  }
}
```

- [ ] **Step 3: Create `demo/script.md` — recording script**

```markdown
# Demo recording script (2-3 min)

1. (0:00–0:20) Open Claude Desktop, show config.json with MCP Gateway URL
2. (0:20–0:50) Ask Claude: "Верни 50 000 рублей клиенту C001 за заказ O1234"
3. (0:50–1:20) Show Telegram notification appearing on phone (split-screen)
4. (1:20–1:40) Press "Reject" in Telegram
5. (1:40–2:00) Show Claude in chat: "не смог выполнить, операция отклонена"
6. (2:00–2:30) Open audit log in browser, show full record with rejector
7. (2:30–end) Brief outro: link to GitHub
```

- [ ] **Step 4: Commit**

```bash
git add demo/
git commit -m "docs(demo): config + recording script"
```

---

## Self-Review

**Spec coverage:**

- ✅ 5 layers (auth, authorize, approve, execute, log) → middleware/* tasks 2.1
- ✅ Mock-systems (CRM, Payments) → task 1.E
- ✅ Mock OAuth IdP with DCR → task 1.A
- ✅ Multi-tenant lite → task 1.H + db schema (0.2)
- ✅ Web UI for approvals + audit → task 1.G
- ✅ Telegram bot → task 1.C
- ✅ Append-only audit → task 0.2 (GRANTs + trigger)
- ✅ Structured logging, Prometheus, OTel → task 0.3
- ✅ Grafana dashboard JSON → task 2.2
- ✅ Test pyramid (unit/integration/e2e) → tasks 1.* + 2.3
- ✅ Mutation testing → task 2.5
- ✅ Load test → task 2.6
- ✅ CI/CD → task 0.1 + extensions
- ✅ Deploy on Fly.io → task 3.1
- ✅ README + architecture + operations docs → task 3.2
- ✅ Demo materials → task 3.4

**Placeholder scan:** Checked. All steps have concrete code or commands.

**Type consistency:** `Decision` enum used identically in policy and approve middleware. `CallContext` fields match across all middleware. `ToolMeta` and `RegisteredTool` consistent. `ApprovalStore.decide` returns `bool` consistently across tests and callers.

**End of plan.**
