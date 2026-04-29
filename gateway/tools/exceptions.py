"""Exception hierarchy for tool execution and upstream calls."""


class ToolError(Exception):
    """Base class for all tool-related errors."""


class UpstreamError(ToolError):
    """Base class for errors talking to an upstream service."""


class UpstreamUnavailable(UpstreamError):
    """Upstream is unreachable (network error, timeout, or circuit open)."""


class UpstreamClientError(UpstreamError):
    """Upstream returned a 4xx response — caller's fault, do not retry."""

    def __init__(self, status: int, body: dict | str):
        super().__init__(f"client error {status}")
        self.status = status
        self.body = body


class UpstreamServerError(UpstreamError):
    """Upstream returned a 5xx response — retryable."""
