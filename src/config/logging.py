"""Structured logging setup using structlog.

We emit JSON in non-development environments so log shippers (Loki, ELK, Datadog)
can parse without a regex. In development we pretty-print to the console because
JSON is unreadable when you're tailing logs by hand.

A ``trace_id`` context var is added so every log entry inside a request carries
the same correlation id. The middleware in ``src/api/main.py`` is responsible for
binding/unbinding that value per request.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

from src.config.settings import Environment, get_settings

# Module-level ContextVar so the request-scoped trace_id is visible to every log
# call made during that request, without threading it through call signatures.
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def _add_trace_id(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor that injects the current trace_id, if one is bound.

    Signature matches ``structlog.types.Processor`` — the first two positional args
    are required by the protocol even though we don't use them.
    """
    trace_id = trace_id_var.get()
    if trace_id is not None:
        event_dict["trace_id"] = trace_id
    return event_dict


def configure_logging() -> None:
    """Idempotent setup. Safe to call from app startup AND from test fixtures."""
    settings = get_settings()

    # Funnel stdlib logging (uvicorn, sqlalchemy, etc.) into structlog so we get one
    # consistent output format instead of two competing log streams.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level,
        force=True,  # override any handlers configured by libraries we imported before us
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_trace_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # JSON in prod/staging for machine parsing; pretty console renderer in dev for humans.
    if settings.environment == Environment.development:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.types.FilteringBoundLogger:
    """Convenience accessor so callers don't import structlog directly.

    The wrapper type is FilteringBoundLogger because that's what
    ``make_filtering_bound_logger`` produces inside :func:`configure_logging`.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
