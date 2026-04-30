"""ASGI middleware adding standard security headers to every response.

Hardens the Web UI against common attack vectors: clickjacking, MIME sniffing,
cross-origin abuse, mixed content, and external resource injection. Headers
follow OWASP recommendations.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Content Security Policy — Web UI uses HTMX (loaded from unpkg) + inline scripts
# emitted by templates (e.g. ADMIN_TOKEN constant in approvals.html). We allow
# 'self' + the unpkg CDN for scripts and 'unsafe-inline' for the small inlined
# bootstrap. Tightening to nonces is a future hardening pass.
CSP_DIRECTIVES = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self' ws: wss:; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        h = response.headers
        # Clickjacking — explicit, even though CSP frame-ancestors does the same.
        h.setdefault("X-Frame-Options", "DENY")
        # MIME sniffing — browser must trust the Content-Type header.
        h.setdefault("X-Content-Type-Options", "nosniff")
        # Cross-origin requests should not leak full URL to other origins.
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Disable Flash / PDF cross-domain access.
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        # Restrict legacy permission features the gateway never uses.
        h.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        # Browser HSTS — only set when behind HTTPS to avoid breaking local http://.
        if request.url.scheme == "https":
            h.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        # Single Content-Security-Policy applied uniformly.
        h.setdefault("Content-Security-Policy", CSP_DIRECTIVES)
        return response


def install(app: Any) -> None:
    """Register the middleware on a FastAPI/Starlette app."""
    app.add_middleware(SecurityHeadersMiddleware)
