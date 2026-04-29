# MCP Gateway — Operations Runbooks

Operational procedures for running MCP Gateway in production: key rotation, audit queries, tenant onboarding, IdP swap, metrics, and audit export.

All commands assume:

- CWD is the repo root.
- The Python venv is activated (`source .venv/bin/activate`) or commands are prefixed with `uv run` / `poetry run`.
- Postgres credentials live in `DATABASE_URL`. The application user is `mcp_app`; admin tasks (GRANTs, role rotation) use `mcp_admin`.

---

## 1. Rotate JWKS keys

Use this when switching from the in-repo mock IdP to a real one, or rotating the signing key on the mock IdP itself. The JWKS endpoint serves multiple keys at once so rotation is zero-downtime.

### 1a. Mock IdP rotation (development)

The mock IdP keeps its keys in `mocks/idp/keys/`. Each key is `{kid}.pem` (private) and `{kid}.pub.pem` (public).

```bash
# 1. Generate a new RSA-2048 keypair and publish it
KID=$(date -u +%Y%m%dT%H%M%SZ)
openssl genrsa -out "mocks/idp/keys/${KID}.pem" 2048
openssl rsa -in "mocks/idp/keys/${KID}.pem" -pubout -out "mocks/idp/keys/${KID}.pub.pem"

# 2. Mark it as the active signer
echo "$KID" > mocks/idp/keys/ACTIVE_KID

# 3. Restart mock-idp; both keys remain in JWKS during the overlap window
docker compose restart mock-idp

# 4. Verify the new kid appears in JWKS
curl -s http://localhost:9000/.well-known/jwks.json | jq '.keys[].kid'

# 5. After all outstanding tokens have expired (default JWT TTL = 1h),
#    delete the old key files and restart again.
rm mocks/idp/keys/<old-kid>.pem mocks/idp/keys/<old-kid>.pub.pem
docker compose restart mock-idp
```

The Gateway's `TokenValidator` caches JWKS for 5 minutes (configurable via `MCP_OAUTH_JWKS_CACHE_TTL`). After rotation, either wait for the cache to expire or `kill -HUP` the gateway to flush.

### 1b. Real IdP rotation

When a real IdP rotates its key, you do nothing on the gateway side — it re-fetches JWKS automatically when an unknown `kid` arrives. To force a refresh:

```bash
# Bust the JWKS cache by hitting the admin endpoint
curl -X POST http://localhost:8000/admin/jwks/refresh -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 2. Query the audit log via SQL

The audit log is the system of record for compliance and incident response. Connect read-only:

```bash
psql "$DATABASE_URL_RO"   # uses mcp_audit_reader role
```

### Common queries

**Last 100 calls in a tenant, newest first:**

```sql
SELECT
  created_at,
  agent_id,
  tool,
  result_status,
  trace_id,
  approval_id
FROM audit_log
WHERE tenant_id = '00000000-0000-0000-0000-0000000000aa'
ORDER BY created_at DESC
LIMIT 100;
```

**All destructive calls awaiting approval that timed out in the last 24h:**

```sql
SELECT a.created_at, a.agent_id, a.tool, a.params_json, a.trace_id
FROM audit_log a
WHERE a.result_status = 'approval_timeout'
  AND a.created_at > now() - interval '24 hours'
ORDER BY a.created_at DESC;
```

**Per-tool error rate (last 7 days):**

```sql
SELECT
  tool,
  count(*) FILTER (WHERE result_status = 'success')::float / count(*) AS success_rate,
  count(*) AS total_calls
FROM audit_log
WHERE created_at > now() - interval '7 days'
GROUP BY tool
ORDER BY total_calls DESC;
```

**Trace correlation — pull every audit row for a single MCP request:**

```sql
SELECT created_at, tool, result_status, result_json
FROM audit_log
WHERE trace_id = '4bf92f3577b34da6a3ce929d0e0e4736'
ORDER BY created_at;
```

**Confirm append-only enforcement is intact (this MUST raise):**

```sql
DELETE FROM audit_log WHERE id = 1;
-- ERROR:  audit_log is append-only
```

If that `DELETE` succeeds, the trigger has been dropped — escalate immediately.

---

## 3. Seed a new tenant

Use the CLI to create a tenant, default role, agent, and OAuth client in one transaction. The command prints the new `client_id` / `client_secret` once — store them in your secret manager.

```bash
python -m gateway.cli seed \
  --tenant-name "acme-corp" \
  --owner-email "ops@acme.example" \
  --role "support-agent" \
  --agent-name "support-bot-prod"
```

Sample output:

```
tenant_id:     a6f2b8b0-8a9e-4c8d-9b2c-1f0c8d3a2e10
agent_id:      f3c4e5d6-7a8b-9c0d-1e2f-3a4b5c6d7e8f
role:          support-agent
client_id:     mcp_acme_3kFQ...
client_secret: <shown once — copy now>
```

To attach the new role to a YAML policy, edit `config/policies.yaml`:

```yaml
roles:
  support-agent:
    tools:
      list_customers: allow
      get_customer:   allow
      refund_payment: requires_approval
      delete_customer: deny
```

Then reload policies (no restart needed):

```bash
curl -X POST http://localhost:8000/admin/policies/reload -H "Authorization: Bearer $ADMIN_TOKEN"
```

To verify the agent can authenticate:

```bash
curl -X POST http://localhost:9000/token \
  -d grant_type=client_credentials \
  -d client_id="$CLIENT_ID" \
  -d client_secret="$CLIENT_SECRET" \
  | jq -r .access_token
```

---

## 4. Swap mock IdP for a real IdP

The Gateway speaks to any OAuth 2.1 / OIDC-compatible IdP that exposes a JWKS endpoint and signs RS256 tokens with the standard claims (`sub`, `aud`, `iss`, `exp`). Tested against Auth0, Keycloak, and Okta.

### Required claims

| Claim | Purpose |
|---|---|
| `sub` | Mapped to `agents.name` (or `agents.id` if it's a UUID) |
| `tenant_id` | Drives row-level filtering — must be a UUID present in `tenants.id` |
| `scopes` | Space-separated; checked by `PolicyEvaluator` if a tool requires a scope |
| `iss`, `aud`, `exp`, `iat` | Standard JWT validation |

If the real IdP cannot mint a `tenant_id` claim, configure a claim mapping in `config/auth.yaml` (e.g. map Auth0 `org_id` → `tenant_id`).

### Configuration

Set the following environment variables and restart the gateway:

| Variable | Mock value | Real-IdP value (example: Auth0) |
|---|---|---|
| `MCP_OAUTH_ISSUER` | `http://mock-idp:9000` | `https://acme.us.auth0.com/` |
| `MCP_OAUTH_JWKS_URL` | `http://mock-idp:9000/.well-known/jwks.json` | `https://acme.us.auth0.com/.well-known/jwks.json` |
| `MCP_OAUTH_AUDIENCE` | `mcp-gateway-dev` | `https://api.acme.example/mcp` |
| `MCP_OAUTH_REQUIRE_DCR` | `true` | usually `false` (real IdPs use admin-API client management) |
| `MCP_OAUTH_JWKS_CACHE_TTL` | `300` | `300` |

```bash
# Validate before restarting prod
python -m gateway.cli verify-idp \
  --issuer "$MCP_OAUTH_ISSUER" \
  --jwks-url "$MCP_OAUTH_JWKS_URL" \
  --audience "$MCP_OAUTH_AUDIENCE"
```

This fetches the OIDC discovery document, downloads JWKS, and prints a sample-claim template so you can confirm the IdP is shaped correctly before flipping traffic.

### Cutover checklist

1. Provision the audience and a test client in the real IdP.
2. Run `verify-idp`. Fix any claim mapping issues.
3. Deploy gateway with the new env vars to a staging instance.
4. Run the E2E suite against staging: `make test-e2e ENVIRONMENT=staging`.
5. Promote to prod. Watch `mcp_gateway_requests_total{status="auth_failed"}` for spikes during the first hour.

---

## 5. View metrics in Grafana

The observability stack runs separately from the application stack:

```bash
docker compose -f docker-compose.observability.yml up -d
```

Then open:

| Service | URL | Notes |
|---|---|---|
| Prometheus | http://localhost:9090 | Raw query interface |
| Grafana    | http://localhost:3000 | Anonymous admin (dev only) |
| Jaeger     | http://localhost:16686 | Trace search by `trace_id` |

The dashboard JSON is committed at `observability/grafana/mcp-gateway.json` and provisioned automatically on first start. It lives at:

http://localhost:3000/d/mcp-gateway/mcp-gateway

### Default panels

| Panel | PromQL | What it answers |
|---|---|---|
| Request rate (per tool) | `sum by (tool) (rate(mcp_gateway_requests_total[1m]))` | Where is traffic going? |
| Latency p95 (per tool) | `histogram_quantile(0.95, sum by (le, tool) (rate(mcp_gateway_request_duration_seconds_bucket[5m])))` | Is anything slow? |
| Error rate | `sum by (status) (rate(mcp_gateway_requests_total{status!="success"}[5m]))` | Are we failing more? |
| Approval funnel | `sum by (decision) (rate(mcp_gateway_approvals_total[5m]))` | Approve vs reject vs timeout |
| Pending approvals | `mcp_gateway_approvals_pending` | Backlog gauge |
| Upstream failures | `sum by (service) (rate(mcp_gateway_upstream_failures_total[5m]))` | Which mock/upstream is sick? |

### Suggested alerts (not provisioned)

- `mcp_gateway_approvals_pending > 50 for 10m` — reviewer queue backed up.
- `rate(mcp_gateway_requests_total{status="internal_error"}[5m]) > 0` — bug in gateway.
- `rate(mcp_gateway_upstream_failures_total[5m]) > 1` — circuit breaker likely open.

To get a trace from a metric: copy `trace_id` from a slow request's log line, paste into Jaeger search, and walk the spans across middleware layers.

---

## 6. Export audit log to S3 (future enhancement)

> **Status: not implemented.** Tracked as a future enhancement. The interface is in place (`AuditSink` is pluggable) but the S3 implementation is a stub.

### Intended design

A new `S3AuditSink` would tee writes from the existing `PostgresAuditSink`, batching rows into compressed JSONL objects:

```
s3://acme-mcp-audit/<tenant_id>/dt=YYYY-MM-DD/hour=HH/<batch-id>.jsonl.gz
```

Hive-style partitioning so Athena / BigQuery external tables can scan efficiently.

### Planned configuration

```bash
MCP_AUDIT_SINK=postgres+s3
MCP_AUDIT_S3_BUCKET=acme-mcp-audit
MCP_AUDIT_S3_REGION=eu-central-1
MCP_AUDIT_S3_BATCH_SIZE=500
MCP_AUDIT_S3_FLUSH_INTERVAL_SECONDS=60
MCP_AUDIT_S3_KMS_KEY_ID=arn:aws:kms:eu-central-1:...:key/...
```

### Open questions before implementation

- Crash-safety of the in-memory batch (likely solved with an outbox table).
- Backfill story for existing rows (`gateway.cli audit export --since ...`).
- Tenant-key separation for compliance (per-tenant prefix or per-tenant bucket).
- IAM model for downstream consumers (Athena workgroups, etc.).

Until this lands, archive the Postgres audit table with the standard `pg_dump --table=audit_log` and ship it to S3 via your existing backup pipeline.

---

## References

- Architecture: `docs/architecture.md`
- Spec: `docs/superpowers/specs/2026-04-29-mcp-gateway-design.md`
- Sample policies: `config/policies.yaml`
