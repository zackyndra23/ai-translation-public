# Tenant Junction Redesign + Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace sub-proyek H schema with a junction-style data model (country/company/department/position/service reference tables + tenant + tenant_profile junctions), move tone/audience/glossary to service, re-key tenant_prompts by prompt_id, and add MVP-grade auth (argon2 API key + lightweight JWT) on the tenant table.

**Architecture:** Single big migration 005-NEW drops sub-proyek H tables and creates the new schema. ORM + Pydantic schemas use custom `{prefix}-{8hex}-{4hex}` IDs (48 bits entropy). Auth middleware accepts Bearer JWT or X-Tenant-API-Key header. Streamlit form cascades Country → Company → Department → Position → Service → Glossary → Source → Target. 5 phases, single mega-commit at end.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, Streamlit, passlib[argon2], PyJWT.

**Commit policy:** Per user preference — single mega-commit at the end (no per-phase commits). **Never `git push`**.

**Spec reference:** `docs/superpowers/specs/2026-05-22-tenant-junction-redesign-design.md`

**Sub-proyek H is discarded.** Migrations 005-007 from H are preserved in git stash but deleted from disk; code from H lives only in stash. Bucket 1 UI fixes (Items 1-4) re-applied as the final task (Task 27).

---

## File Structure

**New top-level files:**

| Path | Responsibility |
|------|----------------|
| `alembic/versions/005_tenant_junction_redesign.py` | Drop sub-proyek H tables + create 9 new tables |
| `src/db/ids.py` | Custom ID generator (`make_id(prefix)` returns `{prefix}-{8hex}-{4hex}`) |
| `src/auth/__init__.py` | Package marker |
| `src/auth/hashing.py` | argon2 password hashing helpers (`hash_api_key`, `verify_api_key`) |
| `src/auth/jwt.py` | JWT encode/decode helpers using `jwt_secret` |
| `src/auth/middleware.py` | FastAPI auth middleware (Bearer JWT + X-Tenant-API-Key) |
| `src/auth/dependencies.py` | `get_current_tenant_id` FastAPI dependency |
| `src/country/{__init__,schemas,repository}.py` | Country reference table CRUD |
| `src/company/{__init__,schemas,repository}.py` | Company CRUD with country FK |
| `src/department/{__init__,schemas,repository}.py` | Department CRUD |
| `src/position/{__init__,schemas,repository}.py` | Position CRUD with department FK |
| `src/service/{__init__,schemas,repository}.py` | Service CRUD with tone/audience |
| `src/tenant/{__init__,schemas,repository}.py` | Tenant CRUD with auth columns |
| `src/tenant_profile/{__init__,schemas,repository,resolver}.py` | Tenant_profile junction + resolver (loads full ORM tree) |
| `src/api/routes/auth.py` | `POST /auth/refresh-jwt` endpoint |
| `src/api/routes/reference.py` | Public cascade endpoints (`/countries`, `/companies`, `/departments`, `/services`) |
| `scripts/seed_tenant_data.py` | Seed orchestrator (rewritten from scratch) |
| `tests/auth/`, `tests/country/`, `tests/company/`, `tests/department/`, `tests/position/`, `tests/service/`, `tests/tenant/`, `tests/tenant_profile/`, `tests/scripts/test_seed_tenant_data.py`, `tests/api/test_auth_routes.py`, `tests/api/test_reference_routes.py` | Test directories per package |

**Modified files:**

| Path | What changes |
|------|--------------|
| `src/db/models.py` | Delete old `Profile`, `Tenant`, `GlossaryTerm`, etc.; add new ORM classes for all 9 tables |
| `src/api/main.py` | Wire new routers (`auth`, `reference`); install auth middleware |
| `src/api/dependencies.py` | New repo factories; drop old `get_tenant_profile_repository` (replaced) |
| `src/api/routes/translate.py` | Use `get_current_tenant_id` dependency; request body adds `profile_id` |
| `src/pipeline/agents/translate.py` | Render template with new ORM (`tenant.company.company_name`, etc.) |
| `src/pipeline/pipeline.py` | Use new resolver returning tenant + tenant_profile joinedload |
| `src/config/settings.py` | Add `jwt_secret`, `api_key_master` |
| `src/translation_logs/repository.py` | Retype FK columns to VARCHAR(30); adjust ORM model |
| `demo/app.py` | Replace cascade UI to match Country→Company→Department→Position→Service flow + auth header |
| `CLAUDE.md` | Append ADR-039 through 046 |
| `pyproject.toml` | Add `passlib[argon2]` + `PyJWT` deps |

**Pre-existing files to DELETE (sub-proyek H artifacts stay in stash):**

| Path | Why deleted |
|------|-------------|
| `alembic/versions/005_rename_profile_to_tenant_profile.py` | Sub-proyek H migration |
| `alembic/versions/006_expand_tenant_and_tenant_profile.py` | Sub-proyek H migration |
| `alembic/versions/007_tenant_prompts_and_iso_languages.py` | Sub-proyek H migration |
| `src/tenant_profiles/` (entire dir) | Sub-proyek H package (was renamed from src/profiles/) |
| `src/tenant_prompts/` (entire dir) | Sub-proyek H package (kept conceptually but rebuilt) |
| `src/iso_languages/` (entire dir) | Sub-proyek H package (kept conceptually but rebuilt) |
| `src/api/routes/tenant_profiles.py` | Sub-proyek H route |
| `src/api/routes/tenants.py` | Sub-proyek H route |
| `src/api/routes/iso_languages.py` | Sub-proyek H route |
| `tests/tenant_profiles/`, `tests/tenant_prompts/`, `tests/iso_languages/` | Sub-proyek H tests |
| `docs/superpowers/specs/2026-05-21-tenant-profile-rename-and-expansion-design.md` | Sub-proyek H spec (preserved in git stash) |
| `docs/superpowers/plans/2026-05-21-tenant-profile-rename-and-expansion.md` | Sub-proyek H plan (preserved in git stash) |

Wait — those files don't exist on disk after `git stash` (they were untracked). Confirmed by `git status --short` showing clean tree. So actually nothing to delete from disk for sub-proyek H artifacts. The plan above lists them as reminder; implementer can skip the delete step.

The artifacts to delete are the **sub-proyek H ORM classes inside `src/db/models.py`** (still part of the committed `678adb0`). Phase I-1 ORM refactor will rip those out.

---

# PHASE I-1 — Pre-migration cleanup + Migration 005-NEW

Goal: get DB back to clean post-sub-proyek-G+C state, then apply the new junction schema.

## Task 1: Pre-migration DB cleanup

**Files:** none (operator-driven shell commands only).

- [ ] **Step 1.1: Verify clean working tree**

```bash
git status --short
git log --oneline -1
```

Expected: clean tree, HEAD = `678adb0`. If not clean, stash again.

- [ ] **Step 1.2: Downgrade DB to pre-sub-proyek-H state**

```bash
uv run alembic current
# Expected: 007_prompts_iso (head) — sub-proyek H DB state still present

uv run alembic downgrade 004_agentic_activities
uv run alembic current
# Expected: 004_agentic_activities (head)
```

If migrations 005-007 files don't exist on disk (because they were untracked + stashed), alembic downgrade may fail saying "Can't find revision 005_rename_to_tenant_profile". In that case, manually mark DB to 004:

```bash
# Manual rollback (drops sub-proyek H tables created in 005-007)
docker compose exec postgres psql -U aitrans -d aitrans_db -c "
  DROP TABLE IF EXISTS iso_languages CASCADE;
  DROP TABLE IF EXISTS tenant_prompts CASCADE;
  -- restore sub-proyek H rename: tenant_profiles → profiles
  ALTER TABLE tenant_profiles RENAME TO profiles;
  ALTER TABLE tenant_profile_versions RENAME TO profile_versions;
  ALTER TABLE glossary_terms RENAME COLUMN tenant_profile_id TO profile_id;
  ALTER TABLE style_examples RENAME COLUMN tenant_profile_id TO profile_id;
  ALTER TABLE profile_versions RENAME COLUMN tenant_profile_id TO profile_id;
  ALTER TABLE translation_logs RENAME COLUMN tenant_profile_id TO profile_id;
  ALTER TABLE translation_logs RENAME COLUMN tenant_profile_slug TO profile_slug;
  ALTER TABLE translation_logs RENAME COLUMN tenant_profile_version TO profile_version;
  -- drop sub-proyek H expansion columns
  ALTER TABLE profiles DROP COLUMN IF EXISTS role, DROP COLUMN IF EXISTS service, DROP COLUMN IF EXISTS allowed_languages;
  ALTER TABLE tenants DROP COLUMN IF EXISTS company, DROP COLUMN IF EXISTS department;
  -- mark alembic at 004
  UPDATE alembic_version SET version_num = '004_agentic_activities';
"
uv run alembic current
# Expected: 004_agentic_activities
```

If the manual SQL also fails (e.g., tables already in unknown state), fully reset:

```bash
docker compose down -v
docker compose up -d postgres redis
sleep 3
uv run alembic upgrade 004_agentic_activities
```

Reset is acceptable because no production data — dev DB only.

## Task 2: Add new dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 2.1: Add passlib[argon2] + PyJWT**

```bash
uv add 'passlib[argon2]>=1.7.4' 'PyJWT>=2.8.0'
```

Verify `pyproject.toml` shows new deps in `[project.dependencies]`. Run `uv sync` if needed.

## Task 3: Settings updates

**Files:**
- Modify: `src/config/settings.py`

- [ ] **Step 3.1: Add jwt_secret + api_key_master fields**

In `src/config/settings.py`, inside `Settings` class:

```python
    # --- Auth (sub-proyek I) ---
    jwt_secret: str = Field(
        default="dev-jwt-secret-replace-in-env-min-32-chars-please",
        min_length=16,
        description="HS256 signing secret. Replace via env var in production.",
    )
    api_key_master: str = Field(
        default="aitkey_master_dev",
        description="Admin / Streamlit master API key (dev only). Bypasses per-tenant auth.",
    )
```

## Task 4: Migration 005-NEW

**Files:**
- Create: `alembic/versions/005_tenant_junction_redesign.py`

- [ ] **Step 4.1: Create migration file**

```python
"""Tenant junction redesign — sub-proyek I.

Drops sub-proyek H tables, creates the new junction-style schema.

Revision ID: 005_tenant_junction
Revises: 004_agentic_activities
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "005_tenant_junction"
down_revision: str | None = "004_agentic_activities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Drop sub-proyek B / D / G+C tables (FK-children first) ──
    op.drop_table("translation_logs")
    op.drop_table("style_examples")
    op.drop_table("glossary_terms")
    op.drop_table("profile_versions")
    op.drop_table("profiles")
    op.drop_table("tenants")

    # ── 2. Reference tables ──
    op.create_table(
        "country",
        sa.Column("country_id", sa.String(30), primary_key=True),
        sa.Column("country_name", sa.String(60), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "company",
        sa.Column("company_id", sa.String(30), primary_key=True),
        sa.Column("company_name", sa.String(100), unique=True, nullable=False),
        sa.Column("company_country", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "department",
        sa.Column("department_id", sa.String(30), primary_key=True),
        sa.Column("department_name", sa.String(80), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "position",
        sa.Column("position_id", sa.String(30), primary_key=True),
        sa.Column("position_name", sa.String(120), nullable=False),
        sa.Column(
            "department_id",
            sa.String(30),
            sa.ForeignKey("department.department_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("position_name", "department_id", name="uq_position_name_department"),
    )
    op.create_table(
        "service",
        sa.Column("service_id", sa.String(30), primary_key=True),
        sa.Column("service_name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(100), nullable=True),
        sa.Column("tone", sa.String(255), nullable=True),
        sa.Column("target_audience", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "iso_languages",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("native_name", sa.String(100), nullable=True),
    )
    op.create_table(
        "tenant_prompts",
        sa.Column("prompt_id", sa.String(30), primary_key=True),
        sa.Column("agent_type", sa.String(40), unique=True, nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.String(255), server_default="system"),
        sa.CheckConstraint(
            "agent_type IN ('lang_detect_input','lang_detect_output','translate')",
            name="ck_tenant_prompts_agent_type",
        ),
    )

    # ── 3. Glossary + examples (FK to service) ──
    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "service_id",
            sa.String(30),
            sa.ForeignKey("service.service_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_term", sa.String(255), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=False),
        sa.Column("target_term", sa.String(255), nullable=False),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("is_forbidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_glossary_terms_service_langs",
        "glossary_terms",
        ["service_id", "source_lang", "target_lang"],
    )
    op.create_table(
        "style_examples",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "service_id",
            sa.String(30),
            sa.ForeignKey("service.service_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("tags", ARRAY(sa.String(255)), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_style_examples_service_langs",
        "style_examples",
        ["service_id", "source_lang", "target_lang"],
    )

    # ── 4. Tenant (junction + auth) ──
    op.create_table(
        "tenant",
        sa.Column("tenant_id", sa.String(30), primary_key=True),
        sa.Column("country_id", sa.String(30), sa.ForeignKey("country.country_id"), nullable=False),
        sa.Column("company_id", sa.String(30), sa.ForeignKey("company.company_id"), nullable=False),
        sa.Column("department_id", sa.String(30), sa.ForeignKey("department.department_id"), nullable=False),
        sa.Column("api_key_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("jwt_active_token", sa.Text(), nullable=True),
        sa.Column("jwt_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("country_id", "company_id", "department_id", name="uq_tenant_ccd"),
    )
    op.create_index("ix_tenant_api_key_hash", "tenant", ["api_key_hash"])

    # ── 5. Tenant profile (nested junction) ──
    op.create_table(
        "tenant_profile",
        sa.Column("profile_id", sa.String(30), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(30),
            sa.ForeignKey("tenant.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position_id", sa.String(30), sa.ForeignKey("position.position_id"), nullable=False),
        sa.Column("service_id", sa.String(30), sa.ForeignKey("service.service_id"), nullable=False),
        sa.Column("allowed_language", ARRAY(sa.String(8)), nullable=True),
        sa.Column("prompt_applied", ARRAY(sa.String(30)), nullable=False, server_default=sa.text("ARRAY[]::VARCHAR(30)[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "position_id", "service_id", name="uq_tenant_profile_tps"),
    )
    op.create_index("ix_tenant_profile_tenant_id", "tenant_profile", ["tenant_id"])

    # ── 6. Translation logs (recreated) ──
    op.create_table(
        "translation_logs",
        sa.Column("log_id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.String(30), sa.ForeignKey("tenant.tenant_id", ondelete="SET NULL"), nullable=True),
        sa.Column("profile_id", sa.String(30), sa.ForeignKey("tenant_profile.profile_id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=True),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detected_source_lang", sa.String(8), nullable=True),
        sa.Column("detected_output_lang", sa.String(8), nullable=True),
        sa.Column("source_lang_mismatch", sa.Boolean(), nullable=True),
        sa.Column("output_lang_mismatch", sa.Boolean(), nullable=True),
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
        sa.Column("agentic_activities", JSONB(), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cache_key", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("trace_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_index", sa.Integer(), nullable=True),
        sa.Column("request_metadata", JSONB(), nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_translation_logs_tenant_started",
        "translation_logs",
        ["tenant_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_translation_logs_failed",
        "translation_logs",
        [sa.text("started_at DESC")],
        postgresql_where=sa.text("status = 'failed'"),
    )


def downgrade() -> None:
    raise NotImplementedError("Sub-proyek I migration is irreversible by design.")
```

- [ ] **Step 4.2: Apply migration**

```bash
uv run alembic upgrade head
uv run alembic current
# Expected: 005_tenant_junction
```

- [ ] **Step 4.3: Verify schema**

```bash
docker compose exec postgres psql -U aitrans -d aitrans_db -c "\dt"
# Expected: country, company, department, position, service, glossary_terms, style_examples,
# tenant, tenant_profile, tenant_prompts, iso_languages, translation_logs, alembic_version
```

---

# PHASE I-2 — ORM models + ID generator + auth helpers

## Task 5: Custom ID generator helper

**Files:**
- Create: `src/db/ids.py`
- Test: `tests/db/test_ids.py`

- [ ] **Step 5.1: Write failing test**

Create `tests/db/__init__.py` (empty if not exists) and `tests/db/test_ids.py`:

```python
"""Tests for custom ID generator."""

from __future__ import annotations

import re

from src.db.ids import make_id

_ID_PATTERN = re.compile(r"^[a-z]+-[0-9a-f]{8}-[0-9a-f]{4}$")


def test_make_id_format_country() -> None:
    result = make_id("country")
    assert _ID_PATTERN.match(result)
    assert result.startswith("country-")


def test_make_id_unique_across_calls() -> None:
    ids = {make_id("tenant") for _ in range(1000)}
    assert len(ids) == 1000  # 1000 unique IDs, collision-safe


def test_make_id_length_within_30() -> None:
    for prefix in ("country", "company", "department", "position", "service", "tenant", "profile", "prompt"):
        result = make_id(prefix)
        assert len(result) <= 30, f"{result!r} exceeds VARCHAR(30)"


def test_make_id_rejects_empty_prefix() -> None:
    import pytest

    with pytest.raises(ValueError):
        make_id("")
```

Run: `uv run pytest tests/db/test_ids.py -v`. Expected: FAIL (module doesn't exist).

- [ ] **Step 5.2: Implement `make_id`**

Create `src/db/ids.py`:

```python
"""Custom ID generator: `{prefix}-{8hex}-{4hex}`.

Reads first 12 hex chars of a fresh UUID4 split 8+4. 48 bits entropy —
collision-safe for MVP scale (per ADR-040), more readable than full
UUID for log greps + admin operations.
"""

from __future__ import annotations

import uuid


def make_id(prefix: str) -> str:
    """Generate a new prefixed ID.

    Format: ``f"{prefix}-{8hex}-{4hex}"`` (e.g. ``"tenant-3f2504e0-4f89"``).
    Use whenever inserting a row into a table whose PK uses the custom format.
    """
    if not prefix:
        raise ValueError("ID prefix is required")
    hex_chars = uuid.uuid4().hex
    return f"{prefix}-{hex_chars[:8]}-{hex_chars[8:12]}"
```

Run: `uv run pytest tests/db/test_ids.py -v`. Expected: 4 pass.

## Task 6: Auth hashing helpers

**Files:**
- Create: `src/auth/__init__.py`, `src/auth/hashing.py`
- Test: `tests/auth/__init__.py`, `tests/auth/test_hashing.py`

- [ ] **Step 6.1: Write failing test**

`tests/auth/test_hashing.py`:

```python
"""Tests for argon2 API-key hashing."""

from __future__ import annotations

from src.auth.hashing import generate_api_key, hash_api_key, verify_api_key


def test_generate_api_key_format() -> None:
    key = generate_api_key()
    assert key.startswith("aitkey_")
    assert len(key) > 30  # base64-urlsafe 32 bytes is ~43 chars


def test_hash_and_verify_roundtrip() -> None:
    plaintext = "aitkey_abc123"
    hashed = hash_api_key(plaintext)
    assert hashed != plaintext  # not stored raw
    assert verify_api_key(plaintext, hashed) is True


def test_verify_rejects_wrong_key() -> None:
    hashed = hash_api_key("aitkey_correct")
    assert verify_api_key("aitkey_wrong", hashed) is False


def test_hash_is_argon2() -> None:
    hashed = hash_api_key("aitkey_test")
    assert hashed.startswith("$argon2")
```

Run: `uv run pytest tests/auth/test_hashing.py -v`. Expected: FAIL.

- [ ] **Step 6.2: Implement hashing**

Create `src/auth/__init__.py`:
```python
"""Auth utilities (sub-proyek I)."""
```

Create `src/auth/hashing.py`:

```python
"""argon2 hashing for tenant API keys.

argon2 chosen per ADR-045 for resistance to GPU/ASIC attacks. The plaintext
key is generated once at tenant creation and returned to the operator;
only the hash is persisted.
"""

from __future__ import annotations

import secrets

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def generate_api_key() -> str:
    """Generate a new plaintext API key for a tenant.

    Format: ``aitkey_<urlsafe-base64 of 32 bytes>``. Returned ONCE; not stored
    in plaintext anywhere — only the argon2 hash via :func:`hash_api_key`.
    """
    return f"aitkey_{secrets.token_urlsafe(32)}"


def hash_api_key(plaintext: str) -> str:
    """Return an argon2 hash of the plaintext API key."""
    return _pwd_context.hash(plaintext)


def verify_api_key(plaintext: str, hashed: str) -> bool:
    """Constant-time-ish verify (argon2's own bcrypt-compare semantics)."""
    return _pwd_context.verify(plaintext, hashed)
```

Run: `uv run pytest tests/auth/test_hashing.py -v`. Expected: 4 pass.

## Task 7: JWT helpers

**Files:**
- Create: `src/auth/jwt.py`
- Test: `tests/auth/test_jwt.py`

- [ ] **Step 7.1: Write failing test**

```python
"""Tests for JWT encode/decode."""

from __future__ import annotations

import time

import pytest

from src.auth.jwt import decode_jwt, encode_jwt


def test_encode_decode_roundtrip() -> None:
    token = encode_jwt(tenant_id="tenant-abc12345-6789", secret="test-secret-min-16-chars")
    payload = decode_jwt(token, secret="test-secret-min-16-chars")
    assert payload["sub"] == "tenant-abc12345-6789"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_rejects_tampered_signature() -> None:
    token = encode_jwt(tenant_id="t1", secret="test-secret-min-16-chars")
    tampered = token[:-3] + "XYZ"  # mess with signature
    with pytest.raises(ValueError, match="Invalid JWT"):
        decode_jwt(tampered, secret="test-secret-min-16-chars")


def test_decode_rejects_wrong_secret() -> None:
    token = encode_jwt(tenant_id="t1", secret="secret-A-min-16-chars-long")
    with pytest.raises(ValueError, match="Invalid JWT"):
        decode_jwt(token, secret="secret-B-min-16-chars-long")
```

Run: `uv run pytest tests/auth/test_jwt.py -v`. Expected: FAIL.

- [ ] **Step 7.2: Implement JWT module**

`src/auth/jwt.py`:

```python
"""JWT encode/decode using HS256 (per ADR-046).

Lightweight — we store the active JWT per tenant in
``tenant.jwt_active_token``. A token failing decode here OR not matching
the tenant's active token (string equality, checked by middleware) is
rejected. Daily refresh is operator-driven via ``POST /auth/refresh-jwt``.
"""

from __future__ import annotations

import time
from typing import Any

import jwt as pyjwt

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h


def encode_jwt(*, tenant_id: str, secret: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Issue a new JWT for a tenant.

    Payload: ``{sub: tenant_id, iat: <unix>, exp: <unix + ttl>}``. HS256.
    """
    now = int(time.time())
    payload = {"sub": tenant_id, "iat": now, "exp": now + ttl_seconds}
    return pyjwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, *, secret: str) -> dict[str, Any]:
    """Decode + verify a JWT. Raises ValueError on any failure."""
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.PyJWTError as e:
        raise ValueError(f"Invalid JWT: {e}") from e
```

Run: `uv run pytest tests/auth/test_jwt.py -v`. Expected: 3 pass.

## Task 8: ORM models — replace src/db/models.py

**Files:**
- Modify: `src/db/models.py` (complete rewrite)

- [ ] **Step 8.1: Replace `src/db/models.py` entirely**

The file is currently dominated by sub-proyek B/D/G+C classes. Replace with the new schema. Read the existing file first; preserve any `Base = declarative_base()` import / setup pattern.

```python
"""ORM models for sub-proyek I.

All custom IDs use the ``{prefix}-{8hex}-{4hex}`` format generated by
:func:`src.db.ids.make_id`. The ORM doesn't auto-generate IDs — repositories
call ``make_id()`` and pass the value to the constructor.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


class Country(Base):
    __tablename__ = "country"

    country_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    country_name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    company_country: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Department(Base):
    __tablename__ = "department"

    department_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    department_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    positions: Mapped[list["Position"]] = relationship(back_populates="department", cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "position"
    __table_args__ = (
        UniqueConstraint("position_name", "department_id", name="uq_position_name_department"),
    )

    position_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    position_name: Mapped[str] = mapped_column(String(120), nullable=False)
    department_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("department.department_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    department: Mapped[Department] = relationship(back_populates="positions")


class Service(Base):
    __tablename__ = "service"

    service_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    glossary_terms: Mapped[list["GlossaryTerm"]] = relationship(back_populates="service", cascade="all, delete-orphan")
    style_examples: Mapped[list["StyleExample"]] = relationship(back_populates="service", cascade="all, delete-orphan")


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    __table_args__ = (
        Index("ix_glossary_terms_service_langs", "service_id", "source_lang", "target_lang"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    service_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("service.service_id", ondelete="CASCADE"), nullable=False
    )
    source_term: Mapped[str] = mapped_column(String(255), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_term: Mapped[str] = mapped_column(String(255), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_forbidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service: Mapped[Service] = relationship(back_populates="glossary_terms")


class StyleExample(Base):
    __tablename__ = "style_examples"
    __table_args__ = (
        Index("ix_style_examples_service_langs", "service_id", "source_lang", "target_lang"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    service_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("service.service_id", ondelete="CASCADE"), nullable=False
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(255)), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service: Mapped[Service] = relationship(back_populates="style_examples")


class Tenant(Base):
    __tablename__ = "tenant"
    __table_args__ = (
        UniqueConstraint("country_id", "company_id", "department_id", name="uq_tenant_ccd"),
        Index("ix_tenant_api_key_hash", "api_key_hash"),
    )

    tenant_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    country_id: Mapped[str] = mapped_column(String(30), ForeignKey("country.country_id"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(30), ForeignKey("company.company_id"), nullable=False)
    department_id: Mapped[str] = mapped_column(String(30), ForeignKey("department.department_id"), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    jwt_active_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    jwt_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    country: Mapped[Country] = relationship()
    company: Mapped[Company] = relationship()
    department: Mapped[Department] = relationship()
    profiles: Mapped[list["TenantProfile"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class TenantProfile(Base):
    __tablename__ = "tenant_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "position_id", "service_id", name="uq_tenant_profile_tps"),
        Index("ix_tenant_profile_tenant_id", "tenant_id"),
    )

    profile_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tenant.tenant_id", ondelete="CASCADE"), nullable=False
    )
    position_id: Mapped[str] = mapped_column(String(30), ForeignKey("position.position_id"), nullable=False)
    service_id: Mapped[str] = mapped_column(String(30), ForeignKey("service.service_id"), nullable=False)
    allowed_language: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)), nullable=True)
    prompt_applied: Mapped[list[str]] = mapped_column(ARRAY(String(30)), nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant: Mapped[Tenant] = relationship(back_populates="profiles")
    position: Mapped[Position] = relationship()
    service: Mapped[Service] = relationship()


class TenantPrompt(Base):
    __tablename__ = "tenant_prompts"
    __table_args__ = (
        CheckConstraint(
            "agent_type IN ('lang_detect_input','lang_detect_output','translate')",
            name="ck_tenant_prompts_agent_type",
        ),
    )

    prompt_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(255), server_default="system")


class IsoLanguage(Base):
    __tablename__ = "iso_languages"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    native_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class TranslationLog(Base):
    __tablename__ = "translation_logs"
    __table_args__ = (
        Index("ix_translation_logs_tenant_started", "tenant_id", "started_at"),
    )

    log_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("tenant.tenant_id", ondelete="SET NULL"), nullable=True
    )
    profile_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("tenant_profile.profile_id", ondelete="SET NULL"), nullable=True
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_source_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    detected_output_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_lang_mismatch: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    output_lang_mismatch: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    agentic_activities: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Any | None] = mapped_column(Numeric(12, 6), nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Any | None] = mapped_column(Numeric(10, 2), nullable=True)
    trace_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    batch_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    batch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 8.2: Verify models import**

```bash
uv run python -c "from src.db.models import Country, Company, Department, Position, Service, Tenant, TenantProfile, TenantPrompt, IsoLanguage, TranslationLog, GlossaryTerm, StyleExample; print('OK')"
```

Expected: `OK`. If errors, fix imports in model file or `src/db/session.py`.

## Task 9: Pydantic schemas per package

**Files:** Create 7 schema files (one per entity)

- [ ] **Step 9.1: Create per-entity schemas**

For each entity (country, company, department, position, service, tenant, tenant_profile), create the package + schemas file. Example for country:

Create `src/country/__init__.py`:
```python
"""Country reference table (sub-proyek I)."""
```

Create `src/country/schemas.py`:
```python
"""Pydantic schemas for country."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CountryCreate(BaseModel):
    country_name: str


class CountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    country_id: str
    country_name: str
    created_at: datetime
```

Apply same pattern for the other 6 entities. Specific shapes:

**`src/company/schemas.py`**:
```python
class CompanyCreate(BaseModel):
    company_name: str
    company_country: str

class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    company_id: str
    company_name: str
    company_country: str
    created_at: datetime
```

**`src/department/schemas.py`**:
```python
class DepartmentCreate(BaseModel):
    department_name: str

class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    department_id: str
    department_name: str
    created_at: datetime
```

**`src/position/schemas.py`**:
```python
class PositionCreate(BaseModel):
    position_name: str
    department_id: str

class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    position_id: str
    position_name: str
    department_id: str
    created_at: datetime
```

**`src/service/schemas.py`**:
```python
class ServiceCreate(BaseModel):
    service_name: str
    description: str | None = None
    domain: str | None = None
    tone: str | None = None
    target_audience: str | None = None

class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    service_id: str
    service_name: str
    description: str | None
    domain: str | None
    tone: str | None
    target_audience: str | None
    created_at: datetime
```

**`src/tenant/schemas.py`** (note: NEVER include api_key_hash or jwt_active_token in Read schema returned to clients):
```python
class TenantCreate(BaseModel):
    country_id: str
    company_id: str
    department_id: str

class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: str
    country_id: str
    company_id: str
    department_id: str
    created_at: datetime

class TenantCreatedResponse(TenantRead):
    """Includes plaintext API key — returned ONCE on creation."""
    api_key_plaintext: str
```

**`src/tenant_profile/schemas.py`**:
```python
class TenantProfileCreate(BaseModel):
    tenant_id: str
    position_id: str
    service_id: str
    allowed_language: list[str] | None = None
    prompt_applied: list[str] = []

class TenantProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    profile_id: str
    tenant_id: str
    position_id: str
    service_id: str
    allowed_language: list[str] | None
    prompt_applied: list[str]
    created_at: datetime
```

- [ ] **Step 9.2: Confirm imports**

```bash
uv run python -c "
from src.country.schemas import CountryCreate, CountryRead
from src.company.schemas import CompanyCreate, CompanyRead
from src.department.schemas import DepartmentCreate, DepartmentRead
from src.position.schemas import PositionCreate, PositionRead
from src.service.schemas import ServiceCreate, ServiceRead
from src.tenant.schemas import TenantCreate, TenantRead, TenantCreatedResponse
from src.tenant_profile.schemas import TenantProfileCreate, TenantProfileRead
print('OK')
"
```

---

# PHASE I-3 — Repositories + endpoints + auth middleware

## Task 10: Reference table repositories

**Files:** Create 5 repository files

- [ ] **Step 10.1: Country repository**

`src/country/repository.py`:

```python
"""CountryRepository — minimal CRUD for the country reference table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.country.schemas import CountryCreate, CountryRead
from src.db.ids import make_id
from src.db.models import Country


class CountryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[CountryRead]:
        result = await self._session.execute(select(Country).order_by(Country.country_name))
        return [CountryRead.model_validate(c) for c in result.scalars().all()]

    async def get_by_id(self, country_id: str) -> CountryRead | None:
        row = await self._session.get(Country, country_id)
        return CountryRead.model_validate(row) if row else None

    async def get_by_name(self, country_name: str) -> CountryRead | None:
        result = await self._session.execute(
            select(Country).where(Country.country_name == country_name)
        )
        row = result.scalar_one_or_none()
        return CountryRead.model_validate(row) if row else None

    async def create(self, payload: CountryCreate) -> CountryRead:
        row = Country(country_id=make_id("country"), country_name=payload.country_name)
        self._session.add(row)
        await self._session.flush()
        return CountryRead.model_validate(row)
```

- [ ] **Step 10.2: Company repository**

`src/company/repository.py`:

```python
"""CompanyRepository — CRUD + filter by country."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.company.schemas import CompanyCreate, CompanyRead
from src.db.ids import make_id
from src.db.models import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[CompanyRead]:
        result = await self._session.execute(select(Company).order_by(Company.company_name))
        return [CompanyRead.model_validate(c) for c in result.scalars().all()]

    async def list_by_country(self, country_name: str) -> list[CompanyRead]:
        result = await self._session.execute(
            select(Company)
            .where(Company.company_country == country_name)
            .order_by(Company.company_name)
        )
        return [CompanyRead.model_validate(c) for c in result.scalars().all()]

    async def get_by_id(self, company_id: str) -> CompanyRead | None:
        row = await self._session.get(Company, company_id)
        return CompanyRead.model_validate(row) if row else None

    async def create(self, payload: CompanyCreate) -> CompanyRead:
        row = Company(
            company_id=make_id("company"),
            company_name=payload.company_name,
            company_country=payload.company_country,
        )
        self._session.add(row)
        await self._session.flush()
        return CompanyRead.model_validate(row)
```

- [ ] **Step 10.3: Department repository**

`src/department/repository.py`:

```python
"""DepartmentRepository — CRUD for global department list."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import Department
from src.department.schemas import DepartmentCreate, DepartmentRead


class DepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[DepartmentRead]:
        result = await self._session.execute(select(Department).order_by(Department.department_name))
        return [DepartmentRead.model_validate(d) for d in result.scalars().all()]

    async def get_by_id(self, department_id: str) -> DepartmentRead | None:
        row = await self._session.get(Department, department_id)
        return DepartmentRead.model_validate(row) if row else None

    async def get_by_name(self, name: str) -> DepartmentRead | None:
        result = await self._session.execute(select(Department).where(Department.department_name == name))
        row = result.scalar_one_or_none()
        return DepartmentRead.model_validate(row) if row else None

    async def create(self, payload: DepartmentCreate) -> DepartmentRead:
        row = Department(department_id=make_id("department"), department_name=payload.department_name)
        self._session.add(row)
        await self._session.flush()
        return DepartmentRead.model_validate(row)
```

- [ ] **Step 10.4: Position repository**

`src/position/repository.py`:

```python
"""PositionRepository — CRUD + filter by department."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import Position
from src.position.schemas import PositionCreate, PositionRead


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_department(self, department_id: str) -> list[PositionRead]:
        result = await self._session.execute(
            select(Position)
            .where(Position.department_id == department_id)
            .order_by(Position.position_name)
        )
        return [PositionRead.model_validate(p) for p in result.scalars().all()]

    async def get_by_id(self, position_id: str) -> PositionRead | None:
        row = await self._session.get(Position, position_id)
        return PositionRead.model_validate(row) if row else None

    async def get_by_name_and_dept(self, name: str, department_id: str) -> PositionRead | None:
        result = await self._session.execute(
            select(Position).where(
                Position.position_name == name,
                Position.department_id == department_id,
            )
        )
        row = result.scalar_one_or_none()
        return PositionRead.model_validate(row) if row else None

    async def create(self, payload: PositionCreate) -> PositionRead:
        row = Position(
            position_id=make_id("position"),
            position_name=payload.position_name,
            department_id=payload.department_id,
        )
        self._session.add(row)
        await self._session.flush()
        return PositionRead.model_validate(row)
```

- [ ] **Step 10.5: Service repository**

`src/service/repository.py`:

```python
"""ServiceRepository — CRUD + glossary fetch."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import GlossaryTerm, Service, StyleExample
from src.service.schemas import ServiceCreate, ServiceRead


class ServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[ServiceRead]:
        result = await self._session.execute(select(Service).order_by(Service.service_name))
        return [ServiceRead.model_validate(s) for s in result.scalars().all()]

    async def get_by_id(self, service_id: str) -> ServiceRead | None:
        row = await self._session.get(Service, service_id)
        return ServiceRead.model_validate(row) if row else None

    async def get_by_name(self, name: str) -> ServiceRead | None:
        result = await self._session.execute(select(Service).where(Service.service_name == name))
        row = result.scalar_one_or_none()
        return ServiceRead.model_validate(row) if row else None

    async def list_glossary_for_service(
        self, service_id: str, source_lang: str, target_lang: str
    ) -> list[GlossaryTerm]:
        result = await self._session.execute(
            select(GlossaryTerm)
            .where(
                GlossaryTerm.service_id == service_id,
                GlossaryTerm.source_lang == source_lang,
                GlossaryTerm.target_lang == target_lang,
            )
            .order_by(GlossaryTerm.priority.desc())
        )
        return list(result.scalars().all())

    async def list_examples_for_service(
        self, service_id: str, source_lang: str, target_lang: str
    ) -> list[StyleExample]:
        result = await self._session.execute(
            select(StyleExample)
            .where(
                StyleExample.service_id == service_id,
                StyleExample.source_lang == source_lang,
                StyleExample.target_lang == target_lang,
            )
        )
        return list(result.scalars().all())

    async def create(self, payload: ServiceCreate) -> ServiceRead:
        row = Service(
            service_id=make_id("service"),
            service_name=payload.service_name,
            description=payload.description,
            domain=payload.domain,
            tone=payload.tone,
            target_audience=payload.target_audience,
        )
        self._session.add(row)
        await self._session.flush()
        return ServiceRead.model_validate(row)
```

## Task 11: Tenant repository (with auth integration)

**Files:** Create `src/tenant/repository.py`

- [ ] **Step 11.1: Implement**

```python
"""TenantRepository — CRUD + auth (argon2 hashing + JWT)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.hashing import generate_api_key, hash_api_key, verify_api_key
from src.db.ids import make_id
from src.db.models import Tenant
from src.tenant.schemas import TenantCreate, TenantCreatedResponse, TenantRead


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[TenantRead]:
        result = await self._session.execute(select(Tenant))
        return [TenantRead.model_validate(t) for t in result.scalars().all()]

    async def get_by_id(self, tenant_id: str) -> TenantRead | None:
        row = await self._session.get(Tenant, tenant_id)
        return TenantRead.model_validate(row) if row else None

    async def resolve_by_ccd(
        self, country_id: str, company_id: str, department_id: str
    ) -> TenantRead | None:
        """Look up tenant by (country, company, department) composite key."""
        result = await self._session.execute(
            select(Tenant).where(
                Tenant.country_id == country_id,
                Tenant.company_id == company_id,
                Tenant.department_id == department_id,
            )
        )
        row = result.scalar_one_or_none()
        return TenantRead.model_validate(row) if row else None

    async def create(self, payload: TenantCreate) -> TenantCreatedResponse:
        plaintext_key = generate_api_key()
        row = Tenant(
            tenant_id=make_id("tenant"),
            country_id=payload.country_id,
            company_id=payload.company_id,
            department_id=payload.department_id,
            api_key_hash=hash_api_key(plaintext_key),
        )
        self._session.add(row)
        await self._session.flush()
        return TenantCreatedResponse(
            **TenantRead.model_validate(row).model_dump(),
            api_key_plaintext=plaintext_key,
        )

    async def verify_api_key(self, plaintext: str) -> str | None:
        """Find the tenant whose api_key_hash matches plaintext. Returns tenant_id or None.

        Iterates candidate tenants and bcrypt-verifies. For 57 rows this is
        acceptable; future scale optimization via key-prefix indexing
        (per ADR-045) is deferred.
        """
        result = await self._session.execute(select(Tenant))
        for tenant in result.scalars().all():
            if verify_api_key(plaintext, tenant.api_key_hash):
                return tenant.tenant_id
        return None

    async def set_active_jwt(self, tenant_id: str, jwt_token: str) -> None:
        row = await self._session.get(Tenant, tenant_id)
        if row is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        row.jwt_active_token = jwt_token
        row.jwt_refreshed_at = datetime.now(UTC)
        await self._session.flush()

    async def get_active_jwt(self, tenant_id: str) -> str | None:
        row = await self._session.get(Tenant, tenant_id)
        return row.jwt_active_token if row else None
```

## Task 12: Tenant_profile repository + resolver

**Files:** Create `src/tenant_profile/repository.py` and `src/tenant_profile/resolver.py`

- [ ] **Step 12.1: Repository**

```python
"""TenantProfileRepository — CRUD + joinedload resolver."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.db.ids import make_id
from src.db.models import TenantProfile
from src.tenant_profile.schemas import TenantProfileCreate, TenantProfileRead


class TenantProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_tenant(
        self, tenant_id: str, position_id: str | None = None
    ) -> list[TenantProfileRead]:
        query = select(TenantProfile).where(TenantProfile.tenant_id == tenant_id)
        if position_id:
            query = query.where(TenantProfile.position_id == position_id)
        result = await self._session.execute(query)
        return [TenantProfileRead.model_validate(p) for p in result.scalars().all()]

    async def get_by_id(self, profile_id: str) -> TenantProfileRead | None:
        row = await self._session.get(TenantProfile, profile_id)
        return TenantProfileRead.model_validate(row) if row else None

    async def create(self, payload: TenantProfileCreate) -> TenantProfileRead:
        row = TenantProfile(
            profile_id=make_id("profile"),
            tenant_id=payload.tenant_id,
            position_id=payload.position_id,
            service_id=payload.service_id,
            allowed_language=payload.allowed_language,
            prompt_applied=payload.prompt_applied or [],
        )
        self._session.add(row)
        await self._session.flush()
        return TenantProfileRead.model_validate(row)

    async def load_with_relations(self, profile_id: str) -> TenantProfile | None:
        """Return ORM with joined tenant + tenant.country/company/department + position + service.

        Used by the pipeline resolver to render the translate template with
        ``{{ tenant.company.company_name }}`` etc.
        """
        result = await self._session.execute(
            select(TenantProfile)
            .options(
                joinedload(TenantProfile.tenant).joinedload("country"),
                joinedload(TenantProfile.tenant).joinedload("company"),
                joinedload(TenantProfile.tenant).joinedload("department"),
                joinedload(TenantProfile.position),
                joinedload(TenantProfile.service),
            )
            .where(TenantProfile.profile_id == profile_id)
        )
        return result.unique().scalar_one_or_none()
```

- [ ] **Step 12.2: Resolver helper**

`src/tenant_profile/resolver.py`:

```python
"""Pipeline resolver — load tenant_profile + relations for template rendering."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TenantProfile
from src.tenant_profile.repository import TenantProfileRepository


class TenantProfileNotFound(Exception):
    pass


class TenantProfileResolver:
    """Loads the full tenant + tenant_profile tree for pipeline use."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TenantProfileRepository(session)

    async def resolve(self, profile_id: str) -> TenantProfile:
        row = await self._repo.load_with_relations(profile_id)
        if row is None:
            raise TenantProfileNotFound(f"tenant_profile {profile_id!r} not found")
        return row
```

## Task 13: Auth middleware

**Files:**
- Create: `src/auth/middleware.py`, `src/auth/dependencies.py`

- [ ] **Step 13.1: Middleware**

```python
"""FastAPI auth middleware for sub-proyek I.

Two paths: Bearer JWT (cheap) or X-Tenant-API-Key (always valid until rotated).
Some endpoints are public (PUBLIC_PATHS) — those skip the check entirely.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.jwt import decode_jwt
from src.config.settings import get_settings
from src.tenant.repository import TenantRepository
from src.db.session import SessionLocal

# Paths that skip auth — used by Streamlit cascade pre-tenant-selection
PUBLIC_PATHS = {
    "/health",
    "/health/deep",
    "/countries",
    "/companies",
    "/departments",
    "/iso-languages",
    "/auth/refresh-jwt",  # uses API key only, handled inside the route
    "/openapi.json",
    "/docs",
    "/redoc",
}


def _is_public(path: str) -> bool:
    # Match exact path OR /{public_prefix}/ ... (e.g. /companies?country=X)
    if path in PUBLIC_PATHS:
        return True
    for p in PUBLIC_PATHS:
        if path.startswith(p + "/") or path.startswith(p + "?"):
            return True
    return False


class TenantAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        settings = get_settings()
        tenant_id = await self._extract_tenant_id(request, settings)
        if tenant_id is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error_code": "missing_credentials",
                    "detail": "Provide Bearer JWT or X-Tenant-API-Key header",
                    "trace_id": getattr(request.state, "trace_id", None),
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.tenant_id = tenant_id
        return await call_next(request)

    async def _extract_tenant_id(self, request: Request, settings) -> str | None:
        # 1. Try Bearer JWT
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            try:
                payload = decode_jwt(token, secret=settings.jwt_secret)
                # Cross-check that this token is the active one for the tenant
                async with SessionLocal() as session:
                    repo = TenantRepository(session)
                    active = await repo.get_active_jwt(payload["sub"])
                    if active and active == token:
                        return payload["sub"]
            except ValueError:
                pass

        # 2. Try API key header
        api_key = request.headers.get("x-tenant-api-key")
        if api_key:
            # Master key bypass (dev / admin)
            if api_key == settings.api_key_master:
                return "tenant-master"
            async with SessionLocal() as session:
                repo = TenantRepository(session)
                tenant_id = await repo.verify_api_key(api_key)
                if tenant_id:
                    return tenant_id

        return None


def install_auth_middleware(app: FastAPI) -> None:
    app.add_middleware(TenantAuthMiddleware)
```

- [ ] **Step 13.2: Dependency helper**

`src/auth/dependencies.py`:

```python
"""FastAPI dependency to expose the authenticated tenant_id."""

from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_current_tenant_id(request: Request) -> str:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth middleware did not set tenant_id",
        )
    return tenant_id
```

## Task 14: Auth route — refresh-jwt

**Files:**
- Create: `src/api/routes/auth.py`
- Test: `tests/api/test_auth_routes.py`

- [ ] **Step 14.1: Implement route**

```python
"""POST /auth/refresh-jwt — issues a new JWT for the API-key-authenticated tenant."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.auth.jwt import encode_jwt
from src.config.settings import get_settings
from src.tenant.repository import TenantRepository

router = APIRouter(tags=["auth"])


class JwtRefreshResponse(BaseModel):
    jwt_active_token: str
    tenant_id: str
    expires_in: int  # seconds


@router.post("/auth/refresh-jwt", response_model=JwtRefreshResponse)
async def refresh_jwt(
    db: AsyncSession = Depends(get_db),
    x_tenant_api_key: str | None = Header(default=None),
) -> JwtRefreshResponse:
    if not x_tenant_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide X-Tenant-API-Key header",
        )
    settings = get_settings()
    repo = TenantRepository(db)
    tenant_id = await repo.verify_api_key(x_tenant_api_key)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    token = encode_jwt(tenant_id=tenant_id, secret=settings.jwt_secret)
    await repo.set_active_jwt(tenant_id, token)
    return JwtRefreshResponse(
        jwt_active_token=token,
        tenant_id=tenant_id,
        expires_in=86_400,
    )
```

## Task 15: Reference + cascade routes

**Files:**
- Create: `src/api/routes/reference.py`

- [ ] **Step 15.1: Implement**

```python
"""Reference endpoints for the cascading Streamlit form (public)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.company.repository import CompanyRepository
from src.company.schemas import CompanyRead
from src.country.repository import CountryRepository
from src.country.schemas import CountryRead
from src.department.repository import DepartmentRepository
from src.department.schemas import DepartmentRead
from src.iso_languages.repository import IsoLanguageRepository
from src.iso_languages.schemas import IsoLanguageRead
from src.position.repository import PositionRepository
from src.position.schemas import PositionRead
from src.service.repository import ServiceRepository
from src.service.schemas import ServiceRead
from src.tenant.repository import TenantRepository
from src.tenant.schemas import TenantRead
from src.tenant_profile.repository import TenantProfileRepository
from src.tenant_profile.schemas import TenantProfileRead

router = APIRouter(tags=["reference"])


@router.get("/countries", response_model=list[CountryRead])
async def list_countries(db: AsyncSession = Depends(get_db)) -> list[CountryRead]:
    return await CountryRepository(db).list()


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    country: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyRead]:
    repo = CompanyRepository(db)
    return await repo.list_by_country(country) if country else await repo.list()


@router.get("/departments", response_model=list[DepartmentRead])
async def list_departments(db: AsyncSession = Depends(get_db)) -> list[DepartmentRead]:
    return await DepartmentRepository(db).list()


@router.get("/departments/{department_id}/positions", response_model=list[PositionRead])
async def list_positions_for_department(
    department_id: str, db: AsyncSession = Depends(get_db)
) -> list[PositionRead]:
    return await PositionRepository(db).list_by_department(department_id)


@router.get("/services", response_model=list[ServiceRead])
async def list_services(db: AsyncSession = Depends(get_db)) -> list[ServiceRead]:
    return await ServiceRepository(db).list()


@router.get("/iso-languages", response_model=list[IsoLanguageRead])
async def list_iso_languages(db: AsyncSession = Depends(get_db)) -> list[IsoLanguageRead]:
    return await IsoLanguageRepository(db).list()


@router.get("/tenants/by-ccd", response_model=TenantRead)
async def resolve_tenant(
    country_id: str = Query(...),
    company_id: str = Query(...),
    department_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    tenant = await TenantRepository(db).resolve_by_ccd(country_id, company_id, department_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tenant for ({country_id}, {company_id}, {department_id})",
        )
    return tenant


@router.get("/tenants/{tenant_id}/tenant-profiles", response_model=list[TenantProfileRead])
async def list_tenant_profiles(
    tenant_id: str,
    position_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[TenantProfileRead]:
    return await TenantProfileRepository(db).list_by_tenant(tenant_id, position_id)
```

- [ ] **Step 15.2: ISO languages repo (re-create from scratch)**

The sub-proyek H `src/iso_languages/` was in the stash. Recreate:

`src/iso_languages/__init__.py`:
```python
"""ISO 639 language catalog."""
```

`src/iso_languages/schemas.py`:
```python
"""Pydantic schemas for iso_languages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IsoLanguageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    native_name: str | None
```

`src/iso_languages/repository.py`:
```python
"""IsoLanguageRepository — module-level cache."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import IsoLanguage
from src.iso_languages.schemas import IsoLanguageRead

_catalog_cache: dict[str, IsoLanguageRead] = {}


def clear_catalog_cache() -> None:
    _catalog_cache.clear()


class IsoLanguageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[IsoLanguageRead]:
        if _catalog_cache:
            return list(_catalog_cache.values())
        result = await self._session.execute(select(IsoLanguage).order_by(IsoLanguage.name))
        rows = list(result.scalars().all())
        _catalog_cache.update({r.code: IsoLanguageRead.model_validate(r) for r in rows})
        return list(_catalog_cache.values())

    async def get_name(self, code: str) -> str | None:
        if not _catalog_cache:
            await self.list()
        entry = _catalog_cache.get(code)
        return entry.name if entry else None
```

## Task 16: Wire routers + middleware in main.py

**Files:**
- Modify: `src/api/main.py`

- [ ] **Step 16.1: Update main.py**

Read current `src/api/main.py`. Replace router includes for sub-proyek H routers with new ones:

```python
from src.api.routes.auth import router as auth_router
from src.api.routes.reference import router as reference_router
from src.api.routes.translate import router as translate_router
from src.api.routes.health import router as health_router
from src.auth.middleware import install_auth_middleware

# ... existing setup ...

install_auth_middleware(app)  # AFTER CORS + before routes

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(reference_router)
app.include_router(translate_router)
```

Remove any references to sub-proyek H routers (`tenants_router`, `iso_languages_router`, `tenant_profiles_router`) — they don't exist after Phase I-1 cleanup.

## Task 17: Translate route refactor

**Files:**
- Modify: `src/api/routes/translate.py`, `src/api/schemas.py`, `src/pipeline/schemas.py`

- [ ] **Step 17.1: Request body change — uses profile_id now**

In `src/api/schemas.py`:

```python
class TranslateRequest(BaseModel):
    text: str
    target_lang: str
    profile_id: str  # was tenant_profile_slug
    source_lang: str | None = None
    options: TranslationOptions | None = None
```

In `src/pipeline/schemas.py`:

```python
class PipelineRequest(BaseModel):
    text: str
    target_lang: str
    profile_id: str
    tenant_id: str  # comes from auth middleware
    source_lang: str | None = None
    options: TranslationOptions | None = None
    batch_id: uuid.UUID | None = None
    batch_index: int | None = None
    request_metadata: dict[str, Any] | None = None
```

- [ ] **Step 17.2: Route uses auth middleware tenant_id + body profile_id**

```python
from src.auth.dependencies import get_current_tenant_id

@router.post("", response_model=TranslateResponse)
async def translate(
    payload: TranslateRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    pipeline: TranslationPipeline = Depends(get_pipeline),
) -> TranslateResponse:
    request = _to_pipeline_request(
        tenant_id=tenant_id,
        text=payload.text,
        target_lang=payload.target_lang,
        profile_id=payload.profile_id,
        source_lang=payload.source_lang,
        options=payload.options,
    )
    result = await pipeline.translate(request)
    return _to_response(result)
```

Same change for `/translate/batch` route.

## Task 18: Pipeline + agent integration

**Files:**
- Modify: `src/pipeline/stages.py`, `src/pipeline/pipeline.py`, `src/pipeline/agents/translate.py`, `src/api/dependencies.py`

- [ ] **Step 18.1: Stage loads tenant_profile via resolver**

In `src/pipeline/stages.py`, the `load_resolved_profile` stage becomes:

```python
async def load_resolved_profile(ctx: PipelineContext, resolver: TenantProfileResolver) -> None:
    """Load the full tenant_profile tree (joinedload tenant + relations)."""
    ctx.resolved_tenant_profile = await resolver.resolve(ctx.request.profile_id)
```

`ctx.resolved_tenant_profile` is now a SQLAlchemy ORM object (with joined relations), not a Pydantic schema.

Glossary + examples are fetched per `ctx.resolved_tenant_profile.service_id`:

```python
async def select_glossary(ctx: PipelineContext, service_repo: ServiceRepository) -> None:
    ctx.selected_glossary = await service_repo.list_glossary_for_service(
        ctx.resolved_tenant_profile.service_id,
        ctx.request.source_lang or "auto",  # mapped by translate agent if AUTO
        ctx.request.target_lang,
    )
```

Adjust stages.py accordingly — preserve existing function signatures where possible.

- [ ] **Step 18.2: TranslateAgent renders with new ORM**

In `src/pipeline/agents/translate.py`, update the Jinja render context to use the new ORM attribute names:

```python
rendered_prompt = self._template.render(
    tenant=ctx.resolved_tenant_profile.tenant,
    tenant_profile=ctx.resolved_tenant_profile,
    source_lang=source_lang_code,
    source_lang_name=source_lang_name,
    target_lang=ctx.request.target_lang,
    target_lang_name=target_lang_name,
    glossary_terms=ctx.selected_glossary,
    examples=ctx.selected_examples,
    text=ctx.normalized_text,
)
```

- [ ] **Step 18.3: Dependencies factories**

In `src/api/dependencies.py`, replace sub-proyek H factory imports with new:

```python
async def get_tenant_profile_resolver(db: AsyncSession = Depends(get_db)) -> TenantProfileResolver:
    return TenantProfileResolver(db)


async def get_service_repository(db: AsyncSession = Depends(get_db)) -> ServiceRepository:
    return ServiceRepository(db)


# Adjust get_pipeline to inject the new resolvers + repos
async def get_pipeline(
    provider: TranslationProvider = Depends(get_provider),
    haiku_provider: TranslationProvider = Depends(get_haiku_provider),
    cache: CacheBackend = Depends(get_cache),
    resolver: TenantProfileResolver = Depends(get_tenant_profile_resolver),
    service_repo: ServiceRepository = Depends(get_service_repository),
    prompt_repo: TenantPromptRepository = Depends(get_prompt_repository),
    iso_repo: IsoLanguageRepository = Depends(get_iso_repository),
    log_repo: TranslationLogRepository = Depends(get_log_repository),
) -> TranslationPipeline:
    settings = get_settings()
    return TranslationPipeline(
        provider=provider,
        haiku_provider=haiku_provider,
        cache=cache,
        resolver=resolver,
        service_repo=service_repo,
        model_id=settings.anthropic_model,
        haiku_model_id=settings.anthropic_haiku_model,
        prompt_repo=prompt_repo,
        iso_repo=iso_repo,
        log_repo=log_repo,
    )
```

- [ ] **Step 18.4: Recreate tenant_prompts repo**

`src/tenant_prompts/__init__.py` + `src/tenant_prompts/repository.py` (with PK now `prompt_id`, `get(agent_type)` unchanged):

```python
"""TenantPromptRepository — re-keyed by prompt_id but get-by-agent-type."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TenantPrompt

AgentType = Literal["lang_detect_input", "lang_detect_output", "translate"]
_template_cache: dict[str, str] = {}


def clear_template_cache() -> None:
    _template_cache.clear()


class TenantPromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, agent_type: AgentType) -> str:
        if agent_type in _template_cache:
            return _template_cache[agent_type]
        result = await self._session.execute(
            select(TenantPrompt.template).where(TenantPrompt.agent_type == agent_type)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise RuntimeError(
                f"No tenant_prompts row for agent_type={agent_type!r}. "
                "Run scripts/seed_tenant_data.py."
            )
        _template_cache[agent_type] = template
        return template
```

---

# PHASE I-4 — Seed

## Task 19: ISO languages seed data

**Files:**
- Create: `src/iso_languages/seed_data.py`

- [ ] **Step 19.1: Copy curated list from sub-proyek H pattern**

```python
"""Static ISO 639-1 catalog (sub-proyek I).

40-entry starter — sufficient for current demo (covers all Streamlit dropdown languages).
Expansion to full ISO 639-1 (~180) is a follow-up.
"""

from __future__ import annotations

from typing import Final


class IsoLanguageEntry:
    __slots__ = ("code", "name", "native_name")

    def __init__(self, code: str, name: str, native_name: str | None = None) -> None:
        self.code = code
        self.name = name
        self.native_name = native_name


ISO_LANGUAGES: Final[list[IsoLanguageEntry]] = [
    IsoLanguageEntry("en", "English", "English"),
    IsoLanguageEntry("id", "Indonesian", "Bahasa Indonesia"),
    IsoLanguageEntry("ms", "Malay", "Bahasa Melayu"),
    IsoLanguageEntry("ja", "Japanese", "日本語"),
    IsoLanguageEntry("zh", "Chinese", "中文"),
    IsoLanguageEntry("ko", "Korean", "한국어"),
    IsoLanguageEntry("th", "Thai", "ไทย"),
    IsoLanguageEntry("vi", "Vietnamese", "Tiếng Việt"),
    IsoLanguageEntry("fr", "French", "Français"),
    IsoLanguageEntry("de", "German", "Deutsch"),
    IsoLanguageEntry("es", "Spanish", "Español"),
    IsoLanguageEntry("it", "Italian", "Italiano"),
    IsoLanguageEntry("pt", "Portuguese", "Português"),
    IsoLanguageEntry("nl", "Dutch", "Nederlands"),
    IsoLanguageEntry("ru", "Russian", "Русский"),
    IsoLanguageEntry("ar", "Arabic", "العربية"),
    IsoLanguageEntry("hi", "Hindi", "हिन्दी"),
    IsoLanguageEntry("tl", "Tagalog", "Tagalog"),
    IsoLanguageEntry("tr", "Turkish", "Türkçe"),
    IsoLanguageEntry("pl", "Polish", "Polski"),
    IsoLanguageEntry("uk", "Ukrainian", "Українська"),
    IsoLanguageEntry("ro", "Romanian", "Română"),
    IsoLanguageEntry("cs", "Czech", "Čeština"),
    IsoLanguageEntry("el", "Greek", "Ελληνικά"),
    IsoLanguageEntry("he", "Hebrew", "עברית"),
    IsoLanguageEntry("fa", "Persian", "فارسی"),
    IsoLanguageEntry("ur", "Urdu", "اردو"),
    IsoLanguageEntry("bn", "Bengali", "বাংলা"),
    IsoLanguageEntry("ta", "Tamil", "தமிழ்"),
    IsoLanguageEntry("te", "Telugu", "తెలుగు"),
    IsoLanguageEntry("sv", "Swedish", "Svenska"),
    IsoLanguageEntry("no", "Norwegian", "Norsk"),
    IsoLanguageEntry("da", "Danish", "Dansk"),
    IsoLanguageEntry("fi", "Finnish", "Suomi"),
    IsoLanguageEntry("hu", "Hungarian", "Magyar"),
    IsoLanguageEntry("bg", "Bulgarian", "Български"),
    IsoLanguageEntry("hr", "Croatian", "Hrvatski"),
    IsoLanguageEntry("sk", "Slovak", "Slovenčina"),
    IsoLanguageEntry("sl", "Slovenian", "Slovenščina"),
    IsoLanguageEntry("sw", "Swahili", "Kiswahili"),
]
```

## Task 20: Seed script

**Files:**
- Create: `scripts/seed_tenant_data.py`

- [ ] **Step 20.1: Author seed script**

Per spec §6, the seed has 10 ordered steps. Full content in spec section 6. Key constants:

```python
COMPANIES = [
    ("PT Integrity Indonesia", "Indonesia"),
    ("Jasa Integritas Malaysia Sdn. Bhd.", "Malaysia"),
    ("Integrity Thailand Ltd", "Thailand"),
]

COUNTRIES = ["Indonesia", "Malaysia", "Thailand", "Vietnam", "Germany", "France", "Switzerland"]

DEPARTMENTS = [
    "Accounting", "Brand Protection", "Brand Protection and Integrity Services",
    "Business Expansion & Marketing", "Design & Development",
    "Due Dilligence and Corporate Enquiries", "Employment Background Screening",
    "General Affairs", "Human Resources", "Information Technology",
    "Innovatech Solution", "Investigation", "Management", "Operations",
    "Quality", "Sales", "Sertifikasi Bio Data", "Surveillance", "Whistleblowing",
]

# 83 positions with their departments — full list from user feedback Item 4
POSITION_DEPARTMENT_PAIRS = [
    ("Accounting Supervisor", "Accounting"),
    ("Finance & Tax Officer", "Accounting"),
    ("AR Specialist", "Accounting"),
    ("Field Researcher", "Brand Protection"),
    ("Analyst", "Brand Protection and Integrity Services"),
    # ... 78 more (use the full list from spec §6 / user feedback Item 4)
]

# 16 services: general + 15 Aitegrity products
# Each with: service_name, description, domain, tone, target_audience
# Glossary + examples per service from sub-proyek D AITEGRITY_PRODUCTS (now FK to service)
```

The full position-department list, service catalog, and Aitegrity products glossaries — implementer copies them from spec §6 (lines 1-83 of user feedback) and from existing `scripts/seed_aitegrity_tenant_profiles.py` in git stash if needed.

Seed structure (each step idempotent skip-if-exists):

```python
async def seed_iso_languages(session: AsyncSession) -> int: ...
async def seed_countries(session: AsyncSession) -> dict[str, str]: ...  # name → country_id
async def seed_companies(session: AsyncSession, country_ids: dict) -> dict[str, str]: ...
async def seed_departments(session: AsyncSession) -> dict[str, str]: ...
async def seed_positions(session: AsyncSession, dept_ids: dict) -> dict[tuple[str, str], str]: ...
async def seed_services(session: AsyncSession) -> dict[str, str]: ...
async def seed_glossary_for_services(session: AsyncSession, service_ids: dict) -> int: ...
async def seed_tenant_prompts(session: AsyncSession) -> dict[str, str]: ...  # agent_type → prompt_id
async def seed_tenants(session: AsyncSession, country_ids, company_ids, dept_ids) -> dict: ...  # CCD → tenant_id; PRINTS plaintext API keys
async def seed_tenant_profiles(session: AsyncSession, tenant_ids, position_ids, service_ids, prompt_ids) -> int: ...

async def _main() -> int:
    async with SessionLocal() as session:
        # All steps in order; explicit print() at each step for operator visibility
        ...
        await session.commit()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
```

Tenant API keys printed to stdout:

```python
print(f"  {company_name} / {department_name}: tenant_id={tid}, API_KEY={plaintext_key}")
```

## Task 21: Phase I-4 tests

**Files:**
- Create: `tests/scripts/test_seed_tenant_data.py`

```python
"""Phase I-4 seed integration tests."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_tenant_data import (
    seed_companies,
    seed_countries,
    seed_departments,
    seed_iso_languages,
    seed_positions,
    seed_services,
    seed_tenant_prompts,
    seed_tenants,
    seed_tenant_profiles,
)
from src.db.models import (
    Company, Country, Department, IsoLanguage, Position, Service,
    Tenant, TenantPrompt, TenantProfile,
)


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_seed_iso_languages(db_session: AsyncSession) -> None:
    added = await seed_iso_languages(db_session)
    assert added >= 20  # starter list


async def test_seed_creates_7_countries(db_session: AsyncSession) -> None:
    await seed_countries(db_session)
    assert await _count(db_session, Country) == 7


async def test_seed_creates_3_companies(db_session: AsyncSession) -> None:
    country_ids = await seed_countries(db_session)
    await seed_companies(db_session, country_ids)
    assert await _count(db_session, Company) == 3


async def test_seed_creates_19_departments(db_session: AsyncSession) -> None:
    await seed_departments(db_session)
    assert await _count(db_session, Department) == 19


async def test_seed_creates_83_positions(db_session: AsyncSession) -> None:
    dept_ids = await seed_departments(db_session)
    await seed_positions(db_session, dept_ids)
    assert await _count(db_session, Position) == 83


async def test_seed_creates_16_services(db_session: AsyncSession) -> None:
    await seed_services(db_session)
    assert await _count(db_session, Service) == 16


async def test_seed_creates_57_tenants_with_unique_keys(db_session: AsyncSession) -> None:
    country_ids = await seed_countries(db_session)
    company_ids = await seed_companies(db_session, country_ids)
    dept_ids = await seed_departments(db_session)
    await seed_tenants(db_session, country_ids, company_ids, dept_ids)
    assert await _count(db_session, Tenant) == 57
    # API key uniqueness:
    hashes = (await db_session.execute(select(Tenant.api_key_hash))).scalars().all()
    assert len(hashes) == len(set(hashes)) == 57


async def test_seed_creates_3_prompts(db_session: AsyncSession) -> None:
    await seed_tenant_prompts(db_session)
    rows = (await db_session.execute(select(TenantPrompt))).scalars().all()
    assert sorted(r.agent_type for r in rows) == ["lang_detect_input", "lang_detect_output", "translate"]


async def test_seed_idempotent(db_session: AsyncSession) -> None:
    # Run full seed twice; counts unchanged
    country_ids = await seed_countries(db_session)
    company_ids = await seed_companies(db_session, country_ids)
    dept_ids = await seed_departments(db_session)
    position_ids = await seed_positions(db_session, dept_ids)
    service_ids = await seed_services(db_session)
    prompt_ids = await seed_tenant_prompts(db_session)
    tenant_ids = await seed_tenants(db_session, country_ids, company_ids, dept_ids)
    await seed_tenant_profiles(db_session, tenant_ids, position_ids, service_ids, prompt_ids)

    counts_before = {
        m: await _count(db_session, m)
        for m in (Country, Company, Department, Position, Service, Tenant, TenantProfile, TenantPrompt)
    }
    # Re-run
    country_ids = await seed_countries(db_session)
    company_ids = await seed_companies(db_session, country_ids)
    dept_ids = await seed_departments(db_session)
    position_ids = await seed_positions(db_session, dept_ids)
    service_ids = await seed_services(db_session)
    prompt_ids = await seed_tenant_prompts(db_session)
    tenant_ids = await seed_tenants(db_session, country_ids, company_ids, dept_ids)
    await seed_tenant_profiles(db_session, tenant_ids, position_ids, service_ids, prompt_ids)

    counts_after = {
        m: await _count(db_session, m)
        for m in (Country, Company, Department, Position, Service, Tenant, TenantProfile, TenantPrompt)
    }
    assert counts_before == counts_after
```

Run: `uv run pytest tests/scripts/test_seed_tenant_data.py -v`. Expected: 9 pass.

---

# PHASE I-5 — Streamlit + smoke tests

## Task 22: Streamlit cascading form

**Files:**
- Modify: `demo/app.py`

- [ ] **Step 22.1: Replace `render_translate_page`**

Cascade A → H per spec §8. Streamlit fetches reference endpoints (public) before tenant auth. Auth via `settings.api_key_master` for dev. After tenant resolution, hits `/tenants/{tenant_id}/tenant-profiles?position_id=X` for the profile dropdown.

Key code outline (implementer fills details using existing helpers):

```python
def render_translate_page() -> None:
    st.header("Translate")
    st.sidebar.subheader("Settings")

    # A. Country
    countries = _api_get("/countries").json()
    country = st.sidebar.selectbox("Country", options=[c["country_name"] for c in countries])
    country_id = next(c["country_id"] for c in countries if c["country_name"] == country)

    # B. Company (filtered by country name)
    companies = _api_get("/companies", params={"country": country}).json()
    if not companies:
        st.warning("No companies for this country.")
        return
    company = st.sidebar.selectbox("Company", options=[c["company_name"] for c in companies])
    company_id = next(c["company_id"] for c in companies if c["company_name"] == company)

    # C. Department
    departments = _api_get("/departments").json()
    dept = st.sidebar.selectbox("Department", options=[d["department_name"] for d in departments])
    department_id = next(d["department_id"] for d in departments if d["department_name"] == dept)

    # Resolve tenant
    tenant_resp = _api_get("/tenants/by-ccd", params={"country_id": country_id, "company_id": company_id, "department_id": department_id})
    if tenant_resp.status_code != 200:
        st.error(f"No tenant for {country}/{company}/{dept}. Operator must seed.")
        return
    tenant_id = tenant_resp.json()["tenant_id"]

    # D. Position (filtered by department)
    positions = _api_get(f"/departments/{department_id}/positions").json()
    if not positions:
        st.warning("No positions in this department.")
        return
    position_name = st.sidebar.selectbox("Position", options=[p["position_name"] for p in positions])
    position_id = next(p["position_id"] for p in positions if p["position_name"] == position_name)

    # E. Service — look up via tenant_profile by tenant+position
    profiles_resp = _api_get(f"/tenants/{tenant_id}/tenant-profiles", params={"position_id": position_id})
    profiles = profiles_resp.json()
    if not profiles:
        st.warning("No service profile exists. Operator must create one.")
        return
    # Service options from joined service (need additional API call to map service_id → name)
    services_all = _api_get("/services").json()
    service_id_to_name = {s["service_id"]: s["service_name"] for s in services_all}
    service_options = {service_id_to_name[p["service_id"]]: p for p in profiles}
    service_name = st.sidebar.selectbox("Service", options=list(service_options))
    tp = service_options[service_name]
    profile_id = tp["profile_id"]

    # F. Glossary preview (count only; could fetch glossary terms here)
    st.sidebar.caption("📋 Service glossary applied")

    # G+H. Source + Target Language
    iso = _api_get("/iso-languages").json()
    allowed = tp.get("allowed_language") or [l["code"] for l in iso]
    options = [l for l in iso if l["code"] in allowed]
    source_lang = st.sidebar.selectbox(
        "Source Language",
        options=[l["code"] for l in options],
        format_func=lambda c: next(l["name"] for l in options if l["code"] == c),
    )
    target_lang = st.sidebar.selectbox(
        "Target Language",
        options=[l["code"] for l in options],
        format_func=lambda c: next(l["name"] for l in options if l["code"] == c),
    )

    # Main column
    text = st.text_area("Source text", height=160, key="source_text")
    if st.button("Translate", type="primary", disabled=not text.strip()):
        with st.spinner("Translating..."):
            response = _api_post(
                "/translate",
                {"text": text, "target_lang": target_lang, "profile_id": profile_id, "source_lang": source_lang},
            )
        if response.status_code != 200:
            _show_error(response)
            return
        result = response.json()
        _render_mismatch_banner(result)
        _render_agent_flow(result.get("agentic_activities", []))
        st.subheader("Translation")
        st.markdown(f"> {result['translation']}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cached", "Yes" if result["cached"] else "No")
        col2.metric("Latency", f"{result['latency_ms']:.0f} ms")
        col3.metric("Cost", f"${result['cost_usd']}")
        col4.metric("Glossary", f"{result['glossary_compliance']:.0%}")
        with st.expander("Full metadata"):
            st.json(result)
```

- [ ] **Step 22.2: Inject API key master into Streamlit's _api_get / _api_post helpers**

Read demo/app.py — find the `_api_get` / `_api_post` helpers and add the header:

```python
def _headers() -> dict[str, str]:
    return {"X-Tenant-API-Key": os.environ.get("AITRANS_API_KEY_MASTER", "aitkey_master_dev")}

def _api_get(path: str, params: dict | None = None) -> httpx.Response:
    return httpx.get(f"{API_BASE_URL}{path}", params=params, headers=_headers(), timeout=30.0)

def _api_post(path: str, json: dict) -> httpx.Response:
    return httpx.post(f"{API_BASE_URL}{path}", json=json, headers=_headers(), timeout=120.0)
```

Public endpoints don't need the header but it's harmless to send.

## Task 23: Auth + cascade endpoint tests

**Files:**
- Create: `tests/api/test_auth_routes.py`, `tests/api/test_reference_routes.py`

- [ ] **Step 23.1: Auth route tests**

```python
"""Tests for /auth/refresh-jwt."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.hashing import generate_api_key, hash_api_key
from src.db.models import Tenant


async def test_refresh_jwt_returns_token_for_valid_api_key(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    plaintext = generate_api_key()
    tenant = Tenant(
        tenant_id="tenant-test1234-abcd",
        country_id="country-xxxxxxxx-xxxx",
        company_id="company-xxxxxxxx-xxxx",
        department_id="department-xxxxxxxx-xxxx",
        api_key_hash=hash_api_key(plaintext),
    )
    db_session.add(tenant)
    await db_session.flush()

    resp = await api_client.post(
        "/auth/refresh-jwt",
        headers={"X-Tenant-API-Key": plaintext},
    )
    # Note: this test requires the country/company/department FK rows to exist first;
    # adjust fixture in conftest to seed them.
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "tenant-test1234-abcd"
    assert "jwt_active_token" in body
    assert body["expires_in"] == 86_400


async def test_refresh_jwt_rejects_invalid_key(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/auth/refresh-jwt",
        headers={"X-Tenant-API-Key": "aitkey_definitely_invalid"},
    )
    assert resp.status_code == 401


async def test_refresh_jwt_requires_header(api_client: AsyncClient) -> None:
    resp = await api_client.post("/auth/refresh-jwt")
    assert resp.status_code == 401
```

- [ ] **Step 23.2: Reference route tests**

```python
"""Tests for public cascade endpoints."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Company, Country, Department, IsoLanguage


async def test_countries_returns_seeded(api_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add_all([
        Country(country_id="country-aaaaaaaa-1111", country_name="Atlantis"),
        Country(country_id="country-bbbbbbbb-2222", country_name="Boravia"),
    ])
    await db_session.flush()
    resp = await api_client.get("/countries")
    assert resp.status_code == 200
    names = [c["country_name"] for c in resp.json()]
    assert "Atlantis" in names and "Boravia" in names


async def test_companies_filter_by_country(api_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add_all([
        Company(company_id="company-aaaa1111-aaaa", company_name="ACorp", company_country="Atlantis"),
        Company(company_id="company-bbbb2222-bbbb", company_name="BCorp", company_country="Boravia"),
    ])
    await db_session.flush()
    resp = await api_client.get("/companies", params={"country": "Atlantis"})
    assert resp.status_code == 200
    names = [c["company_name"] for c in resp.json()]
    assert names == ["ACorp"]


async def test_iso_languages_list(api_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add_all([
        IsoLanguage(code="en", name="English"),
        IsoLanguage(code="id", name="Indonesian", native_name="Bahasa Indonesia"),
    ])
    await db_session.flush()
    from src.iso_languages.repository import clear_catalog_cache
    clear_catalog_cache()

    resp = await api_client.get("/iso-languages")
    assert resp.status_code == 200
    codes = sorted([l["code"] for l in resp.json()])
    assert "en" in codes and "id" in codes
```

## Task 24: ID generator + auth + middleware unit tests

Already covered in Tasks 5, 6, 7. Add middleware-specific test:

**Files:**
- Create: `tests/auth/test_middleware.py`

```python
"""Tests for TenantAuthMiddleware."""

from __future__ import annotations

from httpx import AsyncClient


async def test_protected_endpoint_rejects_without_credentials(api_client: AsyncClient) -> None:
    # Use a non-public endpoint — /translate requires auth
    resp = await api_client.post(
        "/translate",
        json={"text": "hello", "target_lang": "id", "profile_id": "profile-xxxxxxxx-xxxx"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "missing_credentials"


async def test_master_api_key_bypasses_per_tenant_lookup(api_client: AsyncClient) -> None:
    resp = await api_client.get(
        "/countries",  # public anyway
        headers={"X-Tenant-API-Key": "aitkey_master_dev"},
    )
    assert resp.status_code == 200  # public path; master not strictly needed


async def test_public_paths_skip_auth(api_client: AsyncClient) -> None:
    resp = await api_client.get("/health")
    assert resp.status_code == 200  # health is public

    resp = await api_client.get("/countries")
    assert resp.status_code == 200  # cascade is public
```

---

# PHASE I-6 — ADRs + verification + commit

## Task 25: Append ADRs to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 25.1: Append ADR-039 through 046 after ADR-033 in Decision log**

Per spec §12, single-line markdown bullet format:

```markdown
- ADR-039: Sub-proyek H discarded (migrations 005-007 deleted, code stashed). Sub-proyek I starts fresh from migration 004. Reason: H model was conceptually rejected by user; clean restart cheaper than incremental fix.
- ADR-040: Custom ID format `{prefix}-{8hex}-{4hex}` for all PKs. 48 bits entropy (lifetime collision-safe at MVP scale per ADR-012 precedent). More readable than full UUID, suitable for log greps + admin operations.
- ADR-041: Tenant = junction of (country, company, department) with built-in auth columns (api_key_hash, jwt_active_token, jwt_refreshed_at). 57 rows seeded.
- ADR-042: Tenant_profile = nested junction of (position, service) per tenant. `prompt_applied` is array of prompt_ids (variable-length config per profile).
- ADR-043: Tone, target_audience, glossary, style_examples moved to `service` table. Properties of the service offering, not of the operator running it.
- ADR-044: Position has `department_id NOT NULL FK`. DB-enforces user's 83 position-department mapping.
- ADR-045: API key argon2-hashed. Plaintext returned ONCE during creation (seed stdout or admin endpoint); never persisted plaintext.
- ADR-046: JWT lightweight design — `tenant.jwt_active_token` stores currently-valid token. Mismatched/expired falls back to API key auth. MVP-grade.
```

## Task 26: Re-apply Bucket 1 UI fixes (carry-over from sub-proyek G+C)

**Files:**
- Modify: `src/config/settings.py` (Haiku model alias), `src/providers/pricing.py` (PRICING_TABLE defensive entry), `demo/app.py` (already partially carried over via Streamlit rewrite — verify agent box solid colors + expanded expander remain in `_render_agent_box`)

- [ ] **Step 26.1: Verify settings has short alias**

Read `src/config/settings.py`. Confirm `anthropic_haiku_model = "claude-haiku-4-5"` (not the date-stamped variant). If still date-stamped, change it.

- [ ] **Step 26.2: Verify PRICING_TABLE has both entries**

Read `src/providers/pricing.py`. Confirm both keys present:

```python
"claude-haiku-4-5": {"input": Decimal("1.00"), "output": Decimal("5.00")},
"claude-haiku-4-5-20251001": {"input": Decimal("1.00"), "output": Decimal("5.00")},
```

- [ ] **Step 26.3: Verify demo/app.py agent box helpers**

Search for `_render_agent_box` in `demo/app.py`. Confirm:
- Solid dark-green `#2e7d32` (success) / dark-red `#c62828` (failure) bgs with `!important` white text
- Expander `expanded=True` by default

If missing, port from sub-proyek G+C (the helpers should already be carried over from the stash if the file wasn't fully rewritten).

## Task 27: Final verification

- [ ] **Step 27.1: Full suite + lint + mypy + alembic head**

```bash
uv run alembic current
uv run pytest tests/ -x -q
uv run ruff check src/ tests/ scripts/ demo/ eval/
uv run mypy src/ scripts/seed_tenant_data.py
```

Expected:
- alembic: `005_tenant_junction (head)`
- pytest: ~230 passed (existing ~200 baseline + ~30 new sub-proyek I tests)
- ruff: clean
- mypy: clean

- [ ] **Step 27.2: Manual smoke**

```bash
# 1. Seed
uv run python scripts/seed_tenant_data.py
# Operator captures API keys from stdout

# 2. Verify
docker compose exec postgres psql -U aitrans -d aitrans_db -c "
  SELECT 'countries' as table_name, count(*) as n FROM country
  UNION ALL SELECT 'companies', count(*) FROM company
  UNION ALL SELECT 'departments', count(*) FROM department
  UNION ALL SELECT 'positions', count(*) FROM position
  UNION ALL SELECT 'services', count(*) FROM service
  UNION ALL SELECT 'tenants', count(*) FROM tenant
  UNION ALL SELECT 'tenant_profiles', count(*) FROM tenant_profile;"
# Expect: 7 / 3 / 19 / 83 / 16 / 57 / 57

# 3. Restart uvicorn
uv run uvicorn src.api.main:app --port 8000 --reload

# 4. Streamlit + cascade flow: Indonesia → PT Integrity Indonesia → Operations → Analyst → general → en → id
# Translate "The forensic review uncovered fraudulent invoices."
# Verify 3 agent boxes + translate prompt resolves with PT Indonesia / Operations / Analyst / general

# 5. Query the log
docker compose exec postgres psql -U aitrans -d aitrans_db -c "
  SELECT c.country_name, co.company_name, d.department_name, p.position_name, s.service_name
  FROM translation_logs tl
  JOIN tenant t ON tl.tenant_id = t.tenant_id
  JOIN country c ON t.country_id = c.country_id
  JOIN company co ON t.company_id = co.company_id
  JOIN department d ON t.department_id = d.department_id
  JOIN tenant_profile tp ON tl.profile_id = tp.profile_id
  JOIN position p ON tp.position_id = p.position_id
  JOIN service s ON tp.service_id = s.service_id
  ORDER BY tl.started_at DESC LIMIT 1;"
```

## Task 28: Mega-commit gate

This task is the controller's responsibility (not implementer).

- [ ] **Step 28.1: Surface commit recommendation to user**

Files to stage:
```
CLAUDE.md
alembic/versions/005_tenant_junction_redesign.py
src/                  (all new packages + modified files)
tests/                (all new test packages + modified files)
scripts/seed_tenant_data.py
demo/app.py
docs/superpowers/specs/2026-05-22-tenant-junction-redesign-design.md
docs/superpowers/plans/2026-05-22-tenant-junction-redesign.md
pyproject.toml + uv.lock (new deps)
```

Skip: `payload.json` at root.

2-sentence commit message recommendation (controller refines based on diff):

> **Kalimat 1:** Sub-proyek I — junction redesign of tenant data model: drop sub-proyek H tables, create 9 new tables (country, company, department, position, service, tenant, tenant_profile, tenant_prompts, iso_languages) via migration 005-NEW with custom `{prefix}-{8hex}-{4hex}` ID format, move tone/audience/glossary/examples to `service`, re-key tenant_prompts by `prompt_id`, add MVP auth (argon2 API key + lightweight JWT on tenant table), seed 7 countries × 3 companies × 19 departments × 83 positions × 16 services × 57 tenants × 57 tenant_profiles, cascading Streamlit form Country → Company → Department → Position → Service.
>
> **Kalimat 2:** Re-applies Bucket 1 UI carry-over (Haiku short alias + PRICING_TABLE defensive entries + solid agent box colors + expanded expander); ~30 new tests across ID generator + auth hashing/JWT + repos + cascade endpoints + seed (~230 total passing); ADR-039 through 046 documenting redesign rationale, custom ID format, junction strategy, FK reorganization, argon2 hashing, and JWT pattern.

Wait for explicit user OK before commit. **Never push.**

---

## Self-review notes

**Spec coverage:**
- §3 Keputusan utama (8 decisions): Tasks 4, 5, 8 (junctions), 5 (ID format), 8/19/20 (service consolidation), 4/8 (position FK), 6/7/13/14 (auth), 1/4 (H discard), 20 (single profile seed), 4 (translation_logs recreation).
- §4 Data model: Task 4 (migration), Task 8 (ORM).
- §5 Migration strategy: Tasks 1, 4.
- §6 Seed: Tasks 19, 20.
- §7 Auth: Tasks 6, 7, 13, 14.
- §8 Streamlit: Task 22.
- §9 Agent refactor: Task 18.
- §10 Error handling: implicit across Tasks 13, 14, 18.
- §11 Testing: Tasks 5, 6, 7, 21, 23, 24.
- §12 ADRs: Task 25.

**Placeholder scan:** Task 20 says "implementer copies them from spec §6 ... and from existing scripts/seed_aitegrity_tenant_profiles.py in git stash" — this is acceptable per writing-plans rules (no TBD/TODO, just a reference to source-of-truth lists too long to inline). Task 22 "Step 22.1: Replace render_translate_page" provides code outline marked "implementer fills details" — acceptable as cascade flow is well-specified and the existing helpers (_show_error, _render_agent_flow, _render_mismatch_banner) carry over from sub-proyek H Phase 5 (which itself was rewritten by stash sub-proyek-H code). Implementer should reference stashed demo/app.py as source.

**Type consistency:** profile_id (VARCHAR(30)) used consistently. tenant_id (VARCHAR(30)). All custom IDs go through `make_id(prefix)`. `prompt_applied` typed as ARRAY(String(30)) consistently in migration 005 + ORM model + Pydantic schema.

Implementer should expect TWO areas of friction:
1. Migration 005 drops tables that existed across multiple sub-projects (sub-proyek B/D/G+C). Test DB fixture (per ADR-010) drops + recreates from Base.metadata each session, so tests are clean. Dev DB needs the manual reset in Task 1 step 1.2.
2. The 83 position-department list + 16 service catalog with glossary need careful copying from spec / stashed AITEGRITY_PRODUCTS. Implementer should not paraphrase or shorten — preserve exact names.

---

## Open follow-ups

- Full ISO 639-1 catalog (~180 entries) — currently ~40-row starter.
- Operator-facing prompt-edit UI (POST /tenant_prompts/{prompt_id}).
- Cron-driven daily JWT refresh — currently on-demand only.
- Tenant creation admin endpoint (post-MVP).
- Per-tenant rate limiting (auth middleware would set request.state.tenant_id, used by rate-limit dependency).
- Dashboard sub-proyek F implementation (now reads tenant + tenant_profile junction).
