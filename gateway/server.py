"""FastAPI app entrypoint — wires middleware, tools, approvals, audit, and web UI."""

import contextlib
import time
from pathlib import Path

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
from gateway.middleware.audit import make_audit
from gateway.middleware.authenticate import make_authenticate
from gateway.middleware.authorize import make_authorize
from gateway.middleware.approve import make_approve
from gateway.middleware.chain import CallContext, Pipeline
from gateway.middleware.execute import make_execute
from gateway.observability.logging import configure_logging, get_logger
from gateway.observability.metrics import REQUEST_DURATION, REQUESTS_TOTAL
from gateway.observability.tracing import configure_tracing
from gateway.policy.evaluator import PolicyEvaluator
from gateway.policy.loader import load_policies
from gateway.tools.crm import build_crm_tools
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
    pay_client = UpstreamClient(
        settings.payments_base_url, settings.payments_api_key, "payments"
    )
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

        tg_notifier = TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_admin_chat_id
        )
        notifiers.append(tg_notifier)
        tg_app = build_telegram_app(
            settings.telegram_bot_token,
            store,
            broadcaster,
            admin_chat_id=settings.telegram_admin_chat_id,
        )
        await tg_app.initialize()
        await tg_app.start()
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

    # Reaper
    reaper = TimeoutReaper(sf, settings.approval_timeout_seconds, broadcaster)
    reaper.start()

    # Web router (single-tenant view: pick first tenant)
    try:
        async with sf() as s:
            first = (await s.execute(select(Tenant).limit(1))).scalar_one_or_none()
    except Exception as e:
        log.warning("web_router_skipped_db_error", error=str(e))
        first = None

    if first is not None:
        templates = Jinja2Templates(
            directory=str(Path(__file__).parent / "web" / "templates")
        )
        app.include_router(
            make_router(
                templates=templates,
                audit_reader=reader,
                approval_store=store,
                broadcaster=broadcaster,
                session_factory=sf,
                default_tenant_id=first.id,
            )
        )
    else:
        log.warning("web_router_skipped_no_tenants")

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


app = FastAPI(title="MCP Gateway", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "web" / "static")),
    name="static",
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, "db_unavailable") from e


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/mcp/tools")
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


@app.post("/mcp/call/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    payload = await request.json()
    auth_header = request.headers.get("authorization", "")
    token = (
        auth_header[len("Bearer ") :].strip()
        if auth_header.lower().startswith("bearer ")
        else None
    )

    # Redact BEFORE the pipeline runs so audit always has redacted_params,
    # even when authentication or other early steps fail.
    rt = request.app.state.registry.get(tool_name)
    redact_fn = rt.meta.redact if rt else (lambda p: dict(p))
    redacted = redact_fn(payload)

    ctx = CallContext(
        token=token,
        tool=tool_name,
        params=dict(payload),
        redacted_params=redacted,
    )

    pipeline: Pipeline = request.app.state.pipeline
    audit_step = request.app.state.audit_step

    started = time.monotonic()
    try:
        await pipeline.run(ctx)
    finally:
        try:
            await audit_step(ctx)
        except Exception as e:
            log.error("audit_failed", error=str(e), trace_id=ctx.trace_id)
            return JSONResponse(
                {"error": "audit_failure", "trace_id": ctx.trace_id},
                status_code=500,
                headers={"X-Trace-Id": ctx.trace_id},
            )
        duration = time.monotonic() - started
        REQUEST_DURATION.labels(tool=tool_name).observe(duration)
        REQUESTS_TOTAL.labels(
            tool=tool_name,
            status=ctx.result_status,
            tenant=str(ctx.tenant_id) if ctx.tenant_id else "none",
        ).inc()

    headers = {"X-Trace-Id": ctx.trace_id}
    if ctx.result_status == "auth_failed":
        return JSONResponse({"error": str(ctx.error)}, status_code=401, headers=headers)
    if ctx.result_status == "denied":
        return JSONResponse({"error": str(ctx.error)}, status_code=403, headers=headers)
    if ctx.result_status == "rejected":
        return JSONResponse(
            {"error": "approval rejected"}, status_code=403, headers=headers
        )
    if ctx.result_status == "timeout":
        return JSONResponse(
            {"error": "approval timeout"}, status_code=408, headers=headers
        )
    if ctx.result_status == "upstream_unavailable":
        return JSONResponse({"error": str(ctx.error)}, status_code=502, headers=headers)
    if ctx.result_status.startswith("upstream_4xx_"):
        try:
            status_code = int(ctx.result_status[len("upstream_4xx_") :])
        except ValueError:
            status_code = 502
        return JSONResponse(
            {"error": str(ctx.error)}, status_code=status_code, headers=headers
        )
    if ctx.result_status == "upstream_5xx":
        return JSONResponse({"error": str(ctx.error)}, status_code=502, headers=headers)
    if ctx.result_status == "error":
        return JSONResponse(
            {"error": str(ctx.error), "trace_id": ctx.trace_id},
            status_code=500,
            headers=headers,
        )

    return JSONResponse(ctx.result or {}, headers=headers)
