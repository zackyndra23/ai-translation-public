"""FastAPI application entrypoint.

Cross-cutting concerns wired up here:

1. **structlog**: logging configured at import time so every code path
   (including uvicorn workers + Alembic) uses the same processors.

2. **TraceIdMiddleware**: every request gets an ``X-Trace-Id`` (echoed back,
   generated when missing). Bound to a ContextVar so log lines from any code
   path in the request can be correlated.

3. **CORS**: localhost:5173 (frontend-demo Vite, sub-proyek L) and
   localhost:8001 (Phase 7 webpage SDK demo) are allowed. Production
   allowlist will be tighter.

4. **TenantAuthMiddleware**: installed via install_auth_middleware AFTER CORS
   (so preflight 200s are never blocked by auth) and AFTER TraceId (so the
   trace_id is bound before auth logs run). Public paths bypass it entirely.

5. **Exception handlers**: domain exceptions (provider errors, profile
   not-found, etc.) are mapped to typed HTTP responses via
   :mod:`src.api.middleware`.

Routes mount under ``/health``, ``/translate``, ``/auth``, and the reference
endpoints from :mod:`src.api.routes`. The legacy ``/profiles`` CRUD is
replaced by the junction model (tenant + tenant_profile + service); operator
CRUD for the new model is deferred to a follow-up sub-proyek.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.api.middleware import register_exception_handlers
from src.api.routes import health as health_routes
from src.api.routes import translate as translate_routes
from src.api.routes.auth import router as auth_router
from src.api.routes.reference import router as reference_router
from src.auth.middleware import install_auth_middleware
from src.config.logging import configure_logging, get_logger, trace_id_var

configure_logging()
log = get_logger(__name__)

# CORS allowlist. Sub-proyek L extends this to include the frontend-demo
# Vite dev server (:5173). Streamlit (:8501) entries removed — demo/app.py
# was deleted in sub-proyek J. SDK landing page (:8001) retained.
_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Bind an ``X-Trace-Id`` to the structlog context per request.

    We reuse an incoming header if the caller already has one (typical in
    microservice fan-outs) and otherwise mint a fresh hex uuid. The id is
    always echoed back, so the caller can quote it when reporting an issue.
    """

    HEADER = "X-Trace-Id"

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        trace_id = request.headers.get(self.HEADER) or uuid.uuid4().hex
        token = trace_id_var.set(trace_id)
        try:
            log.info("request.start", method=request.method, path=request.url.path)
            response = await call_next(request)
            response.headers[self.HEADER] = trace_id
            log.info(
                "request.end",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            )
            return response
        finally:
            trace_id_var.reset(token)


app = FastAPI(
    title="AI Translation API",
    version="0.1.0",
    description=(
        "Domain-aware translation service powered by Claude with per-profile "
        "glossary, tone, and few-shot examples. See CLAUDE.md for architecture."
    ),
)

# Middleware ordering matters in Starlette/FastAPI: add_middleware wraps in
# reverse order, so the LAST add_middleware call runs FIRST on the request.
# Desired inbound order: CORS -> TraceId -> TenantAuth -> route handler.
# Therefore we register: CORS first, TraceId second, TenantAuth last.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)
app.add_middleware(TraceIdMiddleware)
# TenantAuthMiddleware: validates Bearer JWT or X-Tenant-API-Key on every
# non-public route. PUBLIC_PATHS (health, reference, /auth/refresh-jwt, docs)
# bypass it so the frontend cascade can fetch reference data before login.
install_auth_middleware(app)

# Exception handlers — keep close to app construction so the order is
# obvious to a reader scanning this file.
register_exception_handlers(app)

# Routers. Order matters for Swagger documentation grouping only, not routing.
# health + translate: carried over from MVP.
# auth + reference: added in sub-proyek I (tenant junction redesign).
app.include_router(health_routes.router)
app.include_router(translate_routes.router)
app.include_router(auth_router)
app.include_router(reference_router)

__all__ = ["app"]
