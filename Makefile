PY ?= python3.13

.PHONY: install fmt lint typecheck test test-unit test-integration test-e2e test-security cov up down logs seed clean test-mutation deploy-mocks deploy-gateway

install:
	$(PY) -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev]"
	. .venv/bin/activate && pre-commit install || true

fmt:
	. .venv/bin/activate && ruff format .
	. .venv/bin/activate && ruff check --fix .

lint:
	. .venv/bin/activate && ruff check .
	. .venv/bin/activate && ruff format --check .

typecheck:
	. .venv/bin/activate && mypy gateway

test-unit:
	. .venv/bin/activate && pytest -m "unit" -v

test-integration:
	. .venv/bin/activate && pytest -m "integration" -v

test-e2e:
	docker compose -f docker-compose.test.yml up -d --build
	@sleep 15
	. .venv/bin/activate && pytest -m "e2e" -v || (docker compose -f docker-compose.test.yml down && false)
	docker compose -f docker-compose.test.yml down

test-security:
	. .venv/bin/activate && pytest -m "security" -v
	. .venv/bin/activate && bandit -r gateway -x tests
	. .venv/bin/activate && pip-audit || true

test: test-unit test-integration

cov:
	. .venv/bin/activate && pytest --cov=gateway --cov-report=html --cov-report=term

test-mutation:
	. .venv/bin/activate && mutmut run --paths-to-mutate gateway/policy/,gateway/auth/

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f gateway

seed:
	docker compose exec gateway python -m gateway.cli seed

deploy-mocks:
	flyctl deploy --config mocks/idp/fly.toml -c mocks/idp || true
	flyctl deploy --config mocks/crm/fly.toml -c mocks/crm || true
	flyctl deploy --config mocks/payments/fly.toml -c mocks/payments || true

deploy-gateway:
	flyctl deploy

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build .venv
	find . -type d -name __pycache__ -exec rm -rf {} +
