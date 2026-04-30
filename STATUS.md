# Project Context — handoff for any AI assistant

> **Purpose of this file:** drop this into a fresh Claude / Cursor / ChatGPT chat and get full project context in one message. Updated 2026-04-30.

---

## TL;DR (read this first)

**MCP Gateway** — production-grade security envelope between AI agents and internal company systems. Every tool call passes 5 control layers: **authenticate → authorize → approve → execute → audit**.

- **Status:** technically complete, 76 tests passing, CI green, ready for Loom recording + Loom-link insertion into README
- **Goal:** portfolio project for fulltime remote AI Agent / AI Platform Engineer roles
- **GitHub:** https://github.com/Shcherbin96/mcp-gateway
- **Owner:** Roman Serbin (communicates in Russian; English-language docs/code)
- **Stack:** Python 3.13, FastAPI, FastMCP, SQLAlchemy 2.0 + asyncpg, Postgres, Authlib + PyJWT, python-telegram-bot, structlog + Prometheus + OpenTelemetry, Docker Compose, Fly.io configs (not deployed)

---

## What's built (every layer)

| Layer | Implementation | Files |
|---|---|---|
| **Authenticate** | OAuth 2.1 with PKCE-mandatory authorization_code + client_credentials. Mock IdP with login UI, JWKS endpoint, Dynamic Client Registration. JWKSTokenValidator with strict alg/aud/iss/exp checks (none-alg attack rejected) | `gateway/auth/`, `mocks/idp/main.py` |
| **Authorize** | YAML-based RBAC with conditional rules (e.g. `amount > 1000 → requires_approval`). O(1) role→tool lookup | `gateway/policy/`, `config/policies.yaml` |
| **Approve** | Pending request stored in Postgres. Notifies via CompositeNotifier (Telegram bot inline buttons + WebSocket broadcast to Web UI). PostgreSQL LISTEN/NOTIFY for fast wakeup with 5s polling fallback. Decision reason textarea in UI + `/reject <id> <reason>` Telegram command. Tenant-scoped decide() prevents cross-tenant approval. Telegram callback validates sender chat_id. 5min timeout reaper as background task | `gateway/approval/` |
| **Execute** | UpstreamClient with httpx + Tenacity retry (3 attempts, exp backoff, only on safe failures) + custom CircuitBreaker (5 fails → open 30s). Per-tool registry with destructive flag and PII redact_fn | `gateway/tools/` |
| **Audit** | Append-only via 3-layer enforcement: Postgres trigger (RAISE EXCEPTION on UPDATE/DELETE) + GRANT/REVOKE on `mcp_app` user + SQLAlchemy ORM. PII redacted before write. `try/finally` audit invariant — runs on every outcome including auth fails | `gateway/audit/`, `alembic/versions/0001_initial.py` |

**Cross-cutting:**
- 5-layer middleware Pipeline with short-circuit on error (`gateway/middleware/chain.py`)
- Per-agent rate limiting (60/min, in-memory token bucket)
- Multi-tenant lite (every resource scoped by tenant_id, web UI has tenant selector with cookie persistence)
- Security headers middleware (CSP, HSTS, X-Frame-Options, COOP/CORP, Permissions-Policy)
- MCP Streamable HTTP transport at `POST /mcp/rpc` (MCP 2025-06-18 spec compliant) + legacy REST endpoints + stdio-proxy for Claude Desktop
- Web UI (HTMX + Jinja) with status badges, realtime WS-driven card fade-out, audit filters, approvals dashboard
- Observability: structlog JSON to stdout, Prometheus `/metrics`, OpenTelemetry OTLP, 4-panel Grafana dashboard JSON
- 76 tests (53 unit + 16 integration + 4 e2e + 3 security) — ruff + mypy + bandit + pip-audit clean
- CI on GitHub Actions: lint + unit + integration + e2e + security + build + load-smoke. Currently green.

---

## What's NOT built (deliberately)

These were considered and **scoped out**. Decisions documented in `docs/operations.md` § "Known limitations".

- **Real SSO for admin UI** — uses shared bearer token. Swap to OIDC when more than one human admin
- **Automatic SQLAlchemy tenant filtering** — manual `where(tenant_id == ?)` per query. Auditable + explicit
- **Multi-region failover** — single-instance gateway
- **Real OAuth user backend** — mock IdP has 2 hardcoded users (alice/bob)
- **Slack notifier** — Notifier interface is there, just wasn't built (user doesn't use Slack)
- **Mobile-responsive Web UI** — admin tool, desktop-only
- **Schema-per-tenant Postgres** — row-level filtering is enough for MVP

---

## File structure

```
gateway/                  # Main package
├── auth/                 # JWKSTokenValidator + exceptions
├── approval/             # Store + Telegram + WebSocket + timeout reaper + LISTEN/NOTIFY
├── audit/                # Append-only writer/reader + PII redaction
├── middleware/           # 5-layer pipeline + rate limit + security headers
├── policy/               # YAML loader + evaluator with conditional rules
├── tenants/              # ContextVar-based tenant scoping
├── tools/                # Registry + httpx upstream client + CRM/payments tools + dispatch helper
├── web/                  # FastAPI router + Jinja templates + HTMX + CSS
├── observability/        # structlog + Prometheus metrics + OpenTelemetry
├── db/                   # SQLAlchemy session + ORM models
├── mcp_http.py           # Streamable HTTP MCP transport (/mcp/rpc)
├── mcp_stdio_proxy.py    # stdio→HTTP bridge for Claude Desktop
├── server.py             # FastAPI app + lifespan wiring
├── config.py             # Pydantic Settings
└── cli.py                # `python -m gateway.cli seed`

mocks/
├── idp/                  # OAuth 2.1 IdP with PKCE auth_code + login UI
├── crm/                  # Mock CRM with 6 customers + 6 orders
└── payments/             # Mock Payments with refund/charge endpoints + idempotency keys

tests/                    # 76 tests across unit/integration/e2e/security
docs/
├── architecture.md       # Mermaid diagrams (component, sequence, ER)
├── operations.md         # 6 runbooks + known limitations
├── blog/                 # ~1500-word write-up ready for dev.to / LinkedIn
├── screenshots/          # PNG slots (still empty — user to capture)
├── superpowers/specs/    # Original design doc
└── superpowers/plans/    # Implementation plan

demo/                     # claude_desktop_config.json + bilingual recording script
loadtest/                 # locust file (used by CI smoke job)
observability/            # Prometheus + Grafana provisioning configs
alembic/                  # Schema migrations
.github/                  # CI workflow + issue/PR templates
```

---

## How to run locally

```bash
git clone https://github.com/Shcherbin96/mcp-gateway.git
cd mcp-gateway
make install                # creates .venv + installs deps
docker compose up -d        # postgres + 3 mocks + gateway + seed
docker compose logs gateway | grep "OAuth client"  # extract seeded creds
```

Visit:
- http://localhost:8000/docs — OpenAPI / Swagger
- http://localhost:8000/audit + /approvals — admin UI (needs `Authorization: Bearer demo-admin-token-change-me` via ModHeader)
- http://localhost:8000/healthz, /metrics, /mcp/tools, /mcp/rpc

Telegram + Claude Desktop: see `demo/claude_desktop_config.json` and `.env.example`.

---

## What's pending (user actions)

1. **Record Loom demo** (~5-10 min) — script in `demo/script.md` (RU + EN bilingual)
2. **Capture 4 screenshots** for README — paths defined in `docs/screenshots/README.md`
3. **Add Loom link to README** — replace `*(Loom link goes here)*` in the Demo section
4. **Publish write-up** to dev.to / LinkedIn / Medium — content in `docs/blog/building-production-grade-mcp-gateway.md`

Optional:
5. Delete Railway project at https://railway.com/project/cf6ca7a9-60b6-4b02-9bf0-d19131d9116c (saves $5 trial)
6. Wire `FLY_API_TOKEN` GitHub secret + uncomment deploy job in `.github/workflows/ci.yml` (only if user gets Fly.io account)

---

## Build history (key milestones)

- 2026-04-29 evening: brainstorm + design doc + plan written. Phase 0 (foundation) + Phase 1 (8 parallel modules via subagents) + Phase 2 (integration) + Phase 3 (deploy + docs) complete in one session
- 2026-04-30 morning: Docker tests fixed end-to-end. Important findings closed (rate limit, LISTEN/NOTIFY, conditional policies, real OAuth flow with PKCE, multi-tenant UI, write-up). Telegram + UI polished
- 2026-04-30 midday: Streamable HTTP transport, decision_reason flow, security headers

22 commits on main, all CI green.

---

## Known quirks

- Local dev uses `MCP_WEB_ADMIN_TOKEN=demo-admin-token-change-me` (from `.env`); CI uses `e2e-admin-token` (in `docker-compose.test.yml`). The security tenant-isolation test hardcodes the CI value, so it fails when run locally without override — expected
- `mcp_stdio_proxy` runs from the user's `.venv` and reads `PYTHONPATH` to find the package — Claude Desktop config must set both
- Telegram bot uses long-polling (no public webhook URL needed); works locally without tunnel
- Postgres `mcp_app` user is created in alembic migration with hardcoded password `mcp_app` — fine for dev/CI, document warns to provision externally in prod
- Coverage gate is set to 35% (unit-only) because integration tests cover the bulk; merging coverage in CI is a TODO

---

## Conventions

- **Code style:** ruff format + ruff check. Phased mypy (not strict yet)
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `test:`)
- **Tests:** TDD, marker-based segmentation (`unit`, `integration`, `e2e`, `security`)
- **Comments:** add only when WHY is non-obvious; never restate WHAT
- **Russian/English:** code + docs are English; user-facing chat with the owner is Russian

---

*If you're a Claude/Cursor/ChatGPT instance picking this project up — start with this file, then `README.md`, then `docs/architecture.md`. The code is well-organized; module names match their responsibilities.*
