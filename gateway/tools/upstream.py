"""Async HTTP client for upstream services with retry + circuit breaker."""

import time
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gateway.observability.logging import get_logger
from gateway.observability.metrics import UPSTREAM_FAILURES
from gateway.tools.exceptions import (
    UpstreamClientError,
    UpstreamServerError,
    UpstreamUnavailable,
)

log = get_logger(__name__)


class CircuitBreaker:
    """Half-open circuit breaker; opens after N consecutive failures."""

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

    def on_success(self) -> None:
        self._fails = 0
        self._opened_at = None

    def on_failure(self) -> None:
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
        except (UpstreamUnavailable, UpstreamServerError):
            self.on_failure()
            raise
        else:
            self.on_success()


class UpstreamClient:
    """Async HTTP client with auth header, retry on 5xx, and circuit breaker."""

    def __init__(self, base_url: str, api_key: str, service_name: str, timeout: float = 5.0):
        self._base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key}
        self._service = service_name
        self._client = httpx.AsyncClient(timeout=timeout, base_url=self._base)
        self._breaker = CircuitBreaker(service_name)

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type((UpstreamUnavailable, UpstreamServerError)),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        async with self._breaker.guard():
            try:
                req_headers = dict(self._headers)
                if headers:
                    req_headers.update(headers)
                if idempotency_key:
                    req_headers["idempotency-key"] = idempotency_key
                resp = await self._client.request(
                    method, path, json=json, params=params, headers=req_headers
                )
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
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def post(self, path: str, json: dict, idempotency_key: str | None = None) -> dict:
        resp = await self._request(
            "POST", path, json=json, idempotency_key=idempotency_key or str(uuid4())
        )
        return resp.json()

    async def patch(self, path: str, json: dict) -> dict:
        resp = await self._request("PATCH", path, json=json)
        return resp.json()
