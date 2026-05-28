"""Error hierarchy for provider calls.

The pipeline (Phase 4) and the router (future) react to errors by *class*, not
by inspecting messages. Splitting transient vs permanent at the type level lets
``RetryingProvider`` decide what to do without parsing strings.

Hierarchy::

    TranslationProviderError              (base — never raised directly)
    ├── TransientError                    (retryable — backoff & try again)
    │   └── RateLimitError                (has retry_after hint)
    └── PermanentError                    (do NOT retry — fix the request/config)
        ├── CapabilityError               (provider can't do this)
        └── AuthError                     (credential broken / missing)

When a provider catches an SDK-specific exception, it must wrap it in one of
these and pass the original as ``__cause__`` (use ``raise ... from original``).
That way, ``str(err.__cause__)`` still gives us the upstream message for logs.
"""

from __future__ import annotations


class TranslationProviderError(Exception):
    """Root of all provider errors. Don't raise directly — pick a subclass."""


class TransientError(TranslationProviderError):
    """Likely to succeed if retried. Examples: 5xx, network timeout, connection
    reset. ``RetryingProvider`` will apply exponential backoff to these.
    """


class PermanentError(TranslationProviderError):
    """Will fail the same way on retry. Examples: malformed request, invalid
    auth, content blocked by safety filter. Surface immediately to the caller.
    """


class RateLimitError(TransientError):
    """429 from the provider. Retryable, but only after waiting at least
    ``retry_after_seconds`` (provided by the upstream's ``Retry-After`` header
    when present, otherwise our retry policy's default backoff).

    ``error_code`` is a stable machine-readable tag used by the pipeline,
    agents, and API middleware to produce consistent ``error_code`` fields in
    log rows and HTTP responses — e.g. ``activity.error_code == "rate_limited"``.
    """

    error_code: str = "rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: int = 0) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class CapabilityError(PermanentError):
    """Provider doesn't support a feature the caller requested (e.g. streaming
    when ``supports_streaming=False``, or a language pair in the unsupported
    list). The router should have caught this earlier — if it didn't, that's
    a bug in the routing logic.
    """


class AuthError(PermanentError):
    """Credentials are missing, expired, or rejected. Retrying won't help;
    the operator needs to update the API key.
    """
