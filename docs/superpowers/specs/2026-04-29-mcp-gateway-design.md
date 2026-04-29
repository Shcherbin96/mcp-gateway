# MCP Gateway — Design Document

**Status:** Draft for approval
**Date:** 2026-04-29
**Author:** roman (с Claude Opus 4.7)
**Source spec:** `02-mcp-gateway.md`

---

## 1. Цель и scope

Production-grade MCP-сервер, выступающий защищённым шлюзом между AI-агентами и внутренними системами компании. Каждый tool call проходит через 5 слоёв: authenticate → authorize → approve → execute → log.

**Что в scope:**

- Полная имплементация всех 5 слоёв
- Mock-системы (CRM, Payments) как отдельные сервисы
- Mock OAuth IdP (с возможностью замены на реальный)
- Multi-tenant модель данных (lite — без admin UI)
- Web UI для approvals и audit log
- Telegram-бот для approval-уведомлений
- Структурное логирование, Prometheus-метрики, OpenTelemetry-трейсинг, Grafana-дашборд
- Полная test-пирамида (unit, integration, e2e), mutation testing на critical модулях, locust load test
- CI через GitHub Actions, деплой на Fly.io

**Что вне scope (явно):**

- Реальная интеграция с production CRM/payments — только mock-сервисы
- Tenant management UI — тенанты создаются через CLI/seed
- Биллинг и rate-limiting per-tenant
- Schema-per-tenant изоляция в Postgres (используем `tenant_id` row-level фильтры)
- React/Next-фронтенд — UI на server-rendered Jinja + HTMX
- Slack-бот — оставлено как pluggable interface для будущего

---

## 2. Принятые решения (по итогам брейншторма)

| # | Тема | Решение | Обоснование |
|---|------|---------|-------------|
| 1 | Глубина | Production-ready | Hiring signal — «production engineer» |
| 2 | Mocks | Отдельные FastAPI-сервисы | Реалистичные сетевые ошибки, retry, timeouts |
| 3 | OAuth | Mock IdP + pluggable arch | Демонстрирует знание spec без перебора |
| 4 | Approval | Telegram + Web UI | Красиво на видео + интерактивно для ревьюера |
| 5 | Audit | Web UI + JSON API | UI для людей, API для compliance/SIEM |
| 6 | Tenancy | Multi-tenant lite | SaaS-thinking без overengineering |
| 7 | Структура | Gateway+UI один пакет, mocks отдельно | Корректные service boundaries |
| 8 | Tests/Obs | Расширенный (OTel, Grafana, locust, mutmut) | Полный production toolkit |
| 9 | Deploy | Fly.io | Free tier, managed Postgres, простой CLI |

---

## 3. Высокоуровневая архитектура

```
                                  ┌─ Telegram bot (notifier)
                                  ├─ Web UI (approvals + audit)
                                  │     └─ HTMX, Jinja2
                                  │
   Claude Desktop                 │      ┌──────────────────┐
   /Cursor/Code      ──MCP/HTTP──>│      │  MCP Gateway     │──HTTP──> Mock CRM (FastAPI)
   (mcp client)                   │      │  (FastMCP +      │
                                  │      │   FastAPI)       │──HTTP──> Mock Payments (FastAPI)
                                  │      └────────┬─────────┘
                                  │               │
                                  │      ┌────────┴─────────┐
                                  │      │   Postgres       │
                                  │      │  (tenants,       │
                                  │      │   policies,      │
                                  │      │   approvals,     │
                                  │      │   audit_log)     │
                                  │      └──────────────────┘
                                  │
                                  └─ Mock OAuth (IdP) — отдельный лёгкий FastAPI
                                       выдаёт JWT, JWKS endpoint, DCR
```

### Ключевые architectural choices

1. **5 слоёв = middleware chain в FastMCP/FastAPI**, каждый — отдельный модуль с чётким интерфейсом → можно тестировать изолированно и параллелить разработку через субагентов.
2. **Pluggable interfaces** для всего, что меняется:
   - `TokenValidator` (Mock IdP сейчас, реальный потом)
   - `PolicyStore` (YAML сейчас, БД потом)
   - `ApprovalNotifier` (Telegram + WS сейчас, Slack потом)
   - `AuditSink` (Postgres сейчас, S3/BigQuery потом)
3. **Tenant isolation** на уровне SQLAlchemy через middleware, инжектящий `tenant_id` в каждый query через session-scoped filter.
4. **Audit log immutability** — таблица `audit_log` без UPDATE/DELETE прав для application user в Postgres + триггер `BEFORE UPDATE/DELETE` который RAISE EXCEPTION.
5. **Async-first** — FastMCP, FastAPI, asyncpg, httpx. I/O-heavy gateway требует это.

---

## 4. Компоненты

### 4.1 `gateway/` — основной MCP Gateway пакет

```
gateway/
├── server.py              # FastMCP + FastAPI app entrypoint
├── config.py              # Pydantic Settings (env + yaml)
├── middleware/            # 5 слоёв
│   ├── authenticate.py
│   ├── authorize.py
│   ├── approve.py
│   ├── execute.py
│   └── audit.py
├── auth/
│   ├── oauth_server.py    # /authorize, /token, /jwks, DCR
│   ├── token_validator.py
│   └── models.py
├── policy/
│   ├── loader.py          # YAML → in-memory policy tree
│   ├── evaluator.py       # (role, tool, params) → Decision
│   └── schema.py
├── approval/
│   ├── store.py           # CRUD pending approvals
│   ├── notifier.py        # Abstract base
│   ├── telegram.py
│   ├── websocket.py
│   └── timeout.py         # Background reaper
├── audit/
│   ├── writer.py
│   ├── reader.py
│   └── models.py
├── tools/
│   ├── registry.py        # Метаданные: destructive?, redact_fn
│   ├── crm.py
│   └── payments.py
├── tenants/
│   ├── middleware.py
│   └── models.py
├── web/
│   ├── routes.py          # /audit, /approvals, /healthz, /metrics
│   ├── templates/         # Jinja2
│   └── static/
├── db/
│   ├── session.py
│   └── base.py
├── observability/
│   ├── logging.py         # structlog
│   ├── metrics.py         # Prometheus
│   └── tracing.py         # OpenTelemetry
└── alembic/
```

### 4.2 `mocks/crm/` и `mocks/payments/`

Независимые FastAPI-сервисы (~150 строк каждый), in-memory или SQLite. Эмулируют:
- realistic JSON responses
- requirement API-key (для проверки secrets management в Gateway)
- иногда падают / отдают 5xx (для тестирования retry/circuit breaker)

### 4.3 `mock-idp/`

Лёгкий OAuth Authorization Server (~200 строк FastAPI). Endpoints:
- `/authorize`, `/token`, `/jwks`
- `/.well-known/oauth-authorization-server`
- `/register` (Dynamic Client Registration — требование MCP spec 2026)

Выдаёт RS256 JWT с claims `sub`, `tenant_id`, `scopes`, `exp`, `iss`, `aud`.

### 4.4 Postgres schema

```sql
tenants(id UUID PK, name TEXT, created_at TIMESTAMP)

oauth_clients(id UUID PK, tenant_id FK, client_id TEXT UNIQUE,
              client_secret_hash TEXT, redirect_uris TEXT[], created_at)

agents(id UUID PK, tenant_id FK, name TEXT, role_id FK, owner_email TEXT)

roles(id UUID PK, tenant_id FK, name TEXT,
      UNIQUE(tenant_id, name))

role_permissions(role_id FK, tool_name TEXT,
                 requires_approval BOOLEAN,
                 PRIMARY KEY(role_id, tool_name))

approval_requests(id UUID PK, tenant_id FK, agent_id FK,
                  tool TEXT, params_json JSONB,
                  status TEXT,  -- pending|approved|rejected|timeout
                  requested_at TIMESTAMP, decided_at TIMESTAMP,
                  decided_by TEXT, decision_reason TEXT)

audit_log(id BIGSERIAL PK, tenant_id FK, agent_id FK,
          tool TEXT, params_json JSONB,  -- PII-redacted
          result_status TEXT,  -- success|denied|rejected|timeout|error
          result_json JSONB, approval_id FK NULL,
          trace_id TEXT, created_at TIMESTAMP)
```

Append-only защита `audit_log`:
```sql
GRANT INSERT, SELECT ON audit_log TO mcp_app;
REVOKE UPDATE, DELETE ON audit_log FROM mcp_app;

CREATE TRIGGER audit_log_no_modify
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION raise_exception();
```

Индексы: `audit_log(tenant_id, created_at DESC)`, `audit_log(agent_id, created_at DESC)`, `approval_requests(tenant_id, status, requested_at)`.

---

## 5. Data flow — единый tool call

Сценарий `refund_payment` (destructive case):

1. **Claude → POST /mcp** (JSON-RPC 2.0, `Authorization: Bearer <jwt>`)
2. **[Authenticate]** — `TokenValidator.verify(jwt)` → `{sub, tenant_id, scopes}`. Невалид → 401, audit `auth_failed`.
3. **[Tenant]** — set `request.state.tenant_id` из claims.
4. **[Authorize]** — `PolicyEvaluator.check(role, "refund_payment", params)` → `Decision.RequiresApproval`. Deny → 403, audit `policy_denied`.
5. **[Approve]**
   - `ApprovalStore.create(tenant_id, agent_id, tool, params)` → `approval_id`, status=pending
   - `ApprovalNotifier.notify(approval_id)`:
     - Telegram bot шлёт сообщение с inline-кнопками Approve/Reject
     - WebSocket broadcast в Web UI
   - `await ApprovalStore.wait_for_decision(approval_id, timeout=5min)` через PostgreSQL `LISTEN/NOTIFY`
   - Approved → дальше; Rejected/Timeout → MCP error, audit
6. **[Execute]** — dispatch в `tools/payments.py:refund_payment`. HTTP-call → mock-payments с retry (3 попытки, exp backoff). Response normalisation.
7. **[Audit]** — выполняется ВСЕГДА через `try/finally` в outermost middleware. Append-only INSERT с PII-redacted params.
8. **Response → Claude** (`{result: {content: [...], isError: false}}`).

**Инвариант:** audit пишется на каждом исходе.

---

## 6. Error handling

| Источник | Стратегия | MCP response |
|---|---|---|
| Невалидный JWT | 401, audit `auth_failed` | OAuth error per RFC 6750 |
| Scope mismatch | 403, audit `policy_denied` | MCP error `-32001` |
| Approval rejected | 403, audit `approval_rejected` | MCP error с reason |
| Approval timeout | 408, audit `approval_timeout` | MCP error |
| Upstream network fail | 3 retry exp backoff, потом 502, audit `upstream_unavailable` | MCP error |
| Upstream 5xx | 1 retry, передать как есть | MCP error |
| Upstream 4xx | Не retry, передать | MCP error |
| Postgres down | Health fail, новые → 503 | 503 |
| Telegram bot down | WS-канал работает, лог warning | Не влияет |
| Bug в Gateway | Global handler, 500, audit `internal_error` + trace_id | MCP error + trace_id |

### Принципы

1. **Audit-first** — `try/finally` гарантирует запись audit. Audit fail = 500 + alarm.
2. **Идемпотентность retry** — только safe ops или с `Idempotency-Key` header в downstream.
3. **Circuit breaker** на upstream (5 fails → open 30s).
4. **PII redaction** перед audit — каждый tool в registry имеет `redact_fn(params) → params`.
5. **Trace ID propagation** — клиент видит в `X-Trace-Id` header.

---

## 7. Testing strategy

### Пирамида

- **~150 unit-тестов** — pure logic (PolicyEvaluator, TokenValidator, RedactionRules, RetryPolicy). No I/O.
- **~30 integration-тестов** — `testcontainers-python` Postgres, каждый тест в транзакции с rollback. Покрывают: миграции, audit append-only, approval store concurrent access, OAuth full flow, multi-tenant isolation.
- **1+ E2E** — `docker compose -f docker-compose.test.yml up`, прогон демо-сценария через `httpx.AsyncClient`.
- **Mutation testing** через `mutmut` на `policy/` + `auth/` (security-critical). Survival rate < 10%.
- **Load test** через `locust` — 50 concurrent agents × 100 calls. Замер p50/p95/p99. CI runs smoke @ 10 RPS / 30s.
- **Security tests** — JWT none-algorithm, SQL injection в policy params, IDOR на audit endpoints (cross-tenant).

### CI (GitHub Actions)

```yaml
jobs:
  lint:        ruff + mypy + black --check
  unit:        pytest -m "not integration"
  integration: pytest -m integration  # testcontainers
  e2e:         docker compose up && pytest -m e2e
  security:    bandit + pip-audit + trivy fs
  build:       docker build всех сервисов
  load-smoke:  locust 30s @ 10 RPS
```

Pre-commit: ruff format/check + mypy на staged files.

---

## 8. Observability

### Logging
- `structlog` JSON-формат
- Каждая запись: `trace_id`, `tenant_id`, `agent_id`, `tool` (когда применимо)
- Forwarding через stdout (12-factor)

### Metrics (Prometheus, `/metrics`)
- `mcp_gateway_requests_total{tool, status, tenant}` — counter
- `mcp_gateway_request_duration_seconds{tool}` — histogram
- `mcp_gateway_approvals_pending{tenant}` — gauge
- `mcp_gateway_approvals_total{decision}` — counter
- `mcp_gateway_upstream_failures_total{service}` — counter

### Tracing (OpenTelemetry)
- Auto-instrumentation FastAPI + asyncpg + httpx
- Custom spans per middleware-слой
- OTLP export → локальный collector в `docker-compose.observability.yml` (Jaeger UI)

### Grafana
- Dashboard JSON в `observability/grafana/mcp-gateway.json`
- Панели: request rate, latency p95, approval funnel, error rate by tool

---

## 9. Deployment

**Fly.io** — managed Postgres, free tier, простой CLI.

| Service | Тип |
|---|---|
| `mcp-gateway` | fly.io app, 1 instance, autostart |
| `mock-crm` | fly.io app |
| `mock-payments` | fly.io app |
| `mock-idp` | fly.io app |
| `postgres` | `fly postgres create` (managed) |

Telegram bot — long polling (без публичного webhook URL).

`fly.toml` per-service в репо. Деплой через GitHub Actions при push в `main`.

Локальный dev — `docker compose up` (Gateway + mocks + idp + Postgres + Prometheus + Grafana + Jaeger).

---

## 10. Стек

| Слой | Инструмент |
|---|---|
| MCP framework | FastMCP (Python) |
| HTTP server | FastAPI / Starlette |
| OAuth | Authlib (для mock-idp) + PyJWT (для validator) |
| DB | Postgres + asyncpg + SQLAlchemy 2.0 + Alembic |
| Templates | Jinja2 + HTMX |
| Telegram | `python-telegram-bot` |
| WebSocket | FastAPI native |
| Logging | structlog |
| Metrics | prometheus-client |
| Tracing | opentelemetry-{api,sdk,instrumentation-fastapi,instrumentation-asyncpg,instrumentation-httpx} |
| Tests | pytest, pytest-asyncio, testcontainers, httpx, mutmut, locust |
| Lint | ruff, mypy, black |
| Security scan | bandit, pip-audit, trivy |
| Container | Docker, docker-compose |
| Deploy | Fly.io + GitHub Actions |

---

## 11. Deliverables

- ✅ Public GitHub repo с README + архитектурной диаграммой (mermaid)
- ✅ Публично задеплоенный Gateway + mocks на Fly.io
- ✅ Пример YAML-policy в репо
- ✅ Mock-системы (CRM, payments, IdP)
- ✅ Loom-видео 2-3 мин с демо-сценарием из секции 5
- ✅ Технический write-up «Building production-grade MCP Gateway with human approval»
- ✅ Grafana dashboard JSON
- ✅ Локальный `docker compose up` поднимает всё за 1 команду

---

## 12. Risks и митигации

| Риск | Митигация |
|---|---|
| FastMCP-API меняется (молодая библиотека) | Pin version в `pyproject.toml`, abstraction layer над FastMCP-specifics |
| Telegram-API blocked в некоторых регионах | WS-канал в UI как fallback, документация про это |
| OAuth 2.1 + DCR корректность сложна | Использовать Authlib (проверенная), не писать с нуля |
| Append-only через GRANT обходится superuser | Доп. защита через trigger + документация в README |
| Async + concurrent approvals — race conditions | Pessimistic lock на `approval_requests` row при decide, тесты на конкурентность |
| Long-polling Telegram + autoscaling Fly.io | Bot живёт в singleton service, не scale > 1; документация |

---

## 13. Реализация — план параллелизации через субагентов

После апрува спеки → переход в `writing-plans` для детального плана. Высокоуровневая идея распараллеливания:

**Phase 1 (sequential foundation):**
- Repo skeleton, pyproject.toml, ruff/mypy/CI базовая
- Postgres schema + Alembic миграции
- `db/session.py` + базовые модели

**Phase 2 (parallel, через `general-purpose` субагентов):**
- A: `auth/` + `mock-idp/`
- B: `policy/` + YAML loader
- C: `approval/` + Telegram + WS
- D: `audit/` writer/reader
- E: `mocks/crm/` + `mocks/payments/`
- F: `tools/` registry + implementations
- G: `web/` routes + templates
- H: `observability/` (logging, metrics, tracing)

**Phase 3 (sequential integration):**
- Middleware chain wiring в `server.py`
- E2E flow через docker-compose
- Security review (`security-reviewer` агент)
- Dependency audit (`dependency-auditor` агент)

**Phase 4 (deploy):**
- Fly.io configs
- GitHub Actions
- Loom recording, README, write-up

---

**End of design document.**
