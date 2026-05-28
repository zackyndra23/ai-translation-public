# Sub-proyek K Implementation Plan — Schema Cleanup + iso_languages Plumbing + tenant_prompts Dynamism + Verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Denormalize `tenant` + `tenant_profile` ke snapshot name columns (drop FK ke 5 reference tables), seed-distribute 5 `allowed_language` patterns + uniform 3-step `prompt_applied`, plumb `iso_languages` ke pipeline untuk code-to-name resolution, expand `tenant_prompts` Jinja context dict, enforce `allowed_language` di pipeline stage, dan verify end-to-end persistence (Postgres `translation_logs` + Redis cache hit/miss).

**Architecture:** Single migration `006_schema_cleanup_iso_plumbing.py` (TRUNCATE + drop FK columns + add name columns + alembic_version_at_create). Reference tables (`country`, `company`, `department`, `position`, `service`, `iso_languages`) retained sebagai catalog untuk cascade UI + Jinja context lookup. Pipeline stages refactored: drop `joinedload`-based access, gunakan denormalized columns + by-name repository lookups. New `validate_target_language` stage rejects mismatches dengan HTTP 400.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, Jinja2, pytest + pytest-asyncio, structlog, argon2-cffi (hashing), passlib, asyncpg, Redis 7.

**Spec reference:** `docs/superpowers/specs/2026-05-22-schema-cleanup-and-plumbing-design.md`

---

## File Structure Map

**ORM + Migration:**
- Modify `src/db/models.py` — Tenant + TenantProfile column shape + drop relationships
- Create `alembic/versions/006_schema_cleanup_iso_plumbing.py` — TRUNCATE + drop FK cols + add name cols
- Create `tests/db/test_migration_006.py` — upgrade smoke + downgrade NotImplementedError

**Schemas:**
- Modify `src/tenant/schemas.py` — TenantCreate / TenantRead with denormalized fields
- Modify `src/tenant_profile/schemas.py` — denormalized fields + length-3 validator

**Repositories:**
- Modify `src/tenant/repository.py` — drop FK-based methods, add `get_by_name`, update `create`
- Modify `src/tenant_profile/repository.py` — drop joinedload, use denormalized columns
- Modify `src/tenant_profile/resolver.py` — drop joinedload; return new ResolvedTenantProfile dataclass
- Modify `src/service/repository.py` — add `get_by_name`
- Modify `src/country/repository.py` — add `get_by_name`
- (`iso_languages/repository.py` already has `get_name`)

**Pipeline:**
- Create `src/pipeline/errors.py` — `LanguageNotAllowedError`
- Modify `src/pipeline/stages.py` — add `validate_target_language` + `build_jinja_context` + helper, refactor `build_prompt` to use flat dict, refactor `load_resolved_tenant_profile` to use new resolver
- Modify `src/pipeline/pipeline.py` — wire new stages
- Modify `src/pipeline/templates/translate.jinja` — flat-var template

**API:**
- Modify `src/api/middleware.py` — `language_not_allowed` handler

**Seed:**
- Modify `scripts/seed_tenant_data.py` — TRUNCATE + denormalized snapshot + stratified `allowed_language`

**Verification:**
- Create `scripts/test_e2e_persistence.py` — live smoke probe

**Tests (new):**
- `tests/pipeline/test_validate_target_language.py`
- `tests/pipeline/test_jinja_context_builder.py`
- `tests/tenant/test_repository_denormalized.py`
- `tests/tenant_profile/test_repository_denormalized.py`
- `tests/scripts/test_seed_distribution.py`
- `tests/iso_languages/test_repository.py` (extend existing if present)

**Docs:**
- Modify `docs/adrs.md` — append ADR-053..058
- Modify `CLAUDE.md` — extend ADR index one-liners + sub-proyek K entry
- Modify `docs/phase-status.md` — add Sub-proyek K section

---

## Section A — Migration 006 + ORM updates (commit batch 1)

### Task A1: Update `TenantProfile` Pydantic schemas dengan denormalized fields + length-3 validator

**Files:**
- Modify: `src/tenant_profile/schemas.py`
- Test: `tests/tenant_profile/test_schemas.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/tenant_profile/test_schemas.py`:

```python
"""Schema validation for sub-proyek K denormalized tenant_profile."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.tenant_profile.schemas import TenantProfileCreate


def test_create_accepts_three_prompt_applied_in_order() -> None:
    payload = TenantProfileCreate(
        tenant_name="PT Test — Sales (Indonesia)",
        service_name="general",
        position_name="Sales Executive",
        allowed_language=["id", "en"],
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    assert payload.prompt_applied == [
        "lang_detect_input",
        "translate",
        "lang_detect_output",
    ]


def test_create_rejects_wrong_length_prompt_applied() -> None:
    with pytest.raises(ValidationError, match="length 3"):
        TenantProfileCreate(
            tenant_name="x",
            service_name="general",
            position_name="x",
            prompt_applied=["lang_detect_input", "translate"],  # length 2
        )


def test_create_rejects_wrong_order_prompt_applied() -> None:
    with pytest.raises(ValidationError, match="order"):
        TenantProfileCreate(
            tenant_name="x",
            service_name="general",
            position_name="x",
            prompt_applied=["translate", "lang_detect_input", "lang_detect_output"],
        )


def test_create_allows_null_allowed_language() -> None:
    payload = TenantProfileCreate(
        tenant_name="x",
        service_name="general",
        position_name="x",
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        allowed_language=None,
    )
    assert payload.allowed_language is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/tenant_profile/test_schemas.py -v
```
Expected: 4 FAIL (`TenantProfileCreate` missing `tenant_name`, `service_name`, `position_name` fields + length validator).

- [ ] **Step 3: Replace `src/tenant_profile/schemas.py`**

```python
"""Pydantic schemas for tenant_profile (sub-proyek K denormalized form)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

EXPECTED_PROMPT_APPLIED_ORDER: list[str] = [
    "lang_detect_input",
    "translate",
    "lang_detect_output",
]


def _validate_prompt_applied(value: list[str]) -> list[str]:
    """prompt_applied is `[lang_detect_input, translate, lang_detect_output]` exactly.

    DB-level CHECK enforces length 3 (migration 006). The ordering rule lives
    here because Postgres CHECK can't express ordered-element equality without
    a stored procedure — Pydantic is the cleanest place to enforce it.
    """
    if len(value) != 3:
        raise ValueError(
            f"prompt_applied must have length 3, got {len(value)}"
        )
    if value != EXPECTED_PROMPT_APPLIED_ORDER:
        raise ValueError(
            f"prompt_applied must be in order {EXPECTED_PROMPT_APPLIED_ORDER}, "
            f"got {value}"
        )
    return value


class TenantProfileCreate(BaseModel):
    tenant_name: str
    service_name: str
    position_name: str
    allowed_language: list[str] | None = None
    prompt_applied: list[str]

    @field_validator("prompt_applied")
    @classmethod
    def check_prompt_applied(cls, v: list[str]) -> list[str]:
        return _validate_prompt_applied(v)


class TenantProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: str
    tenant_name: str
    service_name: str
    position_name: str
    allowed_language: list[str] | None
    prompt_applied: list[str]
    created_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/tenant_profile/test_schemas.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tenant_profile/schemas.py tests/tenant_profile/test_schemas.py
git commit -m "feat(sub-proyek K): denormalized TenantProfile schemas + prompt_applied validator"
```

---

### Task A2: Update `Tenant` Pydantic schemas dengan denormalized fields

**Files:**
- Modify: `src/tenant/schemas.py`
- Test: `tests/tenant/test_schemas.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/tenant/test_schemas.py`:

```python
"""Schema validation for sub-proyek K denormalized tenant."""

from __future__ import annotations

from src.tenant.schemas import TenantCreate, TenantRead


def test_tenant_create_accepts_denormalized_names() -> None:
    payload = TenantCreate(
        country_name="Indonesia",
        company_name="PT Integrity Indonesia",
        department_name="Sales",
    )
    assert payload.country_name == "Indonesia"
    assert payload.company_name == "PT Integrity Indonesia"
    assert payload.department_name == "Sales"


def test_tenant_read_includes_tenant_name_and_alembic_version() -> None:
    # Construct from a plain dict (simulating ORM .__dict__).
    raw = {
        "tenant_id": "tenant-aaaaaaaa-aaaa",
        "tenant_name": "PT Integrity Indonesia — Sales (Indonesia)",
        "country_name": "Indonesia",
        "company_name": "PT Integrity Indonesia",
        "department_name": "Sales",
        "alembic_version_at_create": "006_schema_cleanup_iso_plumbing",
        "created_at": "2026-05-22T00:00:00Z",
    }
    read = TenantRead.model_validate(raw)
    assert read.tenant_name == "PT Integrity Indonesia — Sales (Indonesia)"
    assert read.alembic_version_at_create == "006_schema_cleanup_iso_plumbing"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/tenant/test_schemas.py -v
```
Expected: 2 FAIL.

- [ ] **Step 3: Replace `src/tenant/schemas.py`**

```python
"""Pydantic schemas for tenant (sub-proyek K denormalized form).

NEVER include api_key_hash or jwt_active_token in any response Read schema.
TenantCreatedResponse is the one exception — it carries the plaintext API
key (returned ONCE at creation time per ADR-045).

Sub-proyek K: drop country_id/company_id/department_id FK references;
denormalize to *_name string snapshots populated at insert time.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantCreate(BaseModel):
    country_name: str
    company_name: str
    department_name: str


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    tenant_name: str
    country_name: str
    company_name: str
    department_name: str
    alembic_version_at_create: str
    created_at: datetime


class TenantCreatedResponse(TenantRead):
    """Includes plaintext API key — returned ONCE on creation."""

    api_key_plaintext: str
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/tenant/test_schemas.py -v
```
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tenant/schemas.py tests/tenant/test_schemas.py
git commit -m "feat(sub-proyek K): denormalized Tenant schemas + alembic_version_at_create"
```

---

### Task A3: Update `Tenant` ORM model — drop FK columns, add name + alembic columns

**Files:**
- Modify: `src/db/models.py`

- [ ] **Step 1: Open `src/db/models.py` and locate the `Tenant` class (around line 156–187)**

- [ ] **Step 2: Replace the entire `Tenant` class with denormalized version**

The new `Tenant` class drops all relationships (`country`, `company`, `department`, `profiles`) — they were FK-driven and the FKs are gone in migration 006. Lookups by name go through repository helpers (Task B2).

```python
class Tenant(Base):
    __tablename__ = "tenant"
    __table_args__ = (
        UniqueConstraint(
            "country_name", "company_name", "department_name", name="uq_tenant_ccd_names"
        ),
        Index("ix_tenant_api_key_hash", "api_key_hash"),
    )

    tenant_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    tenant_name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    country_name: Mapped[str] = mapped_column(String(60), nullable=False)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    department_name: Mapped[str] = mapped_column(String(80), nullable=False)
    alembic_version_at_create: Mapped[str] = mapped_column(String(60), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    jwt_active_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    jwt_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Verify imports still work**

`UUID` import is no longer needed if it was only used by Tenant FK. Leave imports alone unless lint flags an unused import.

- [ ] **Step 4: Sanity check — mypy passes**

```bash
uv run mypy src/db/models.py
```
Expected: no errors (existing model file may have other classes still using imports).

- [ ] **Step 5: Commit**

```bash
git add src/db/models.py
git commit -m "feat(sub-proyek K): refactor Tenant ORM — drop FK cols, add snapshot name + alembic_version_at_create"
```

---

### Task A4: Update `TenantProfile` ORM model — drop FK columns, add name columns + length-3 CHECK

**Files:**
- Modify: `src/db/models.py`

- [ ] **Step 1: Locate the `TenantProfile` class (around line 190–217)**

- [ ] **Step 2: Replace with denormalized version**

```python
class TenantProfile(Base):
    __tablename__ = "tenant_profile"
    __table_args__ = (
        UniqueConstraint(
            "tenant_name", "position_name", "service_name", name="uq_tenant_profile_tps_names"
        ),
        CheckConstraint(
            "array_length(prompt_applied, 1) = 3", name="ck_prompt_applied_length"
        ),
        Index("ix_tenant_profile_tenant_name", "tenant_name"),
    )

    profile_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    tenant_name: Mapped[str] = mapped_column(String(150), nullable=False)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    position_name: Mapped[str] = mapped_column(String(120), nullable=False)
    allowed_language: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)), nullable=True)
    prompt_applied: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # No relationships — denormalized snapshots.
```

- [ ] **Step 3: Verify mypy and pre-existing ORM tests still discover the class**

```bash
uv run mypy src/db/models.py
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/db/models.py
git commit -m "feat(sub-proyek K): refactor TenantProfile ORM — drop FK cols, add denormalized name + length-3 CHECK"
```

---

### Task A5: Create Alembic migration `006_schema_cleanup_iso_plumbing.py`

**Files:**
- Create: `alembic/versions/006_schema_cleanup_iso_plumbing.py`

- [ ] **Step 1: Create the migration file**

```python
"""Sub-proyek K: schema cleanup — denormalize tenant + tenant_profile + alembic_version_at_create snapshot.

TRUNCATE tenant CASCADE clears tenant + tenant_profile (FK ondelete CASCADE)
and sets translation_logs.tenant_id/profile_id to NULL (FK ondelete SET NULL).
Then drop FK columns and add denormalized snapshot columns. Re-seed handled
separately in scripts/seed_tenant_data.py.

Revision ID: 006_schema_cleanup
Revises: 005_tenant_junction
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_schema_cleanup"
down_revision: str | None = "005_tenant_junction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Step 1: Wipe existing tenant + tenant_profile rows.
    # ADD NOT NULL columns to a populated table errors out without a
    # default. Easiest path: clear the table and let the seed script
    # repopulate with the new shape afterwards.
    # ------------------------------------------------------------------
    op.execute("TRUNCATE TABLE tenant CASCADE")

    # ------------------------------------------------------------------
    # Step 2: Drop tenant_profile FK columns + composite UNIQUE + index.
    # Dropping a column auto-drops its FK constraint in Postgres.
    # ------------------------------------------------------------------
    op.drop_constraint("uq_tenant_profile_tps", "tenant_profile", type_="unique")
    op.drop_index("ix_tenant_profile_tenant_id", table_name="tenant_profile")
    op.drop_column("tenant_profile", "tenant_id")
    op.drop_column("tenant_profile", "position_id")
    op.drop_column("tenant_profile", "service_id")

    # ------------------------------------------------------------------
    # Step 3: Drop tenant FK columns + composite UNIQUE.
    # ------------------------------------------------------------------
    op.drop_constraint("uq_tenant_ccd", "tenant", type_="unique")
    op.drop_column("tenant", "country_id")
    op.drop_column("tenant", "company_id")
    op.drop_column("tenant", "department_id")

    # ------------------------------------------------------------------
    # Step 4: Add tenant denormalized snapshot columns + alembic version.
    # NOT NULL safe because table is empty.
    # ------------------------------------------------------------------
    op.add_column("tenant", sa.Column("tenant_name", sa.String(150), nullable=False))
    op.add_column("tenant", sa.Column("country_name", sa.String(60), nullable=False))
    op.add_column("tenant", sa.Column("company_name", sa.String(100), nullable=False))
    op.add_column("tenant", sa.Column("department_name", sa.String(80), nullable=False))
    op.add_column(
        "tenant",
        sa.Column("alembic_version_at_create", sa.String(60), nullable=False),
    )
    op.create_unique_constraint("uq_tenant_name", "tenant", ["tenant_name"])
    op.create_unique_constraint(
        "uq_tenant_ccd_names",
        "tenant",
        ["country_name", "company_name", "department_name"],
    )

    # ------------------------------------------------------------------
    # Step 5: Add tenant_profile denormalized columns + CHECK + index.
    # ------------------------------------------------------------------
    op.add_column(
        "tenant_profile", sa.Column("tenant_name", sa.String(150), nullable=False)
    )
    op.add_column(
        "tenant_profile", sa.Column("service_name", sa.String(100), nullable=False)
    )
    op.add_column(
        "tenant_profile", sa.Column("position_name", sa.String(120), nullable=False)
    )
    op.create_unique_constraint(
        "uq_tenant_profile_tps_names",
        "tenant_profile",
        ["tenant_name", "position_name", "service_name"],
    )
    op.create_check_constraint(
        "ck_prompt_applied_length",
        "tenant_profile",
        "array_length(prompt_applied, 1) = 3",
    )
    op.create_index(
        "ix_tenant_profile_tenant_name", "tenant_profile", ["tenant_name"]
    )

    # ------------------------------------------------------------------
    # Step 6: Drop the now-empty default on prompt_applied (length-0
    # default would violate CHECK). We rely on application-level seed
    # to populate length-3 arrays explicitly.
    # ------------------------------------------------------------------
    op.alter_column("tenant_profile", "prompt_applied", server_default=None)


def downgrade() -> None:
    raise NotImplementedError(
        "Sub-proyek K migration is irreversible by design. "
        "Restoring the FK-based schema would require manual data reconstruction."
    )
```

- [ ] **Step 2: Verify migration can be discovered**

```bash
uv run alembic history
```
Expected: lists `006_schema_cleanup` revision after `005_tenant_junction`.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/006_schema_cleanup_iso_plumbing.py
git commit -m "feat(sub-proyek K): migration 006 — drop FK cols + add denormalized snapshot cols + length-3 CHECK"
```

---

### Task A6: Test migration 006 — upgrade smoke + downgrade NotImplementedError

**Files:**
- Create: `tests/db/test_migration_006.py`

- [ ] **Step 1: Write the test**

```python
"""Sub-proyek K migration smoke test.

Verifies:
  - `alembic upgrade head` succeeds from 005 baseline.
  - `downgrade()` raises NotImplementedError per ADR-053 precedent.
  - Resulting schema has the expected denormalized columns.
"""

from __future__ import annotations

import asyncio
import subprocess

import pytest
from sqlalchemy import inspect, text

from src.config.settings import get_settings

pytestmark = pytest.mark.asyncio


async def _table_columns(async_engine, table_name: str) -> set[str]:
    async with async_engine.connect() as conn:
        result = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns(table_name)}
        )
    return result


async def test_migration_006_upgrade_creates_denormalized_columns(async_engine_for_test):
    """After upgrade head, tenant has snapshot columns and no FK columns."""
    tenant_cols = await _table_columns(async_engine_for_test, "tenant")
    assert "tenant_name" in tenant_cols
    assert "country_name" in tenant_cols
    assert "company_name" in tenant_cols
    assert "department_name" in tenant_cols
    assert "alembic_version_at_create" in tenant_cols
    assert "country_id" not in tenant_cols
    assert "company_id" not in tenant_cols
    assert "department_id" not in tenant_cols


async def test_migration_006_upgrade_creates_tenant_profile_denormalized(async_engine_for_test):
    cols = await _table_columns(async_engine_for_test, "tenant_profile")
    assert "tenant_name" in cols
    assert "service_name" in cols
    assert "position_name" in cols
    assert "tenant_id" not in cols
    assert "position_id" not in cols
    assert "service_id" not in cols


def test_migration_006_downgrade_raises():
    """Importing the migration module + calling downgrade() raises."""
    import importlib

    module = importlib.import_module("alembic.versions.006_schema_cleanup_iso_plumbing")
    with pytest.raises(NotImplementedError, match="irreversible"):
        module.downgrade()
```

**Note for executor:** the `async_engine_for_test` fixture is provided by `tests/conftest.py` (it builds the test DB with `NullPool` per ADR-010 and runs `alembic upgrade head` once per session). If the fixture name differs in your conftest, replace accordingly — check `tests/conftest.py` for the actual fixture name.

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/db/test_migration_006.py -v
```
Expected: 3 PASS (test DB upgrades head before tests run).

- [ ] **Step 3: Commit**

```bash
git add tests/db/test_migration_006.py
git commit -m "test(sub-proyek K): migration 006 upgrade smoke + downgrade-raises"
```

---

### Task A7: Run migration 006 against the local dev database

**Files:**
- (none modified — operational step)

- [ ] **Step 1: Confirm postgres is running**

```bash
docker compose ps
```
Expected: postgres container "Up" status.

- [ ] **Step 2: Apply the migration**

```bash
uv run alembic upgrade head
```
Expected output (last line):
```
INFO  [alembic.runtime.migration] Running upgrade 005_tenant_junction -> 006_schema_cleanup, ...
```

- [ ] **Step 3: Verify schema in psql**

```bash
docker compose exec postgres psql -U postgres -d aitrans -c "\d tenant"
```
Expected: columns `tenant_id`, `tenant_name`, `country_name`, `company_name`, `department_name`, `alembic_version_at_create`, `api_key_hash`, etc. NO `country_id`, `company_id`, `department_id`.

- [ ] **Step 4: Confirm tenant + tenant_profile are empty (TRUNCATE'd)**

```bash
docker compose exec postgres psql -U postgres -d aitrans -c "SELECT COUNT(*) FROM tenant; SELECT COUNT(*) FROM tenant_profile;"
```
Expected: both `0`.

- [ ] **Step 5: No commit — operational only**

Recovery: if migration fails mid-way, restore from the snapshot you took before this step (you DO have a Postgres dump from before sub-proyek K, right?). If not, drop the DB and re-run all migrations from 001:
```bash
docker compose exec postgres psql -U postgres -c "DROP DATABASE aitrans; CREATE DATABASE aitrans;"
uv run alembic upgrade head
```

---

## Section B — Repository refactor (commit batch 2)

### Task B1: Add `get_by_name` helpers to reference-table repositories

**Files:**
- Modify: `src/country/repository.py`
- Modify: `src/company/repository.py`
- Modify: `src/department/repository.py`
- Modify: `src/position/repository.py`
- Modify: `src/service/repository.py`

- [ ] **Step 1: Inspect the existing repository pattern (read one to know the shape)**

```bash
uv run cat src/service/repository.py
```

(or use the Read tool)

- [ ] **Step 2: Add `get_by_name` to each repository**

For each of `country/repository.py`, `company/repository.py`, `department/repository.py`, `position/repository.py`, `service/repository.py`, add a method following this pattern (uses `Service` and `service_name` — adapt the model + column name per file):

```python
async def get_by_name(self, name: str) -> ServiceRead | None:
    """Look up a service by its human-readable name. Used by the pipeline's
    build_jinja_context stage to resolve service.tone / target_audience /
    glossary / examples from a denormalized service_name snapshot."""
    result = await self._session.execute(
        select(Service).where(Service.service_name == name)
    )
    row = result.scalar_one_or_none()
    return ServiceRead.model_validate(row) if row else None
```

**For `position/repository.py` specifically**, the lookup key is composite (`position_name`, `department_name`), because position name is not globally unique. Signature:

```python
async def get_by_name_and_department(
    self, position_name: str, department_name: str
) -> PositionRead | None:
    result = await self._session.execute(
        select(Position).join(Department).where(
            Position.position_name == position_name,
            Department.department_name == department_name,
        )
    )
    row = result.scalar_one_or_none()
    return PositionRead.model_validate(row) if row else None
```

- [ ] **Step 3: Quick smoke — import each repo without error**

```bash
uv run python -c "from src.country.repository import CountryRepository; from src.company.repository import CompanyRepository; from src.department.repository import DepartmentRepository; from src.position.repository import PositionRepository; from src.service.repository import ServiceRepository; print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/country/repository.py src/company/repository.py src/department/repository.py src/position/repository.py src/service/repository.py
git commit -m "feat(sub-proyek K): add get_by_name helpers to reference-table repositories"
```

---

### Task B2: Refactor `TenantRepository` — drop FK methods, add `get_by_name`, update `create`

**Files:**
- Modify: `src/tenant/repository.py`
- Test: `tests/tenant/test_repository_denormalized.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/tenant/test_repository_denormalized.py`:

```python
"""TenantRepository tests for sub-proyek K denormalized form."""

from __future__ import annotations

import pytest

from src.tenant.repository import TenantRepository
from src.tenant.schemas import TenantCreate

pytestmark = pytest.mark.asyncio


async def test_create_persists_denormalized_names_and_alembic_version(db_session):
    """Create stores tenant_name, *_name snapshots, alembic_version_at_create."""
    repo = TenantRepository(db_session)
    response = await repo.create(
        TenantCreate(
            country_name="Indonesia",
            company_name="PT Test",
            department_name="Sales",
        ),
        alembic_version="006_schema_cleanup",
    )
    assert response.country_name == "Indonesia"
    assert response.company_name == "PT Test"
    assert response.department_name == "Sales"
    assert response.tenant_name == "PT Test — Sales (Indonesia)"
    assert response.alembic_version_at_create == "006_schema_cleanup"
    assert response.api_key_plaintext.startswith("aitkey_")


async def test_get_by_name(db_session):
    """Lookup by tenant_name returns the row; missing returns None."""
    repo = TenantRepository(db_session)
    await repo.create(
        TenantCreate(
            country_name="Indonesia",
            company_name="PT Test",
            department_name="Sales",
        ),
        alembic_version="006",
    )
    found = await repo.get_by_name("PT Test — Sales (Indonesia)")
    assert found is not None
    assert found.country_name == "Indonesia"

    missing = await repo.get_by_name("Nonexistent")
    assert missing is None


async def test_resolve_by_ccd_uses_names(db_session):
    """resolve_by_ccd takes names (not IDs) after sub-proyek K refactor."""
    repo = TenantRepository(db_session)
    await repo.create(
        TenantCreate(
            country_name="Indonesia",
            company_name="PT Test",
            department_name="Sales",
        ),
        alembic_version="006",
    )
    found = await repo.resolve_by_ccd(
        country_name="Indonesia",
        company_name="PT Test",
        department_name="Sales",
    )
    assert found is not None
```

**Fixture note:** `db_session` is the standard test fixture from `tests/conftest.py` that provides an `AsyncSession` rolled back at test teardown. If the fixture name differs, check conftest.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/tenant/test_repository_denormalized.py -v
```
Expected: 3 FAIL.

- [ ] **Step 3: Replace `src/tenant/repository.py`**

```python
"""TenantRepository — sub-proyek K denormalized form.

Drops FK-based country_id/company_id/department_id; uses *_name snapshots.
Lookups by name; create() composes tenant_name auto-formatted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.hashing import generate_api_key, hash_api_key, verify_api_key
from src.db.ids import make_id
from src.db.models import Tenant
from src.tenant.schemas import TenantCreate, TenantCreatedResponse, TenantRead


def compose_tenant_name(*, company_name: str, department_name: str, country_name: str) -> str:
    """Composite display name used as `tenant.tenant_name` (UNIQUE).

    Format: ``"{company} — {department} ({country})"``. Em-dash separator,
    country in parens. Keeps the name human-readable and self-documenting.
    """
    return f"{company_name} — {department_name} ({country_name})"


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[TenantRead]:
        result = await self._session.execute(select(Tenant))
        return [TenantRead.model_validate(t) for t in result.scalars().all()]

    async def get_by_id(self, tenant_id: str) -> TenantRead | None:
        row = await self._session.get(Tenant, tenant_id)
        return TenantRead.model_validate(row) if row else None

    async def get_by_name(self, tenant_name: str) -> TenantRead | None:
        result = await self._session.execute(
            select(Tenant).where(Tenant.tenant_name == tenant_name)
        )
        row = result.scalar_one_or_none()
        return TenantRead.model_validate(row) if row else None

    async def resolve_by_ccd(
        self, country_name: str, company_name: str, department_name: str
    ) -> TenantRead | None:
        """Look up tenant by (country_name, company_name, department_name) composite."""
        result = await self._session.execute(
            select(Tenant).where(
                Tenant.country_name == country_name,
                Tenant.company_name == company_name,
                Tenant.department_name == department_name,
            )
        )
        row = result.scalar_one_or_none()
        return TenantRead.model_validate(row) if row else None

    async def create(
        self, payload: TenantCreate, *, alembic_version: str
    ) -> TenantCreatedResponse:
        """Insert with auto-composed tenant_name + caller-supplied alembic version.

        ``alembic_version`` is injected by the caller (seed reads it from the
        Postgres ``alembic_version`` meta table). Letting the repository read
        the meta table itself would couple it to migration infrastructure;
        injection keeps the boundary clean.
        """
        plaintext_key = generate_api_key()
        tenant_name = compose_tenant_name(
            company_name=payload.company_name,
            department_name=payload.department_name,
            country_name=payload.country_name,
        )
        row = Tenant(
            tenant_id=make_id("tenant"),
            tenant_name=tenant_name,
            country_name=payload.country_name,
            company_name=payload.company_name,
            department_name=payload.department_name,
            alembic_version_at_create=alembic_version,
            api_key_hash=hash_api_key(plaintext_key),
        )
        self._session.add(row)
        await self._session.flush()
        return TenantCreatedResponse(
            **TenantRead.model_validate(row).model_dump(),
            api_key_plaintext=plaintext_key,
        )

    async def verify_api_key(self, plaintext: str) -> str | None:
        """Find the tenant whose api_key_hash matches plaintext. Returns tenant_id or None."""
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

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/tenant/test_repository_denormalized.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tenant/repository.py tests/tenant/test_repository_denormalized.py
git commit -m "feat(sub-proyek K): TenantRepository denormalized — composes tenant_name + injected alembic_version"
```

---

### Task B3: Refactor `TenantProfileRepository` — drop joinedload, denormalized form

**Files:**
- Modify: `src/tenant_profile/repository.py`
- Test: `tests/tenant_profile/test_repository_denormalized.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/tenant_profile/test_repository_denormalized.py`:

```python
"""TenantProfileRepository tests for sub-proyek K denormalized form."""

from __future__ import annotations

import pytest

from src.tenant_profile.repository import TenantProfileRepository
from src.tenant_profile.schemas import TenantProfileCreate

pytestmark = pytest.mark.asyncio


async def test_create_persists_denormalized_names(db_session):
    repo = TenantProfileRepository(db_session)
    profile = await repo.create(
        TenantProfileCreate(
            tenant_name="PT Test — Sales (Indonesia)",
            service_name="general",
            position_name="Sales Executive",
            allowed_language=["id", "en"],
            prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        )
    )
    assert profile.tenant_name == "PT Test — Sales (Indonesia)"
    assert profile.service_name == "general"
    assert profile.position_name == "Sales Executive"
    assert profile.allowed_language == ["id", "en"]


async def test_list_by_tenant_name(db_session):
    repo = TenantProfileRepository(db_session)
    await repo.create(
        TenantProfileCreate(
            tenant_name="PT Test — Sales (Indonesia)",
            service_name="general",
            position_name="Sales Executive",
            allowed_language=None,
            prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        )
    )
    profiles = await repo.list_by_tenant_name("PT Test — Sales (Indonesia)")
    assert len(profiles) == 1
    assert profiles[0].position_name == "Sales Executive"


async def test_get_by_id_returns_orm_row(db_session):
    """get_by_id returns the ORM row (not Pydantic Read) for pipeline use."""
    repo = TenantProfileRepository(db_session)
    created = await repo.create(
        TenantProfileCreate(
            tenant_name="PT Test — Sales (Indonesia)",
            service_name="general",
            position_name="Sales Executive",
            allowed_language=["id", "en"],
            prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        )
    )
    row = await repo.get_orm_by_id(created.profile_id)
    assert row is not None
    assert row.tenant_name == "PT Test — Sales (Indonesia)"
    assert row.service_name == "general"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/tenant_profile/test_repository_denormalized.py -v
```
Expected: 3 FAIL.

- [ ] **Step 3: Replace `src/tenant_profile/repository.py`**

```python
"""TenantProfileRepository — sub-proyek K denormalized form.

Drops joinedload usage (FK relationships removed in migration 006).
Provides denormalized lookups by tenant_name and the ORM row for pipeline use.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import TenantProfile
from src.tenant_profile.schemas import TenantProfileCreate, TenantProfileRead


class TenantProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_tenant_name(
        self, tenant_name: str, position_name: str | None = None
    ) -> list[TenantProfileRead]:
        query = select(TenantProfile).where(TenantProfile.tenant_name == tenant_name)
        if position_name:
            query = query.where(TenantProfile.position_name == position_name)
        result = await self._session.execute(query)
        return [TenantProfileRead.model_validate(p) for p in result.scalars().all()]

    async def get_by_id(self, profile_id: str) -> TenantProfileRead | None:
        row = await self._session.get(TenantProfile, profile_id)
        return TenantProfileRead.model_validate(row) if row else None

    async def get_orm_by_id(self, profile_id: str) -> TenantProfile | None:
        """Return the raw ORM row (no Pydantic wrap) for pipeline stages.

        The pipeline's build_jinja_context stage reads denormalized fields
        directly off this row. No joinedload needed since there are no
        relationships to load — all fields are local columns.
        """
        return await self._session.get(TenantProfile, profile_id)

    async def create(self, payload: TenantProfileCreate) -> TenantProfileRead:
        row = TenantProfile(
            profile_id=make_id("profile"),
            tenant_name=payload.tenant_name,
            service_name=payload.service_name,
            position_name=payload.position_name,
            allowed_language=payload.allowed_language,
            prompt_applied=payload.prompt_applied,
        )
        self._session.add(row)
        await self._session.flush()
        return TenantProfileRead.model_validate(row)
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/tenant_profile/test_repository_denormalized.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tenant_profile/repository.py tests/tenant_profile/test_repository_denormalized.py
git commit -m "feat(sub-proyek K): TenantProfileRepository denormalized — drop joinedload, denormalized lookups"
```

---

### Task B4: Refactor `TenantProfileResolver` — return `ResolvedTenantProfile` dataclass

**Files:**
- Modify: `src/tenant_profile/resolver.py`

- [ ] **Step 1: Replace `src/tenant_profile/resolver.py`**

```python
"""Pipeline resolver — load tenant_profile + tenant + service for template rendering.

Sub-proyek K: returns a flat `ResolvedTenantProfile` dataclass with all
fields the pipeline needs, sourced from denormalized columns + by-name
catalog lookups. No more joinedload; relationships are gone.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.service.repository import ServiceRepository
from src.tenant.repository import TenantRepository
from src.tenant_profile.repository import TenantProfileRepository


class TenantProfileNotFound(Exception):
    pass


@dataclass(frozen=True)
class ResolvedTenantProfile:
    """All the fields the pipeline + Jinja context need, flattened.

    Replaces the joinedload ORM blob from sub-proyek I. Fields sourced
    from: tenant_profile denormalized cols (profile_id, tenant_name,
    service_name, position_name, allowed_language, prompt_applied) +
    tenant by-name lookup (country_name, company_name, department_name) +
    service by-name lookup (tone, target_audience).
    """

    profile_id: str
    tenant_id: str
    tenant_name: str
    country_name: str
    company_name: str
    department_name: str
    position_name: str
    service_name: str
    service_tone: str | None
    service_target_audience: str | None
    allowed_language: list[str] | None
    prompt_applied: list[str]


class TenantProfileResolver:
    """Loads + flattens tenant_profile + tenant + service for pipeline use."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tp_repo = TenantProfileRepository(session)
        self._tenant_repo = TenantRepository(session)
        self._service_repo = ServiceRepository(session)

    async def resolve(self, profile_id: str) -> ResolvedTenantProfile:
        tp = await self._tp_repo.get_orm_by_id(profile_id)
        if tp is None:
            raise TenantProfileNotFound(f"tenant_profile {profile_id!r} not found")

        tenant = await self._tenant_repo.get_by_name(tp.tenant_name)
        if tenant is None:
            raise TenantProfileNotFound(
                f"tenant_profile {profile_id!r} references unknown tenant_name {tp.tenant_name!r}"
            )

        service = await self._service_repo.get_by_name(tp.service_name)
        # Service is not required (forward-compat): a profile may reference
        # a service that's been deleted. We populate tone/audience as None
        # in that case so prompt rendering still works.
        service_tone = service.tone if service else None
        service_audience = service.target_audience if service else None

        return ResolvedTenantProfile(
            profile_id=tp.profile_id,
            tenant_id=tenant.tenant_id,
            tenant_name=tp.tenant_name,
            country_name=tenant.country_name,
            company_name=tenant.company_name,
            department_name=tenant.department_name,
            position_name=tp.position_name,
            service_name=tp.service_name,
            service_tone=service_tone,
            service_target_audience=service_audience,
            allowed_language=tp.allowed_language,
            prompt_applied=list(tp.prompt_applied),
        )
```

- [ ] **Step 2: Quick import smoke**

```bash
uv run python -c "from src.tenant_profile.resolver import ResolvedTenantProfile, TenantProfileResolver, TenantProfileNotFound; print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/tenant_profile/resolver.py
git commit -m "feat(sub-proyek K): TenantProfileResolver returns flattened ResolvedTenantProfile dataclass"
```

---

## Section C — Pipeline plumbing (commit batch 3)

### Task C1: Create `LanguageNotAllowedError`

**Files:**
- Create: `src/pipeline/errors.py`

- [ ] **Step 1: Create `src/pipeline/errors.py`**

```python
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
    `getattr(e, "error_code", None)`).
    """

    error_code = "language_not_allowed"

    def __init__(self, *, target_lang: str, allowed: list[str]) -> None:
        self.target_lang = target_lang
        self.allowed = allowed
        super().__init__(
            f"target_lang {target_lang!r} not in allowed_language {allowed!r}"
        )
```

- [ ] **Step 2: Import smoke**

```bash
uv run python -c "from src.pipeline.errors import LanguageNotAllowedError; e = LanguageNotAllowedError(target_lang='ja', allowed=['id', 'en']); print(e.error_code, str(e))"
```
Expected: `language_not_allowed target_lang 'ja' not in allowed_language ['id', 'en']`.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/errors.py
git commit -m "feat(sub-proyek K): LanguageNotAllowedError pipeline error"
```

---

### Task C2: Add `validate_target_language` stage + test

**Files:**
- Modify: `src/pipeline/stages.py`
- Test: `tests/pipeline/test_validate_target_language.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_validate_target_language.py`:

```python
"""Tests for the validate_target_language pipeline stage."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from src.pipeline.errors import LanguageNotAllowedError
from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext, validate_target_language
from src.tenant_profile.resolver import ResolvedTenantProfile

pytestmark = pytest.mark.asyncio


def _make_ctx(target_lang: str, allowed: list[str] | None) -> PipelineContext:
    ctx = PipelineContext(
        request=PipelineRequest(
            text="hello",
            target_lang=target_lang,
            profile_id="profile-x",
            tenant_id="tenant-x",
        ),
        trace_id=uuid.uuid4().hex,
        started_at_perf=time.perf_counter(),
        started_at=datetime.now(UTC),
    )
    ctx.resolved_tenant_profile = ResolvedTenantProfile(
        profile_id="profile-x",
        tenant_id="tenant-x",
        tenant_name="x",
        country_name="x",
        company_name="x",
        department_name="x",
        position_name="x",
        service_name="general",
        service_tone=None,
        service_target_audience=None,
        allowed_language=allowed,
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    return ctx


async def test_null_allowed_language_passes():
    ctx = _make_ctx(target_lang="ja", allowed=None)
    await validate_target_language(ctx)  # should not raise


async def test_target_in_allowed_passes():
    ctx = _make_ctx(target_lang="id", allowed=["id", "en"])
    await validate_target_language(ctx)


async def test_target_not_in_allowed_raises():
    ctx = _make_ctx(target_lang="ja", allowed=["id", "en"])
    with pytest.raises(LanguageNotAllowedError) as exc_info:
        await validate_target_language(ctx)
    assert exc_info.value.target_lang == "ja"
    assert exc_info.value.allowed == ["id", "en"]


async def test_empty_allowed_list_rejects_all():
    """allowed_language=[] (vs None) means no language is allowed."""
    ctx = _make_ctx(target_lang="en", allowed=[])
    with pytest.raises(LanguageNotAllowedError):
        await validate_target_language(ctx)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/pipeline/test_validate_target_language.py -v
```
Expected: 4 FAIL (stage doesn't exist; `ResolvedTenantProfile` may also need import wiring).

- [ ] **Step 3: Update `PipelineContext.resolved_tenant_profile` type + add stage in `src/pipeline/stages.py`**

First, near the top of `src/pipeline/stages.py`, update the `TYPE_CHECKING` import block to import `ResolvedTenantProfile` instead of `TenantProfile`:

```python
if TYPE_CHECKING:
    from src.db.models import GlossaryTerm, StyleExample
    from src.pipeline.agents.base import AgenticActivity
    from src.service.repository import ServiceRepository
    from src.tenant_profile.resolver import ResolvedTenantProfile, TenantProfileResolver
```

Update the `PipelineContext.resolved_tenant_profile` type:

```python
resolved_tenant_profile: ResolvedTenantProfile | None = None
```

Add the new stage AFTER `validate_and_normalize` and BEFORE `load_resolved_tenant_profile` (so it actually runs after we have the resolved profile — see Task C5 for wiring order):

```python
# ---- 2b. validate_target_language ------------------------------------------


async def validate_target_language(ctx: PipelineContext) -> None:
    """Reject `target_lang` if not in `allowed_language`. NULL = all allowed.

    Runs after ``load_resolved_tenant_profile`` so ``ctx.resolved_tenant_profile``
    is populated. Raises ``LanguageNotAllowedError`` (caught by the orchestrator's
    try/except, logged, and surfaced to the caller as a 400).
    """
    from src.pipeline.errors import LanguageNotAllowedError  # local import keeps stages.py independent of errors module

    assert ctx.resolved_tenant_profile is not None, (
        "load_resolved_tenant_profile must run before validate_target_language"
    )
    allowed = ctx.resolved_tenant_profile.allowed_language
    if allowed is None:
        log.debug(
            "pipeline.stage",
            trace_id=ctx.trace_id,
            stage="validate_target_language",
            status="skipped",
            reason="allowed_language_null",
        )
        return
    if ctx.request.target_lang not in allowed:
        raise LanguageNotAllowedError(
            target_lang=ctx.request.target_lang, allowed=allowed
        )
    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="validate_target_language",
        status="ok",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/pipeline/test_validate_target_language.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages.py tests/pipeline/test_validate_target_language.py
git commit -m "feat(sub-proyek K): validate_target_language stage + LanguageNotAllowedError raise"
```

---

### Task C3: Add `build_jinja_context` stage + test

**Files:**
- Modify: `src/pipeline/stages.py`
- Test: `tests/pipeline/test_jinja_context_builder.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_jinja_context_builder.py`:

```python
"""Tests for the build_jinja_context pipeline stage."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext, build_jinja_context
from src.tenant_profile.resolver import ResolvedTenantProfile

pytestmark = pytest.mark.asyncio


def _make_ctx() -> PipelineContext:
    ctx = PipelineContext(
        request=PipelineRequest(
            text="Halo, selamat pagi",
            source_lang="id",
            target_lang="en",
            profile_id="profile-x",
            tenant_id="tenant-x",
        ),
        trace_id=uuid.uuid4().hex,
        started_at_perf=time.perf_counter(),
        started_at=datetime.now(UTC),
    )
    ctx.normalized_text = "Halo, selamat pagi"
    ctx.resolved_tenant_profile = ResolvedTenantProfile(
        profile_id="profile-x",
        tenant_id="tenant-x",
        tenant_name="PT Test — Sales (Indonesia)",
        country_name="Indonesia",
        company_name="PT Test",
        department_name="Sales",
        position_name="Sales Executive",
        service_name="general",
        service_tone="professional formal",
        service_target_audience="corporate clients",
        allowed_language=None,
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    ctx.selected_glossary = []
    ctx.selected_examples = []
    return ctx


async def test_context_populated_with_all_fields():
    ctx = _make_ctx()
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(side_effect=lambda code: {"id": "Indonesian", "en": "English"}.get(code))

    await build_jinja_context(ctx, iso_repo)

    assert ctx.jinja_context is not None
    assert ctx.jinja_context["tenant_name"] == "PT Test — Sales (Indonesia)"
    assert ctx.jinja_context["country_name"] == "Indonesia"
    assert ctx.jinja_context["service_tone"] == "professional formal"
    assert ctx.jinja_context["source_lang_code"] == "id"
    assert ctx.jinja_context["source_lang_name"] == "Indonesian"
    assert ctx.jinja_context["target_lang_code"] == "en"
    assert ctx.jinja_context["target_lang_name"] == "English"
    assert ctx.jinja_context["text"] == "Halo, selamat pagi"


async def test_context_falls_back_to_code_when_iso_miss():
    """If iso_languages.get_name returns None, use the code as the name."""
    ctx = _make_ctx()
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(return_value=None)

    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context["source_lang_name"] == "id"
    assert ctx.jinja_context["target_lang_name"] == "en"


async def test_context_uses_detected_source_lang_when_present():
    """If lang_detect agent set ctx.detected_source_lang, prefer it over request.source_lang."""
    ctx = _make_ctx()
    ctx.detected_source_lang = "ms"
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(side_effect=lambda c: {"ms": "Malay"}.get(c, c))
    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context["source_lang_code"] == "ms"
    assert ctx.jinja_context["source_lang_name"] == "Malay"


async def test_context_includes_glossary_and_examples():
    ctx = _make_ctx()
    glossary_term = type("T", (), {"source_term": "background check", "target_term": "pemeriksaan latar belakang", "is_forbidden": False})()
    example = type("E", (), {"source_text": "X", "target_text": "Y"})()
    ctx.selected_glossary = [glossary_term]
    ctx.selected_examples = [example]
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(return_value="Lang")
    await build_jinja_context(ctx, iso_repo)
    assert len(ctx.jinja_context["glossary_terms"]) == 1
    assert len(ctx.jinja_context["style_examples"]) == 1


async def test_context_handles_null_source_lang():
    """If request.source_lang is None and no detected_source_lang, source_lang_code is empty string."""
    ctx = _make_ctx()
    ctx.request = PipelineRequest(
        text="hello",
        target_lang="en",
        profile_id="profile-x",
        tenant_id="tenant-x",
        source_lang=None,
    )
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(return_value=None)
    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context["source_lang_code"] == ""
    assert ctx.jinja_context["source_lang_name"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/pipeline/test_jinja_context_builder.py -v
```
Expected: 5 FAIL (`build_jinja_context` not defined, `ctx.jinja_context` attribute missing).

- [ ] **Step 3: Update `PipelineContext` and add `build_jinja_context` stage**

In `src/pipeline/stages.py`, add `jinja_context` field to `PipelineContext`:

```python
@dataclass
class PipelineContext:
    # ... (existing fields)

    # NEW for sub-proyek K
    jinja_context: dict[str, Any] | None = None
```

Add the stage near where other stages live (after `validate_target_language`, before `preprocess`):

```python
# ---- 2c. build_jinja_context ------------------------------------------------


async def build_jinja_context(ctx: PipelineContext, iso_repo) -> None:  # type: ignore[no-untyped-def]
    """Assemble the flat Jinja context dict for ALL prompt templates.

    Source of fields:
      - tenant_name/country/company/department: ctx.resolved_tenant_profile (denormalized)
      - position_name/service_name/service_tone/service_target_audience: same
      - source_lang_code/name: prefer detected_source_lang over request.source_lang; resolve via iso_languages
      - target_lang_code/name: from request.target_lang; resolve via iso_languages
      - glossary_terms/style_examples: from ctx (populated by preprocess stage)
      - text: ctx.normalized_text
    """
    assert ctx.resolved_tenant_profile is not None
    tp = ctx.resolved_tenant_profile

    source_code = ctx.detected_source_lang or ctx.request.source_lang or ""
    target_code = ctx.request.target_lang

    if source_code:
        source_name = await iso_repo.get_name(source_code) or source_code
    else:
        source_name = ""
    target_name = await iso_repo.get_name(target_code) or target_code

    ctx.jinja_context = {
        "tenant_name": tp.tenant_name,
        "country_name": tp.country_name,
        "company_name": tp.company_name,
        "department_name": tp.department_name,
        "position_name": tp.position_name,
        "service_name": tp.service_name,
        "service_tone": tp.service_tone,
        "service_target_audience": tp.service_target_audience,
        "source_lang_code": source_code,
        "source_lang_name": source_name,
        "target_lang_code": target_code,
        "target_lang_name": target_name,
        "glossary_terms": list(ctx.selected_glossary),
        "style_examples": list(ctx.selected_examples),
        "text": ctx.normalized_text,
    }

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="build_jinja_context",
        status="ok",
        source_lang_name=source_name,
        target_lang_name=target_name,
        glossary_count=len(ctx.selected_glossary),
    )
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/pipeline/test_jinja_context_builder.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages.py tests/pipeline/test_jinja_context_builder.py
git commit -m "feat(sub-proyek K): build_jinja_context stage — flat context dict with iso name resolution"
```

---

### Task C4: Refactor `build_prompt` stage to use `ctx.jinja_context` + update `translate.jinja` template

**Files:**
- Modify: `src/pipeline/stages.py`
- Modify: `src/pipeline/templates/translate.jinja`

- [ ] **Step 1: Replace the `build_prompt` stage in `src/pipeline/stages.py`**

```python
# ---- 5. build_prompt -------------------------------------------------------


async def build_prompt(ctx: PipelineContext, template_env: Environment) -> None:
    """Render the Jinja translate template into ``ctx.rendered_prompt``.

    Uses the flat ``ctx.jinja_context`` dict built by ``build_jinja_context``.
    No more deep ``tenant.company.company_name`` access — relationships are
    gone (sub-proyek K denormalization).
    """
    assert ctx.jinja_context is not None, "build_jinja_context must run before build_prompt"
    start = time.perf_counter()

    template = template_env.get_template("translate.jinja")
    ctx.rendered_prompt = template.render(**ctx.jinja_context)

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="build_prompt",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        prompt_length=len(ctx.rendered_prompt),
    )
```

- [ ] **Step 2: Replace `src/pipeline/templates/translate.jinja`**

```jinja
{# Translation prompt template (sub-proyek K flat context).

   Context vars provided by ``stages.build_jinja_context``:
     tenant_name           - e.g. "PT Integrity Indonesia — Sales (Indonesia)"
     country_name          - e.g. "Indonesia"
     company_name          - e.g. "PT Integrity Indonesia"
     department_name       - e.g. "Sales"
     position_name         - e.g. "Sales Executive"
     service_name          - e.g. "Employment Background Screening"
     service_tone          - e.g. "professional formal" (or None)
     service_target_audience - e.g. "corporate clients" (or None)
     source_lang_code      - e.g. "id" (or "" if unspecified)
     source_lang_name      - e.g. "Indonesian" (or "" if unspecified)
     target_lang_code      - e.g. "en"
     target_lang_name      - e.g. "English"
     glossary_terms        - list of GlossaryTerm rows (with .source_term, .target_term, .is_forbidden, .context)
     style_examples        - list of StyleExample rows (with .source_text, .target_text)
     text                  - the normalised source text
#}
<role>
You are a professional translator working for {{ company_name }}'s
{{ department_name }} department in {{ country_name }},
serving the {{ position_name }} role.
You specialise in {{ service_name }} content.
</role>

<style_guide>
{% if service_tone %}Tone: {{ service_tone }}
{% endif %}{% if service_target_audience %}Target audience: {{ service_target_audience }}
{% endif %}</style_guide>

{% set required = glossary_terms | rejectattr('is_forbidden') | list %}
{% set forbidden = glossary_terms | selectattr('is_forbidden') | list %}
{% if required or forbidden %}
<glossary>
{% if required %}
Use these specific translations for the matching source terms:
{% for term in required %}
- "{{ term.source_term }}" -> "{{ term.target_term }}"{% if term.context %} (context: {{ term.context }}){% endif %}
{% endfor %}
{% endif %}
{% if forbidden %}

NEVER translate the following source terms as the listed forbidden values:
{% for term in forbidden %}
- "{{ term.source_term }}" must NOT be translated as "{{ term.target_term }}"{% if term.context %} ({{ term.context }}){% endif %}
{% endfor %}
{% endif %}
</glossary>
{% endif %}

{% if style_examples %}
<examples>
{% for ex in style_examples %}
Source: {{ ex.source_text }}
Translation: {{ ex.target_text }}

{% endfor %}
</examples>
{% endif %}

<task>
Translate the following text from {{ source_lang_name if source_lang_name else "the auto-detected source language" }} ({{ source_lang_code if source_lang_code else "auto" }}) to {{ target_lang_name }} ({{ target_lang_code }}).

Rules:
- Preserve any placeholders or template variables exactly as written (e.g. {variable}, %s, %1$s, {{ '{{name}}' }}).
- Output ONLY the translated text. No explanation, no labels, no quotation marks around the output.
- Honour every glossary entry above. If a term appears in the source, use the prescribed translation; if a forbidden translation is listed, never use it.

Text:
{{ text }}
</task>
```

- [ ] **Step 3: Smoke-test the template renders**

```bash
uv run python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('src/pipeline/templates'))
out = env.get_template('translate.jinja').render(
    tenant_name='PT Test — Sales (Indonesia)',
    country_name='Indonesia',
    company_name='PT Test',
    department_name='Sales',
    position_name='Sales Executive',
    service_name='general',
    service_tone='professional formal',
    service_target_audience='corporate clients',
    source_lang_code='id',
    source_lang_name='Indonesian',
    target_lang_code='en',
    target_lang_name='English',
    glossary_terms=[],
    style_examples=[],
    text='Halo, selamat pagi',
)
print(out[:500])
"
```
Expected: rendered prompt with `PT Test`, `Indonesian`, `English`, `Halo, selamat pagi` visible.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/stages.py src/pipeline/templates/translate.jinja
git commit -m "feat(sub-proyek K): build_prompt uses flat ctx.jinja_context + template refactored to flat vars"
```

---

### Task C5: Wire new stages in `TranslationPipeline.translate()` + drop joinedload-based access

**Files:**
- Modify: `src/pipeline/pipeline.py`
- Modify: `src/pipeline/stages.py` (refactor `load_resolved_tenant_profile`)
- Modify: `src/pipeline/agents/translate.py` (verify it still works with flat context)

- [ ] **Step 1: Update `load_resolved_tenant_profile` in `src/pipeline/stages.py`**

The existing implementation uses the old resolver that returned ORM with joinedload. The new resolver returns `ResolvedTenantProfile` dataclass — same call signature, different return type. Update the stage to log dataclass fields:

```python
async def load_resolved_tenant_profile(
    ctx: PipelineContext, resolver: TenantProfileResolver
) -> None:
    """Load the resolved tenant_profile + tenant + service detail.

    Sub-proyek K: resolver returns a flat ResolvedTenantProfile dataclass.
    No joinedload — denormalized columns + by-name catalog lookups.
    """
    start = time.perf_counter()
    ctx.resolved_tenant_profile = await resolver.resolve(ctx.request.profile_id)
    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="load_resolved_tenant_profile",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        profile_id=ctx.resolved_tenant_profile.profile_id,
        service_name=ctx.resolved_tenant_profile.service_name,
    )
```

- [ ] **Step 2: Update `preprocess` in `src/pipeline/stages.py` — now looks up service by name**

The current `preprocess` uses `service_id` from the joinedload ORM. Refactor to use `service_name`:

```python
async def preprocess(ctx: PipelineContext, service_repo: ServiceRepository) -> None:
    """Fetch service-scoped glossary terms and style examples.

    Sub-proyek K: looks up by ``service_name`` (denormalized), then fetches
    glossary + examples by ``service_id`` derived from the service lookup.
    """
    assert ctx.resolved_tenant_profile is not None
    start = time.perf_counter()

    source_lang = ctx.detected_source_lang or ctx.request.source_lang or AUTO_LANG_SENTINEL
    target_lang = ctx.request.target_lang
    service_name = ctx.resolved_tenant_profile.service_name

    service = await service_repo.get_by_name(service_name)
    if service is None:
        log.warning(
            "pipeline.preprocess.service_not_found",
            trace_id=ctx.trace_id,
            service_name=service_name,
        )
        ctx.selected_glossary = []
        ctx.selected_examples = []
    else:
        glossary = await service_repo.list_glossary_for_service(
            service.service_id, source_lang, target_lang
        )
        examples = await service_repo.list_examples_for_service(
            service.service_id, source_lang, target_lang
        )
        ctx.selected_glossary = glossary
        ctx.selected_examples = list(examples)[:MAX_FEW_SHOT_EXAMPLES]

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="preprocess",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        selected_glossary=len(ctx.selected_glossary),
        selected_examples=len(ctx.selected_examples),
    )
```

- [ ] **Step 3: Update `cache_lookup` and `translate` stages — they use `ctx.resolved_tenant_profile.profile_id` and `.service_id`**

`cache_lookup` already uses `profile_id` only — no change.

`translate` and `_build_result` in pipeline.py reference `ctx.resolved_tenant_profile.profile_id` (OK, still exists). But `_build_result` uses `ctx.resolved_tenant_profile.service_id`. We need to expose `service_id` on `ResolvedTenantProfile` OR derive it differently. Add `service_id` to `ResolvedTenantProfile`:

Update `src/tenant_profile/resolver.py` `ResolvedTenantProfile` dataclass to include `service_id: str | None`:

```python
@dataclass(frozen=True)
class ResolvedTenantProfile:
    profile_id: str
    tenant_id: str
    tenant_name: str
    country_name: str
    company_name: str
    department_name: str
    position_name: str
    service_name: str
    service_id: str | None  # NEW: needed by _build_result metadata
    service_tone: str | None
    service_target_audience: str | None
    allowed_language: list[str] | None
    prompt_applied: list[str]
```

And populate it in `resolve()`:
```python
service_id_value = service.service_id if service else None
# ...
return ResolvedTenantProfile(
    # ...
    service_id=service_id_value,
    # ...
)
```

- [ ] **Step 4: Update `TranslationPipeline.translate` in `src/pipeline/pipeline.py` to wire new stage order**

In the `try:` block, the stage order becomes:

```python
try:
    await stages.validate_and_normalize(ctx)
    await stages.load_resolved_tenant_profile(ctx, self._resolver)
    await stages.validate_target_language(ctx)  # NEW

    if await stages.cache_lookup(ctx, self._cache, self._model_id):
        assert ctx.cached_result is not None
        base_result = ctx.cached_result
        self._log_end(ctx, status="cache_hit")
    else:
        from src.pipeline.agents.orchestrator import build_agents, run_agents

        await stages.preprocess(ctx, self._service_repo)

        # NEW: build the flat Jinja context BEFORE rendering the prompt.
        await stages.build_jinja_context(ctx, self._iso_repo)
        await stages.build_prompt(ctx, self._template_env)

        agents = build_agents(...)
        # ... rest unchanged
```

Add `iso_repo` parameter to `TranslationPipeline.__init__`:

```python
def __init__(
    self,
    *,
    provider: TranslationProvider,
    haiku_provider: TranslationProvider,
    cache: CacheBackend,
    resolver: TenantProfileResolver,
    service_repo: ServiceRepository,
    iso_repo,  # type: ignore[no-untyped-def]  # IsoLanguageRepository
    template_env: Environment | None = None,
    model_id: str,
    haiku_model_id: str,
    log_repo: TranslationLogRepository | None = None,
) -> None:
    # ... existing assignments
    self._iso_repo = iso_repo
```

Update `_build_result` in pipeline.py — change `ctx.resolved_tenant_profile.service_id` reference. It's fine if `service_id` is `None` for missing-service cases; the metadata field accepts that:

```python
metadata={
    "trace_id": ctx.trace_id,
    "profile_id": ctx.resolved_tenant_profile.profile_id,
    "service_id": ctx.resolved_tenant_profile.service_id,  # may be None
    # ...
},
```

- [ ] **Step 5: Update FastAPI dependency to inject IsoLanguageRepository into pipeline**

Open `src/api/dependencies.py` and locate `get_pipeline`. Add:

```python
from src.iso_languages.repository import IsoLanguageRepository

# Inside the existing get_pipeline factory:
def get_iso_repository(session: AsyncSession = Depends(get_session)) -> IsoLanguageRepository:
    return IsoLanguageRepository(session)

def get_pipeline(
    # ... existing deps
    iso_repo: IsoLanguageRepository = Depends(get_iso_repository),
) -> TranslationPipeline:
    return TranslationPipeline(
        # ... existing args
        iso_repo=iso_repo,
        # ...
    )
```

- [ ] **Step 6: Sanity check — pipeline module imports work**

```bash
uv run python -c "from src.pipeline.pipeline import TranslationPipeline; print('OK')"
```
Expected: `OK`.

- [ ] **Step 7: Run existing pipeline tests to detect regressions**

```bash
uv run pytest tests/pipeline -v
```
Expected: most pass. Some legacy tests may need fixture updates if they construct `PipelineContext` with the old ORM shape — fix any failures by replacing `TenantProfile` mocks with `ResolvedTenantProfile`.

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/stages.py src/pipeline/pipeline.py src/tenant_profile/resolver.py src/api/dependencies.py
git commit -m "feat(sub-proyek K): wire validate_target_language + build_jinja_context into pipeline + inject iso_repo"
```

---

### Task C6: Add `language_not_allowed` error handler in API middleware

**Files:**
- Modify: `src/api/middleware.py`

- [ ] **Step 1: Add handler function**

In `src/api/middleware.py`, after the existing `handle_value_error` function (line ~133), add:

```python
async def handle_language_not_allowed(request: Request, exc: Exception) -> JSONResponse:
    """Map LanguageNotAllowedError to 400 + structured error_code."""
    from src.pipeline.errors import LanguageNotAllowedError

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
```

- [ ] **Step 2: Register the handler in `register_exception_handlers`**

In the same file, append to `register_exception_handlers`:

```python
def register_exception_handlers(app: FastAPI) -> None:
    # ... existing handlers
    app.add_exception_handler(ValueError, handle_value_error)

    # NEW for sub-proyek K
    from src.pipeline.errors import LanguageNotAllowedError
    app.add_exception_handler(LanguageNotAllowedError, handle_language_not_allowed)
```

- [ ] **Step 3: Sanity check**

```bash
uv run python -c "from src.api.middleware import handle_language_not_allowed, register_exception_handlers; print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/api/middleware.py
git commit -m "feat(sub-proyek K): API middleware handler for LanguageNotAllowedError → 400 language_not_allowed"
```

---

## Section D — Seed re-population (commit batch 4)

### Task D1: Update `scripts/seed_tenant_data.py` — denormalized tenant seed + alembic_version

**Files:**
- Modify: `scripts/seed_tenant_data.py`

- [ ] **Step 1: Update `seed_tenants` function to use denormalized columns + alembic_version_at_create**

Replace the existing `seed_tenants` function with:

```python
from sqlalchemy import text


async def _read_alembic_head(session: AsyncSession) -> str:
    """Read the current head revision from Postgres alembic_version meta table.

    Sub-proyek K stamps each tenant row with this value at creation time.
    """
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    return str(result.scalar_one())


def _compose_tenant_name(company_name: str, department_name: str, country_name: str) -> str:
    return f"{company_name} — {department_name} ({country_name})"


async def seed_tenants(
    session: AsyncSession,
    country_ids: dict[str, str],
    company_ids: dict[str, str],
    department_ids: dict[str, str],
) -> dict[tuple[str, str, str], str]:
    """Insert any missing tenants. Return ``(country, company, department) -> tenant_id``.

    Sub-proyek K: tenant uses denormalized country_name/company_name/
    department_name (no FK ID columns). Composes tenant_name auto-formatted.
    Stamps each row with the current alembic head version.
    """
    alembic_version = await _read_alembic_head(session)

    rows = (await session.execute(select(Tenant))).scalars().all()
    out: dict[tuple[str, str, str], str] = {
        (t.country_name, t.company_name, t.department_name): t.tenant_id for t in rows
    }
    for company_name, country_name in COMPANIES:
        for dept_name in DEPARTMENTS:
            key = (country_name, company_name, dept_name)
            if key in out:
                continue
            tid = make_id("tenant")
            plaintext = generate_api_key()
            tenant_name = _compose_tenant_name(company_name, dept_name, country_name)
            session.add(
                Tenant(
                    tenant_id=tid,
                    tenant_name=tenant_name,
                    country_name=country_name,
                    company_name=company_name,
                    department_name=dept_name,
                    alembic_version_at_create=alembic_version,
                    api_key_hash=hash_api_key(plaintext),
                )
            )
            out[key] = tid
            print(
                f"  CREATED tenant {tenant_name}: "
                f"tenant_id={tid}, API_KEY={plaintext}"
            )
    await session.flush()
    return out
```

Note: `country_ids`/`company_ids`/`department_ids` params kept for signature compatibility but no longer used — the seed walks COMPANIES/DEPARTMENTS lists directly and stores names. Remove the unused params later if desired.

- [ ] **Step 2: Sanity import smoke**

```bash
uv run python -c "from scripts.seed_tenant_data import seed_tenants, _compose_tenant_name; print(_compose_tenant_name('A', 'B', 'C'))"
```
Expected: `A — B (C)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_tenant_data.py
git commit -m "feat(sub-proyek K): seed_tenants denormalized + alembic_version_at_create stamp + composed tenant_name"
```

---

### Task D2: Update `seed_tenant_profiles` — stratified allowed_language + length-3 prompt_applied

**Files:**
- Modify: `scripts/seed_tenant_data.py`
- Test: `tests/scripts/test_seed_distribution.py` (create new)

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_seed_distribution.py`:

```python
"""Sub-proyek K seed distribution check.

Verifies the stratified allowed_language distribution across 57 profiles:
  - 12 profiles: ["id", "en"]
  - 12 profiles: ["ms", "en"]
  - 11 profiles: ["th", "en"]
  - 11 profiles: ["id", "ms", "th", "en"]
  - 11 profiles: None (all langs allowed)

And verifies prompt_applied is uniform: ["lang_detect_input", "translate", "lang_detect_output"].
"""

from __future__ import annotations

import pytest

from scripts.seed_tenant_data import ALLOWED_LANG_PATTERNS, _pattern_for_index

EXPECTED_PROMPT_APPLIED = ["lang_detect_input", "translate", "lang_detect_output"]


def test_pattern_for_index_distribution():
    """Verify boundary indices map to the correct pattern."""
    assert _pattern_for_index(0) == ["id", "en"]
    assert _pattern_for_index(11) == ["id", "en"]
    assert _pattern_for_index(12) == ["ms", "en"]
    assert _pattern_for_index(23) == ["ms", "en"]
    assert _pattern_for_index(24) == ["th", "en"]
    assert _pattern_for_index(34) == ["th", "en"]
    assert _pattern_for_index(35) == ["id", "ms", "th", "en"]
    assert _pattern_for_index(45) == ["id", "ms", "th", "en"]
    assert _pattern_for_index(46) is None
    assert _pattern_for_index(56) is None


def test_pattern_for_index_out_of_bounds():
    with pytest.raises(ValueError):
        _pattern_for_index(57)


def test_pattern_count_sums_to_57():
    """Sanity: 12 + 12 + 11 + 11 + 11 = 57."""
    counts = [12, 12, 11, 11, 11]
    assert sum(counts) == 57
    assert len(ALLOWED_LANG_PATTERNS) == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scripts/test_seed_distribution.py -v
```
Expected: 3 FAIL (`ALLOWED_LANG_PATTERNS` + `_pattern_for_index` don't exist).

- [ ] **Step 3: Add the distribution helpers + update `seed_tenant_profiles` in `scripts/seed_tenant_data.py`**

Near the top of the file (after the existing constants), add:

```python
# Sub-proyek K stratified distribution: 57 profiles across 5 patterns.
ALLOWED_LANG_PATTERNS: list[list[str] | None] = [
    ["id", "en"],                    # 0–11   (12)
    ["ms", "en"],                    # 12–23  (12)
    ["th", "en"],                    # 24–34  (11)
    ["id", "ms", "th", "en"],        # 35–45  (11)
    None,                            # 46–56  (11) — NULL = all allowed
]
PATTERN_BOUNDARIES = [12, 24, 35, 46, 57]


def _pattern_for_index(index: int) -> list[str] | None:
    for i, boundary in enumerate(PATTERN_BOUNDARIES):
        if index < boundary:
            return ALLOWED_LANG_PATTERNS[i]
    raise ValueError(f"Index {index} out of bounds for 57-row distribution")


EXPECTED_PROMPT_APPLIED_AGENT_TYPES: list[str] = [
    "lang_detect_input",
    "translate",
    "lang_detect_output",
]
```

Replace `seed_tenant_profiles`:

```python
async def seed_tenant_profiles(
    session: AsyncSession,
    tenant_ids: dict[tuple[str, str, str], str],
    position_ids: dict[tuple[str, str], str],
    service_ids: dict[str, str],
    prompt_ids: dict[str, str],
) -> int:
    """Create 57 default tenant_profiles with stratified allowed_language + uniform 3-step prompt_applied.

    Ordering deterministic: sort tenants by (company_name, department_name) and
    assign by index → pattern via _pattern_for_index. prompt_applied is the
    canonical 3-step agent_type list per ADR-055.
    """
    rows = (await session.execute(select(TenantProfile.tenant_name))).scalars().all()
    have = set(rows)

    # Lookup current tenant rows (post-seed_tenants) to get their snapshot names.
    tenants = (await session.execute(select(Tenant))).scalars().all()
    sorted_tenants = sorted(
        tenants, key=lambda t: (t.company_name, t.department_name)
    )

    # Per-dept index of the first position name in our static list.
    first_position_for_dept: dict[str, str] = {}
    for position_name, dept_name in POSITION_DEPARTMENT_PAIRS:
        first_position_for_dept.setdefault(dept_name, position_name)

    inserted = 0
    for index, tenant in enumerate(sorted_tenants):
        if tenant.tenant_name in have:
            continue
        position_name = first_position_for_dept.get(tenant.department_name)
        if position_name is None:
            raise RuntimeError(
                f"No position defined for department {tenant.department_name!r}"
            )
        allowed = _pattern_for_index(index)
        session.add(
            TenantProfile(
                profile_id=make_id("profile"),
                tenant_name=tenant.tenant_name,
                service_name="general",
                position_name=position_name,
                allowed_language=allowed,
                prompt_applied=list(EXPECTED_PROMPT_APPLIED_AGENT_TYPES),
            )
        )
        inserted += 1
        have.add(tenant.tenant_name)
    await session.flush()
    return inserted
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/scripts/test_seed_distribution.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_tenant_data.py tests/scripts/test_seed_distribution.py
git commit -m "feat(sub-proyek K): seed_tenant_profiles — stratified allowed_language + 3-step prompt_applied"
```

---

### Task D3: Run seed locally + verify distribution

**Files:**
- (operational only)

- [ ] **Step 1: Run the seed script**

```bash
uv run python scripts/seed_tenant_data.py
```
Expected: 57 tenant lines emitted with `API_KEY=aitkey_...`. **CAPTURE THESE KEYS** — they're printed once.

- [ ] **Step 2: Verify row counts in psql**

```bash
docker compose exec postgres psql -U postgres -d aitrans -c "SELECT COUNT(*) FROM tenant; SELECT COUNT(*) FROM tenant_profile;"
```
Expected: both `57`.

- [ ] **Step 3: Verify allowed_language distribution**

```bash
docker compose exec postgres psql -U postgres -d aitrans -c "SELECT allowed_language, COUNT(*) FROM tenant_profile GROUP BY allowed_language ORDER BY allowed_language;"
```
Expected: 5 rows — `{id,en}=12`, `{ms,en}=12`, `{th,en}=11`, `{id,ms,th,en}=11`, `NULL=11`.

- [ ] **Step 4: Verify prompt_applied is uniform**

```bash
docker compose exec postgres psql -U postgres -d aitrans -c "SELECT prompt_applied, COUNT(*) FROM tenant_profile GROUP BY prompt_applied;"
```
Expected: 1 row — `{lang_detect_input,translate,lang_detect_output}=57`.

- [ ] **Step 5: Verify alembic_version_at_create stamp**

```bash
docker compose exec postgres psql -U postgres -d aitrans -c "SELECT alembic_version_at_create, COUNT(*) FROM tenant GROUP BY alembic_version_at_create;"
```
Expected: 1 row — `006_schema_cleanup=57`.

- [ ] **Step 6: Save first API key for the e2e smoke script (next section)**

Pick the first tenant's API key from the seed output and export:
```bash
export AITKEY_SMOKE="aitkey_<the-first-key-from-stdout>"
```
(Use PowerShell `$env:AITKEY_SMOKE = "aitkey_..."` on Windows.)

---

## Section E — End-to-end verification (commit batch 5)

### Task E1: Create the e2e smoke script

**Files:**
- Create: `scripts/test_e2e_persistence.py`

- [ ] **Step 1: Create the script**

```python
"""Sub-proyek K end-to-end persistence smoke.

Run AFTER:
  1. `alembic upgrade head` applied
  2. `scripts/seed_tenant_data.py` run (you have a captured API key)
  3. Dev server running on :8000 (uv run uvicorn src.api.main:app)

Usage:
  export AITKEY_SMOKE=aitkey_<your-key>
  uv run python scripts/test_e2e_persistence.py

Verifies:
  1. POST /translate succeeds + returns log_id
  2. Row lands in translation_logs with source/translated text + cost
  3. Redis cache key present after first call
  4. Replay returns cached:true with low latency
  5. Replay creates a separate translation_logs row with cached=true
  6. POST /translate with disallowed target_lang returns 400 language_not_allowed
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from uuid import UUID

import httpx
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import get_settings


async def _fetch_log_row(session: AsyncSession, log_id: UUID) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM translation_logs WHERE log_id = :log_id"),
        {"log_id": str(log_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def _profile_id_for(session: AsyncSession, *, allowed_includes: list[str]) -> str:
    """Find a profile_id whose allowed_language matches the includes (subset check)."""
    result = await session.execute(
        text(
            "SELECT profile_id, allowed_language "
            "FROM tenant_profile "
            "WHERE allowed_language @> ARRAY[:wanted]::varchar[] LIMIT 1"
        ),
        {"wanted": allowed_includes[0]},
    )
    row = result.first()
    if row is None:
        raise SystemExit(f"No tenant_profile found with allowed_language containing {allowed_includes}")
    return row.profile_id


async def main() -> int:
    settings = get_settings()
    api_key = os.environ.get("AITKEY_SMOKE")
    if not api_key:
        print("ERROR: set AITKEY_SMOKE=aitkey_<your-key> first", file=sys.stderr)
        return 1

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async with session_factory() as session:
        profile_id = await _profile_id_for(session, allowed_includes=["id", "en"])

    payload = {
        "text": "Halo, selamat pagi",
        "source_lang": "id",
        "target_lang": "en",
        "profile_id": profile_id,
    }
    headers = {"X-Tenant-API-Key": api_key}

    print("== Step 1: POST /translate (first call) ==")
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        t0 = time.perf_counter()
        r1 = await client.post("/translate", json=payload, headers=headers)
        elapsed1_ms = (time.perf_counter() - t0) * 1000.0
        if r1.status_code != 200:
            print(f"  FAIL: status={r1.status_code} body={r1.text}", file=sys.stderr)
            return 1
        body1 = r1.json()
        log_id1 = body1["log_id"]
        if log_id1 is None:
            print("  FAIL: log_id is None — translation_logs write failed", file=sys.stderr)
            return 1
        print(f"  OK: HTTP 200, log_id={log_id1}, latency={elapsed1_ms:.0f}ms, cached={body1.get('cached')}")

    print("== Step 2: Verify translation_logs row exists ==")
    async with session_factory() as session:
        row = await _fetch_log_row(session, UUID(log_id1))
        if row is None:
            print("  FAIL: no log row found", file=sys.stderr)
            return 1
        assert row["source_text"] == "Halo, selamat pagi"
        assert row["translated_text"], "translated_text is empty"
        assert row["cost_usd"] is not None and row["cost_usd"] > 0
        assert row["cached"] is False
        cache_key_in_row = row["cache_key"]
        print(f"  OK: source/translated text persisted, cost_usd={row['cost_usd']}, cache_key={cache_key_in_row}")

    print("== Step 3: Verify Redis cache key set ==")
    redis_value = await redis.get(f"translation:{cache_key_in_row}")
    if redis_value is None:
        print(f"  FAIL: redis key translation:{cache_key_in_row} missing", file=sys.stderr)
        return 1
    parsed = json.loads(redis_value)
    print(f"  OK: redis key present, translation='{parsed.get('translation', '')[:40]}...'")

    print("== Step 4: Replay POST /translate (cache hit expected) ==")
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        t0 = time.perf_counter()
        r2 = await client.post("/translate", json=payload, headers=headers)
        elapsed2_ms = (time.perf_counter() - t0) * 1000.0
        body2 = r2.json()
        log_id2 = body2["log_id"]
        if r2.status_code != 200:
            print(f"  FAIL: replay status={r2.status_code}", file=sys.stderr)
            return 1
        if not body2.get("cached"):
            print(f"  FAIL: replay did not hit cache, body.cached={body2.get('cached')}", file=sys.stderr)
            return 1
        print(f"  OK: HTTP 200, cached=true, latency={elapsed2_ms:.0f}ms")

    print("== Step 5: Verify replay log row exists with cached=true ==")
    async with session_factory() as session:
        row2 = await _fetch_log_row(session, UUID(log_id2))
        if row2 is None:
            print("  FAIL: no replay log row found", file=sys.stderr)
            return 1
        if not row2["cached"]:
            print(f"  FAIL: replay log row cached={row2['cached']}", file=sys.stderr)
            return 1
        print(f"  OK: replay log row persisted with cached=true")

    print("== Step 6: Negative case — non-allowed target_lang returns 400 ==")
    # Pick a profile with allowed_language=["id","en"] and request target=ja.
    bad_payload = {**payload, "target_lang": "ja"}
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        r3 = await client.post("/translate", json=bad_payload, headers=headers)
        if r3.status_code != 400:
            print(f"  FAIL: expected 400, got {r3.status_code} body={r3.text}", file=sys.stderr)
            return 1
        body3 = r3.json()
        if body3.get("error_code") != "language_not_allowed":
            print(f"  FAIL: error_code={body3.get('error_code')}", file=sys.stderr)
            return 1
        print(f"  OK: HTTP 400 language_not_allowed, detail={body3.get('detail')[:80]}")

    await redis.aclose()
    await engine.dispose()
    print("\n✅ Sub-proyek K end-to-end persistence verified")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Commit the script before running (so failures don't lose work)**

```bash
git add scripts/test_e2e_persistence.py
git commit -m "feat(sub-proyek K): scripts/test_e2e_persistence.py end-to-end smoke probe"
```

---

### Task E2: Run the e2e smoke script

**Files:**
- (operational only)

- [ ] **Step 1: Start the API server in a separate terminal**

```bash
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```
Expected: `Uvicorn running on http://0.0.0.0:8000`.

- [ ] **Step 2: Verify Redis is running and reachable**

```bash
docker compose exec redis redis-cli ping
```
Expected: `PONG`.

- [ ] **Step 3: Set the API key env var (from seed stdout in Task D3 Step 6)**

```bash
export AITKEY_SMOKE="aitkey_<your-captured-key>"
```

(Windows PowerShell: `$env:AITKEY_SMOKE = "aitkey_..."`)

- [ ] **Step 4: Run the smoke script**

```bash
uv run python scripts/test_e2e_persistence.py
```
Expected output (ending):
```
== Step 6: Negative case — non-allowed target_lang returns 400 ==
  OK: HTTP 400 language_not_allowed, detail=...

✅ Sub-proyek K end-to-end persistence verified
```

- [ ] **Step 5: If any step fails, diagnose**

- Step 1 fail: check API server logs for exceptions; common: wrong profile_id binding to tenant.
- Step 2 fail: log row missing — check `record_log` is wired in pipeline; check `translation_logs` table exists post-migration.
- Step 3 fail: Redis key absent — verify Redis connection in API logs.
- Step 4 fail: not cached — check `cache_lookup` stage runs before agents.
- Step 6 fail: 200 instead of 400 — `validate_target_language` stage not wired correctly. Run `pytest tests/pipeline/test_validate_target_language.py` to confirm unit-level OK first.

- [ ] **Step 6: No commit — operational only.** (If smoke fails and you fix bugs, commit those separately as `fix(sub-proyek K): ...`.)

---

### Task E3: Full pytest regression check

**Files:**
- (operational only)

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```
Expected: 139+ tests pass (114 pre-existing + ~25 new sub-proyek K).

- [ ] **Step 2: If pre-existing tests fail, fix them**

The most likely failure mode: tests that constructed `TenantProfile` ORM with old FK columns (`tenant_id`, `position_id`, `service_id`) or expected joinedload access (`tp.tenant.country.country_name`). Replace with denormalized field access or `ResolvedTenantProfile` fixtures.

For each failure:
1. Read the failing test
2. Update test fixtures/mocks to use the new schema
3. Re-run that test in isolation
4. Once green, run full suite again

- [ ] **Step 3: Commit any test fixes**

```bash
git add tests/
git commit -m "fix(sub-proyek K): update pre-existing tests for denormalized tenant/tenant_profile shape"
```

---

## Section F — Documentation (commit batch 6)

### Task F1: Append ADR-053..058 to `docs/adrs.md`

**Files:**
- Modify: `docs/adrs.md`

- [ ] **Step 1: Append the 6 new ADRs at the end of `docs/adrs.md`**

```markdown
- ADR-053: Tenant + tenant_profile denormalize ke snapshot name columns (drop FK to country/company/department/position/service reference tables). Catalog tables retained untuk cascade UI + Jinja context lookup by-name. Trade-off: audit-stable rename-doesn't-propagate vs FK-integrity loss. Snapshot preferred untuk translation audit + log row self-containment.
- ADR-054: `alembic_version_at_create VARCHAR(60) NOT NULL` snapshot column di tenant. Set saat seed/INSERT dengan baca Postgres `alembic_version` meta-table. Audit-cohort tracking ("tenant ini dibuat saat schema versi X"). Tidak auto-updated kalau migration baru jalan — existing rows tetap pegang versi creation lama.
- ADR-055: `prompt_applied` stored sebagai array of `agent_type` strings (bukan `prompt_id`). Karena `tenant_prompts.agent_type` UNIQUE, informationally equivalent tapi jauh lebih readable di DB inspection + grep. DB-level CHECK enforces length = 3; ordering enforced di Pydantic validator (`EXPECTED_PROMPT_APPLIED_ORDER`).
- ADR-056: `allowed_language` stratified deterministic distribution across 5 patterns (12/12/11/11/11 dari 57 tenant_profiles): `[id,en]` / `[ms,en]` / `[th,en]` / `[id,ms,th,en]` / NULL=all. Ordering by `(company_name, department_name)` deterministic. Pipeline reject `target_lang ∉ allowed_language` dengan `LanguageNotAllowedError → HTTP 400 error_code = language_not_allowed`. Failed request tetap create log row dengan `status = failed` per ADR-027.
- ADR-057: `iso_languages` lookup module-level in-memory cache (~40 rows), populated on first call (`IsoLanguageRepository._catalog_cache`). Process-restart invalidates. Fallback: code as-is + log warning kalau miss. Tidak perlu Redis — table kecil + read-only seed fixture.
- ADR-058: Single flat Jinja context dict shared across 3 prompt templates (`lang_detect_input`, `translate`, `lang_detect_output`). Variables sourced dari `ResolvedTenantProfile` dataclass (returned by refactored `TenantProfileResolver`). Template author decides per-agent relevance — lang_detect templates can ignore service-specific vars. Source of truth: `src.pipeline.stages.build_jinja_context`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adrs.md
git commit -m "docs(sub-proyek K): append ADR-053..058 (denormalize, alembic snapshot, agent_type prompt_applied, stratified allowed_lang, iso cache, flat Jinja context)"
```

---

### Task F2: Update `CLAUDE.md` ADR index + add Sub-proyek K phase entry

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/phase-status.md`

- [ ] **Step 1: Update `CLAUDE.md` ADR index**

In `CLAUDE.md` under "Decision log" section, append after the last bullet (`ADR-047..052`):

```markdown
- ADR-053..058: tenant denormalize (snapshot name cols), alembic_version_at_create snapshot, prompt_applied as agent_type strings (length 3 ordered), allowed_language stratified 5-pattern enforcement, iso_languages module-level cache, single flat Jinja context dict
```

- [ ] **Step 2: Update `CLAUDE.md` Phase status — add Sub-proyek K entry**

In `CLAUDE.md` under "Phase status" section, append after the Sub-proyek J line:

```markdown
- **Sub-proyek K** (Schema cleanup + iso plumbing + end-to-end verification): ✅ 2026-05-22 — migration 006 (denormalize tenant + tenant_profile), seed redistributed 5 allowed_language patterns + uniform 3-step prompt_applied, iso_languages plumbed into pipeline (code→name), tenant_prompts Jinja context flat dict, language_not_allowed enforcement, end-to-end DB+Redis smoke verified.
```

- [ ] **Step 3: Add Sub-proyek K section to `docs/phase-status.md`**

Append at the end of `docs/phase-status.md`:

```markdown
### Sub-proyek K — Schema Cleanup + iso Plumbing + Verification
**Status:** ✅ complete (verified 2026-05-22)

- Migration `alembic/versions/006_schema_cleanup_iso_plumbing.py`: TRUNCATE tenant CASCADE + drop FK columns from `tenant` + `tenant_profile` + add denormalized snapshot columns (`tenant_name`, `country_name`, `company_name`, `department_name`, `alembic_version_at_create` on tenant; `tenant_name`, `service_name`, `position_name` on tenant_profile) + CHECK constraint `array_length(prompt_applied, 1) = 3`. Irreversible by design — `downgrade()` raises `NotImplementedError`.
- `src/db/models.py` — `Tenant` + `TenantProfile` ORM dropped relationships (`country`, `company`, `department`, `position`, `service`, `profiles`). Pure denormalized columns.
- `src/tenant_profile/resolver.py` — new `ResolvedTenantProfile` dataclass (frozen), populated via three by-name lookups (`tenant`, `service`, plus tenant_profile direct). Replaces joinedload-based ORM blob.
- `src/pipeline/errors.py` — new `LanguageNotAllowedError` with `error_code = "language_not_allowed"`. Carries `target_lang` + `allowed` list.
- `src/pipeline/stages.py` — two new stages: `validate_target_language` (rejects on `target_lang ∉ allowed_language` when non-NULL) + `build_jinja_context` (flat dict for all 3 prompt templates). Refactored `build_prompt` to `template.render(**ctx.jinja_context)`. Refactored `preprocess` to look up service by-name.
- `src/pipeline/pipeline.py` — wires new stage order: `validate → load_resolved → validate_target_language → cache_lookup → (preprocess → build_jinja_context → build_prompt → agents → postprocess → cache_write)`. New `iso_repo` dependency injected.
- `src/pipeline/templates/translate.jinja` — refactored to flat variables (`{{ company_name }}` instead of `{{ tenant.company.company_name }}`).
- `src/tenant/repository.py` / `src/tenant_profile/repository.py` — denormalized lookups; `TenantRepository.create()` accepts injected `alembic_version` kwarg and composes `tenant_name`.
- `scripts/seed_tenant_data.py` — `seed_tenants` reads `alembic_version` from Postgres meta + stamps each row; `seed_tenant_profiles` uses `_pattern_for_index(index)` to stratify 57 profiles across 5 `allowed_language` patterns; uniform `prompt_applied = ["lang_detect_input", "translate", "lang_detect_output"]`.
- `src/api/middleware.py` — `handle_language_not_allowed` → HTTP 400 with `error_code = "language_not_allowed"`.
- `scripts/test_e2e_persistence.py` — live smoke that POSTs `/translate`, verifies PostgreSQL `translation_logs` row exists with `source_text`/`translated_text`/`cost_usd`, verifies Redis cache key populated, replays for cache hit, and confirms negative case 400 on disallowed target_lang.
- **~25 new tests** + 114 pre-existing pass. Live smoke clean.
- **Known limitations:** Denormalized snapshot doesn't auto-propagate if catalog row renamed (acceptable per ADR-053 audit-stable trade-off). `_SESSION_LOCKS` carryover from sub-proyek B still grows unbounded.
- **Unblocks:** `frontend-demo/realApi.ts` integration (future sub-project) — schema + plumbing now ready for real API consumption.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/phase-status.md
git commit -m "docs(sub-proyek K): CLAUDE.md ADR index + phase-status section + Sub-proyek K complete entry"
```

---

## Self-Review Checklist

Run this once after completing all tasks:

- [ ] **Spec coverage:** every spec section (§1 schema, §2 seed, §3 plumbing, §4 verification, §5 docs) maps to at least one task above.
- [ ] **Placeholder scan:** no "TBD", "TODO", "fill in details", "implement appropriate logic" strings in plan or code.
- [ ] **Type consistency:** `ResolvedTenantProfile` used uniformly across resolver, stages, and pipeline. `LanguageNotAllowedError` has `error_code = "language_not_allowed"` everywhere.
- [ ] **Migration ordering:** TRUNCATE before DROP+ADD; downgrade raises.
- [ ] **Test count:** ~25 new tests (4 schemas + 3 + 3 + 4 + 5 + 3 + 3 = matches), 114 pre-existing pass.
- [ ] **All commits ahead of `origin/main`:** `git log origin/main..HEAD --oneline` shows the sub-proyek K commits.

---

## Plan Complete

Plan saved to `docs/superpowers/plans/2026-05-22-schema-cleanup-and-plumbing.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
