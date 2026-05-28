# Translation Log Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every `/translate` invocation (success + failure) to Postgres as foundation for observability, traceability, and dashboard analytics.

**Architecture:** New `translation_logs` table + ORM model + repository + `record_log` pipeline stage that runs in a `finally` block (success and failure paths). Write is sync within the pipeline but tolerant of DB failure (warn + swallow, match cache ADR-013). Forward columns for sub-proyek C (language detection) and analytics dashboard (F) included nullable now to avoid migration chain.

**Tech Stack:** PostgreSQL 16, SQLAlchemy 2.0 (async, `Mapped[]` style), Alembic, Pydantic v2, FastAPI, pytest + pytest-asyncio.

**Commit policy:** Per user preference, NO commits during execution of individual tasks. Plan is organized into 3 phases; at the end of each phase a 2-sentence commit message is recommended and the user explicitly confirms before the `git commit` command runs. **Never `git push`** — user pushes manually.

**Spec reference:** `docs/superpowers/specs/2026-05-21-translation-log-table-design.md`

---

## File Structure

**New files:**

| Path | Responsibility |
|------|----------------|
| `alembic/versions/002_translation_logs.py` | Migration: CREATE TABLE + 3 indexes |
| `src/translation_logs/__init__.py` | Package marker (empty) |
| `src/translation_logs/schemas.py` | `TranslationLogCreate`, `TranslationLogRead` Pydantic models |
| `src/translation_logs/repository.py` | `TranslationLogRepository` (`create()` + `NotImplementedError` stubs for read methods) |
| `src/translation_logs/sanitize.py` | `sanitize_error(text)` — regex redact + truncate |
| `tests/translation_logs/__init__.py` | Package marker (empty) |
| `tests/translation_logs/test_sanitize.py` | Sanitize unit tests |
| `tests/translation_logs/test_repository.py` | Repository unit tests |
| `tests/translation_logs/test_record_log_stage.py` | Stage unit tests with mocked repo |
| `tests/pipeline/test_pipeline_logging.py` | Pipeline integration tests (success / cache hit / error paths) |
| `tests/pipeline/test_pipeline_batch_logging.py` | Batch logging tests |
| `tests/api/test_translate_logging.py` | API-level log_id propagation tests |

**Modified files:**

| Path | Change |
|------|--------|
| `src/db/models.py` | Add `TranslationLog` ORM model |
| `src/pipeline/schemas.py` | Add `batch_id`, `batch_index`, `request_metadata` to `PipelineRequest`; add `log_id` to `PipelineResult` |
| `src/pipeline/stages.py` | Extend `PipelineContext` with new fields; add `record_log` stage function |
| `src/pipeline/pipeline.py` | Update `TranslationPipeline.__init__` (add `log_repo`); refactor `translate()` to `try / except / finally` with `record_log` in finally; inject `log_id` into returned result |
| `src/api/schemas.py` | Add `log_id` field to `TranslateResponse` and `BatchTranslateResultItem` |
| `src/api/dependencies.py` | Add `get_translation_log_repository` factory; update `get_pipeline` to inject `log_repo` |
| `src/api/routes/translate.py` | Update `_to_response` (echo `log_id`); update `_to_pipeline_request` (pass `batch_id`/`batch_index`); generate `batch_id` once in `/batch` |
| `tests/api/conftest.py` | (No change needed — existing `get_db` override carries log repo) |
| `CLAUDE.md` | Append ADR-026, ADR-027, ADR-028; add Phase status entry for "Sub-proyek B" |

---

# PHASE 1 — Data layer

Goal of phase: tabel ada di Postgres, ORM model bisa CRUD, repository punya `create()` yang ter-test, sanitize helper bekerja. Pipeline belum tahu apa-apa tentang ini — sub-proyek tetap shippable kalau berhenti di sini (zero behavior change, hanya capability tambahan).

## Task 1: Migration + ORM model

**Files:**
- Create: `alembic/versions/002_translation_logs.py`
- Modify: `src/db/models.py` (append new model class)

- [ ] **Step 1.1: Create migration file**

Create `alembic/versions/002_translation_logs.py` with full content:

```python
"""Translation log table — observability and dashboard data source.

Revision ID: 002_translation_logs
Revises: 001_profile_schema
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "002_translation_logs"
down_revision: str | None = "001_profile_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_logs",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=True),
        sa.Column("batch_index", sa.Integer(), nullable=True),
        # Multi-tenancy & profile snapshot
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id"),
            nullable=False,
        ),
        sa.Column("profile_slug", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("quality_mode", sa.String(16), nullable=True),
        # Request
        sa.Column("source_lang", sa.String(8), nullable=False),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_length", sa.Integer(), nullable=False),
        sa.Column("source_text_hash", sa.CHAR(64), nullable=False),
        # Response
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("translated_text_length", sa.Integer(), nullable=True),
        # Model & cost
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        # Pipeline outcome
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("cache_key", sa.CHAR(32), nullable=True),
        sa.Column("glossary_compliance_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("glossary_violations", JSONB(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        # Prompt template
        sa.Column(
            "prompt_template_name",
            sa.String(64),
            nullable=False,
            server_default="translate",
        ),
        sa.Column("prompt_template_version", sa.String(32), nullable=True),
        # Forward columns for sub-proyek C
        sa.Column("detected_source_lang", sa.String(8), nullable=True),
        sa.Column("detected_output_lang", sa.String(8), nullable=True),
        sa.Column("source_lang_mismatch", sa.Boolean(), nullable=True),
        sa.Column("output_lang_mismatch", sa.Boolean(), nullable=True),
        # Open-ended metadata
        sa.Column("request_metadata", JSONB(), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("provider_duration_ms", sa.Integer(), nullable=True),
        # Constraints
        sa.CheckConstraint(
            "status IN ('success','failed')",
            name="ck_translation_logs_status",
        ),
        sa.CheckConstraint(
            "glossary_compliance_score IS NULL OR (glossary_compliance_score >= 0 AND glossary_compliance_score <= 1)",
            name="ck_translation_logs_compliance",
        ),
    )

    op.create_index(
        "ix_translation_logs_tenant_started",
        "translation_logs",
        ["tenant_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_translation_logs_tenant_profile_started",
        "translation_logs",
        ["tenant_id", "profile_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_translation_logs_failed_partial",
        "translation_logs",
        ["tenant_id", sa.text("started_at DESC")],
        postgresql_where=sa.text("status = 'failed'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_translation_logs_failed_partial", table_name="translation_logs"
    )
    op.drop_index(
        "ix_translation_logs_tenant_profile_started", table_name="translation_logs"
    )
    op.drop_index("ix_translation_logs_tenant_started", table_name="translation_logs")
    op.drop_table("translation_logs")
```

- [ ] **Step 1.2: Add ORM model**

Append to `src/db/models.py` after `ProfileVersion` class:

```python
class TranslationLog(Base):
    """Audit row for every translation call (success or failure).

    Written by the ``record_log`` pipeline stage in a ``finally`` block, so
    we get one row per ``TranslationPipeline.translate`` invocation regardless
    of outcome. ADR-026 explains the full-plaintext storage choice.

    Denormalised on purpose: ``profile_slug`` and ``quality_mode`` are duplicated
    from the profile so dashboard GROUP BY queries don't need joins, and so
    historical truth is preserved if a profile is renamed.
    """

    __tablename__ = "translation_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success','failed')",
            name="ck_translation_logs_status",
        ),
        CheckConstraint(
            "glossary_compliance_score IS NULL OR "
            "(glossary_compliance_score >= 0 AND glossary_compliance_score <= 1)",
            name="ck_translation_logs_compliance",
        ),
        Index(
            "ix_translation_logs_tenant_started",
            "tenant_id",
            "started_at",
        ),
        Index(
            "ix_translation_logs_tenant_profile_started",
            "tenant_id",
            "profile_id",
            "started_at",
        ),
        Index(
            "ix_translation_logs_failed_partial",
            "tenant_id",
            "started_at",
            postgresql_where=text("status = 'failed'"),
        ),
    )

    # Identity
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    batch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Multi-tenancy & profile snapshot
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id"),
        nullable=False,
    )
    profile_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Request
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_text_length: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Response
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Model & cost
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # Pipeline outcome
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    cache_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    glossary_compliance_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    glossary_violations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Prompt template
    prompt_template_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="translate", server_default="translate"
    )
    prompt_template_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Forward columns for sub-proyek C
    detected_source_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    detected_output_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_lang_mismatch: Mapped[bool | None] = mapped_column(nullable=True)
    output_lang_mismatch: Mapped[bool | None] = mapped_column(nullable=True)

    # Open-ended metadata
    request_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Also update the imports at the top of `src/db/models.py` to include the additional symbols this model needs. Replace the existing `from sqlalchemy import (...)` block with:

```python
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
```

Note: `Decimal` from stdlib `decimal` module (top-level import); `Numeric` and `text` are new sqlalchemy imports.

- [ ] **Step 1.3: Apply migration against dev DB and verify**

Run:

```bash
uv run alembic upgrade head
```

Expected: migration runs without error, creates `translation_logs` table.

Verify table exists by running psql:

```bash
docker compose exec postgres psql -U postgres -d aitrans_db -c "\d translation_logs"
```

Expected output: table description showing all columns from §4 of the spec, plus 3 indexes (`ix_translation_logs_tenant_started`, `ix_translation_logs_tenant_profile_started`, `ix_translation_logs_failed_partial`).

- [ ] **Step 1.4: Verify ORM registration via existing test suite**

Run:

```bash
uv run pytest tests/ -x -q
```

Expected: existing tests pass. The `tests/conftest.py` imports `src.db.models` and calls `Base.metadata.create_all(...)`. If the `TranslationLog` model has a typing error, this would fail at collection time.

Expected: all pre-existing tests pass, no new failures introduced.

## Task 2: Sanitize helper + Pydantic schemas

**Files:**
- Create: `src/translation_logs/__init__.py` (empty)
- Create: `src/translation_logs/sanitize.py`
- Create: `src/translation_logs/schemas.py`
- Create: `tests/translation_logs/__init__.py` (empty)
- Create: `tests/translation_logs/test_sanitize.py`

- [ ] **Step 2.1: Create package markers**

Create `src/translation_logs/__init__.py` with content:

```python
"""Translation log persistence: schemas, repository, sanitization."""
```

Create `tests/translation_logs/__init__.py` with empty content (just file existence).

- [ ] **Step 2.2: Write failing sanitize tests**

Create `tests/translation_logs/test_sanitize.py`:

```python
"""Tests for sanitize_error: regex redact + truncate.

Per ADR-028, sanitization is intentionally minimal — two regex patterns
plus a hard truncate. We expand reactively when new sensitive-pattern
classes show up in real error logs.
"""

from __future__ import annotations

from src.translation_logs.sanitize import sanitize_error


def test_sanitize_strips_anthropic_api_key() -> None:
    given = "Auth failed: sk-ant-abc123xyz_DEF456 is expired"
    result = sanitize_error(given)
    assert "sk-ant-abc123xyz_DEF456" not in result
    assert "***REDACTED***" in result


def test_sanitize_strips_bearer_token() -> None:
    given = "Header: Authorization: Bearer eyJhbGc.eyJzdWI.signature"
    result = sanitize_error(given)
    assert "eyJhbGc.eyJzdWI.signature" not in result
    assert "***REDACTED***" in result


def test_sanitize_truncates_to_2000_chars() -> None:
    given = "x" * 5000
    result = sanitize_error(given)
    assert len(result) == 2000


def test_sanitize_preserves_short_innocent_text() -> None:
    given = "Profile 'asuransi' not found"
    result = sanitize_error(given)
    assert result == given


def test_sanitize_handles_empty_string() -> None:
    assert sanitize_error("") == ""


def test_sanitize_handles_multiple_secrets_in_one_string() -> None:
    given = "sk-ant-abc and Bearer xyz both present"
    result = sanitize_error(given)
    assert "sk-ant-abc" not in result
    assert "Bearer xyz" not in result
    assert result.count("***REDACTED***") == 2
```

- [ ] **Step 2.3: Run tests, verify they fail with ImportError**

```bash
uv run pytest tests/translation_logs/test_sanitize.py -v
```

Expected: collection error or all tests fail with `ModuleNotFoundError: No module named 'src.translation_logs.sanitize'`.

- [ ] **Step 2.4: Implement sanitize_error**

Create `src/translation_logs/sanitize.py`:

```python
"""Redact sensitive patterns from error messages before persisting them.

Per ADR-028 we keep this minimal: two regex rules cover the patterns
Anthropic SDK has been observed echoing back. Add more reactively as we
encounter new ones — preempting every possible token format is bikeshedding.
"""

from __future__ import annotations

import re

# Anthropic API keys: "sk-ant-" prefix followed by URL-safe characters.
# Trailing punctuation kept out of the match so error messages remain readable
# ("sk-ant-abc123. Token expired." → "***REDACTED***. Token expired.").
_ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")

# Bearer tokens: case-sensitive scheme name, whitespace, then the token value.
# JWT-shaped tokens contain dots; we accept dots inside the value.
_BEARER_TOKEN = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")

# Hard cap on stored error_detail length. 2000 chars is plenty for a typical
# stack frame + exception message; longer messages are almost always
# auto-generated noise (HTML pages, full DOM dumps, etc.).
_MAX_LEN = 2000


def sanitize_error(text: str) -> str:
    """Return ``text`` with known secrets redacted and length capped.

    The function is deliberately stateless and fast (single regex pass each).
    """
    if not text:
        return text
    redacted = _ANTHROPIC_KEY.sub("***REDACTED***", text)
    redacted = _BEARER_TOKEN.sub("***REDACTED***", redacted)
    return redacted[:_MAX_LEN]
```

- [ ] **Step 2.5: Run tests, verify they pass**

```bash
uv run pytest tests/translation_logs/test_sanitize.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 2.6: Write failing schema tests**

Create `tests/translation_logs/test_schemas.py`:

```python
"""Pydantic schema tests for translation_logs domain."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.translation_logs.schemas import TranslationLogCreate


def _minimal_kwargs() -> dict:
    """Smallest payload that satisfies all NOT NULL fields."""
    return dict(
        trace_id="abc123",
        tenant_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        profile_slug="general",
        profile_version=1,
        source_lang="en",
        target_lang="id",
        source_text="hello",
        source_text_length=5,
        source_text_hash="a" * 64,
        model_id="claude-sonnet-4-6",
        status="success",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=42,
    )


def test_create_accepts_minimal_payload() -> None:
    payload = TranslationLogCreate(**_minimal_kwargs())
    assert payload.status == "success"
    assert payload.cache_hit is False  # default
    assert payload.translated_text is None  # nullable default
    assert payload.batch_id is None  # nullable default
    assert payload.prompt_template_name == "translate"  # default


def test_create_rejects_invalid_status() -> None:
    kwargs = _minimal_kwargs()
    kwargs["status"] = "pending"
    with pytest.raises(ValidationError):
        TranslationLogCreate(**kwargs)


def test_create_accepts_full_failure_payload() -> None:
    kwargs = _minimal_kwargs()
    kwargs["status"] = "failed"
    kwargs["error_code"] = "rate_limited"
    kwargs["error_detail"] = "429 from provider"
    kwargs["translated_text"] = None
    payload = TranslationLogCreate(**kwargs)
    assert payload.status == "failed"
    assert payload.error_code == "rate_limited"


def test_create_accepts_cache_hit_payload() -> None:
    kwargs = _minimal_kwargs()
    kwargs["cache_hit"] = True
    kwargs["cache_key"] = "a" * 32
    kwargs["translated_text"] = "halo"
    kwargs["translated_text_length"] = 4
    kwargs["input_tokens"] = None
    kwargs["output_tokens"] = None
    kwargs["cost_usd"] = None
    payload = TranslationLogCreate(**kwargs)
    assert payload.cache_hit is True
    assert payload.cost_usd is None


def test_create_accepts_forward_c_columns() -> None:
    kwargs = _minimal_kwargs()
    kwargs["detected_source_lang"] = "fr"
    kwargs["source_lang_mismatch"] = True
    payload = TranslationLogCreate(**kwargs)
    assert payload.detected_source_lang == "fr"
    assert payload.source_lang_mismatch is True
```

- [ ] **Step 2.7: Run tests, verify they fail**

```bash
uv run pytest tests/translation_logs/test_schemas.py -v
```

Expected: `ImportError` / `ModuleNotFoundError` for `src.translation_logs.schemas`.

- [ ] **Step 2.8: Implement schemas**

Create `src/translation_logs/schemas.py`:

```python
"""Pydantic schemas for translation log persistence.

``TranslationLogCreate`` is the write boundary: the ``record_log`` stage
builds one of these from ``PipelineContext`` and hands it to the repository.

``TranslationLogRead`` is a placeholder used by sub-proyek F (dashboard).
We define it here for type-coherence — read methods on the repository
return ``TranslationLogRead``, even though they currently raise
``NotImplementedError``. Locking the shape in now means the dashboard
implementation doesn't have to backfill type hints later.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TranslationLogCreate(BaseModel):
    """All fields needed to insert one row into ``translation_logs``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Identity
    trace_id: str = Field(min_length=1)
    batch_id: uuid.UUID | None = None
    batch_index: int | None = None

    # Multi-tenancy & profile snapshot
    tenant_id: uuid.UUID
    profile_id: uuid.UUID
    profile_slug: str = Field(min_length=1, max_length=64)
    profile_version: int
    quality_mode: str | None = Field(default=None, max_length=16)

    # Request
    source_lang: str = Field(min_length=1, max_length=8)
    target_lang: str = Field(min_length=1, max_length=8)
    source_text: str
    source_text_length: int = Field(ge=0)
    source_text_hash: str = Field(min_length=64, max_length=64)

    # Response (nullable on error)
    translated_text: str | None = None
    translated_text_length: int | None = None

    # Model & cost
    model_id: str = Field(min_length=1, max_length=64)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None

    # Pipeline outcome
    status: Literal["success", "failed"]
    cache_hit: bool = False
    cache_key: str | None = Field(default=None, min_length=32, max_length=32)
    glossary_compliance_score: Decimal | None = Field(default=None, ge=0, le=1)
    glossary_violations: list[dict[str, Any]] | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_detail: str | None = None

    # Prompt template
    prompt_template_name: str = Field(default="translate", max_length=64)
    prompt_template_version: str | None = Field(default=None, max_length=32)

    # Forward columns for sub-proyek C (language detection)
    detected_source_lang: str | None = Field(default=None, max_length=8)
    detected_output_lang: str | None = Field(default=None, max_length=8)
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None

    # Open-ended metadata
    request_metadata: dict[str, Any] | None = None

    # Timing
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    provider_duration_ms: int | None = Field(default=None, ge=0)


class TranslationLogRead(BaseModel):
    """Read shape — placeholder; sub-proyek F implements the read methods.

    Same field set as the Create model plus the server-generated ``id``.
    """

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: uuid.UUID
    trace_id: str
    batch_id: uuid.UUID | None
    batch_index: int | None

    tenant_id: uuid.UUID
    profile_id: uuid.UUID
    profile_slug: str
    profile_version: int
    quality_mode: str | None

    source_lang: str
    target_lang: str
    source_text: str
    source_text_length: int
    source_text_hash: str

    translated_text: str | None
    translated_text_length: int | None

    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None

    status: str
    cache_hit: bool
    cache_key: str | None
    glossary_compliance_score: Decimal | None
    glossary_violations: list[dict[str, Any]] | None
    error_code: str | None
    error_detail: str | None

    prompt_template_name: str
    prompt_template_version: str | None

    detected_source_lang: str | None
    detected_output_lang: str | None
    source_lang_mismatch: bool | None
    output_lang_mismatch: bool | None

    request_metadata: dict[str, Any] | None

    started_at: datetime
    completed_at: datetime
    duration_ms: int
    provider_duration_ms: int | None
```

- [ ] **Step 2.9: Run schema tests, verify they pass**

```bash
uv run pytest tests/translation_logs/test_schemas.py -v
```

Expected: all 5 tests PASS.

## Task 3: Repository

**Files:**
- Create: `src/translation_logs/repository.py`
- Create: `tests/translation_logs/test_repository.py`

- [ ] **Step 3.1: Write failing repository tests**

Create `tests/translation_logs/test_repository.py`:

```python
"""Repository tests — uses the same db_session fixture as profile tests.

The session is per-test with rollback teardown (see tests/conftest.py),
so each test sees a clean slate without manual cleanup.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TranslationLog
from src.profiles.repository import ProfileRepository
from src.profiles.schemas import ProfileCreate
from src.translation_logs.repository import TranslationLogRepository
from src.translation_logs.schemas import TranslationLogCreate


async def _seed_tenant_and_profile(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a tenant + profile, return their IDs."""
    repo = ProfileRepository(session)
    tenant = await repo.create_tenant("test-tenant")
    profile = await repo.create_profile(
        tenant.id,
        ProfileCreate(
            slug="general",
            name="General",
            domain="general",
            tone="professional",
            target_audience="general public",
        ),
    )
    await session.flush()
    return tenant.id, profile.id


def _payload(tenant_id: uuid.UUID, profile_id: uuid.UUID, **overrides) -> TranslationLogCreate:
    """Minimal valid Create payload, with overrides for test variation."""
    defaults = dict(
        trace_id="trace-test",
        tenant_id=tenant_id,
        profile_id=profile_id,
        profile_slug="general",
        profile_version=1,
        source_lang="en",
        target_lang="id",
        source_text="hello",
        source_text_length=5,
        source_text_hash="a" * 64,
        model_id="claude-sonnet-4-6",
        status="success",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=100,
    )
    defaults.update(overrides)
    return TranslationLogCreate(**defaults)


async def test_create_returns_uuid_and_persists_row(db_session: AsyncSession) -> None:
    tenant_id, profile_id = await _seed_tenant_and_profile(db_session)
    repo = TranslationLogRepository(db_session)

    log_id = await repo.create(_payload(tenant_id, profile_id))

    assert isinstance(log_id, uuid.UUID)

    row = await db_session.execute(select(TranslationLog).where(TranslationLog.id == log_id))
    saved = row.scalar_one()
    assert saved.trace_id == "trace-test"
    assert saved.status == "success"
    assert saved.source_lang == "en"
    assert saved.cache_hit is False


async def test_create_defaults_forward_c_columns_to_null(db_session: AsyncSession) -> None:
    tenant_id, profile_id = await _seed_tenant_and_profile(db_session)
    repo = TranslationLogRepository(db_session)

    log_id = await repo.create(_payload(tenant_id, profile_id))

    row = await db_session.execute(select(TranslationLog).where(TranslationLog.id == log_id))
    saved = row.scalar_one()
    assert saved.detected_source_lang is None
    assert saved.detected_output_lang is None
    assert saved.source_lang_mismatch is None
    assert saved.output_lang_mismatch is None


async def test_create_persists_failed_row_with_error_details(db_session: AsyncSession) -> None:
    tenant_id, profile_id = await _seed_tenant_and_profile(db_session)
    repo = TranslationLogRepository(db_session)

    log_id = await repo.create(
        _payload(
            tenant_id,
            profile_id,
            status="failed",
            translated_text=None,
            error_code="rate_limited",
            error_detail="429 from provider",
        )
    )

    row = await db_session.execute(select(TranslationLog).where(TranslationLog.id == log_id))
    saved = row.scalar_one()
    assert saved.status == "failed"
    assert saved.translated_text is None
    assert saved.error_code == "rate_limited"
    assert saved.error_detail == "429 from provider"


async def test_recent_raises_not_implemented(db_session: AsyncSession) -> None:
    repo = TranslationLogRepository(db_session)
    with pytest.raises(NotImplementedError, match="sub-proyek F"):
        await repo.recent(tenant_id=uuid.uuid4(), limit=10)


async def test_by_profile_raises_not_implemented(db_session: AsyncSession) -> None:
    repo = TranslationLogRepository(db_session)
    with pytest.raises(NotImplementedError, match="sub-proyek F"):
        await repo.by_profile(tenant_id=uuid.uuid4(), profile_id=uuid.uuid4())


async def test_aggregate_cost_raises_not_implemented(db_session: AsyncSession) -> None:
    repo = TranslationLogRepository(db_session)
    with pytest.raises(NotImplementedError, match="sub-proyek F"):
        await repo.aggregate_cost(tenant_id=uuid.uuid4())
```

- [ ] **Step 3.2: Run tests, verify they fail**

```bash
uv run pytest tests/translation_logs/test_repository.py -v
```

Expected: `ImportError` for `src.translation_logs.repository`.

- [ ] **Step 3.3: Implement repository**

Create `src/translation_logs/repository.py`:

```python
"""Async repository for translation log persistence.

Mirrors the patterns from ``src.profiles.repository`` — constructor takes the
session, methods return either primitives (UUID for ``create``) or Pydantic
``Read`` models (sub-proyek F). The repo does NOT call ``session.commit()``;
the API layer is responsible for transaction boundaries.

Read methods are stubs because sub-proyek F (dashboard) is what consumes
them. Locking the interface here means we don't have to revisit this module
when F lands — only add bodies.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TranslationLog
from src.translation_logs.schemas import TranslationLogCreate, TranslationLogRead


class TranslationLogRepository:
    """All persistence operations against the ``translation_logs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, payload: TranslationLogCreate) -> uuid.UUID:
        """Insert one log row and return its id.

        We return the UUID rather than the Read model because callers (the
        ``record_log`` stage, primarily) only need the id to thread back
        into the response. Loading the full row would be a wasted round-trip.
        """
        row = TranslationLog(**payload.model_dump())
        self._session.add(row)
        await self._session.flush()  # populate server-default id
        return row.id

    # ---- Read methods — stubs for sub-proyek F (dashboard) ------------------

    async def recent(
        self, *, tenant_id: uuid.UUID, limit: int = 50
    ) -> list[TranslationLogRead]:
        """Return the most recent N log rows for a tenant.

        Implemented by sub-proyek F. The stub raises NotImplementedError so
        a premature call surfaces immediately instead of silently returning
        an empty list.
        """
        raise NotImplementedError(
            "recent() is implemented by sub-proyek F (dashboard); not available in sub-proyek B"
        )

    async def by_profile(
        self, *, tenant_id: uuid.UUID, profile_id: uuid.UUID, limit: int = 50
    ) -> list[TranslationLogRead]:
        raise NotImplementedError(
            "by_profile() is implemented by sub-proyek F (dashboard); not available in sub-proyek B"
        )

    async def aggregate_cost(self, *, tenant_id: uuid.UUID) -> dict[str, object]:
        raise NotImplementedError(
            "aggregate_cost() is implemented by sub-proyek F (dashboard); not available in sub-proyek B"
        )
```

- [ ] **Step 3.4: Run tests, verify they pass**

```bash
uv run pytest tests/translation_logs/ -v
```

Expected: all tests in `tests/translation_logs/` PASS (sanitize + schemas + repository).

- [ ] **Step 3.5: Run full suite to confirm no regression**

```bash
uv run pytest -x -q
```

Expected: pre-existing tests + new tests all pass.

- [ ] **Step 3.6: Lint + typecheck**

```bash
uv run ruff check src/translation_logs/ tests/translation_logs/
uv run mypy src/translation_logs/
```

Expected: clean.

### Phase 1 commit gate

**Do NOT commit yet.** Phase 1 is complete (tabel ada, schemas + repo + sanitize bekerja, semua test hijau) — at this point the implementer should:

1. Run `git status` and `git diff` to confirm the changes are exactly the Phase 1 files: `alembic/versions/002_translation_logs.py`, `src/db/models.py`, `src/translation_logs/*`, `tests/translation_logs/*`.
2. Wait for the executor (this skill or subagent) to surface a 2-sentence commit message recommendation.
3. The user reviews and explicitly confirms before any `git commit` runs. **No `git push`.**

Suggested commit message shape (the executor will refine based on the actual diff): *"Add translation_logs table with ORM model, Pydantic schemas, sanitize helper, and write-only repository. Foundation for sub-proyek B (translation logging) and sub-proyek F (dashboard)."*

---

# PHASE 2 — Pipeline integration

Goal: pipeline tahu cara menulis log row, baik di success path maupun di error path, dan API response carry `log_id`. Pipeline tests confirm behavior. Belum touching API routes yet — API still has old signatures so log_id won't reach HTTP responses sampai Phase 3.

## Task 4: Schema extensions

**Files:**
- Modify: `src/pipeline/schemas.py`
- Modify: `src/pipeline/stages.py` (PipelineContext extension only — no record_log yet)

- [ ] **Step 4.1: Extend PipelineRequest with batch + metadata fields**

In `src/pipeline/schemas.py`, replace the `PipelineRequest` class with:

```python
class PipelineRequest(BaseModel):
    """Inbound translation request.

    ``source_lang=None`` means "let the model detect it". We pass that hint
    through to the prompt; the model returns a translation and we record
    whatever the request told us into the result (so the cache key remains
    stable for "auto" callers — they all share the same cache namespace).

    ``batch_id`` + ``batch_index`` are populated by the ``/translate/batch``
    endpoint so log rows from one batch share an identifier; for single
    ``/translate`` calls both are ``None``.

    ``request_metadata`` is an open-ended dict echoed through to the log row
    (SDK version, user agent, page url, etc.); not used by the pipeline itself.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = Field(min_length=1)
    target_lang: str = Field(min_length=2, max_length=5)
    profile_slug: str = Field(min_length=1)
    tenant_id: uuid.UUID
    source_lang: str | None = Field(default=None, max_length=5)
    options: TranslationOptions = Field(default_factory=TranslationOptions)
    batch_id: uuid.UUID | None = None
    batch_index: int | None = None
    request_metadata: dict[str, Any] | None = None
```

- [ ] **Step 4.2: Extend PipelineResult with log_id**

In the same file `src/pipeline/schemas.py`, replace the `PipelineResult` class with:

```python
class PipelineResult(BaseModel):
    """Outbound translation result.

    ``cached=True`` means the result came from Redis. In that case
    ``cost_usd`` is zero (we didn't pay the API for this call) and
    ``latency_ms`` reflects the cache lookup, not the original translation.
    ``metadata`` is the catch-all for diagnostic information that doesn't
    have a fixed schema — trace_id, profile_version, resolution_chain,
    glossary_violation_count, etc.

    ``log_id`` is populated by the pipeline orchestrator after the
    ``record_log`` stage runs. ``None`` means the log write failed (DB
    unavailable) and the response had to be returned without persistent
    correlation — clients can still use ``metadata["trace_id"]`` for that.
    """

    translation: str
    source_lang: str
    target_lang: str
    cached: bool
    provider: str
    model: str
    latency_ms: float
    cost_usd: Decimal
    glossary_compliance: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    log_id: uuid.UUID | None = None
```

- [ ] **Step 4.3: Extend PipelineContext dataclass**

In `src/pipeline/stages.py`, replace the `PipelineContext` dataclass definition with:

```python
@dataclass
class PipelineContext:
    """Mutable bag of state threaded through the pipeline.

    Why a dataclass and not a TypedDict: we need defaults (most fields are
    populated as stages run), and the IDE / mypy autocompletion on attribute
    access is genuinely useful when wiring tests for individual stages.
    """

    request: PipelineRequest
    trace_id: str
    started_at_perf: float  # ``time.perf_counter()`` snapshot for total latency
    started_at: datetime  # wall-clock start for the log row

    # Populated by stages as the pipeline runs.
    normalized_text: str = ""
    source_text_hash: str = ""  # sha256(normalized_text), set in validate_and_normalize
    resolved_profile: ResolvedProfile | None = None
    cache_key: str | None = None
    cached_result: PipelineResult | None = None
    selected_glossary: list[ResolvedGlossaryTerm] = field(default_factory=list)
    selected_examples: list[ResolvedStyleExample] = field(default_factory=list)
    rendered_prompt: str = ""
    translation_result: TranslationResult | None = None
    compliance_score: float = 1.0
    compliance_violations: list[ComplianceViolation] = field(default_factory=list)

    # Populated by the orchestrator/record_log stage.
    status: str = "success"  # 'success' | 'failed', overridden in except block
    error_code: str | None = None
    error_detail: str | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    provider_duration_ms: int | None = None
    log_id: uuid.UUID | None = None
    prompt_template_name: str = "translate"
    prompt_template_version: str | None = None
```

Add the required imports at the top of `src/pipeline/stages.py` (next to the existing ones):

```python
import hashlib
import uuid
from datetime import datetime
```

- [ ] **Step 4.4: Compute source_text_hash in validate_and_normalize**

In `src/pipeline/stages.py`, replace the `validate_and_normalize` function with:

```python
async def validate_and_normalize(ctx: PipelineContext) -> None:
    """Strip whitespace, NFC-normalise unicode, and reject empty text.

    NFC (canonical composition) means "é" and "e\\u0301" hash to the same
    cache key. Without it, two visually identical inputs could miss cache
    against each other — a frustrating bug to diagnose.

    Also computes ``source_text_hash`` for the log row; doing it here keeps
    hash + normalisation co-located (the hash must reflect the post-NFC
    string, otherwise the log loses determinism).
    """
    start = time.perf_counter()
    text = ctx.request.text.strip()
    text = unicodedata.normalize("NFC", text)
    if not text:
        raise ValueError("Translation text is empty after normalization")

    target = ctx.request.target_lang.strip()
    if not target:
        raise ValueError("target_lang must be a non-empty language code")

    ctx.normalized_text = text
    ctx.source_text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="validate_and_normalize",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        text_length=len(text),
    )
```

- [ ] **Step 4.5: Run existing pipeline tests, confirm no regression**

```bash
uv run pytest tests/pipeline/ -v
```

Expected: all pre-existing pipeline tests pass. The new fields on `PipelineContext` and `PipelineRequest` are additive with defaults, and existing tests don't reference them.

## Task 5: record_log stage

**Files:**
- Modify: `src/pipeline/stages.py` (append `record_log` function)
- Create: `tests/translation_logs/test_record_log_stage.py`

- [ ] **Step 5.1: Write failing stage tests**

Create `tests/translation_logs/test_record_log_stage.py`:

```python
"""record_log stage tests with a mocked repository.

The stage's invariants:

1. On success, ``ctx.log_id`` is populated with the repository's return value.
2. Any exception from the repository (DB unavailable, unexpected) is swallowed;
   ``ctx.log_id`` stays ``None``; pipeline continues. record_log runs in
   ``finally`` and MUST NEVER raise — that would mask the original pipeline
   exception (if any) and break error semantics.
3. When the context is too incomplete to build a valid payload (profile
   resolution never ran, or completed_at not yet set), the stage skips the
   write cleanly without raising.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext, record_log


def _make_ctx(**overrides) -> PipelineContext:
    """Return a PipelineContext fully populated enough for record_log."""
    request = PipelineRequest(
        text="hello",
        target_lang="id",
        profile_slug="general",
        tenant_id=uuid.uuid4(),
        source_lang="en",
    )
    ctx = PipelineContext(
        request=request,
        trace_id="trace-test",
        started_at_perf=0.0,
        started_at=datetime.now(timezone.utc),
    )
    ctx.normalized_text = "hello"
    ctx.source_text_hash = "a" * 64
    ctx.completed_at = datetime.now(timezone.utc)
    ctx.duration_ms = 50
    ctx.status = "success"

    # Populate profile context (normally set by load_resolved_profile)
    profile_id = uuid.uuid4()
    resolved = MagicMock()
    resolved.id = profile_id
    resolved.slug = "general"
    resolved.version = 1
    resolved.quality_mode = "balanced"
    ctx.resolved_profile = resolved

    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


async def test_record_log_success_sets_log_id() -> None:
    expected_id = uuid.uuid4()
    repo = MagicMock()
    repo.create = AsyncMock(return_value=expected_id)

    ctx = _make_ctx()
    await record_log(ctx, repo, model_id="claude-sonnet-4-6")

    assert ctx.log_id == expected_id
    repo.create.assert_called_once()


async def test_record_log_swallows_sqlalchemy_error() -> None:
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=OperationalError("disconnect", {}, None))

    ctx = _make_ctx()
    await record_log(ctx, repo, model_id="claude-sonnet-4-6")  # must not raise

    assert ctx.log_id is None


async def test_record_log_swallows_arbitrary_repo_error() -> None:
    """record_log runs in finally — it must NEVER raise. Broad swallow."""
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=RuntimeError("anything weird"))

    ctx = _make_ctx()
    await record_log(ctx, repo, model_id="claude-sonnet-4-6")  # must not raise

    assert ctx.log_id is None


async def test_record_log_skips_when_resolved_profile_missing() -> None:
    """If profile resolution failed (resolved_profile is None), skip write cleanly.

    profile_id is NOT NULL in the schema, so without resolved_profile we cannot
    construct a valid TranslationLogCreate. Skip silently instead of writing
    a half-row or raising.
    """
    repo = MagicMock()
    repo.create = AsyncMock()

    ctx = _make_ctx()
    ctx.resolved_profile = None

    await record_log(ctx, repo, model_id="claude-sonnet-4-6")  # must not raise

    assert ctx.log_id is None
    repo.create.assert_not_called()


async def test_record_log_skips_when_completed_at_missing() -> None:
    repo = MagicMock()
    repo.create = AsyncMock()

    ctx = _make_ctx()
    ctx.completed_at = None

    await record_log(ctx, repo, model_id="claude-sonnet-4-6")

    assert ctx.log_id is None
    repo.create.assert_not_called()


async def test_record_log_carries_translated_text_when_success() -> None:
    repo = MagicMock()
    repo.create = AsyncMock(return_value=uuid.uuid4())

    ctx = _make_ctx()
    translation_result = MagicMock()
    translation_result.translation = "halo dunia"
    translation_result.model = "claude-sonnet-4-6"
    translation_result.tokens_input = 10
    translation_result.tokens_output = 4
    translation_result.cost_usd = "0.0001"
    ctx.translation_result = translation_result

    await record_log(ctx, repo, model_id="claude-sonnet-4-6")

    payload = repo.create.call_args[0][0]
    assert payload.translated_text == "halo dunia"
    assert payload.input_tokens == 10
    assert payload.output_tokens == 4


async def test_record_log_failed_status_passes_error_fields() -> None:
    repo = MagicMock()
    repo.create = AsyncMock(return_value=uuid.uuid4())

    ctx = _make_ctx(
        status="failed",
        error_code="rate_limited",
        error_detail="429 from provider",
    )

    await record_log(ctx, repo, model_id="claude-sonnet-4-6")

    payload = repo.create.call_args[0][0]
    assert payload.status == "failed"
    assert payload.error_code == "rate_limited"
    assert payload.error_detail == "429 from provider"
    assert payload.translated_text is None
```

- [ ] **Step 5.2: Run tests, verify they fail**

```bash
uv run pytest tests/translation_logs/test_record_log_stage.py -v
```

Expected: `ImportError` for `record_log` from `src.pipeline.stages`.

- [ ] **Step 5.3: Implement record_log stage**

First add the module-level imports for the new dependencies. At the top of `src/pipeline/stages.py`, in the import block, add:

```python
from src.translation_logs.repository import TranslationLogRepository
from src.translation_logs.sanitize import sanitize_error
from src.translation_logs.schemas import TranslationLogCreate
```

There is no circular import — `src.translation_logs.*` only depends on `src.db.*` which doesn't reach back into `src.pipeline.*`.

Then append the new stage at the bottom of `src/pipeline/stages.py`:

```python
# ---- 9. record_log -------------------------------------------------------


async def record_log(
    ctx: PipelineContext,
    repo: TranslationLogRepository,
    *,
    model_id: str,
) -> None:
    """Persist one ``translation_logs`` row from the context.

    Called from the pipeline's ``finally`` block — runs on both success and
    failure paths. This function MUST NEVER raise: it's running in finally,
    and a raise here would mask the original pipeline exception (if any).
    All exceptions are caught and logged as warnings; ``ctx.log_id`` stays
    ``None`` when the write fails so the response signals "log not persisted".

    This matches the cache-layer degradation pattern (ADR-013): the
    translation API stays healthy when an auxiliary data store is unhealthy.
    """
    start = time.perf_counter()
    try:
        payload = _build_log_payload(ctx, model_id=model_id)
        if payload is None:
            # Context was incomplete (profile resolution never ran, etc.).
            # That's expected on certain failure paths — not a real error.
            log.debug(
                "pipeline.stage",
                trace_id=ctx.trace_id,
                stage="record_log",
                status="skipped",
                reason="incomplete_context",
            )
            return
        ctx.log_id = await repo.create(payload)
        log.debug(
            "pipeline.stage",
            trace_id=ctx.trace_id,
            stage="record_log",
            duration_ms=(time.perf_counter() - start) * 1000.0,
            status="ok",
            log_id=str(ctx.log_id),
        )
    except Exception as exc:  # noqa: BLE001 — intentional broad catch in finally-stage
        # Last-line-of-defence: never propagate. The cache layer takes the same
        # approach (ADR-013) and for the same reason — an auxiliary store
        # going wrong shouldn't break the primary API contract.
        log.warning(
            "translation_log.write_failed",
            trace_id=ctx.trace_id,
            error=str(exc)[:500],
            error_type=type(exc).__name__,
        )


def _build_log_payload(
    ctx: PipelineContext,
    *,
    model_id: str,
) -> TranslationLogCreate | None:
    """Project the PipelineContext into a TranslationLogCreate payload.

    Returns ``None`` when the context is fundamentally too incomplete to form
    a valid payload (profile resolution never ran, completed_at not yet
    set). Returning instead of asserting/raising means the ``finally`` block
    can gracefully skip the write without polluting error reporting.

    Split out so tests can target the projection logic without the
    swallow-and-log wrapper around it.
    """
    if ctx.resolved_profile is None:
        return None
    if ctx.completed_at is None or ctx.duration_ms is None:
        return None

    # On cache hit, translation came from cache — translated_text is on
    # ctx.cached_result. Otherwise it's on translation_result.
    cache_hit = ctx.cached_result is not None
    if cache_hit:
        translated_text = ctx.cached_result.translation if ctx.cached_result else None
        input_tokens = None  # NULL on cache hit: we didn't call the provider
        output_tokens = None
        cost_usd = None
        glossary_compliance_score = (
            Decimal(str(ctx.cached_result.glossary_compliance))
            if ctx.cached_result
            else None
        )
        provider_duration_ms = None
    else:
        translated_text = ctx.translation_result.translation if ctx.translation_result else None
        input_tokens = ctx.translation_result.tokens_input if ctx.translation_result else None
        output_tokens = ctx.translation_result.tokens_output if ctx.translation_result else None
        cost_usd = (
            Decimal(str(ctx.translation_result.cost_usd))
            if ctx.translation_result
            else None
        )
        glossary_compliance_score = Decimal(str(ctx.compliance_score))
        provider_duration_ms = ctx.provider_duration_ms

    glossary_violations: list[dict[str, Any]] | None = None
    if ctx.compliance_violations:
        glossary_violations = [
            {
                "source": v.source_term,
                "expected": v.expected_target,
                "is_forbidden": v.is_forbidden,
                "found": v.found_in_translation,
            }
            for v in ctx.compliance_violations
        ]

    return TranslationLogCreate(
        trace_id=ctx.trace_id,
        batch_id=ctx.request.batch_id,
        batch_index=ctx.request.batch_index,
        tenant_id=ctx.request.tenant_id,
        profile_id=ctx.resolved_profile.id,
        profile_slug=ctx.resolved_profile.slug,
        profile_version=ctx.resolved_profile.version,
        quality_mode=ctx.resolved_profile.quality_mode,
        source_lang=ctx.request.source_lang or AUTO_LANG_SENTINEL,
        target_lang=ctx.request.target_lang,
        source_text=ctx.normalized_text or ctx.request.text,
        source_text_length=len(ctx.normalized_text or ctx.request.text),
        source_text_hash=ctx.source_text_hash or "0" * 64,
        translated_text=translated_text,
        translated_text_length=len(translated_text) if translated_text else None,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        status=ctx.status,
        cache_hit=cache_hit,
        cache_key=ctx.cache_key,
        glossary_compliance_score=glossary_compliance_score,
        glossary_violations=glossary_violations,
        error_code=ctx.error_code,
        error_detail=sanitize_error(ctx.error_detail) if ctx.error_detail else None,
        prompt_template_name=ctx.prompt_template_name,
        prompt_template_version=ctx.prompt_template_version,
        request_metadata=ctx.request.request_metadata,
        started_at=ctx.started_at,
        completed_at=ctx.completed_at,
        duration_ms=ctx.duration_ms,
        provider_duration_ms=provider_duration_ms,
    )
```

- [ ] **Step 5.4: Run tests, verify they pass**

```bash
uv run pytest tests/translation_logs/test_record_log_stage.py -v
```

Expected: all 5 tests PASS.

## Task 6: Pipeline orchestrator integration

**Files:**
- Modify: `src/pipeline/pipeline.py` (constructor + translate method)
- Create: `tests/pipeline/test_pipeline_logging.py`
- Create: `tests/pipeline/test_pipeline_batch_logging.py`

- [ ] **Step 6.1: Write failing pipeline integration tests**

Create `tests/pipeline/test_pipeline_logging.py`:

```python
"""Integration tests for TranslationPipeline + translation_logs.

These use real Postgres (via db_session fixture) and a mocked provider,
so they're deterministic and don't hit the real Anthropic API.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

import fakeredis.aioredis

from src.cache.redis_cache import RedisCache
from src.db.models import TranslationLog
from src.pipeline.pipeline import TranslationPipeline, build_template_env
from src.pipeline.schemas import PipelineRequest
from src.profiles.repository import ProfileRepository
from src.profiles.resolver import ProfileResolver
from src.profiles.schemas import ProfileCreate
from src.providers.base import TranslationResult
from src.providers.errors import RateLimitError
from src.translation_logs.repository import TranslationLogRepository


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, str]:
    repo = ProfileRepository(session)
    tenant = await repo.create_tenant("test-tenant")
    await repo.create_profile(
        tenant.id,
        ProfileCreate(
            slug="general",
            name="General",
            domain="general",
            tone="professional",
            target_audience="general public",
        ),
    )
    await session.flush()
    return tenant.id, "general"


def _make_pipeline(
    *,
    session: AsyncSession,
    provider_result: TranslationResult | None = None,
    provider_exc: Exception | None = None,
) -> TranslationPipeline:
    provider = MagicMock()
    if provider_exc:
        provider.translate = AsyncMock(side_effect=provider_exc)
    else:
        provider.translate = AsyncMock(
            return_value=provider_result
            or TranslationResult(
                translation="halo dunia",
                provider="claude",
                model="claude-sonnet-4-6",
                tokens_input=10,
                tokens_output=4,
                cost_usd=Decimal("0.0001"),
                latency_ms=100.0,
                metadata={"stop_reason": "end_turn"},
            )
        )

    cache = RedisCache(client=fakeredis.aioredis.FakeRedis(decode_responses=False))
    profile_repo = ProfileRepository(session)
    resolver = ProfileResolver(profile_repo)
    log_repo = TranslationLogRepository(session)

    return TranslationPipeline(
        provider=provider,
        cache=cache,
        resolver=resolver,
        template_env=build_template_env(),
        model_id="claude-sonnet-4-6",
        log_repo=log_repo,
    )


async def _count_logs(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(TranslationLog).where(
            TranslationLog.tenant_id == tenant_id
        )
    )
    return result.scalar_one()


async def test_pipeline_writes_log_on_success(db_session: AsyncSession) -> None:
    tenant_id, profile_slug = await _seed(db_session)
    pipeline = _make_pipeline(session=db_session)

    result = await pipeline.translate(
        PipelineRequest(
            text="hello world",
            target_lang="id",
            profile_slug=profile_slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    assert result.log_id is not None
    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id == result.log_id)
    )
    saved = row.scalar_one()
    assert saved.status == "success"
    assert saved.cache_hit is False
    assert saved.translated_text == "halo dunia"
    assert saved.input_tokens == 10
    assert saved.output_tokens == 4
    assert saved.error_code is None


async def test_pipeline_writes_log_on_cache_hit(db_session: AsyncSession) -> None:
    tenant_id, profile_slug = await _seed(db_session)
    pipeline = _make_pipeline(session=db_session)

    request = PipelineRequest(
        text="hello world",
        target_lang="id",
        profile_slug=profile_slug,
        tenant_id=tenant_id,
        source_lang="en",
    )
    # First call populates the cache.
    await pipeline.translate(request)
    # Second call hits the cache.
    result = await pipeline.translate(request)

    assert result.cached is True
    assert result.log_id is not None
    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id == result.log_id)
    )
    saved = row.scalar_one()
    assert saved.cache_hit is True
    assert saved.input_tokens is None  # didn't call provider
    assert saved.output_tokens is None
    assert saved.cost_usd is None


async def test_pipeline_writes_log_on_provider_error(db_session: AsyncSession) -> None:
    tenant_id, profile_slug = await _seed(db_session)
    pipeline = _make_pipeline(
        session=db_session,
        provider_exc=RateLimitError("rate limited", retry_after_s=10.0),
    )

    with pytest.raises(RateLimitError):
        await pipeline.translate(
            PipelineRequest(
                text="hello",
                target_lang="id",
                profile_slug=profile_slug,
                tenant_id=tenant_id,
                source_lang="en",
            )
        )

    # Even though pipeline raised, the log row must be there.
    count = await _count_logs(db_session, tenant_id)
    assert count == 1
    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.tenant_id == tenant_id)
    )
    saved = row.scalar_one()
    assert saved.status == "failed"
    assert saved.translated_text is None
    assert saved.error_code == "RateLimitError"


async def test_pipeline_writes_log_on_profile_not_found(db_session: AsyncSession) -> None:
    tenant_id, _ = await _seed(db_session)
    pipeline = _make_pipeline(session=db_session)

    with pytest.raises(Exception):  # ProfileNotFoundError or similar
        await pipeline.translate(
            PipelineRequest(
                text="hello",
                target_lang="id",
                profile_slug="nonexistent-profile",
                tenant_id=tenant_id,
                source_lang="en",
            )
        )

    # Profile resolution failed BEFORE the profile context populated, so
    # the log row payload construction will hit a ValidationError and the
    # stage swallows it — no row is written.
    count = await _count_logs(db_session, tenant_id)
    assert count == 0


async def test_pipeline_continues_when_log_write_fails(db_session: AsyncSession) -> None:
    """If the repo throws, translate still returns success with log_id=None."""
    tenant_id, profile_slug = await _seed(db_session)
    pipeline = _make_pipeline(session=db_session)

    # Override the log repo with one that raises on every create().
    failing_repo = MagicMock()
    failing_repo.create = AsyncMock(side_effect=OperationalError("disconnect", {}, None))
    pipeline._log_repo = failing_repo  # type: ignore[assignment]

    result = await pipeline.translate(
        PipelineRequest(
            text="hello",
            target_lang="id",
            profile_slug=profile_slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    assert result.translation == "halo dunia"  # translate succeeded
    assert result.log_id is None  # but no log row id


async def test_pipeline_log_forward_c_columns_are_null(db_session: AsyncSession) -> None:
    tenant_id, profile_slug = await _seed(db_session)
    pipeline = _make_pipeline(session=db_session)

    result = await pipeline.translate(
        PipelineRequest(
            text="hello",
            target_lang="id",
            profile_slug=profile_slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id == result.log_id)
    )
    saved = row.scalar_one()
    assert saved.detected_source_lang is None
    assert saved.detected_output_lang is None
    assert saved.source_lang_mismatch is None
    assert saved.output_lang_mismatch is None


async def test_pipeline_log_sanitizes_error_detail(db_session: AsyncSession) -> None:
    """Provider exception with API key in message → log error_detail redacted."""
    tenant_id, profile_slug = await _seed(db_session)
    secret = "sk-ant-supersecret123_DEF456"
    pipeline = _make_pipeline(
        session=db_session,
        provider_exc=RuntimeError(f"Auth failed: {secret} expired"),
    )

    with pytest.raises(RuntimeError):
        await pipeline.translate(
            PipelineRequest(
                text="hello",
                target_lang="id",
                profile_slug=profile_slug,
                tenant_id=tenant_id,
                source_lang="en",
            )
        )

    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.tenant_id == tenant_id)
    )
    saved = row.scalar_one()
    assert secret not in (saved.error_detail or "")
    assert "***REDACTED***" in (saved.error_detail or "")
```

Create `tests/pipeline/test_pipeline_batch_logging.py`:

```python
"""Batch-translation log behavior.

The /translate/batch route generates one batch_id per HTTP request and
threads it through each item's PipelineRequest. Each item gets its own
log row sharing the batch_id but with its own batch_index.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.redis_cache import RedisCache
from src.db.models import TranslationLog
from src.pipeline.pipeline import TranslationPipeline, build_template_env
from src.pipeline.schemas import PipelineRequest
from src.profiles.repository import ProfileRepository
from src.profiles.resolver import ProfileResolver
from src.profiles.schemas import ProfileCreate
from src.providers.base import TranslationResult
from src.translation_logs.repository import TranslationLogRepository


async def _seed(session: AsyncSession) -> uuid.UUID:
    repo = ProfileRepository(session)
    tenant = await repo.create_tenant("test-tenant")
    await repo.create_profile(
        tenant.id,
        ProfileCreate(
            slug="general",
            name="General",
            domain="general",
            tone="professional",
            target_audience="general public",
        ),
    )
    await session.flush()
    return tenant.id


def _make_pipeline(session: AsyncSession) -> TranslationPipeline:
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation="halo",
            provider="claude",
            model="claude-sonnet-4-6",
            tokens_input=5,
            tokens_output=2,
            cost_usd=Decimal("0.00005"),
            latency_ms=50.0,
            metadata={},
        )
    )
    cache = RedisCache(client=fakeredis.aioredis.FakeRedis(decode_responses=False))
    profile_repo = ProfileRepository(session)
    resolver = ProfileResolver(profile_repo)
    log_repo = TranslationLogRepository(session)
    return TranslationPipeline(
        provider=provider,
        cache=cache,
        resolver=resolver,
        template_env=build_template_env(),
        model_id="claude-sonnet-4-6",
        log_repo=log_repo,
    )


async def test_batch_creates_one_row_per_item_with_shared_batch_id(
    db_session: AsyncSession,
) -> None:
    tenant_id = await _seed(db_session)
    pipeline = _make_pipeline(db_session)

    batch_id = uuid.uuid4()
    requests = [
        PipelineRequest(
            text=f"hello {i}",
            target_lang="id",
            profile_slug="general",
            tenant_id=tenant_id,
            source_lang="en",
            batch_id=batch_id,
            batch_index=i,
        )
        for i in range(3)
    ]
    for req in requests:
        await pipeline.translate(req)

    rows = await db_session.execute(
        select(TranslationLog)
        .where(TranslationLog.batch_id == batch_id)
        .order_by(TranslationLog.batch_index)
    )
    saved = list(rows.scalars().all())
    assert len(saved) == 3
    assert [r.batch_index for r in saved] == [0, 1, 2]
    assert all(r.batch_id == batch_id for r in saved)


async def test_batch_partial_failure_writes_both_success_and_failed_rows(
    db_session: AsyncSession,
) -> None:
    tenant_id = await _seed(db_session)
    pipeline = _make_pipeline(db_session)

    # Item index 1 will fail, items 0 and 2 succeed.
    call_count = {"n": 0}

    async def flaky_translate(request):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated transient error")
        return TranslationResult(
            translation="halo",
            provider="claude",
            model="claude-sonnet-4-6",
            tokens_input=5,
            tokens_output=2,
            cost_usd=Decimal("0.00005"),
            latency_ms=50.0,
            metadata={},
        )

    pipeline._provider.translate = AsyncMock(side_effect=flaky_translate)  # type: ignore[assignment]

    batch_id = uuid.uuid4()
    for i in range(3):
        req = PipelineRequest(
            text=f"hello {i}",
            target_lang="id",
            profile_slug="general",
            tenant_id=tenant_id,
            source_lang="en",
            batch_id=batch_id,
            batch_index=i,
        )
        try:
            await pipeline.translate(req)
        except RuntimeError:
            pass

    rows = await db_session.execute(
        select(TranslationLog)
        .where(TranslationLog.batch_id == batch_id)
        .order_by(TranslationLog.batch_index)
    )
    saved = list(rows.scalars().all())
    assert len(saved) == 3
    statuses = [r.status for r in saved]
    assert statuses == ["success", "failed", "success"]
```

- [ ] **Step 6.2: Run tests, verify they fail**

```bash
uv run pytest tests/pipeline/test_pipeline_logging.py tests/pipeline/test_pipeline_batch_logging.py -v
```

Expected: all tests fail because `TranslationPipeline.__init__` doesn't yet accept `log_repo` (and `result.log_id` doesn't propagate from a `record_log` call yet).

- [ ] **Step 6.3: Refactor TranslationPipeline.__init__ to accept log_repo**

First add the runtime import. In `src/pipeline/pipeline.py`, add this line in the import block at top of file:

```python
from src.translation_logs.repository import TranslationLogRepository
```

(No cycle: `src.translation_logs.repository` only depends on `src.db.*` and `src.translation_logs.schemas`, none of which import `src.pipeline.*`.)

Then replace the `__init__` method with:

```python
    def __init__(
        self,
        *,
        provider: TranslationProvider,
        cache: CacheBackend,
        resolver: ProfileResolver,
        template_env: Environment | None = None,
        model_id: str,
        log_repo: TranslationLogRepository,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._resolver = resolver
        self._template_env = template_env or build_template_env()
        # ``model_id`` participates in the cache key so swapping models
        # automatically invalidates everything. We capture it explicitly
        # rather than reading from the provider on each call to keep the
        # key stable across in-flight requests if the provider is swapped.
        self._model_id = model_id
        self._log_repo = log_repo
```

- [ ] **Step 6.4: Refactor TranslationPipeline.translate to try/except/finally**

Replace the entire `translate` method body with:

```python
    async def translate(self, request: PipelineRequest) -> PipelineResult:
        """Run the request through every stage and return the final result.

        Short-circuit on cache hit: stages 4-8 are skipped and we return the
        rebuilt cached result directly. On miss, the full pipeline runs and
        the new result is written back to cache.

        The ``finally`` block runs ``record_log`` on every path — success,
        cache hit, or failure — so the translation_logs table holds a row
        for every invocation regardless of outcome. Log-write failures are
        swallowed by the stage so they cannot affect the response.
        """
        from datetime import datetime, timezone

        trace_id = uuid.uuid4().hex
        started_at_wall = datetime.now(timezone.utc)
        ctx = stages.PipelineContext(
            request=request,
            trace_id=trace_id,
            started_at_perf=time.perf_counter(),
            started_at=started_at_wall,
        )

        log.info(
            "pipeline.start",
            trace_id=trace_id,
            tenant_id=str(request.tenant_id),
            profile_slug=request.profile_slug,
            target_lang=request.target_lang,
            source_lang=request.source_lang,
            text_length=len(request.text),
        )

        base_result: PipelineResult | None = None
        try:
            await stages.validate_and_normalize(ctx)
            await stages.load_resolved_profile(ctx, self._resolver)

            if await stages.cache_lookup(ctx, self._cache, self._model_id):
                # Short-circuit. ``ctx.cached_result`` was populated with
                # cache-aware overrides (cached=True, cost=0, latency=lookup).
                assert ctx.cached_result is not None
                base_result = ctx.cached_result
                self._log_end(ctx, status="cache_hit")
            else:
                await stages.preprocess(ctx)
                await stages.build_prompt(ctx, self._template_env)
                provider_start = time.perf_counter()
                await stages.translate(ctx, self._provider)
                ctx.provider_duration_ms = int(
                    (time.perf_counter() - provider_start) * 1000.0
                )
                await stages.postprocess_and_verify(ctx)

                base_result = self._build_result(ctx)
                await stages.cache_write(ctx, base_result, self._cache)

                self._log_end(ctx, status="ok")

            ctx.status = "success"
        except Exception as e:
            ctx.status = "failed"
            ctx.error_code = getattr(e, "error_code", None) or type(e).__name__
            ctx.error_detail = str(e)
            # Top-level error logging. We re-raise — the API layer (Phase 5)
            # will convert provider / pipeline exceptions into HTTP responses.
            log.error(
                "pipeline.failed",
                trace_id=trace_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
        finally:
            ctx.completed_at = datetime.now(timezone.utc)
            ctx.duration_ms = int(
                (time.perf_counter() - ctx.started_at_perf) * 1000.0
            )
            # record_log is tolerant — DB issues swallowed, never re-raises.
            await stages.record_log(ctx, self._log_repo, model_id=self._model_id)

        # Only reached on the success path. Patch the log_id into the result.
        assert base_result is not None
        return base_result.model_copy(update={"log_id": ctx.log_id})
```

- [ ] **Step 6.5: Run pipeline integration tests, verify they pass**

```bash
uv run pytest tests/pipeline/test_pipeline_logging.py tests/pipeline/test_pipeline_batch_logging.py -v
```

Expected: all tests PASS.

- [ ] **Step 6.6: Run full test suite, confirm no regression**

```bash
uv run pytest -x -q
```

Expected: ALL tests pass. Pre-existing pipeline tests + new logging tests + earlier translation_logs tests all green.

- [ ] **Step 6.7: Lint + typecheck**

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: clean.

### Phase 2 commit gate

**Do NOT commit yet.** At this point pipeline writes log rows on every path and ports results back to callers via `result.log_id` — but the API layer doesn't yet expose `log_id` in the HTTP response. Behavior-wise the API is unchanged.

Suggested commit message shape (executor will refine): *"Wire translation log recording into TranslationPipeline via record_log stage in a finally block. Pipeline now persists one row per call (success, cache hit, or failure) without affecting response latency or correctness."*

---

# PHASE 3 — API surface + docs

Goal: HTTP response carries `log_id`; batch endpoint generates shared `batch_id`; ADR & phase status updated in CLAUDE.md.

## Task 7: API response schemas + dependencies

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `src/api/dependencies.py`
- Modify: `src/api/routes/translate.py`
- Create: `tests/api/test_translate_logging.py`

- [ ] **Step 7.1: Write failing API logging tests**

Create `tests/api/test_translate_logging.py`:

```python
"""API tests for log_id propagation and translation_logs persistence.

Uses the existing api_client fixture (which overrides db_session,
provider, cache via dependency_overrides). The session.commit no-op
trick means log row writes are visible within the request but rolled
back at test teardown.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TranslationLog


async def test_translate_response_includes_log_id(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await api_client.post(
        "/translate",
        json={
            "text": "Hello world",
            "target_lang": "id",
            "profile_slug": "general",
            "source_lang": "en",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "log_id" in body
    assert body["log_id"] is not None
    # Verify the log row actually exists.
    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id == uuid.UUID(body["log_id"]))
    )
    saved = row.scalar_one()
    assert saved.status == "success"


async def test_batch_response_includes_log_id_per_item(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await api_client.post(
        "/translate/batch",
        json={
            "items": [
                {"id": "a", "text": "Hello"},
                {"id": "b", "text": "World"},
            ],
            "target_lang": "id",
            "profile_slug": "general",
            "source_lang": "en",
        },
    )
    assert response.status_code == 200
    body = response.json()
    translations = body["translations"]
    assert len(translations) == 2
    for item in translations:
        assert "log_id" in item
        assert item["log_id"] is not None


async def test_batch_log_rows_share_batch_id(
    api_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await api_client.post(
        "/translate/batch",
        json={
            "items": [
                {"id": "a", "text": "Hello"},
                {"id": "b", "text": "World"},
            ],
            "target_lang": "id",
            "profile_slug": "general",
            "source_lang": "en",
        },
    )
    assert response.status_code == 200
    log_ids = [uuid.UUID(item["log_id"]) for item in response.json()["translations"]]

    rows = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id.in_(log_ids))
    )
    saved = list(rows.scalars().all())
    assert len(saved) == 2
    # All items in a batch share one batch_id (server-generated).
    assert saved[0].batch_id is not None
    assert saved[0].batch_id == saved[1].batch_id


async def test_translate_error_response_uses_trace_id_not_log_id(
    api_client: AsyncClient,
) -> None:
    """ErrorResponse envelope does NOT include log_id; correlation is via trace_id."""
    response = await api_client.post(
        "/translate",
        json={
            "text": "Hello",
            "target_lang": "id",
            "profile_slug": "nonexistent-profile-slug",  # triggers 404
            "source_lang": "en",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert "log_id" not in body
    assert "trace_id" in body
```

- [ ] **Step 7.2: Run tests, verify they fail**

```bash
uv run pytest tests/api/test_translate_logging.py -v
```

Expected: tests fail because `log_id` isn't in the response schema yet (`KeyError` on body["log_id"]) and pipeline construction in `get_pipeline` doesn't yet accept `log_repo`.

- [ ] **Step 7.3: Add log_id to TranslateResponse**

In `src/api/schemas.py`, replace the `TranslateResponse` class:

```python
class TranslateResponse(BaseModel):
    """Single-translation response body — flattened :class:`PipelineResult`."""

    translation: str
    source_lang: str
    target_lang: str
    cached: bool
    provider: str
    model: str
    latency_ms: float
    cost_usd: Decimal
    glossary_compliance: float
    metadata: dict[str, Any]
    log_id: uuid.UUID | None = None
```

And `BatchTranslateResultItem`:

```python
class BatchTranslateResultItem(BaseModel):
    """One result in a batch response."""

    id: str
    text: str
    cached: bool
    log_id: uuid.UUID | None = None
    # ``error`` is populated when this particular item failed; the rest of the
    # batch may still have succeeded (partial-success semantics).
    error: str | None = None
```

- [ ] **Step 7.4: Add translation log repo dependency**

Add the runtime import at the top of `src/api/dependencies.py` (in the existing import block):

```python
from src.translation_logs.repository import TranslationLogRepository
```

After the `get_repository` function, add:

```python
async def get_translation_log_repository(
    db: AsyncSession = Depends(get_db),
) -> TranslationLogRepository:
    """Per-request repository for translation_logs writes."""
    return TranslationLogRepository(db)
```

Then update `get_pipeline` to inject the log repo:

```python
async def get_pipeline(
    provider: TranslationProvider = Depends(get_provider),
    cache: CacheBackend = Depends(get_cache),
    resolver: ProfileResolver = Depends(get_resolver),
    template_env: Environment = Depends(get_template_env),
    log_repo: TranslationLogRepository = Depends(get_translation_log_repository),
) -> TranslationPipeline:
    """Build the pipeline per request.

    Pipeline construction is cheap (just attribute assignment); the
    expensive parts — the SDK client and connection pool — live behind the
    cached singletons above. Building per-request keeps the per-request
    resolver and log repo (which hold sessions) wired correctly.
    """
    return TranslationPipeline(
        provider=provider,
        cache=cache,
        resolver=resolver,
        template_env=template_env,
        model_id=get_settings().anthropic_model,
        log_repo=log_repo,
    )
```

## Task 8: API route updates

- [ ] **Step 8.1: Update _to_response to propagate log_id**

In `src/api/routes/translate.py`, replace `_to_response`:

```python
def _to_response(result: PipelineResult) -> TranslateResponse:
    return TranslateResponse(
        translation=result.translation,
        source_lang=result.source_lang,
        target_lang=result.target_lang,
        cached=result.cached,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        glossary_compliance=result.glossary_compliance,
        metadata=result.metadata,
        log_id=result.log_id,
    )
```

- [ ] **Step 8.2: Update _to_pipeline_request to accept batch fields**

Replace `_to_pipeline_request`:

```python
def _to_pipeline_request(
    *,
    tenant_id: uuid.UUID,
    text: str,
    target_lang: str,
    profile_slug: str,
    source_lang: str | None,
    options: TranslationOptions | None,
    batch_id: uuid.UUID | None = None,
    batch_index: int | None = None,
) -> PipelineRequest:
    return PipelineRequest(
        text=text,
        target_lang=target_lang,
        profile_slug=profile_slug,
        tenant_id=tenant_id,
        source_lang=source_lang,
        options=options or TranslationOptions(),
        batch_id=batch_id,
        batch_index=batch_index,
    )
```

- [ ] **Step 8.3: Update /batch endpoint to generate batch_id**

Replace the `translate_batch` function:

```python
@router.post("/batch", response_model=BatchTranslateResponse)
async def translate_batch(
    payload: BatchTranslateRequest,
    pipeline: TranslationPipeline = Depends(get_pipeline),
    tenant: TenantRead = Depends(get_current_tenant),
) -> BatchTranslateResponse:
    """Translate many items in parallel.

    ``asyncio.gather(return_exceptions=True)`` collects exceptions instead of
    short-circuiting, so a single bad item never sinks the whole batch.
    Per-item errors land in ``BatchTranslateResultItem.error``; successful
    items have ``error=None``.

    A single ``batch_id`` is generated once per HTTP request and threaded
    through every item's ``PipelineRequest`` so all log rows from this
    batch share an identifier (with their own ``batch_index`` for ordering).

    Concurrency: we don't currently throttle. With ``max_length=100`` in the
    request schema and the provider's own rate-limit retry behaviour, this
    is fine for MVP; a semaphore + dynamic batching is a Phase-6 optimisation.
    """
    batch_id = uuid.uuid4()

    async def _one(idx: int, item: BatchTranslateItem) -> BatchTranslateResultItem:
        try:
            result = await pipeline.translate(
                _to_pipeline_request(
                    tenant_id=tenant.id,
                    text=item.text,
                    target_lang=payload.target_lang,
                    profile_slug=payload.profile_slug,
                    source_lang=payload.source_lang,
                    options=payload.options,
                    batch_id=batch_id,
                    batch_index=idx,
                )
            )
            return BatchTranslateResultItem(
                id=item.id,
                text=result.translation,
                cached=result.cached,
                log_id=result.log_id,
            )
        except Exception as e:
            # Catch broadly here ON PURPOSE — a per-item failure must NOT
            # break the rest of the batch. The exception type is preserved
            # in the message for the caller to inspect. The log row for this
            # failure has already been written by record_log (in finally).
            log.warning(
                "translate.batch.item_failed",
                item_id=item.id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return BatchTranslateResultItem(
                id=item.id,
                text="",
                cached=False,
                error=f"{type(e).__name__}: {e}",
            )

    results = await asyncio.gather(
        *(_one(i, item) for i, item in enumerate(payload.items))
    )
    return BatchTranslateResponse(translations=list(results))
```

- [ ] **Step 8.4: Run API tests, verify they pass**

```bash
uv run pytest tests/api/test_translate_logging.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 8.5: Run full suite + lint + mypy**

```bash
uv run pytest -x -q
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: all green.

## Task 9: ADR additions + Phase status update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 9.1: Append ADRs to CLAUDE.md "Decision log" section**

Add these three ADRs at the end of the existing ADR list in CLAUDE.md (after ADR-025):

```markdown
- ADR-026: Translation log menyimpan `source_text` & `translated_text` full plaintext. PII trade-off diterima untuk MVP (single-tenant, operator internal); mitigasi reaktif berupa future redaction flag + dashboard access control kalau pelanggan eksternal onboard.
- ADR-027: `record_log` swallows `SQLAlchemyError` + `ValidationError`; `log_id` nullable di response untuk signal write failure. Cache-pattern degradation (ADR-013) di-extend ke log layer — translation API tetap healthy meski log store unhealthy.
- ADR-028: `error_detail` sanitization minimal via regex (`sk-ant-…`, `Bearer …` patterns), expand reactively bukan upfront. Over-engineering token-pattern detection sebelum pattern muncul di logs nyata = bikeshedding.
```

- [ ] **Step 9.2: Add sub-proyek B to Phase status section**

In CLAUDE.md "Phase status" section, after the existing "Phase 7" line and "MVP complete" paragraph, append:

```markdown

**Post-MVP sub-projects (started 2026-05-21):**

- **Sub-proyek B — Translation log table**: ✅ complete (verified 2026-05-XX, replace with actual verification date)
  - Migration `alembic/versions/002_translation_logs.py` creates `translation_logs` with denormalized profile_slug/quality_mode, forward-compat columns for sub-proyek C (detected_source_lang, detected_output_lang, *_lang_mismatch), and 3 indexes (tenant+started, tenant+profile+started, partial-failed).
  - `src/translation_logs/{schemas,repository,sanitize}.py` — TranslationLogCreate / TranslationLogRead Pydantic; repository.create() inserts a row, read methods (recent / by_profile / aggregate_cost) are NotImplementedError stubs handed off to sub-proyek F. sanitize_error redacts `sk-ant-…` + `Bearer …` and truncates to 2000 chars.
  - `src/pipeline/stages.py` `record_log` stage + `_build_log_payload` helper run inside the pipeline's `finally` block on every call (success, cache hit, failure). All SQLAlchemyError + ValidationError swallowed (ADR-027); pipeline result carries `log_id` (None when write failed).
  - `src/pipeline/pipeline.py` `TranslationPipeline.translate()` refactored to `try / except / finally`; `__init__` now requires `log_repo: TranslationLogRepository`.
  - `src/api/routes/translate.py` generates one `batch_id` per `/translate/batch` request; per-item `batch_index` threaded through `PipelineRequest`.
  - `TranslateResponse.log_id` and `BatchTranslateResultItem.log_id` expose the row id; clients correlate failed calls via the existing `ErrorResponse.trace_id`.
  - X new tests (X sanitize, X schemas, X repository, X record_log stage, 7 pipeline integration, 2 batch logging, 4 API). Live smoke: hit `/translate` once → row visible in psql; trigger error → failed row with sanitized detail.
  - Unblocks: sub-proyek C (lang detection — populate forward columns), sub-proyek F (dashboard — implement read methods).
```

Replace `X` with actual test counts after running the suite. The "verification date" can be filled when the implementer manually verifies end-to-end.

## Task 10: Final verification

- [ ] **Step 10.1: Apply migration and run full test suite**

```bash
uv run alembic upgrade head
uv run pytest -v
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: migration is at head (no-op if already applied), all tests pass, lint and typecheck clean.

- [ ] **Step 10.2: Manual smoke — single translate**

Start the API:

```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

In another terminal:

```bash
curl -s -X POST http://localhost:8000/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello world","target_lang":"id","profile_slug":"general","source_lang":"en"}' | jq .
```

Expected: response includes `log_id` (UUID). Then verify the row:

```bash
docker compose exec postgres psql -U postgres -d aitrans_db -c \
  "SELECT id, status, source_lang, target_lang, source_text, translated_text, cost_usd FROM translation_logs ORDER BY started_at DESC LIMIT 1;"
```

Expected: one row with `status='success'`, the input text, the translated output, a non-zero `cost_usd`.

- [ ] **Step 10.3: Manual smoke — batch translate**

```bash
curl -s -X POST http://localhost:8000/translate/batch \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"id":"a","text":"Hello"},{"id":"b","text":"World"}],"target_lang":"id","profile_slug":"general","source_lang":"en"}' | jq .
```

Expected: 2 items, each with a `log_id`. Verify shared `batch_id`:

```bash
docker compose exec postgres psql -U postgres -d aitrans_db -c \
  "SELECT batch_id, batch_index, source_text, status FROM translation_logs WHERE batch_id IS NOT NULL ORDER BY started_at DESC, batch_index LIMIT 2;"
```

Expected: 2 rows sharing one `batch_id` value, `batch_index` 0 and 1.

- [ ] **Step 10.4: Manual smoke — error path with sanitization**

Trigger a 404:

```bash
curl -s -X POST http://localhost:8000/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":"hi","target_lang":"id","profile_slug":"does-not-exist","source_lang":"en"}' | jq .
```

Expected: `error_code: profile_not_found`, `trace_id` present, `log_id` absent. **No row should be persisted** for this case (per the test `test_pipeline_writes_log_on_profile_not_found`, profile resolution fails before the context is populated enough to construct a valid log payload — the swallow path takes over).

Verify no leftover error row:

```bash
docker compose exec postgres psql -U postgres -d aitrans_db -c \
  "SELECT count(*) FROM translation_logs WHERE error_code = 'ProfileNotFound';"
```

Expected: `0`.

- [ ] **Step 10.5: Fill in actual test counts and verification date in CLAUDE.md**

Run:

```bash
uv run pytest --collect-only -q tests/translation_logs/ tests/pipeline/test_pipeline_logging.py tests/pipeline/test_pipeline_batch_logging.py tests/api/test_translate_logging.py | grep "test_" | wc -l
```

Update the test counts and the verification date in the CLAUDE.md sub-proyek B paragraph.

### Phase 3 commit gate

**Stop here.** Implementation is complete and verified. At this point the executor should:

1. Run `git status` and `git diff` to inspect all changes.
2. Surface a 2-sentence commit message recommendation covering API + docs changes (the executor will pick the actual wording based on the diff; a starting shape: *"Expose `log_id` in /translate and /translate/batch responses; batch endpoint now generates a shared `batch_id` so all items in one call share a correlation handle. CLAUDE.md updated with ADR-026/027/028 and sub-proyek B phase status."*).
3. Wait for the user's explicit OK before running `git commit`.
4. **Do not `git push`.** The user pushes manually.

If the user prefers a different phase grouping (one commit for the whole sub-proyek instead of three), bundle the staged diffs accordingly.

---

## Open follow-ups (not blockers for this plan)

- **`prompt_template_version` populate strategy** — currently leave NULL. When template versioning becomes useful (multi-template, A/B prompts), wire from a constant or jinja-file hash.
- **Migration smoke test** — deliberately omitted; alembic-from-pytest tests are flaky vs. their value at MVP scale. Manual `alembic upgrade head` smoke covers it.
- **Sub-proyek C handoff** — when language detection ships, populate `detected_source_lang`, `detected_output_lang`, `source_lang_mismatch`, `output_lang_mismatch` columns. No schema change needed.
- **Sub-proyek F handoff** — implement `TranslationLogRepository.recent` / `by_profile` / `aggregate_cost`; build dashboard view that reads from the table.
