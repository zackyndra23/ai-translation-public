# Agentic Activity Tracking + Language Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor pipeline into 3-agent orchestration (lang_detect_input + translate in Group 1, lang_detect_output in Group 2). Each agent's prompt/tokens/cost/latency captured as `AgenticActivity`, surfaced in API response + persisted to translation_logs + cached in Redis + visualized in Streamlit horizontal-lanes layout. Mismatch flags populate sub-proyek B's forward columns.

**Architecture:** New `src/pipeline/agents/` package with `Agent` Protocol, `AgenticActivity` Pydantic, `LangDetectAgent` + `TranslateAgent`, and a cancellation-safe `run_agents` orchestrator. `TranslationPipeline.translate` replaces its direct translate-stage call with `build_agents() + run_agents()`. Migration 004 adds `agentic_activities JSONB NULL` column.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, asyncio.gather, Anthropic SDK (Claude Haiku for detection, Sonnet for translate), Streamlit with custom HTML for agent boxes.

**Commit policy:** Per user preference — D + prompt_applied + G+C all bundled into one mega-commit at the end with explicit user confirmation. **Never `git push`.**

**Spec reference:** `docs/superpowers/specs/2026-05-21-agentic-tracking-and-lang-detection-design.md`

---

## File Structure

**New files:**

| Path | Responsibility |
|------|----------------|
| `src/pipeline/agents/__init__.py` | Public exports |
| `src/pipeline/agents/base.py` | `Agent` Protocol, `AgenticActivity` Pydantic |
| `src/pipeline/agents/lang_detect.py` | `LangDetectAgent` (Haiku-backed, input/output direction param) |
| `src/pipeline/agents/translate.py` | `TranslateAgent` (refactored from current translate stage) |
| `src/pipeline/agents/orchestrator.py` | `run_agents`, `_safe_run`, `build_agents` |
| `alembic/versions/004_translation_logs_agentic_activities.py` | Migration |
| `tests/pipeline/agents/__init__.py` | Empty marker |
| `tests/pipeline/agents/test_lang_detect_agent.py` | 3 unit tests |
| `tests/pipeline/agents/test_translate_agent.py` | 2 unit tests |
| `tests/pipeline/agents/test_orchestrator.py` | 2 unit tests (group ordering, cancellation safety) |
| `tests/pipeline/test_pipeline_agents.py` | 6 integration tests |
| `tests/api/test_agentic_response.py` | 4 API tests |

**Modified files:**

| Path | Change |
|------|--------|
| `src/config/settings.py` | Add `anthropic_haiku_model: str = "claude-haiku-4-5-20251001"` |
| `src/db/models.py` | Add `agentic_activities` JSONB column to TranslationLog |
| `src/translation_logs/schemas.py` | Add `agentic_activities` to Create + Read |
| `src/pipeline/schemas.py` | Add 5 new fields to PipelineResult |
| `src/pipeline/stages.py` | Extend PipelineContext (add `agentic_activities`, `detected_*`, `*_mismatch`); update `_build_log_payload`; existing `translate` stage stays as a helper used by TranslateAgent |
| `src/pipeline/pipeline.py` | Refactor `translate()`: call `build_agents() + run_agents()` instead of direct translate stage |
| `src/api/schemas.py` | Add 5 fields to `TranslateResponse` + `BatchTranslateResultItem` |
| `src/api/routes/translate.py` | `_to_response` includes new fields |
| `src/api/dependencies.py` | Inject `haiku_model_id` alongside sonnet `model_id` |
| `demo/app.py` | Mismatch banner + `_render_agent_flow` + `_render_agent_box` helpers |
| `CLAUDE.md` | Append ADR-031, ADR-032, ADR-033 |

---

# Task 1: Settings — add Haiku model config

**Files:**
- Modify: `src/config/settings.py`

- [ ] **Step 1.1: Add Haiku model setting**

Read `src/config/settings.py` to find the existing `anthropic_model` field. After it, add:

```python
    # Lang-detection agents use Haiku (cheap + fast). The main translate
    # stays on Sonnet for translation quality.
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"
```

- [ ] **Step 1.2: Verify settings load**

```bash
uv run python -c "from src.config.settings import get_settings; print(get_settings().anthropic_haiku_model)"
```

Expected: `claude-haiku-4-5-20251001`.

---

# Task 2: Migration 004 + ORM column

**Files:**
- Create: `alembic/versions/004_translation_logs_agentic_activities.py`
- Modify: `src/db/models.py`

- [ ] **Step 2.1: Create migration**

Create `alembic/versions/004_translation_logs_agentic_activities.py`:

```python
"""Add agentic_activities JSONB column to translation_logs.

Revision ID: 004_agentic_activities
Revises: 003_rendered_prompt
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004_agentic_activities"
down_revision: str | None = "003_rendered_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable so existing rows keep working; new rows populated by
    # _build_log_payload from ctx.agentic_activities.
    op.add_column(
        "translation_logs",
        sa.Column("agentic_activities", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("translation_logs", "agentic_activities")
```

- [ ] **Step 2.2: Add ORM column to TranslationLog**

In `src/db/models.py`, find the `TranslationLog` class. After the `rendered_prompt` Mapped column (added in earlier prompt_applied task), add:

```python
    agentic_activities: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
```

- [ ] **Step 2.3: Apply migration**

```bash
uv run alembic upgrade head
docker compose exec postgres psql -U aitrans -d aitrans_db -c "\d translation_logs" | grep agentic_activities
```

Expected: column `agentic_activities | jsonb` visible.

- [ ] **Step 2.4: Verify tests still pass (column nullable, no regression)**

```bash
uv run pytest tests/ -x -q
```

Expected: 202 passed (no new tests yet, but no regression).

---

# Task 3: AgenticActivity Pydantic + Agent Protocol + tests

**Files:**
- Create: `src/pipeline/agents/__init__.py`
- Create: `src/pipeline/agents/base.py`
- Create: `tests/pipeline/agents/__init__.py`
- Create: `tests/pipeline/agents/test_agentic_activity_schema.py`

TDD: tests first, then implementation.

- [ ] **Step 3.1: Create package markers**

`src/pipeline/agents/__init__.py`:

```python
"""Agent abstraction for multi-step pipeline orchestration (sub-proyek G+C)."""
```

`tests/pipeline/agents/__init__.py`: empty file.

- [ ] **Step 3.2: Write failing schema tests**

Create `tests/pipeline/agents/test_agentic_activity_schema.py`:

```python
"""Schema sanity tests for AgenticActivity Pydantic model."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.pipeline.agents.base import AgenticActivity


def _minimal() -> dict:
    return dict(
        name="lang_detect_input",
        agent_type="language_detection",
        group_index=1,
        latency_ms=400.0,
        status="success",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )


def test_minimal_payload_accepted() -> None:
    activity = AgenticActivity(**_minimal())
    assert activity.name == "lang_detect_input"
    assert activity.status == "success"
    assert activity.model_id is None
    assert activity.cost_usd is None
    assert activity.result is None


def test_failed_status_with_error_fields() -> None:
    payload = _minimal()
    payload["status"] = "failed"
    payload["error_code"] = "rate_limited"
    payload["error_detail"] = "429 from provider"
    activity = AgenticActivity(**payload)
    assert activity.status == "failed"
    assert activity.error_code == "rate_limited"


def test_invalid_status_rejected() -> None:
    payload = _minimal()
    payload["status"] = "pending"
    with pytest.raises(ValidationError):
        AgenticActivity(**payload)


def test_full_llm_call_payload() -> None:
    payload = _minimal()
    payload["model_id"] = "claude-haiku-4-5-20251001"
    payload["prompt_applied"] = "Detect the language of: ..."
    payload["input_tokens"] = 50
    payload["output_tokens"] = 12
    payload["cost_usd"] = Decimal("0.00006")
    payload["result"] = {"detected_lang": "fr", "confidence": 0.95}
    activity = AgenticActivity(**payload)
    assert activity.input_tokens == 50
    assert activity.result == {"detected_lang": "fr", "confidence": 0.95}
```

- [ ] **Step 3.3: Run tests to verify they fail**

```bash
uv run pytest tests/pipeline/agents/test_agentic_activity_schema.py -v
```

Expected: ImportError on `src.pipeline.agents.base`.

- [ ] **Step 3.4: Implement AgenticActivity + Agent Protocol**

Create `src/pipeline/agents/base.py`:

```python
"""Agent Protocol + AgenticActivity Pydantic.

Per ADR-031, agents soft-fail (don't block primary translate). Per ADR-032,
``AgenticActivity.result`` is ``dict[str, Any]`` not typed per agent — shape
varies, JSONB serialization-friendly, future agents extend without schema
migration.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class AgenticActivity(BaseModel):
    """One agent's execution record — captured per-request, propagated to
    response + log (JSONB) + Redis cache.

    All LLM-call fields (model_id, prompt_applied, input_tokens,
    output_tokens, cost_usd) are nullable so future non-LLM agents (e.g.,
    regex-based glossary enforcer) can emit activities without bogus zeros.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    agent_type: str  # "language_detection" | "translation"
    group_index: int

    model_id: str | None = None
    prompt_applied: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None

    latency_ms: float
    status: Literal["success", "failed", "skipped"]
    started_at: datetime
    completed_at: datetime

    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: str | None = None


@runtime_checkable
class Agent(Protocol):
    """Protocol every agent implements.

    Non-translate agents must catch their own exceptions and emit an
    AgenticActivity with status='failed'. The TranslateAgent is allowed to
    propagate exceptions — the orchestrator's ``_safe_run`` wrapper captures
    them so the rest of the group still runs.
    """

    name: str
    agent_type: str
    group_index: int

    async def run(self, ctx: "PipelineContext") -> AgenticActivity: ...
```

The `"PipelineContext"` forward reference avoids importing from `src.pipeline.stages` (which would create a cycle once stages.py imports back into agents/).

- [ ] **Step 3.5: Run tests to verify they pass**

```bash
uv run pytest tests/pipeline/agents/test_agentic_activity_schema.py -v
```

Expected: all 4 tests PASS.

---

# Task 4: PipelineContext extensions + PipelineResult fields

**Files:**
- Modify: `src/pipeline/stages.py` (PipelineContext dataclass)
- Modify: `src/pipeline/schemas.py` (PipelineResult)
- Modify: `src/translation_logs/schemas.py` (TranslationLogCreate + TranslationLogRead)

These extensions are precursors to Task 5+ — context fields populated by orchestrator, response fields propagated by `_build_result`.

- [ ] **Step 4.1: Extend `PipelineContext` with agentic fields**

In `src/pipeline/stages.py`, find the `PipelineContext` dataclass. After the existing `log_id` field, add:

```python
    # Populated by run_agents (sub-proyek G+C).
    agentic_activities: list["AgenticActivity"] = field(default_factory=list)
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
```

Add the import at the top of `src/pipeline/stages.py` (inside any existing TYPE_CHECKING block, or guard a new one — these fields use string annotation so runtime import is optional):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.agents.base import AgenticActivity
```

If TYPE_CHECKING already exists, just add the import line.

- [ ] **Step 4.2: Extend `PipelineResult` with agentic fields**

In `src/pipeline/schemas.py`, find the `PipelineResult` class. After the existing `prompt_applied` field, add:

```python
    agentic_activities: list[AgenticActivity] = Field(default_factory=list)
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
```

Add the import at the top of `src/pipeline/schemas.py`:

```python
from src.pipeline.agents.base import AgenticActivity
```

- [ ] **Step 4.3: Extend `TranslationLogCreate` + `TranslationLogRead`**

In `src/translation_logs/schemas.py`, add to both `TranslationLogCreate` and `TranslationLogRead`. For Create (in the section with detection forward columns, before `request_metadata`):

```python
    # Full agent activities list (sub-proyek G+C). JSONB-serialized.
    agentic_activities: list[dict[str, Any]] | None = None
```

For Read, mirror with non-default field:

```python
    agentic_activities: list[dict[str, Any]] | None
```

We use `dict[str, Any]` rather than `list[AgenticActivity]` because the DB column stores raw JSONB and the schemas don't re-validate the activity shape on read (Read is permissive per ADR-032 spirit).

- [ ] **Step 4.4: Verify no regression**

```bash
uv run pytest tests/ -x -q
uv run mypy src/
```

Expected: 202 still pass (existing tests don't reference the new fields; defaults make them transparent).

---

# Task 5: LangDetectAgent + unit tests (TDD)

**Files:**
- Create: `tests/pipeline/agents/test_lang_detect_agent.py`
- Create: `src/pipeline/agents/lang_detect.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/pipeline/agents/test_lang_detect_agent.py`:

```python
"""Unit tests for LangDetectAgent — both input and output direction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.pipeline.agents.lang_detect import LangDetectAgent
from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext
from src.providers.base import TranslationResult


def _ctx_with_text(text: str = "Bonjour le monde") -> PipelineContext:
    request = PipelineRequest(
        text=text,
        target_lang="id",
        profile_slug="general",
        tenant_id=uuid.uuid4(),
        source_lang="en",
    )
    ctx = PipelineContext(
        request=request,
        trace_id="trace-test",
        started_at_perf=0.0,
        started_at=datetime.now(UTC),
    )
    ctx.normalized_text = text
    return ctx


async def test_lang_detect_input_success() -> None:
    """Detects language of normalized input text via Haiku."""
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation="fr",
            provider="claude",
            model="claude-haiku-4-5-20251001",
            tokens_input=50,
            tokens_output=12,
            cost_usd=Decimal("0.00006"),
            latency_ms=412.0,
            metadata={"stop_reason": "end_turn"},
        )
    )
    agent = LangDetectAgent(
        name="lang_detect_input",
        group_index=1,
        text_source="input",
        provider=provider,
        model_id="claude-haiku-4-5-20251001",
    )

    activity = await agent.run(_ctx_with_text("Bonjour le monde"))

    assert activity.name == "lang_detect_input"
    assert activity.agent_type == "language_detection"
    assert activity.group_index == 1
    assert activity.status == "success"
    assert activity.model_id == "claude-haiku-4-5-20251001"
    assert activity.input_tokens == 50
    assert activity.output_tokens == 12
    assert activity.cost_usd == Decimal("0.00006")
    assert activity.result == {"detected_lang": "fr"}


async def test_lang_detect_output_reads_from_translate_activity() -> None:
    """Output-direction detect reads from prior translate activity's result."""
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation="fr",
            provider="claude",
            model="claude-haiku-4-5-20251001",
            tokens_input=60,
            tokens_output=12,
            cost_usd=Decimal("0.00007"),
            latency_ms=398.0,
            metadata={},
        )
    )
    agent = LangDetectAgent(
        name="lang_detect_output",
        group_index=2,
        text_source="output",
        provider=provider,
        model_id="claude-haiku-4-5-20251001",
    )

    ctx = _ctx_with_text("Hello world")
    # Simulate Group 1 having completed: translate agent's activity is in ctx.
    from src.pipeline.agents.base import AgenticActivity

    ctx.agentic_activities = [
        AgenticActivity(
            name="translate",
            agent_type="translation",
            group_index=1,
            latency_ms=1840.0,
            status="success",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            result={"translation": "Bonjour le monde", "stop_reason": "end_turn"},
        )
    ]

    activity = await agent.run(ctx)

    assert activity.name == "lang_detect_output"
    assert activity.status == "success"
    assert activity.result == {"detected_lang": "fr"}
    # Provider was called with the translated text, not the source input.
    call_args = provider.translate.call_args[0][0]
    assert "Bonjour le monde" in call_args.text


async def test_lang_detect_swallows_provider_error() -> None:
    """When the provider raises, agent emits failed activity (doesn't propagate)."""
    from src.providers.errors import RateLimitError

    provider = MagicMock()
    provider.translate = AsyncMock(side_effect=RateLimitError("rate limited"))
    agent = LangDetectAgent(
        name="lang_detect_input",
        group_index=1,
        text_source="input",
        provider=provider,
        model_id="claude-haiku-4-5-20251001",
    )

    activity = await agent.run(_ctx_with_text("anything"))  # must NOT raise

    assert activity.status == "failed"
    assert activity.error_code == "rate_limited"
    assert activity.result is None
```

- [ ] **Step 5.2: Run tests to verify failure**

```bash
uv run pytest tests/pipeline/agents/test_lang_detect_agent.py -v
```

Expected: ImportError on `src.pipeline.agents.lang_detect`.

- [ ] **Step 5.3: Implement LangDetectAgent**

Create `src/pipeline/agents/lang_detect.py`:

```python
"""LangDetectAgent — single class, reusable for input + output direction.

Calls Claude Haiku with a tight system prompt that returns just the
ISO 639-1 code. The result.detected_lang field is what the pipeline post-
processes to compute source_lang_mismatch and output_lang_mismatch.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from src.pipeline.agents.base import AgenticActivity
from src.providers.base import (
    TranslationOptions,
    TranslationProvider,
    TranslationRequest,
)
from src.translation_logs.sanitize import sanitize_error

_DETECT_SYSTEM_PROMPT = (
    "You are a language identifier. Reply with ONLY the ISO 639-1 code of "
    "the language of the input text. Examples: 'en' for English, 'id' for "
    "Indonesian, 'fr' for French, 'ja' for Japanese. No quotes, no "
    "explanation, just the 2-letter lowercase code."
)


class LangDetectAgent:
    """Agent that detects the language of either the input source text or the
    translated output text, depending on ``text_source``.

    Soft-fail (ADR-031): any exception captured as status='failed' activity.
    """

    agent_type = "language_detection"

    def __init__(
        self,
        *,
        name: str,
        group_index: int,
        text_source: Literal["input", "output"],
        provider: TranslationProvider,
        model_id: str,
    ) -> None:
        self.name = name
        self.group_index = group_index
        self.text_source = text_source
        self._provider = provider
        self._model_id = model_id

    async def run(self, ctx: "PipelineContext") -> AgenticActivity:  # type: ignore[name-defined]
        from src.pipeline.stages import PipelineContext  # noqa: F401 — forward ref

        text = self._resolve_text(ctx)
        if not text:
            # Either input was empty (shouldn't happen — validate_and_normalize
            # would have failed) or output detection ran without a translate
            # activity in ctx.
            return self._skipped(reason="text_unavailable")

        started = datetime.now(UTC)
        perf_start = time.perf_counter()
        try:
            request = TranslationRequest(
                text=text,
                source_lang="auto",
                target_lang="en",  # token-saving placeholder; we don't actually translate
                options=TranslationOptions(
                    temperature=0.0,
                    max_tokens=8,  # 2-char code + room for safety; cheap
                    system_prompt_override=_DETECT_SYSTEM_PROMPT,
                ),
            )
            # We reuse the TranslationProvider abstraction for the LLM call.
            # The model_id is fixed for this agent (Haiku) — the provider
            # respects its own default model, so we pass an option override
            # via the provider factory pattern, OR we use a per-call override.
            # In practice: we configure a separate provider instance with
            # haiku_model_id; that's done in build_agents().
            result = await self._provider.translate(request)
        except Exception as exc:
            completed = datetime.now(UTC)
            latency_ms = (time.perf_counter() - perf_start) * 1000.0
            return AgenticActivity(
                name=self.name,
                agent_type=self.agent_type,
                group_index=self.group_index,
                model_id=self._model_id,
                prompt_applied=_DETECT_SYSTEM_PROMPT,
                latency_ms=latency_ms,
                status="failed",
                started_at=started,
                completed_at=completed,
                error_code=getattr(exc, "error_code", None) or type(exc).__name__,
                error_detail=sanitize_error(str(exc)),
            )

        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0
        detected = result.translation.strip().lower()[:5]  # be defensive
        return AgenticActivity(
            name=self.name,
            agent_type=self.agent_type,
            group_index=self.group_index,
            model_id=self._model_id,
            prompt_applied=_DETECT_SYSTEM_PROMPT,
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
            cost_usd=Decimal(str(result.cost_usd)),
            latency_ms=latency_ms,
            status="success",
            started_at=started,
            completed_at=completed,
            result={"detected_lang": detected},
        )

    def _resolve_text(self, ctx: "PipelineContext") -> str | None:  # type: ignore[name-defined]
        if self.text_source == "input":
            return ctx.normalized_text or None
        # output direction: look up translate agent's activity in ctx
        for activity in ctx.agentic_activities:
            if activity.agent_type == "translation" and activity.status == "success":
                if activity.result and "translation" in activity.result:
                    return activity.result["translation"]
        return None

    def _skipped(self, *, reason: str) -> AgenticActivity:
        now = datetime.now(UTC)
        return AgenticActivity(
            name=self.name,
            agent_type=self.agent_type,
            group_index=self.group_index,
            latency_ms=0.0,
            status="skipped",
            started_at=now,
            completed_at=now,
            result={"reason": reason},
        )
```

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
uv run pytest tests/pipeline/agents/test_lang_detect_agent.py -v
```

Expected: all 3 tests PASS.

---

# Task 6: TranslateAgent + unit tests (TDD)

**Files:**
- Create: `tests/pipeline/agents/test_translate_agent.py`
- Create: `src/pipeline/agents/translate.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/pipeline/agents/test_translate_agent.py`:

```python
"""Unit tests for TranslateAgent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pipeline.agents.translate import TranslateAgent
from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext
from src.providers.base import TranslationResult
from src.providers.errors import RateLimitError


def _ctx() -> PipelineContext:
    request = PipelineRequest(
        text="Hello world",
        target_lang="id",
        profile_slug="general",
        tenant_id=uuid.uuid4(),
        source_lang="en",
    )
    ctx = PipelineContext(
        request=request,
        trace_id="trace-test",
        started_at_perf=0.0,
        started_at=datetime.now(UTC),
    )
    ctx.normalized_text = "Hello world"
    ctx.rendered_prompt = "<role>You are a translator</role>..."
    return ctx


async def test_translate_agent_success() -> None:
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation="Halo dunia",
            provider="claude",
            model="claude-sonnet-4-6",
            tokens_input=312,
            tokens_output=87,
            cost_usd=Decimal("0.00132"),
            latency_ms=1840.0,
            metadata={"stop_reason": "end_turn"},
        )
    )
    agent = TranslateAgent(
        name="translate",
        group_index=1,
        provider=provider,
        model_id="claude-sonnet-4-6",
    )

    activity = await agent.run(_ctx())

    assert activity.name == "translate"
    assert activity.agent_type == "translation"
    assert activity.status == "success"
    assert activity.input_tokens == 312
    assert activity.output_tokens == 87
    assert activity.cost_usd == Decimal("0.00132")
    assert activity.result["translation"] == "Halo dunia"
    assert activity.result["stop_reason"] == "end_turn"


async def test_translate_agent_propagates_provider_error() -> None:
    """Unlike lang_detect, translate is the primary value — errors propagate."""
    provider = MagicMock()
    provider.translate = AsyncMock(
        side_effect=RateLimitError("rate limited")
    )
    agent = TranslateAgent(
        name="translate",
        group_index=1,
        provider=provider,
        model_id="claude-sonnet-4-6",
    )

    with pytest.raises(RateLimitError):
        await agent.run(_ctx())
```

- [ ] **Step 6.2: Run tests to verify failure**

```bash
uv run pytest tests/pipeline/agents/test_translate_agent.py -v
```

Expected: ImportError on `src.pipeline.agents.translate`.

- [ ] **Step 6.3: Implement TranslateAgent**

Create `src/pipeline/agents/translate.py`:

```python
"""TranslateAgent — wraps the main LLM translate call as an Agent.

Unlike LangDetectAgent, this agent propagates provider errors (primary value
of the pipeline — failures must surface). The orchestrator's _safe_run
wraps both kinds: for translation agent_type, it captures the activity and
re-raises after the group completes.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

from src.pipeline.agents.base import AgenticActivity
from src.providers.base import (
    TranslationOptions,
    TranslationProvider,
    TranslationRequest,
)


class TranslateAgent:
    """Main translation agent. Sonnet-backed. Errors propagate.

    Reads ctx.normalized_text, ctx.rendered_prompt (from existing
    build_prompt stage), ctx.request (for source_lang/target_lang options),
    and emits an AgenticActivity with the translation result.
    """

    agent_type = "translation"

    def __init__(
        self,
        *,
        name: str,
        group_index: int,
        provider: TranslationProvider,
        model_id: str,
    ) -> None:
        self.name = name
        self.group_index = group_index
        self._provider = provider
        self._model_id = model_id

    async def run(self, ctx: "PipelineContext") -> AgenticActivity:  # type: ignore[name-defined]
        from src.pipeline.stages import AUTO_LANG_SENTINEL  # avoid cycle at import time

        started = datetime.now(UTC)
        perf_start = time.perf_counter()

        request = TranslationRequest(
            text=ctx.normalized_text,
            source_lang=ctx.request.source_lang or AUTO_LANG_SENTINEL,
            target_lang=ctx.request.target_lang,
            profile={"slug": ctx.request.profile_slug},
            options=TranslationOptions(
                temperature=ctx.request.options.temperature,
                max_tokens=ctx.request.options.max_tokens,
                system_prompt_override=ctx.rendered_prompt,
            ),
        )
        # No try/except — primary value, errors propagate per ADR-031.
        result = await self._provider.translate(request)

        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0

        # Mirror into ctx.translation_result for legacy stages (postprocess,
        # cache_write) that still reference it. The agent abstraction wraps
        # the same SDK call; we just also capture per-agent metrics.
        ctx.translation_result = result

        return AgenticActivity(
            name=self.name,
            agent_type=self.agent_type,
            group_index=self.group_index,
            model_id=self._model_id,
            prompt_applied=ctx.rendered_prompt,
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
            cost_usd=Decimal(str(result.cost_usd)),
            latency_ms=latency_ms,
            status="success",
            started_at=started,
            completed_at=completed,
            result={
                "translation": result.translation,
                "stop_reason": result.metadata.get("stop_reason"),
            },
        )
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
uv run pytest tests/pipeline/agents/test_translate_agent.py -v
```

Expected: 2 tests PASS.

---

# Task 7: Orchestrator (run_agents + build_agents + _safe_run) + unit tests

**Files:**
- Create: `tests/pipeline/agents/test_orchestrator.py`
- Create: `src/pipeline/agents/orchestrator.py`

- [ ] **Step 7.1: Write failing orchestrator tests**

Create `tests/pipeline/agents/test_orchestrator.py`:

```python
"""Unit tests for the orchestrator's group ordering + cancellation safety."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pipeline.agents.base import AgenticActivity
from src.pipeline.agents.orchestrator import _safe_run, run_agents
from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext
from src.providers.errors import RateLimitError


def _ctx() -> PipelineContext:
    request = PipelineRequest(
        text="x",
        target_lang="id",
        profile_slug="general",
        tenant_id=uuid.uuid4(),
        source_lang="en",
    )
    return PipelineContext(
        request=request,
        trace_id="t",
        started_at_perf=0.0,
        started_at=datetime.now(UTC),
    )


def _stub_agent(name: str, agent_type: str, group: int, *, will_fail: bool = False) -> MagicMock:
    """A MagicMock-Agent that emits an AgenticActivity with success or failure."""
    agent = MagicMock()
    agent.name = name
    agent.agent_type = agent_type
    agent.group_index = group

    async def _run(ctx):  # noqa: ARG001
        if will_fail:
            if agent_type == "translation":
                raise RateLimitError("translate failed")
            # non-translate fails internally → returns failed activity
            return AgenticActivity(
                name=name,
                agent_type=agent_type,
                group_index=group,
                latency_ms=10.0,
                status="failed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                error_code="some_error",
            )
        return AgenticActivity(
            name=name,
            agent_type=agent_type,
            group_index=group,
            latency_ms=10.0,
            status="success",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            result={"detected_lang": "en"} if agent_type == "language_detection" else {"translation": "x"},
        )

    agent.run = AsyncMock(side_effect=_run)
    return agent


async def test_run_agents_orders_by_group() -> None:
    agents = [
        _stub_agent("translate", "translation", 1),
        _stub_agent("detect_in", "language_detection", 1),
        _stub_agent("detect_out", "language_detection", 2),
    ]

    activities = await run_agents(_ctx(), agents)

    assert len(activities) == 3
    # Group 1 entries come before group 2 entries
    g1_count = sum(1 for a in activities if a.group_index == 1)
    g2_count = sum(1 for a in activities if a.group_index == 2)
    assert g1_count == 2
    assert g2_count == 1
    # group 2 activity is last
    assert activities[-1].group_index == 2


async def test_run_agents_reraises_translate_failure_after_recording_group() -> None:
    agents = [
        _stub_agent("detect_in", "language_detection", 1),
        _stub_agent("translate", "translation", 1, will_fail=True),
        _stub_agent("detect_out", "language_detection", 2),  # should not be reached
    ]

    with pytest.raises(RateLimitError):
        await run_agents(_ctx(), agents)
    # Note: the detect_in activity should have been recorded into ctx
    # somewhere — actually, run_agents returns activities only when no error.
    # On error, partial activities accessible via... we'll test this via the
    # pipeline integration tests. Here we just confirm the re-raise happens.
```

- [ ] **Step 7.2: Run tests to verify failure**

```bash
uv run pytest tests/pipeline/agents/test_orchestrator.py -v
```

Expected: ImportError on `src.pipeline.agents.orchestrator`.

- [ ] **Step 7.3: Implement orchestrator**

Create `src/pipeline/agents/orchestrator.py`:

```python
"""Group-by + asyncio.gather orchestration with cancellation safety.

Per spec §4.3: agents are organized into integer-indexed groups; within a
group they run in parallel via asyncio.gather; groups run sequentially in
ascending order.

The translate agent (agent_type='translation') is allowed to propagate
provider errors. ``_safe_run`` wraps every agent so siblings in the same
group are NOT cancelled by a translate failure mid-flight — the exception
is captured along with all sibling activities, then re-raised after the
group completes (so the pipeline's record_log finally block sees a
complete activities list).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from src.pipeline.agents.base import Agent, AgenticActivity
from src.translation_logs.sanitize import sanitize_error


async def run_agents(
    ctx: "PipelineContext",  # type: ignore[name-defined]
    agents: list[Agent],
) -> list[AgenticActivity]:
    """Run agents grouped by group_index, return all captured activities.

    Re-raises the translate agent's exception (if any) after recording
    every activity in the failing group, so partial results land in
    ctx.agentic_activities AND the log row.
    """
    activities: list[AgenticActivity] = []
    grouped: dict[int, list[Agent]] = {}
    for agent in agents:
        grouped.setdefault(agent.group_index, []).append(agent)

    pending_raise: BaseException | None = None
    for group_index in sorted(grouped):
        group_agents = grouped[group_index]
        gather_results = await asyncio.gather(
            *(_safe_run(agent, ctx) for agent in group_agents),
            return_exceptions=False,  # _safe_run never raises
        )
        for activity, raised in gather_results:
            activities.append(activity)
            # Mirror into ctx so output-direction lang detect can read prior groups.
            ctx.agentic_activities.append(activity)
            if raised is not None and activity.agent_type == "translation":
                pending_raise = raised

    if pending_raise is not None:
        raise pending_raise
    return activities


async def _safe_run(
    agent: Agent,
    ctx: "PipelineContext",  # type: ignore[name-defined]
) -> tuple[AgenticActivity, BaseException | None]:
    """Run an agent and capture (activity, exception). Never raises.

    Non-translate agents: agent.run() catches its own errors and emits a
    status='failed' activity; raised is None.

    TranslateAgent: agent.run() propagates errors. _safe_run captures the
    exception, synthesizes a status='failed' activity, returns both.
    """
    started = datetime.now(UTC)
    perf_start = time.perf_counter()
    try:
        activity = await agent.run(ctx)
        return activity, None
    except Exception as exc:
        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0
        activity = AgenticActivity(
            name=agent.name,
            agent_type=agent.agent_type,
            group_index=agent.group_index,
            latency_ms=latency_ms,
            status="failed",
            started_at=started,
            completed_at=completed,
            error_code=getattr(exc, "error_code", None) or type(exc).__name__,
            error_detail=sanitize_error(str(exc)),
        )
        return activity, exc


def build_agents(
    ctx: "PipelineContext",  # type: ignore[name-defined,unused-argument]
    *,
    provider: "TranslationProvider",  # type: ignore[name-defined]
    haiku_provider: "TranslationProvider",  # type: ignore[name-defined]
    sonnet_model_id: str,
    haiku_model_id: str,
) -> list[Agent]:
    """Configure the 3 agents for one /translate request.

    Two provider instances: one configured with sonnet default (for translate),
    one with haiku default (for lang detect). They share the same underlying
    Anthropic SDK client class but different model_id defaults.
    """
    from src.pipeline.agents.lang_detect import LangDetectAgent
    from src.pipeline.agents.translate import TranslateAgent

    return [
        LangDetectAgent(
            name="lang_detect_input",
            group_index=1,
            text_source="input",
            provider=haiku_provider,
            model_id=haiku_model_id,
        ),
        TranslateAgent(
            name="translate",
            group_index=1,
            provider=provider,
            model_id=sonnet_model_id,
        ),
        LangDetectAgent(
            name="lang_detect_output",
            group_index=2,
            text_source="output",
            provider=haiku_provider,
            model_id=haiku_model_id,
        ),
    ]
```

- [ ] **Step 7.4: Run tests to verify they pass**

```bash
uv run pytest tests/pipeline/agents/ -v
```

Expected: all 9 agent tests pass (4 schema + 3 lang_detect + 2 translate + 2 orchestrator = 11. Adjusted: 4+3+2+2=11).

---

# Task 8: Provider factory — Haiku instance

**Files:**
- Modify: `src/providers/factory.py`
- Modify: `src/api/dependencies.py`

The factory currently builds one Sonnet-configured provider. We need a second instance configured for Haiku.

- [ ] **Step 8.1: Read existing factory pattern**

Read `src/providers/factory.py` to understand the existing `get_provider("claude-sonnet")` function (Phase 2 code).

- [ ] **Step 8.2: Add Haiku provider factory entry**

In `src/providers/factory.py`, find the `get_provider` function. Update it to accept a `model_id` override OR to support a `"claude-haiku"` shortcut. Easiest path: add a `model_id_override` parameter:

```python
def get_provider(
    name: str,
    *,
    model_id_override: str | None = None,
) -> TranslationProvider:
    """Return a configured provider by name.

    ``model_id_override``: when set, the returned provider uses this as its
    default model_id instead of the factory's default. Used by sub-proyek
    G+C to spin up a Haiku-backed provider for lang detection while the
    primary Sonnet provider stays for translate.
    """
    if name == "claude-sonnet":
        from src.providers.claude import ClaudeProvider
        from src.providers.retrying import RetryingProvider

        settings = get_settings()
        default_model = model_id_override or settings.anthropic_model
        inner = ClaudeProvider(
            anthropic_api_key=settings.anthropic_api_key,
            default_model=default_model,
        )
        return RetryingProvider(inner)
    raise ValueError(f"Unknown provider: {name}")
```

(Adapt to the existing function's actual structure — if it's already structured around a registry, plug into that. The important contract: the override flows into ClaudeProvider's `default_model` so the SDK call uses Haiku for lang detection.)

- [ ] **Step 8.3: Update `get_pipeline` dependency to build both providers**

In `src/api/dependencies.py`, find `get_pipeline`. The current `_build_provider` lru_cached creates one Sonnet provider. Add a second cached factory for Haiku:

```python
@lru_cache(maxsize=1)
def _build_haiku_provider() -> TranslationProvider:
    """Haiku-default provider for lang_detect agents. Process-wide singleton."""
    settings = get_settings()
    return build_provider("claude-sonnet", model_id_override=settings.anthropic_haiku_model)


def get_haiku_provider() -> TranslationProvider:
    return _build_haiku_provider()
```

Then update `get_pipeline` to accept and forward both:

```python
async def get_pipeline(
    provider: TranslationProvider = Depends(get_provider),
    haiku_provider: TranslationProvider = Depends(get_haiku_provider),
    cache: CacheBackend = Depends(get_cache),
    resolver: ProfileResolver = Depends(get_resolver),
    template_env: Environment = Depends(get_template_env),
    log_repo: TranslationLogRepository = Depends(get_log_repository),
) -> TranslationPipeline:
    settings = get_settings()
    return TranslationPipeline(
        provider=provider,
        haiku_provider=haiku_provider,
        cache=cache,
        resolver=resolver,
        template_env=template_env,
        model_id=settings.anthropic_model,
        haiku_model_id=settings.anthropic_haiku_model,
        log_repo=log_repo,
    )
```

(The `TranslationPipeline.__init__` signature is updated in Task 9.)

---

# Task 9: TranslationPipeline refactor — call run_agents instead of translate stage

**Files:**
- Modify: `src/pipeline/pipeline.py`

This is the biggest single refactor. The orchestrator now:
1. Runs validate_and_normalize, load_resolved_profile, cache_lookup, preprocess, build_prompt stages (unchanged).
2. Replaces the direct `await stages.translate(ctx, self._provider)` call with `build_agents(ctx, ...) + await run_agents(ctx, agents)`.
3. Computes mismatch flags from the resulting activities.
4. Runs postprocess_and_verify (against ctx.translation_result, which TranslateAgent populates).
5. Cache_write, record_log (unchanged).

- [ ] **Step 9.1: Update `TranslationPipeline.__init__` signature**

In `src/pipeline/pipeline.py`, find `__init__`. Update signature to add `haiku_provider` and `haiku_model_id`:

```python
    def __init__(
        self,
        *,
        provider: TranslationProvider,
        haiku_provider: TranslationProvider,
        cache: CacheBackend,
        resolver: ProfileResolver,
        template_env: Environment | None = None,
        model_id: str,
        haiku_model_id: str,
        log_repo: TranslationLogRepository | None = None,
    ) -> None:
        self._provider = provider
        self._haiku_provider = haiku_provider
        self._cache = cache
        self._resolver = resolver
        self._template_env = template_env or build_template_env()
        self._model_id = model_id
        self._haiku_model_id = haiku_model_id
        self._log_repo = log_repo
```

- [ ] **Step 9.2: Update `TranslationPipeline.translate` to use agents**

Replace the section that currently runs `await stages.translate(ctx, self._provider)` and `provider_duration_ms` capture. Find the block (in the `else:` branch of cache hit), and replace:

```python
            else:
                await stages.preprocess(ctx)
                await stages.build_prompt(ctx, self._template_env)
                provider_start = time.perf_counter()
                await stages.translate(ctx, self._provider)
                ctx.provider_duration_ms = int(
                    (time.perf_counter() - provider_start) * 1000.0
                )
                await stages.postprocess_and_verify(ctx)
                ...
```

with:

```python
            else:
                from src.pipeline.agents.orchestrator import build_agents, run_agents

                await stages.preprocess(ctx)
                await stages.build_prompt(ctx, self._template_env)

                agents = build_agents(
                    ctx,
                    provider=self._provider,
                    haiku_provider=self._haiku_provider,
                    sonnet_model_id=self._model_id,
                    haiku_model_id=self._haiku_model_id,
                )
                provider_start = time.perf_counter()
                # run_agents populates ctx.agentic_activities AND
                # ctx.translation_result (via TranslateAgent). Raises if
                # TranslateAgent fails (primary value).
                await run_agents(ctx, agents)
                ctx.provider_duration_ms = int(
                    (time.perf_counter() - provider_start) * 1000.0
                )

                # Compute mismatch flags from agent results.
                _populate_mismatch_flags(ctx)

                await stages.postprocess_and_verify(ctx)
                ...
```

- [ ] **Step 9.3: Add `_populate_mismatch_flags` helper**

In `src/pipeline/pipeline.py`, add this helper as a module-level function (above the `TranslationPipeline` class):

```python
def _populate_mismatch_flags(ctx: "stages.PipelineContext") -> None:
    """Read detection results from ctx.agentic_activities and write
    ctx.detected_source_lang / detected_output_lang / source_lang_mismatch /
    output_lang_mismatch.

    Mismatch is None when detection didn't run (e.g., agent failed) or when
    user didn't claim a source_lang (auto-detect mode — nothing to mismatch).
    """
    for activity in ctx.agentic_activities:
        if activity.agent_type != "language_detection":
            continue
        if activity.status != "success" or not activity.result:
            continue
        detected = activity.result.get("detected_lang")
        if not detected:
            continue
        if activity.name == "lang_detect_input":
            ctx.detected_source_lang = detected
            claimed = ctx.request.source_lang
            ctx.source_lang_mismatch = (
                None if claimed is None else (detected != claimed)
            )
        elif activity.name == "lang_detect_output":
            ctx.detected_output_lang = detected
            ctx.output_lang_mismatch = detected != ctx.request.target_lang
```

- [ ] **Step 9.4: Update `_build_result` to include agentic fields**

Find the `_build_result` method on `TranslationPipeline`. Add agentic field passes to the PipelineResult construction:

```python
        return PipelineResult(
            translation=ctx.translation_result.translation,
            source_lang=resolved_source,
            target_lang=ctx.request.target_lang,
            cached=False,
            provider=ctx.translation_result.provider,
            model=ctx.translation_result.model,
            latency_ms=total_latency_ms,
            cost_usd=Decimal(ctx.translation_result.cost_usd),
            glossary_compliance=ctx.compliance_score,
            metadata={
                "trace_id": ctx.trace_id,
                "profile_version": ctx.resolved_profile.version,
                "resolution_chain": ctx.resolved_profile.resolution_chain,
                "tokens_input": ctx.translation_result.tokens_input,
                "tokens_output": ctx.translation_result.tokens_output,
                "glossary_violations": len(ctx.compliance_violations),
                "stop_reason": ctx.translation_result.metadata.get("stop_reason"),
            },
            prompt_applied=ctx.rendered_prompt or None,
            agentic_activities=list(ctx.agentic_activities),
            detected_source_lang=ctx.detected_source_lang,
            detected_output_lang=ctx.detected_output_lang,
            source_lang_mismatch=ctx.source_lang_mismatch,
            output_lang_mismatch=ctx.output_lang_mismatch,
        )
```

- [ ] **Step 9.5: Update `_build_log_payload` to populate forward columns and JSONB**

In `src/pipeline/stages.py`, find `_build_log_payload`. Update the construction to also pass detected_* and mismatch fields plus agentic_activities serialized:

```python
    return TranslationLogCreate(
        ...existing fields...
        detected_source_lang=ctx.detected_source_lang,
        detected_output_lang=ctx.detected_output_lang,
        source_lang_mismatch=ctx.source_lang_mismatch,
        output_lang_mismatch=ctx.output_lang_mismatch,
        agentic_activities=(
            [act.model_dump(mode="json") for act in ctx.agentic_activities]
            if ctx.agentic_activities
            else None
        ),
    )
```

(The detected_source_lang, detected_output_lang, source_lang_mismatch, output_lang_mismatch already exist as columns from sub-proyek B — finally populated.)

- [ ] **Step 9.6: Run unit tests for pipeline**

```bash
uv run pytest tests/pipeline/ -v
```

Expected: existing pipeline tests need updating for the new constructor signature (haiku_provider + haiku_model_id). Integration tests will be written in Task 10.

You may need to update `tests/pipeline/test_pipeline_logging.py` and `tests/pipeline/test_pipeline_batch_logging.py` `_make_pipeline` helpers to construct the second provider. Add a `haiku_provider = MagicMock()` with `provider.translate = AsyncMock(return_value=TranslationResult(translation="en", ...))` and pass `haiku_provider=haiku_provider, haiku_model_id="claude-haiku-4-5"` to the constructor.

- [ ] **Step 9.7: Run full suite**

```bash
uv run pytest tests/ -x -q
```

Expected: 202+ passing (helpers updated, no regression).

---

# Task 10: Integration tests for full agent pipeline

**Files:**
- Create: `tests/pipeline/test_pipeline_agents.py`

- [ ] **Step 10.1: Write integration tests**

Create `tests/pipeline/test_pipeline_agents.py`:

```python
"""Integration tests: full pipeline with 3 agents through real Postgres
+ fakeredis + mocked Anthropic providers.
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
            tone="professional formal",
            target_audience="corporate clients, compliance officers, legal/HR teams",
        ),
    )
    await session.flush()
    return tenant.id, "general"


def _make_haiku_provider(detected_lang: str = "en") -> MagicMock:
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation=detected_lang,
            provider="claude",
            model="claude-haiku-4-5-20251001",
            tokens_input=50,
            tokens_output=12,
            cost_usd=Decimal("0.00006"),
            latency_ms=400.0,
            metadata={"stop_reason": "end_turn"},
        )
    )
    return provider


def _make_sonnet_provider(translation: str = "halo dunia") -> MagicMock:
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation=translation,
            provider="claude",
            model="claude-sonnet-4-6",
            tokens_input=312,
            tokens_output=87,
            cost_usd=Decimal("0.00132"),
            latency_ms=1840.0,
            metadata={"stop_reason": "end_turn"},
        )
    )
    return provider


def _make_pipeline(
    session: AsyncSession,
    *,
    sonnet: MagicMock,
    haiku: MagicMock,
) -> TranslationPipeline:
    cache = RedisCache(client=fakeredis.aioredis.FakeRedis(decode_responses=False))
    profile_repo = ProfileRepository(session)
    resolver = ProfileResolver(profile_repo)
    log_repo = TranslationLogRepository(session)
    return TranslationPipeline(
        provider=sonnet,
        haiku_provider=haiku,
        cache=cache,
        resolver=resolver,
        template_env=build_template_env(),
        model_id="claude-sonnet-4-6",
        haiku_model_id="claude-haiku-4-5-20251001",
        log_repo=log_repo,
    )


async def test_pipeline_runs_3_agents_in_2_groups(db_session: AsyncSession) -> None:
    tenant_id, slug = await _seed(db_session)
    pipeline = _make_pipeline(
        db_session,
        sonnet=_make_sonnet_provider("halo dunia"),
        haiku=_make_haiku_provider("en"),  # both detects return 'en'
    )

    result = await pipeline.translate(
        PipelineRequest(
            text="hello world",
            target_lang="id",
            profile_slug=slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    assert len(result.agentic_activities) == 3
    group_indices = sorted([a.group_index for a in result.agentic_activities])
    assert group_indices == [1, 1, 2]
    names = sorted([a.name for a in result.agentic_activities])
    assert names == ["lang_detect_input", "lang_detect_output", "translate"]


async def test_pipeline_populates_mismatch_flags_true(db_session: AsyncSession) -> None:
    tenant_id, slug = await _seed(db_session)
    pipeline = _make_pipeline(
        db_session,
        sonnet=_make_sonnet_provider("halo dunia"),
        haiku=_make_haiku_provider("fr"),  # detects French — mismatch with claimed 'en'
    )

    result = await pipeline.translate(
        PipelineRequest(
            text="Bonjour",
            target_lang="id",
            profile_slug=slug,
            tenant_id=tenant_id,
            source_lang="en",  # claimed wrong
        )
    )

    assert result.detected_source_lang == "fr"
    assert result.source_lang_mismatch is True
    # output detect also returns 'fr', target_lang is 'id', so output mismatch True
    assert result.output_lang_mismatch is True


async def test_pipeline_populates_mismatch_flags_false_when_match(
    db_session: AsyncSession,
) -> None:
    tenant_id, slug = await _seed(db_session)
    pipeline = _make_pipeline(
        db_session,
        sonnet=_make_sonnet_provider("halo dunia"),
        haiku=_make_haiku_provider("en"),  # matches claimed 'en'
    )

    result = await pipeline.translate(
        PipelineRequest(
            text="hello",
            target_lang="en",  # same as detected output for this test
            profile_slug=slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    assert result.detected_source_lang == "en"
    assert result.source_lang_mismatch is False


async def test_pipeline_mismatch_none_when_detection_fails(
    db_session: AsyncSession,
) -> None:
    tenant_id, slug = await _seed(db_session)
    # Haiku provider raises — both lang detect agents fail
    haiku = MagicMock()
    haiku.translate = AsyncMock(side_effect=RateLimitError("rate limited"))
    pipeline = _make_pipeline(
        db_session,
        sonnet=_make_sonnet_provider("halo dunia"),
        haiku=haiku,
    )

    result = await pipeline.translate(
        PipelineRequest(
            text="hello",
            target_lang="id",
            profile_slug=slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    # Translate succeeded; both detects failed → mismatch fields are None.
    assert result.translation == "halo dunia"
    assert result.detected_source_lang is None
    assert result.source_lang_mismatch is None
    assert result.output_lang_mismatch is None
    # Activities still recorded with status='failed'.
    failed = [a for a in result.agentic_activities if a.status == "failed"]
    assert len(failed) == 2  # both lang detects


async def test_pipeline_cache_hit_preserves_agentic_activities(
    db_session: AsyncSession,
) -> None:
    tenant_id, slug = await _seed(db_session)
    pipeline = _make_pipeline(
        db_session,
        sonnet=_make_sonnet_provider("halo dunia"),
        haiku=_make_haiku_provider("en"),
    )

    request = PipelineRequest(
        text="hello world",
        target_lang="id",
        profile_slug=slug,
        tenant_id=tenant_id,
        source_lang="en",
    )
    first = await pipeline.translate(request)
    # Second call hits cache
    second = await pipeline.translate(request)

    assert second.cached is True
    # Cache hit replays the activities from the original call
    assert len(second.agentic_activities) == 3
    assert second.detected_source_lang == "en"


async def test_pipeline_log_row_has_agentic_activities_jsonb(
    db_session: AsyncSession,
) -> None:
    tenant_id, slug = await _seed(db_session)
    pipeline = _make_pipeline(
        db_session,
        sonnet=_make_sonnet_provider("halo dunia"),
        haiku=_make_haiku_provider("fr"),
    )

    result = await pipeline.translate(
        PipelineRequest(
            text="Bonjour",
            target_lang="id",
            profile_slug=slug,
            tenant_id=tenant_id,
            source_lang="en",
        )
    )

    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id == result.log_id)
    )
    saved = row.scalar_one()
    assert saved.detected_source_lang == "fr"
    assert saved.source_lang_mismatch is True
    assert saved.agentic_activities is not None
    assert len(saved.agentic_activities) == 3
```

- [ ] **Step 10.2: Run integration tests**

```bash
uv run pytest tests/pipeline/test_pipeline_agents.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 10.3: Run full suite**

```bash
uv run pytest tests/ -x -q
```

Expected: ~213 passed (202 prior + 11 new — 4 schema + 3 lang_detect + 2 translate + 2 orchestrator + 6 integration). Numbers may shift slightly if older tests' helpers need updating.

---

# Task 11: API surface + tests

**Files:**
- Modify: `src/api/schemas.py` (TranslateResponse + BatchTranslateResultItem)
- Modify: `src/api/routes/translate.py` (_to_response + batch _one)
- Create: `tests/api/test_agentic_response.py`

- [ ] **Step 11.1: Add fields to API response schemas**

In `src/api/schemas.py`, find `TranslateResponse`. After `prompt_applied`, add:

```python
    agentic_activities: list[dict[str, Any]] = []
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
```

Same fields on `BatchTranslateResultItem`:

```python
    agentic_activities: list[dict[str, Any]] = []
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
```

Using `list[dict[str, Any]]` rather than `list[AgenticActivity]` at the API layer for consistency with how the field will serialize over HTTP. The values pass through unchanged from `PipelineResult.agentic_activities` (which uses the typed schema internally).

- [ ] **Step 11.2: Update `_to_response` in routes/translate.py**

Find `_to_response`. Update construction to pass new fields. The PipelineResult side has `agentic_activities: list[AgenticActivity]`; converting to list of dicts for HTTP:

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
        prompt_applied=result.prompt_applied,
        agentic_activities=[a.model_dump(mode="json") for a in result.agentic_activities],
        detected_source_lang=result.detected_source_lang,
        detected_output_lang=result.detected_output_lang,
        source_lang_mismatch=result.source_lang_mismatch,
        output_lang_mismatch=result.output_lang_mismatch,
    )
```

Update the batch `_one` similarly to include these fields in `BatchTranslateResultItem`.

- [ ] **Step 11.3: Write API tests**

Create `tests/api/test_agentic_response.py`:

```python
"""API tests for sub-proyek G+C: agentic_activities and mismatch fields."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TranslationLog


async def test_translate_response_includes_agentic_activities(
    api_client: AsyncClient,
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
    assert "agentic_activities" in body
    activities = body["agentic_activities"]
    assert isinstance(activities, list)
    assert len(activities) == 3
    names = sorted([a["name"] for a in activities])
    assert names == ["lang_detect_input", "lang_detect_output", "translate"]


async def test_translate_response_includes_mismatch_fields(
    api_client: AsyncClient,
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
    body = response.json()
    # Fields present (values may be None or bool)
    assert "detected_source_lang" in body
    assert "detected_output_lang" in body
    assert "source_lang_mismatch" in body
    assert "output_lang_mismatch" in body


async def test_translate_log_row_persists_agentic_activities(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await api_client.post(
        "/translate",
        json={
            "text": "Hello",
            "target_lang": "id",
            "profile_slug": "general",
            "source_lang": "en",
        },
    )
    body = response.json()
    log_id = uuid.UUID(body["log_id"])

    row = await db_session.execute(
        select(TranslationLog).where(TranslationLog.id == log_id)
    )
    saved = row.scalar_one()
    assert saved.agentic_activities is not None
    assert len(saved.agentic_activities) == 3


async def test_batch_response_each_item_has_agentic_activities(
    api_client: AsyncClient,
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
    for item in body["translations"]:
        assert "agentic_activities" in item
        assert len(item["agentic_activities"]) == 3
```

**Test fixture note:** `tests/api/conftest.py` already overrides `get_provider`. We need to ALSO override `get_haiku_provider` to use a mock. Update `tests/api/conftest.py` `api_client` fixture to add:

```python
    # Existing overrides...
    app.dependency_overrides[api_deps.get_provider] = _override_provider

    # NEW: override haiku provider too
    def _override_haiku_provider() -> TranslationProvider:
        # Return another mock — could share with sonnet for simplicity, but
        # separate makes intent clear.
        haiku = MagicMock()
        haiku.translate = AsyncMock(
            return_value=TranslationResult(
                translation="en",
                provider="claude",
                model="claude-haiku-4-5-20251001",
                tokens_input=50,
                tokens_output=12,
                cost_usd=Decimal("0.00006"),
                latency_ms=400.0,
                metadata={"stop_reason": "end_turn"},
            )
        )
        return haiku

    app.dependency_overrides[api_deps.get_haiku_provider] = _override_haiku_provider
```

(The fixture already imports `Decimal` and `TranslationResult` etc. — confirm + add if missing.)

- [ ] **Step 11.4: Run API tests**

```bash
uv run pytest tests/api/test_agentic_response.py -v
uv run pytest tests/ -x -q
```

Expected: 4 new tests pass; total ~217 passing.

---

# Task 12: Streamlit redesign — mismatch banner + agent flow viz

**Files:**
- Modify: `demo/app.py`

- [ ] **Step 12.1: Add helpers**

In `demo/app.py`, add at module level (after `LANGUAGE_OPTIONS` and the existing helpers):

```python
def _render_mismatch_banner(result: dict) -> None:
    """Show a red banner above the translation when source/output lang detection
    disagrees with what the user claimed."""
    msgs: list[str] = []
    if result.get("source_lang_mismatch"):
        detected = result.get("detected_source_lang", "?")
        claimed = result.get("source_lang", "?")
        msgs.append(f"Source: detected '{detected}' but you claimed '{claimed}'")
    if result.get("output_lang_mismatch"):
        detected_out = result.get("detected_output_lang", "?")
        target = result.get("target_lang", "?")
        msgs.append(f"Output: detected '{detected_out}' but target was '{target}'")
    if msgs:
        st.error("⚠ Language mismatch — " + " | ".join(msgs))


def _render_agent_box(act: dict) -> None:
    """Render one agent activity as a colored box with metrics."""
    color = "#e3f2fd" if act["agent_type"] == "language_detection" else "#e8f5e9"
    border_color = "#1976d2" if act["agent_type"] == "language_detection" else "#388e3c"
    cost = f"${act['cost_usd']}" if act.get("cost_usd") else "—"
    if act.get("input_tokens") is not None:
        tokens = f"{act['input_tokens']}→{act.get('output_tokens', '?')} tok"
    else:
        tokens = "—"
    result_preview = ""
    if act.get("result"):
        if "detected_lang" in act["result"]:
            result_preview = f"→ {act['result']['detected_lang']}"
        elif "translation" in act["result"]:
            trunc = act["result"]["translation"][:40]
            result_preview = f"→ \"{trunc}…\""
    status_icon = "✓" if act["status"] == "success" else "✗"
    st.markdown(
        f"""<div style="background:{color};border-left:4px solid {border_color};
            border-radius:6px;padding:10px;margin-bottom:8px;font-size:13px">
        <strong>{status_icon} {act['name']}</strong><br>
        <span style="color:#666;font-size:12px">{act.get('model_id') or 'non-LLM'}</span><br>
        <span style="font-size:12px">{tokens} · {cost} · {act['latency_ms']:.0f}ms</span><br>
        <span style="font-size:12px;color:#1976d2">{result_preview}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_agent_flow(activities: list[dict]) -> None:
    """Render the agent flow: one row per group_index, columns within each row."""
    if not activities:
        return
    st.markdown("### 🤖 Agent flow")
    groups: dict[int, list[dict]] = {}
    for act in activities:
        groups.setdefault(act["group_index"], []).append(act)
    for gid in sorted(groups):
        suffix = " (parallel)" if len(groups[gid]) > 1 else ""
        st.caption(f"Group {gid}{suffix}")
        cols = st.columns(len(groups[gid]))
        for col, act in zip(cols, groups[gid], strict=False):
            with col:
                _render_agent_box(act)
```

- [ ] **Step 12.2: Wire helpers into `render_translate_page`**

In `render_translate_page()`, find the section right after `result = response.json()` and before the `st.subheader("Translation")` line. Insert:

```python
        # ⚠ Mismatch banner FIRST (red, prominent)
        _render_mismatch_banner(result)

        # 🤖 Agent flow visualization above translation
        _render_agent_flow(result.get("agentic_activities", []))

        st.subheader("Translation")
        # ... existing translation display ...
```

The existing "Full metadata" expander remains unchanged — it shows the full response JSON including `agentic_activities` for developer-side debugging.

- [ ] **Step 12.3: Lint + verify Streamlit imports cleanly**

```bash
uv run ruff check demo/app.py
uv run python -c "import demo.app; print('OK')"
```

Expected: ruff clean (note: existing `tests/eval/test_metrics.py` unrelated issue persists — ignore), import OK.

---

# Task 13: ADR-031 / 032 / 033 in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 13.1: Append ADRs**

Find the "Decision log" section in CLAUDE.md. After the most recent ADR (ADR-030 from sub-proyek D), append:

```markdown
- ADR-031: Agent failures soft-fail by default — `LangDetectAgent`-style agents catch their own exceptions and emit `status="failed"` activities; only `TranslateAgent` (the primary value) propagates errors. Orchestrator's `_safe_run` captures translate exceptions along with sibling activities, then re-raises after the group completes so partial state lands in the log row. Extends graceful-degradation pattern from ADR-013 (cache) and ADR-027 (record_log) to the agentic layer.
- ADR-032: `AgenticActivity.result` typed as `dict[str, Any]` (JSONB-serialized), not typed per agent. Shape varies per agent type (lang_detect: `{detected_lang, confidence}`; translate: `{translation, stop_reason}`). Union with discriminator complicates Pydantic + JSONB serialization for low value; future agents extend without schema migration.
- ADR-033: Lang detection backend = Claude Haiku (LLM). Authentic agentic narrative for stakeholder demos; cost overhead negligible (~$0.0001/call vs. $0.001-0.005 main translate); reuses ClaudeProvider abstraction. Frontend langdetect (Streamlit typing-detection UX added with prompt_applied) retained at a different layer for a different purpose (proactive type-time vs. confirmatory post-request).
```

- [ ] **Step 13.2: Verify formatting**

Spot-check the surrounding ADRs to confirm consistent single-line markdown bullet format.

---

# Task 14: Final verification + bundled commit gate

This task is orchestrator-driven (controller, not implementer). All implementation tasks done — now we verify everything and prepare commit.

- [ ] **Step 14.1: Full verification**

```bash
uv run alembic current  # expect: 004_agentic_activities (head)
uv run pytest tests/ -x -q  # expect: ~217 passed
uv run ruff check scripts/ src/ tests/api/ tests/pipeline/ tests/scripts/ tests/translation_logs/  # expect: clean on our scope (existing tests/eval issue unrelated)
uv run mypy src/ scripts/seed_aitegrity_profiles.py  # expect: clean
git status --short  # confirm working tree state
```

- [ ] **Step 14.2: Surface commit recommendation to user**

The bundled commit covers EVERYTHING uncommitted since `e593c05`:

- Sub-proyek D: scripts/seed_aitegrity_profiles.py + 9 tests + 15 product profiles + ADR-030
- prompt_applied feature: migration 003 + PipelineResult.prompt_applied + Streamlit "Full metadata" exposure
- Sub-proyek G+C: agents package + migration 004 + Streamlit agent flow viz + ADR-031/032/033

Surface to user (controller does this — not the implementer):

```
## Bundled mega-commit recommendation

**Kalimat 1:**
> Sub-proyek D + G + C mega-bundle — seed 15 Aitegrity products (flat from `general`, ADR-030); add `prompt_applied` field to /translate response + `rendered_prompt` JSONB column (migration 003); introduce agent abstraction with `lang_detect_input`/`translate`/`lang_detect_output` in parallel groups, `agentic_activities` JSONB column (migration 004), mismatch flag computation, Streamlit horizontal-lanes flow viz + red mismatch banner (ADR-031/032/033).

**Kalimat 2:**
> ~26 new tests across schema sanity, agent unit, orchestrator, pipeline integration, and API surface; 217 total passing. Sub-proyek B forward columns finally populated by lang-detect agents.
```

User confirms, controller runs `git add` + `git commit` (no push).

---

## Open follow-ups (out of scope for this plan)

- `quality_check` agent (LLM critique of translation) — Group 2 parallel with lang_detect_output. Separate sub-proyek.
- `glossary_enforcer` agent — Group 3 sequential after translate. Separate sub-proyek.
- Sub-proyek F dashboard reading agentic_activities aggregations.
- Hybrid library/LLM lang detection escalation (cost optimization).
- Hard-fail policy override per agent (operator-controlled).
