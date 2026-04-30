"""FastAPI app entrypoint — wires middleware, tools, approvals, audit, and web UI."""

import contextlib
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.approval.notifier import CompositeNotifier
from gateway.approval.store import ApprovalStore
from gateway.approval.timeout import TimeoutReaper
from gateway.approval.websocket import WebSocketBroadcaster
from gateway.audit.reader import AuditReader
from gateway.audit.writer import AuditWriter
from gateway.auth.token_validator import JWKSTokenValidator
from gateway.config import get_settings
from gateway.db.models import Tenant
from gateway.db.session import engine
from gateway.mcp_http import make_mcp_http_router
from gateway.middleware.approve import make_approve
from gateway.middleware.audit import make_audit
from gateway.middleware.authenticate import make_authenticate
from gateway.middleware.authorize import make_authorize
from gateway.middleware.chain import Pipeline
from gateway.middleware.execute import make_execute
from gateway.middleware.rate_limit import RateLimiter
from gateway.observability.logging import configure_logging, get_logger
from gateway.observability.tracing import configure_tracing
from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.loader import load_policies
from gateway.tools.crm import build_crm_tools
from gateway.tools.dispatch import invoke_tool
from gateway.tools.payments import build_payment_tools
from gateway.tools.registry import ToolRegistry
from gateway.tools.upstream import UpstreamClient
from gateway.web.routes import make_router

log = get_logger(__name__)
settings = get_settings()


def _jwks_provider_from_url(url: str):
    """Lazy refreshing JWKS fetcher backed by PyJWKClient."""
    import jwt

    client = jwt.PyJWKClient(url, cache_keys=True, lifespan=600)

    def provider():
        return [(k.key_id, k.key) for k in client.get_signing_keys()]

    return provider


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_tracing(app)

    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app.state.session_factory = sf

    # Auth
    validator = JWKSTokenValidator(
        jwks_provider=_jwks_provider_from_url(settings.oauth_jwks_url),
        issuer=settings.oauth_issuer,
        audience=settings.oauth_audience,
    )

    # Policy
    policy_doc = load_policies(settings.policy_file)
    evaluator = PolicyEvaluator(policy_doc)

    # Tools
    crm_client = UpstreamClient(settings.crm_base_url, settings.crm_api_key, "crm")
    pay_client = UpstreamClient(settings.payments_base_url, settings.payments_api_key, "payments")
    registry = ToolRegistry()
    for meta, handler in build_crm_tools(crm_client) + build_payment_tools(pay_client):
        registry.register(meta, handler)
    app.state.registry = registry

    # Approvals
    store = ApprovalStore(sf)
    broadcaster = WebSocketBroadcaster()
    notifiers: list = [broadcaster]
    tg_app = None
    if settings.telegram_bot_token and settings.telegram_admin_chat_id:
        from gateway.approval.telegram import TelegramNotifier
        from gateway.approval.telegram_bot import build_telegram_app

        tg_notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_admin_chat_id)
        notifiers.append(tg_notifier)
        tg_app = build_telegram_app(
            settings.telegram_bot_token,
            store,
            broadcaster,
            admin_chat_id=settings.telegram_admin_chat_id,
        )
        await tg_app.initialize()
        await tg_app.start()
        if tg_app.updater is not None:
            await tg_app.updater.start_polling()
    app.state.tg_app = tg_app

    notifier = CompositeNotifier(notifiers)

    # Audit
    writer = AuditWriter(sf)
    reader = AuditReader(sf)

    # Pipeline
    app.state.pipeline = Pipeline(
        steps=[
            make_authenticate(validator),
            make_authorize(evaluator, sf),
            make_approve(store, notifier),
            make_execute(registry),
        ]
    )
    app.state.audit_step = make_audit(writer)

    # Rate limiter (per agent_id; falls back to client IP when no token).
    app.state.rate_limiter = RateLimiter(
        rate_per_minute=settings.rate_limit_per_minute,
        burst=settings.rate_limit_burst,
    )

    # Reaper
    reaper = TimeoutReaper(sf, settings.approval_timeout_seconds, broadcaster)
    reaper.start()

    # Web router (single-tenant view). Tenant resolution happens lazily on each
    # request via a callable, so the gateway can boot before seeding completes.
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))

    async def _resolve_default_tenant() -> UUID | None:
        try:
            async with sf() as s:
                first = (await s.execute(select(Tenant).limit(1))).scalar_one_or_none()
                return first.id if first is not None else None
        except Exception as e:
            log.warning("web_default_tenant_lookup_failed", error=str(e))
            return None

    app.include_router(
        make_router(
            templates=templates,
            audit_reader=reader,
            approval_store=store,
            broadcaster=broadcaster,
            session_factory=sf,
            default_tenant_id=_resolve_default_tenant,
        )
    )

    # MCP Streamable HTTP transport (single endpoint at /mcp/rpc).
    # Mounted lazily inside lifespan because the legacy /mcp/tools and
    # /mcp/call/{tool_name} routes below depend on app.state.* being populated
    # — same lifecycle expectation applies here.
    app.include_router(make_mcp_http_router())

    try:
        yield
    finally:
        await reaper.stop()
        if app.state.tg_app:
            with contextlib.suppress(Exception):
                await app.state.tg_app.updater.stop()
            with contextlib.suppress(Exception):
                await app.state.tg_app.stop()
            with contextlib.suppress(Exception):
                await app.state.tg_app.shutdown()
        with contextlib.suppress(Exception):
            await crm_client.aclose()
        with contextlib.suppress(Exception):
            await pay_client.aclose()


app = FastAPI(
    title="MCP Gateway",
    description=(
        "Production-grade Model Context Protocol gateway. "
        "Every tool call passes through 5 control layers: "
        "authenticate → authorize → approve → execute → audit."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "MCP",
            "description": (
                "Model Context Protocol endpoints. ``/mcp/rpc`` is the spec-compliant "
                "Streamable HTTP transport (MCP 2025-06-18). ``/mcp/tools`` and "
                "``/mcp/call/{tool_name}`` are the legacy REST surface — kept for "
                "backward compatibility, prefer ``/mcp/rpc`` for new clients."
            ),
        },
        {"name": "Approvals", "description": "Human-in-the-loop approval flow (admin-only)."},
        {"name": "Audit", "description": "Append-only audit log query API (admin-only)."},
        {"name": "Operations", "description": "Health, readiness, Prometheus metrics."},
    ],
)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "web" / "static")),
    name="static",
)


@app.get("/healthz", tags=["Operations"], summary="Liveness probe")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", tags=["Operations"], summary="Readiness probe (checks DB)")
async def readyz():
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, "db_unavailable") from e


@app.get(
    "/metrics",
    tags=["Operations"],
    summary="Prometheus metrics",
    response_class=PlainTextResponse,
)
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get(
    "/mcp/tools",
    tags=["MCP"],
    summary="List available tools (legacy REST — prefer /mcp/rpc tools/list)",
)
async def list_tools(request: Request):
    return {
        "tools": [
            {
                "name": m.name,
                "description": m.description,
                "inputSchema": m.input_schema,
            }
            for m in request.app.state.registry.list()
        ]
    }


@app.post(
    "/mcp/call/{tool_name}",
    tags=["MCP"],
    summary="Invoke a tool — legacy REST surface (prefer /mcp/rpc tools/call)",
)
async def call_tool(tool_name: str, request: Request):
    payload = await request.json()
    auth_header = request.headers.get("authorization", "")
    token = (
        auth_header[len("Bearer ") :].strip() if auth_header.lower().startswith("bearer ") else None
    )
    client_ip = request.client.host if request.client else None

    outcome = await invoke_tool(
        app_state=request.app.state,
        tool_name=tool_name,
        payload=payload,
        token=token,
        client_ip=client_ip,
    )

    if outcome.rate_limited:
        return JSONResponse(
            outcome.body,
            status_code=429,
            headers={"Retry-After": str(int(outcome.retry_after))},
        )

    headers = {"X-Trace-Id": outcome.trace_id} if outcome.trace_id else {}
    return JSONResponse(outcome.body, status_code=outcome.http_status, headers=headers)
