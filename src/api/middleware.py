"""Exception handlers — map domain errors to HTTP responses.

FastAPI calls the handler whose key matches the *most derived* class of the
raised exception. Our hierarchy is set up so registering a handler for
``TransientError`` covers ``RateLimitError`` too, etc., unless we add a more
specific handler — which we do, because rate limits deserve a 429 + the
upstream's ``Retry-After`` hint.

The trace_id in every response body comes from :data:`trace_id_var` (set by
``TraceIdMiddleware`` in :mod:`src.api.main`). That lets a 4xx/5xx response
travel back to ops dashboards with the same id used in server logs.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.api.schemas import ErrorResponse
from src.config.logging import get_logger, trace_id_var
from src.pipeline.errors import LanguageNotAllowedError
from src.providers.errors import (
    AuthError,
    CapabilityError,
    PermanentError,
    RateLimitError,
    TransientError,
)
from src.tenant_profile.resolver import TenantProfileNotFound

log = get_logger(__name__)


def _error_payload(
    *, error_code: str, detail: str, status_code: int, extra_headers: dict[str, str] | None = None
) -> JSONResponse:
    """Build a uniform ``ErrorResponse`` payload with the active trace_id."""
    body = ErrorResponse(
        error_code=error_code,
        detail=detail,
        trace_id=trace_id_var.get(),
    ).model_dump()
    headers = extra_headers or {}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


# ---- Provider errors ------------------------------------------------------


async def handle_rate_limit(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitError)
    # Echo the upstream's Retry-After hint so HTTP-level clients (and CDNs)
    # can back off correctly without parsing the body.
    headers = {}
    if exc.retry_after_seconds > 0:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    log.warning("api.error.rate_limit", retry_after=exc.retry_after_seconds, detail=str(exc))
    return _error_payload(
        error_code="rate_limited",
        detail=str(exc),
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        extra_headers=headers,
    )


async def handle_auth_error(request: Request, exc: Exception) -> JSONResponse:
    # Auth failures are an *operator* problem (bad API key, expired creds),
    # not a caller problem. 500 — service is misconfigured.
    log.error("api.error.provider_auth", detail=str(exc))
    return _error_payload(
        error_code="provider_auth_failed",
        detail="Upstream provider rejected our credentials. Check server configuration.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def handle_capability_error(request: Request, exc: Exception) -> JSONResponse:
    # The caller asked for something the provider can't do (unsupported
    # language pair, unknown provider name). 400 is the most honest code.
    log.info("api.error.capability", detail=str(exc))
    return _error_payload(
        error_code="capability_unsupported",
        detail=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


async def handle_transient_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, TransientError)
    log.warning("api.error.transient", detail=str(exc), type=type(exc).__name__)
    return _error_payload(
        error_code="upstream_transient",
        detail="Translation provider is temporarily unavailable. Please retry.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


async def handle_permanent_error(request: Request, exc: Exception) -> JSONResponse:
    # Bad input that the provider rejected. We don't know whether the issue
    # is the prompt, the language, or the content — but it WILL fail again,
    # so we report 400.
    log.warning("api.error.permanent", detail=str(exc), type=type(exc).__name__)
    return _error_payload(
        error_code="upstream_rejected",
        detail=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


# ---- Profile / resolver errors -------------------------------------------


async def handle_profile_not_found(request: Request, exc: Exception) -> JSONResponse:
    log.info("api.error.profile_not_found", detail=str(exc))
    return _error_payload(
        error_code="profile_not_found",
        detail=str(exc),
        status_code=status.HTTP_404_NOT_FOUND,
    )


# ---- Generic ValueError -> 400 --------------------------------------------


async def handle_value_error(request: Request, exc: Exception) -> JSONResponse:
    # We raise ``ValueError`` from the pipeline's input-validation stage.
    # Treat it as a client error — empty text, bad language code, etc.
    log.info("api.error.value", detail=str(exc))
    return _error_payload(
        error_code="bad_request",
        detail=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


# ---- Pipeline language gate ----------------------------------------------


async def handle_language_not_allowed(request: Request, exc: Exception) -> JSONResponse:
    """Map :class:`LanguageNotAllowedError` to 400 + structured error_code.

    The error itself already carries the machine-readable ``error_code``
    attribute, but we hard-code the literal here too so the API contract
    is self-evident at the handler site.
    """
    assert isinstance(exc, LanguageNotAllowedError)
    log.info(
        "api.error.language_not_allowed",
        target_lang=exc.target_lang,
        allowed=exc.allowed,
    )
    return _error_payload(
        error_code="language_not_allowed",
        detail=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


# ---- Wiring ---------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all handlers to a FastAPI app.

    Order matters in FastAPI: a more specific class registered later wins
    over a less specific one. We register from base → derived so the
    derived handlers take precedence.
    """
    # Provider hierarchy: base classes first, then specific subclasses.
    app.add_exception_handler(TransientError, handle_transient_error)
    app.add_exception_handler(PermanentError, handle_permanent_error)
    app.add_exception_handler(RateLimitError, handle_rate_limit)  # subclass of Transient
    app.add_exception_handler(AuthError, handle_auth_error)  # subclass of Permanent
    app.add_exception_handler(CapabilityError, handle_capability_error)  # subclass of Permanent

    # Tenant profile resolver errors.
    app.add_exception_handler(TenantProfileNotFound, handle_profile_not_found)

    # Generic input errors.
    app.add_exception_handler(ValueError, handle_value_error)

    # Sub-proyek K language gate.
    app.add_exception_handler(LanguageNotAllowedError, handle_language_not_allowed)
