# Load tests

A small Locust smoke test that hammers the MCP Gateway with weighted calls
to `/mcp/call/get_customer` (weight 3) and `/mcp/call/list_orders`
(weight 1), using a real bearer token issued by the mock IdP.

## Prerequisites

- The gateway is reachable on `--host` (default for examples below: `http://localhost:8000`).
- The mock IdP is reachable on `IDP_URL` (defaults to `http://localhost:9000`).
- The IdP exposes `POST /register` (returns `client_id` / `client_secret`)
  and `POST /token` (client_credentials grant returning `access_token`).

The token is fetched once at test start (see `@events.test_start`) and
shared with every spawned `GatewayUser` via
`environment.parsed_options.token`.

## Running locally (interactive UI)

Bring the stack up with `docker compose up -d`, then:

```bash
.venv/bin/locust -f loadtest/locustfile.py --host http://localhost:8000
```

Open http://localhost:8089 to start a run.

If your IdP is somewhere else, override it:

```bash
IDP_URL=http://localhost:9000 \
  .venv/bin/locust -f loadtest/locustfile.py --host http://localhost:8000
```

## Headless smoke (matches CI)

The `load-smoke` job in `.github/workflows/ci.yml` runs:

```bash
locust -f loadtest/locustfile.py --headless \
  -u 10 -r 5 -t 30s \
  --host http://localhost:8000 \
  --only-summary
```

That spawns 10 users at 5/s, runs for 30 seconds, and prints only the
final summary. Use the same flags locally to reproduce CI behavior.
