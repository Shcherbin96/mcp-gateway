# Building a Production-Grade MCP Gateway with Human Approval

> A walk through what it takes to put an AI agent in front of real company systems — and why "build the agent" is the easy part.

---

## The 80% nobody shows you

Open any Model Context Protocol tutorial and you'll see the same demo: a 30-line Python file that exposes `get_weather` or `read_file`, a screenshot of Claude Desktop calling it, the words "now you have a custom MCP server!" and a thumbnail.

That's a toy.

The real question for any company that wants AI agents in production isn't *can the agent call this tool* — it's all of these:

- **Who** is calling it? Is it actually our agent, or someone who phished the API key?
- **What** are they allowed to do? `support_agent` should read customer profiles, but absolutely not refund payments.
- **Should a human approve** this specific call before it executes? "Refund $50,000" is not a fire-and-forget operation.
- **Where is the audit trail** when the regulator asks who decided to make that refund last quarter?
- **How do you stop** a misbehaving or compromised agent from draining the system in 30 seconds?

A "build an agent" tutorial answers none of these. So I built the other 80%: a security envelope between AI agents and internal company systems.

This post walks through what's in it, the design choices, and the things I deliberately chose *not* to build.

---

## The 5-layer pipeline

Every tool call from Claude (or Cursor, or Continue, or any MCP client) passes through five middleware layers:

```
Claude → [Authenticate] → [Authorize] → [Approve?] → [Execute] → [Audit] → Response
```

Each layer is a small async function. They share a `CallContext` that accumulates state (token claims, decision, approval ID, result). If any layer sets `ctx.error`, the chain short-circuits — but **audit always runs**, in a `try/finally`, so we have a record of *every* outcome including auth failures.

That last invariant is non-obvious and load-bearing. The most common audit-log mistake is "we only log success." Then a regulator asks "show me every denied request from January" and you have nothing.

### Layer 1: Authenticate (OAuth 2.1)

Tokens are signed JWTs from an OAuth Authorization Server. The gateway validates:
- signature against the IdP's JWKS (cached, refreshed every 10 min)
- algorithm in `{RS256, ES256}` — explicitly rejecting `none` (the classic JWT attack)
- `exp`, `aud`, `iss` claims
- required claims via `options={"require": [...]}` so PyJWT doesn't silently accept missing ones

The mock IdP I shipped with the project speaks the full **OAuth 2.1 spec including PKCE-mandatory authorization_code flow** plus client_credentials. Not because the demo needs it, but because the [MCP 2026 spec](https://modelcontextprotocol.io) requires Dynamic Client Registration, and showing you understand the actual spec ranks higher in interviews than "I imported a library."

### Layer 2: Authorize (RBAC via YAML)

Policies live in `config/policies.yaml`:

```yaml
roles:
  - name: support_agent
    tools:
      - tool: get_customer
      - tool: refund_payment
        requires_approval:
          - param: amount
            op: gt
            value: 1000
```

The evaluator returns `Decision.ALLOW | DENY | REQUIRES_APPROVAL`. The `requires_approval` field is a bool *or a list of conditions* — small refunds go through, big ones gate.

Policy decisions are logged with the role and tool. Future you, debugging an "agent suddenly can't do X," will thank present you.

### Layer 3: Approve (Human-in-the-loop)

This is the layer most demos skip. For destructive tools, the gateway:

1. Writes a row to `approval_requests` with status=`pending`
2. Notifies via *all* configured channels (Telegram bot + WebSocket-driven web UI). The notifier is a `CompositeNotifier` with a Protocol — adding Slack later is one new file, no plumbing.
3. Awaits the decision via **PostgreSQL `LISTEN/NOTIFY`** (with a 5s polling fallback for failover safety)
4. Returns the result to the caller, or times out at 5 min and writes `timeout` to the audit log

The Telegram side is fun: bot sends an inline keyboard `[✅ Approve] [❌ Reject]`, you tap on your phone, the callback handler verifies the message originated from the configured admin chat (not just anyone who's added the bot), updates the DB row, and the gateway's `wait_for_decision` wakes up via NOTIFY.

A subtle bug I caught and fixed during the security review: the original web UI `/approvals/{id}/decide` endpoint had **no authentication**, and `decided_by` was a query param the caller controlled. So an attacker who could reach the gateway's port could approve any pending action and forge the audit log to claim it was the CISO. The fix: shared-secret bearer auth on all admin endpoints, `decided_by` derived from the authenticated identity. Lesson: if you have to ask "should this endpoint require auth?", the answer is yes.

### Layer 4: Execute

Real HTTP call to the upstream system through an `UpstreamClient` wrapper that adds:
- 3-attempt retry with exponential backoff (Tenacity) — only on safe failure modes (network errors, 5xx)
- A circuit breaker (5 consecutive failures → open for 30s → fast-fail) so a flapping upstream can't take down the whole gateway
- Idempotency keys on POSTs (so retries don't double-charge cards)

Each upstream is a separate client instance with its own breaker state. The metric `mcp_gateway_upstream_failures_total{service}` gives you a per-upstream signal in Grafana.

### Layer 5: Audit (append-only)

The fun one. The audit table is enforced as append-only at *three* levels:

```sql
CREATE TRIGGER audit_log_no_modify
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify_fn();

GRANT INSERT, SELECT ON audit_log TO mcp_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM mcp_app;
```

The application user `mcp_app` literally cannot modify a row. There's a security test that connects as `mcp_app` and tries to UPDATE — it expects `InsufficientPrivilegeError`. If anyone removes those GRANTs, the test fails.

PII is redacted before write via per-tool `redact_fn` — the `charge_card` tool turns `4111111111111234` into `****1234` before the row hits Postgres. The full PAN still flows to the upstream payment processor (it has to), just not into the audit log.

---

## Multi-tenancy lite

Every resource (`oauth_clients`, `agents`, `roles`, `approval_requests`, `audit_log`) carries a `tenant_id`. There's no automatic `WHERE tenant_id = ?` injection — that's a future feature. Today every repository explicitly filters by tenant, and there's a security test that creates two tenants and asserts queries from tenant A never see tenant B's rows.

The web UI has a tenant dropdown that admins can switch between. Selection persists via `HttpOnly` cookie. Cross-tenant access via random UUID guess returns 404, not silently-fall-back-to-default.

---

## Per-agent rate limiting

A bespoke ~60-LOC token-bucket limiter, keyed by JWT `sub` (agent_id). 60 req/min per agent by default, with a small burst capacity. Returns 429 + `Retry-After`. The limiter sits *outside* the pipeline — we don't burn an audit row on every rate-limited request, just count them in Prometheus.

I deliberately didn't reach for `slowapi` (Flask flavor, heavy) or external Redis (premature for a single-instance gateway). When you scale horizontally you'll outgrow the in-process limiter — but by then you'll know what you actually want.

---

## What I deliberately did *not* build

This is the section I think hiring managers find most useful, because it shows you can actually *cut scope* instead of building everything you've ever read about:

- **No automatic SQLAlchemy tenant filtering.** Manual `where(tenant_id == X)` in every query. Adding a row-level event hook is correct in the long run; for v1 the explicit filter is auditable and obvious.
- **No real SSO for the admin UI.** Single shared bearer token. When this becomes a problem (i.e., more than one human admin), swap to OIDC.
- **No external secrets manager.** `.env` file. Migrating to AWS Secrets Manager / Vault is a 30-minute swap when needed.
- **No Slack notifier.** The `Notifier` interface is there. Adding Slack is mostly boilerplate; I left it as the smallest possible "yes, this is pluggable" demonstration.
- **No multi-region failover.** Single Fly.io region. Fly.io handles the spread when you need it.

The discipline isn't "I built everything." It's "I built the things that have non-trivial design decisions, and skipped the things that are well-understood swaps."

---

## What I learned

**Three reviewers caught more in 90 minutes than I would have in a week.**

I spun up the project across two sessions with parallel subagents — and at the end ran three specialised review agents (security, dependencies, code quality) in parallel. The security reviewer caught the unauthenticated approval endpoint and the audit-forgery query param. The dependency auditor flagged that `python-telegram-bot` is LGPL-3.0 (fine for server-side use, but the kind of thing a legal team will ask about). The code reviewer caught the polling-vs-LISTEN/NOTIFY discrepancy with the original spec.

None of those are sexy bugs. All of them are exactly what a code review at a real company finds. The lesson isn't "use AI reviewers" — it's "build a habit of getting independent eyes on security-sensitive code, especially when you wrote the spec yourself."

**The five-layer pipeline pattern generalizes.**

This isn't really an MCP-specific architecture. The same shape — auth → authorize → approve → execute → audit — applies to any system where AI calls into the real world. Banking transactions, infrastructure changes, customer-facing emails. If you're building agentic systems for a company in 2026, you'll build this exact diagram for *something*. The MCP Gateway is one instance of it.

**The hardest part wasn't the code.**

It was deciding what to *not* build. Production-grade doesn't mean "everything possible," it means "everything that has a non-obvious design choice, plus the operational scaffolding to deploy and debug." A one-week sprint can produce more robust software than a six-month one if you keep ruthlessly cutting scope.

---

## Try it

```bash
git clone https://github.com/Shcherbin96/mcp-gateway.git
cd mcp-gateway
make install
docker compose up -d
make seed
```

The README walks through Claude Desktop integration via a small stdio-to-HTTP MCP proxy (because Claude Desktop natively speaks stdio MCP and our gateway speaks HTTP — the proxy holds the OAuth credentials and translates).

A 2-minute Loom demo is in the repo. Issues and PRs welcome.

---

*Roman Serbin — building agentic infrastructure. [GitHub](https://github.com/Shcherbin96) · [Repo](https://github.com/Shcherbin96/mcp-gateway)*
