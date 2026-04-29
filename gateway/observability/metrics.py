"""Prometheus metric definitions. Exported via /metrics endpoint."""

from prometheus_client import Counter, Gauge, Histogram

REQUESTS_TOTAL = Counter(
    "mcp_gateway_requests_total",
    "Total tool-call requests handled by the gateway",
    ["tool", "status", "tenant"],
)

REQUEST_DURATION = Histogram(
    "mcp_gateway_request_duration_seconds",
    "End-to-end request duration including approval wait",
    ["tool"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300),
)

APPROVALS_PENDING = Gauge(
    "mcp_gateway_approvals_pending",
    "Number of approval requests currently awaiting decision",
    ["tenant"],
)

APPROVALS_TOTAL = Counter(
    "mcp_gateway_approvals_total",
    "Total approval decisions by outcome",
    ["decision"],
)

UPSTREAM_FAILURES = Counter(
    "mcp_gateway_upstream_failures_total",
    "Upstream service failures (network, 5xx, circuit-open)",
    ["service"],
)
