"""Pipeline-specific error types.

Lives separately from src.providers.errors so the pipeline can raise
domain-level errors (LanguageNotAllowedError, etc.) without polluting
the provider abstraction.
"""

from __future__ import annotations


class LanguageNotAllowedError(Exception):
    """Raised when target_lang is not in tenant_profile.allowed_language.

    Carries the rejected lang + allowed list so the API error handler
    can include them in the response body. ``error_code`` attribute is
    read by the pipeline's exception logger (per pipeline.py:152
    ``getattr(e, "error_code", None)``).
    """

    error_code = "language_not_allowed"

    def __init__(self, *, target_lang: str, allowed: list[str]) -> None:
        self.target_lang = target_lang
        self.allowed = allowed
        super().__init__(f"target_lang {target_lang!r} not in allowed_language {allowed!r}")
