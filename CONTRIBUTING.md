# Contributing to MCP Gateway

Thanks for considering a contribution. The project is small, so process is light — but discipline matters because this codebase ships into security-sensitive contexts.

## Getting set up

```bash
git clone https://github.com/Shcherbin96/mcp-gateway.git
cd mcp-gateway
make install         # creates .venv, installs deps, sets up pre-commit
docker compose up -d # starts postgres + mocks + gateway
make seed            # seeds demo tenant + agent + OAuth client
```

Verify your setup:

```bash
make test-unit       # ~12s, no Docker required
make test-integration # spins up a Postgres testcontainer
```

## Workflow

1. Open an issue first for non-trivial work (use the templates in `.github/ISSUE_TEMPLATE/`). For typo fixes / small refactors, jump straight to a PR.
2. Branch from `main`: `git checkout -b feat/<short-name>` or `fix/<short-name>`.
3. Follow TDD: write a failing test that demonstrates the gap, then implement.
4. Keep commits focused and message-style consistent with `git log` (Conventional Commits — `feat:`, `fix:`, `chore:`, `test:`, `docs:`).
5. Open a PR. CI runs lint + unit + integration + e2e + security automatically.

## Code style

- **Formatter:** `ruff format` (enforced by pre-commit + CI). Don't argue with the formatter.
- **Linter:** `ruff check`. The full ruleset is in `pyproject.toml`. Two ignores worth knowing: `E402` (we allow conditional imports inside functions for optional deps like Telegram), `N818` (legacy `Token*` exception names without `Error` suffix).
- **Types:** `mypy gateway` must pass. We're in a phased typing migration (full `--strict` is the goal, currently we don't enforce annotation completeness on every dict literal).
- **Comments:** add a comment only when the *why* is non-obvious. Don't restate what well-named code already says.

## Tests

- **Unit** (`tests/<module>/`): fast, no I/O, mock heavy. Mark with `@pytest.mark.unit`. Aim for these to cover pure logic — policy evaluation, JWT verification, redaction, retry policies.
- **Integration** (`@pytest.mark.integration`): touch a real Postgres via testcontainers. Use the `db_engine` and `db_session` fixtures from `tests/conftest.py`.
- **E2E** (`@pytest.mark.e2e`): full stack via `docker-compose.test.yml`. Run with `make test-e2e`. Slow; only run locally before opening a PR.
- **Security** (`@pytest.mark.security`): JWT attacks, tenant isolation, audit immutability. Touch sensitive surfaces — review carefully.

If you change a security-sensitive surface (anything in `gateway/auth/`, `gateway/middleware/authenticate.py`, `gateway/audit/`, `gateway/middleware/approve.py`), add a corresponding security test.

## Architecture decisions

If you're proposing something that changes a layer's contract (replacing the policy engine, swapping the audit sink, adding a new notifier transport), add a short ADR (Architecture Decision Record) to `docs/adr/` explaining the trade-off. Template:

```markdown
# ADR-N: <Title>

**Status:** Proposed | Accepted | Superseded
**Date:** YYYY-MM-DD

## Context

What problem are we solving? What are the constraints?

## Decision

What we chose, and the alternative we rejected.

## Consequences

What changes for users / operators / future contributors?
```

## Security

If you discover a security issue, **do not open a public issue**. Email the maintainer at `roman@…` (or open a private security advisory in GitHub) with a description and reproducer.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
