# Design — Schema Cleanup + iso_languages Plumbing + tenant_prompts Dynamism + DB/Redis Verification (Sub-proyek K)

> **Tanggal**: 2026-05-22
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: K — schema cleanup + iso_languages plumbing + tenant_prompts dynamism + end-to-end persistence verification
> **Depends on**: sub-proyek I (tenant junction schema as starting point), sub-proyek B (translation_logs persistence layer)
> **Unblocks**: real-API integration di `frontend-demo/` (replace `mockApi.ts` dengan `realApi.ts`); future dashboard sub-projects yang baca translation_logs

---

## 1. Konteks & motivasi

Sub-proyek I (commit `824ac8d`) men-set up tenant junction model dengan FK ke 3 reference tables (`country`, `company`, `department`) + nested junction `tenant_profile` dengan FK ke `position` + `service`. Model itu benar untuk catalog cascade UI di frontend, tapi user feedback (2026-05-22) menyatakan **tenant + tenant_profile rows seharusnya self-contained snapshot**, bukan FK-driven:

- Operator-facing operations (translation_logs audit, prompt rendering, allowed-language enforcement) butuh nama langsung, bukan ID. Tiap operation harus joinedload 3-5 reference tables — overhead + dependency yang tidak perlu.
- Snapshot semantics: kalau company di-rename di catalog (e.g. legal entity rename), tenant row + downstream translation_logs harus tetap menyimpan nama saat row dibuat — audit trail stability.
- `iso_languages` table sudah ter-seed di sub-proyek I tapi **belum diplumb** ke pipeline — lang_detect agent sekarang return code, prompt translate dapat code, tidak dapat name (e.g. "id" bukan "Indonesian"). LLM diberi prompt yang menyebut "id" → semantically poorer dibanding "Indonesian".
- `tenant_prompts.template` cuma terima subset variable dari context — kalau operator mau prompt lebih dinamis ("Anda adalah {{position_name}} di {{department_name}} {{company_name}}, berdomisili di {{country_name}}, menerjemahkan {{service_name}}..."), context dict belum lengkap.
- End-to-end persistence (Postgres `translation_logs` + Redis cache key) belum di-verify secara live setelah sub-proyek I redesign — last live verification adalah Phase 4 di pre-redesign model.

Sub-proyek K addresses semua 4 di atas dalam satu coherent migration + plumbing + verification cycle.

---

## 2. Goals & non-goals

**Goals:**
- Migration `006_schema_cleanup_iso_plumbing.py` drop FK columns dari `tenant` + `tenant_profile`, replace dengan snapshot name columns + `alembic_version_at_create`.
- Re-seed 57 tenants + 57 tenant_profiles dengan denormalized data, `prompt_applied = ["lang_detect_input", "translate", "lang_detect_output"]` (uniform), `allowed_language` stratified 5 patterns.
- `iso_languages` lookup utility + pipeline plumbing: code-to-name resolution sebelum render translate prompt.
- `tenant_prompts` Jinja context expansion: expose semua field tenant/profile + service detail + iso lang names + glossary + examples + text.
- `allowed_language` enforcement stage di pipeline: reject `target_lang` mismatches dengan HTTP 400.
- End-to-end live smoke verifying `/translate` writes to PostgreSQL `translation_logs` AND populates Redis cache key (idempotent replay → cache hit).
- 114 pre-existing tests + ~25 new tests pass.

**Non-goals:**
- Bukan multi-tenant cross-DB partitioning — tetap single Postgres + single Redis.
- Bukan operator-facing UI untuk edit tenant_prompts templates — admin endpoint reserved untuk future.
- Bukan vector-search glossary — exact-match retrieval (sub-proyek I default) tetap dipakai.
- Bukan `realApi.ts` di frontend-demo — itu sub-proyek terpisah (future). Sub-proyek K hanya verify backend end-to-end via `scripts/`.
- Bukan rollback migration — `downgrade()` raises NotImplementedError (sesuai precedent sub-proyek I).
- Bukan ordering enforcement DB-level untuk `prompt_applied` (Pydantic validator handles ordering; CHECK constraint hanya enforce length 3).
- Bukan operator-overrideable distribution untuk `allowed_language` — deterministic stratified seed only.

---

## 3. Keputusan utama

### 3.1 Snapshot denormalization (FK drop, name columns)

`tenant` & `tenant_profile` rows menyimpan **string snapshots** dari nama country/company/department/position/service saat row dibuat. Reference tables (`country`, `company`, `department`, `position`, `service`, `iso_languages`, `tenant_prompts`) **tetap dipertahankan** sebagai catalog untuk:
- Cascade UI di frontend (Country → Company → Department → Position → Service dropdown chains).
- `tenant_prompts` Jinja context: prompt rendering looks up service detail (tone, target_audience, glossary, examples) by-name via repository method.
- Future admin UI: edit country/company/department names sambil mempertahankan snapshot history di existing tenant rows.

**Trade-off:** snapshot tidak auto-propagate kalau reference row di-rename. Operator harus manually update tenant rows (atau accept historical name). Diterima karena:
1. Audit/log stability — translation_logs query "what was company X doing at time Y" reproducible tanpa join risk.
2. Rename di reference catalog jarang terjadi untuk MVP scope.
3. Tenant rows adalah contract entities — pinning nama di point of creation lebih akurat dari business perspective.

**Alternative rejected:** keep FKs + add name columns (hybrid). Rejected karena redundansi tanpa added benefit — denormalized snapshot sudah cukup untuk semua use cases.

### 3.2 `tenant_name` auto-generated dari composite

`tenant_name` di seed: `f"{company_name} — {department_name} ({country_name})"` (em-dash separator, country in parens). Contoh: `"PT Aitegrity — Customer Service (Indonesia)"`. UNIQUE constraint di DB.

**Trade-off:** human-readable + self-documenting. Tidak fully canonical (kalau company di-rename di catalog, tenant_name + composite (company_name, department_name, country_name) drift). Acceptable per §3.1 snapshot semantics.

### 3.3 `prompt_applied` semantics: array of agent_type strings (length 3, ordered)

Schema sekarang `ARRAY(String(30))`. Sub-proyek I seed ngisi dengan `prompt_id` strings. Sub-proyek K re-seed dengan literal `agent_type` strings:

```python
prompt_applied = ["lang_detect_input", "translate", "lang_detect_output"]
```

**Why agent_type bukan prompt_id?** `tenant_prompts.agent_type` sudah UNIQUE — keduanya informationally equivalent, tapi agent_type strings jauh lebih readable di DB inspection + grep. Tidak ada loss-of-fidelity.

**DB-level constraint:** CHECK `array_length(prompt_applied, 1) = 3`. Ordering enforced di Pydantic validator (`PromptAppliedValidator`), bukan DB (would need stored procedure — over-engineering).

**Trade-off:** sub-proyek I existing data harus di-overwrite (destructive re-seed). Acceptable — seed re-runs idempotent skip-if-exists untuk reference tables, destructive untuk tenant + tenant_profile.

### 3.4 `allowed_language` stratified deterministic distribution

5 pattern seeded across 57 tenant_profiles dengan stride 12 (ordering by `(company_name, department_name)`):

| Index range | Allowed languages | Count |
|---|---|---|
| 0–11 | `["id", "en"]` | 12 |
| 12–23 | `["ms", "en"]` | 12 |
| 24–34 | `["th", "en"]` | 11 |
| 35–45 | `["id", "ms", "th", "en"]` | 11 |
| 46–56 | `NULL` (all langs allowed) | 11 |

Deterministic by ordering pair = reproducible setiap re-seed. Tidak per-country (sub-proyek I cuma punya 3 country distributions, tidak cukup variety untuk 5 pattern coverage).

**Enforcement:** new pipeline stage `validate_target_language` after `validate_and_normalize`. Check `target_lang ∈ tenant_profile.allowed_language` kalau bukan NULL. Mismatch → `LanguageNotAllowedError → HTTP 400 error_code = "language_not_allowed"`. Failed request tetap creates `translation_logs` row dengan `status = "failed"` (per ADR-027 record_log finally pattern).

### 3.5 `alembic_version_at_create` snapshot column

Tambah kolom `alembic_version_at_create VARCHAR(60) NOT NULL` ke `tenant`. Saat seed:

```python
# Read current head from Postgres meta table
result = await session.execute(text("SELECT version_num FROM alembic_version"))
current_version = result.scalar_one()  # e.g. "006_schema_cleanup_iso_plumbing"
# Set di tenant row creation
tenant = Tenant(..., alembic_version_at_create=current_version, ...)
```

Audit purpose: "tenant dibuat saat schema versi X". Tidak auto-update — kalau migration baru jalan, existing tenant rows tetap pegang versi creation lama. Future analysis: `SELECT alembic_version_at_create, COUNT(*) FROM tenant GROUP BY alembic_version_at_create` untuk track tenant cohort per schema generation.

**Alternative rejected:** mirror current schema version (update via trigger). Rejected karena lose audit history + trigger overhead.

### 3.6 `iso_languages` lookup plumbing

`src/iso_languages/repository.py` extend dengan:

```python
async def get_language_name(self, code: str) -> str | None:
    """Resolve BCP-47 code → English name. None if not in table."""
```

Caller (`src/pipeline/stages.py` new helper) wraps fallback:
```python
def resolve_lang_name(repo, code: str) -> str:
    name = await repo.get_language_name(code)
    if name is None:
        logger.warning("iso_language_miss", code=code)
        return code  # fallback to code as-is
    return name
```

In-memory cache: module-level dict populated saat first call (iso_languages ~40 rows; tidak perlu Redis — small + read-only).

**Trade-off:** in-memory cache invalidated on process restart only. Kalau operator adds new iso row, restart-required. Acceptable — iso_languages adalah seed-time fixture, jarang di-update.

### 3.7 Jinja context dict (uniform across 3 prompt templates)

Orchestrator builds 1 context dict, render semua 3 templates dengan dict yang sama:

```python
{
    "tenant_name": str,
    "country_name": str,
    "company_name": str,
    "department_name": str,
    "position_name": str,
    "service_name": str,
    "service_tone": str | None,
    "service_target_audience": str | None,
    "source_lang_code": str,        # e.g. "id"
    "source_lang_name": str,        # e.g. "Indonesian"
    "target_lang_code": str,
    "target_lang_name": str,
    "glossary_terms": list[dict],   # resolved from service
    "style_examples": list[dict],   # resolved from service
    "text": str,                    # input
}
```

**Variabel sources:**
- `tenant_name`, `country_name`, `company_name`, `department_name`: tenant row (denormalized)
- `position_name`, `service_name`: tenant_profile row (denormalized)
- `service_tone`, `service_target_audience`, `glossary_terms`, `style_examples`: lookup `service` table by `service_name` (catalog query)
- `source_lang_name`, `target_lang_name`: iso_languages lookup (§3.6)
- `source_lang_code`, `target_lang_code`: passthrough dari request
- `text`: passthrough dari request

**Lang detect specific:** untuk `lang_detect_input` agent, `source_lang_code/name` belum diketahui (itulah yang dideteksi). Template pakai placeholder `"unknown"` atau hanya akses `target_lang_code/name`. Konvensi: template author decides.

### 3.8 Rollout strategy: Opsi A — One migration, four-stage commit

Single migration 006 + sequential commits dalam 1 branch:
1. Commit 1: migration 006 + ORM model update (schema only)
2. Commit 2: seed script update + run (data refresh)
3. Commit 3: pipeline plumbing (iso lookup + Jinja context + allowed_language stage)
4. Commit 4: verification script + tests

Konsisten dengan sub-proyek I & J pattern (single coherent change per sub-proyek).

---

## 4. Schema changes (migration 006)

### 4.1 `tenant` table

| Operation | Column | Type | Constraint |
|---|---|---|---|
| DROP | `country_id` | VARCHAR(30) FK | — |
| DROP | `company_id` | VARCHAR(30) FK | — |
| DROP | `department_id` | VARCHAR(30) FK | — |
| DROP CONSTRAINT | `uq_tenant_ccd` | composite UNIQUE | — |
| ADD | `tenant_name` | VARCHAR(150) | UNIQUE NOT NULL |
| ADD | `country_name` | VARCHAR(60) | NOT NULL |
| ADD | `company_name` | VARCHAR(100) | NOT NULL |
| ADD | `department_name` | VARCHAR(80) | NOT NULL |
| ADD | `alembic_version_at_create` | VARCHAR(60) | NOT NULL |
| ADD CONSTRAINT | `uq_tenant_ccd_names` | composite UNIQUE | (country_name, company_name, department_name) |

**Unchanged:** `tenant_id` (PK), `api_key_hash`, `jwt_active_token`, `jwt_refreshed_at`, `created_at`, index `ix_tenant_api_key_hash`.

### 4.2 `tenant_profile` table

| Operation | Column | Type | Constraint |
|---|---|---|---|
| DROP | `tenant_id` | VARCHAR(30) FK | — |
| DROP | `position_id` | VARCHAR(30) FK | — |
| DROP | `service_id` | VARCHAR(30) FK | — |
| DROP CONSTRAINT | `uq_tenant_profile_tps` | composite UNIQUE | — |
| DROP INDEX | `ix_tenant_profile_tenant_id` | — | — |
| ADD | `tenant_name` | VARCHAR(150) | NOT NULL |
| ADD | `service_name` | VARCHAR(100) | NOT NULL |
| ADD | `position_name` | VARCHAR(120) | NOT NULL |
| ADD CONSTRAINT | `uq_tenant_profile_tps_names` | composite UNIQUE | (tenant_name, position_name, service_name) |
| ADD CONSTRAINT | `ck_prompt_applied_length` | CHECK | array_length(prompt_applied, 1) = 3 |
| ADD INDEX | `ix_tenant_profile_tenant_name` | — | (tenant_name) |

**Unchanged:** `profile_id` (PK), `allowed_language`, `prompt_applied`, `created_at`.

### 4.3 `translation_logs` table — unchanged

`tenant_id` FK to `tenant.tenant_id` masih valid (PK retained). `profile_id` FK to `tenant_profile.profile_id` masih valid. Tidak ada perubahan ke translation_logs schema di migration 006.

### 4.4 ORM model changes (`src/db/models.py`)

- `Tenant.country` / `.company` / `.department` SQLAlchemy relationships → DROP. Repository method `get_country_by_name(name) → Country` etc untuk catalog lookups.
- `TenantProfile.tenant` / `.position` / `.service` relationships → DROP. Repository method `get_service_by_name(name) → Service` (used by Jinja context builder untuk tone/target_audience/glossary/examples lookup).
- New ORM column attributes match §4.1 + §4.2.

### 4.5 Migration ordering (upgrade)

**Critical:** ADD NOT NULL columns ke tabel yang punya existing rows akan FAIL (no default value to backfill). Karena seed akan destructive re-seed setelah migration, paling clean: TRUNCATE existing rows DI DALAM migration, lalu DROP+ADD columns ke empty table.

1. `op.execute("TRUNCATE TABLE tenant CASCADE")` — clears tenant + tenant_profile (FK ondelete CASCADE dari sub-proyek I); sets `translation_logs.tenant_id` + `.profile_id` ke NULL (FK ondelete SET NULL). Operator API keys hilang dari DB; harus capture ulang saat seed re-run.
2. ALTER TABLE `tenant_profile` DROP CONSTRAINT `uq_tenant_profile_tps`, DROP INDEX `ix_tenant_profile_tenant_id`, DROP COLUMN `tenant_id`, DROP COLUMN `position_id`, DROP COLUMN `service_id`.
3. ALTER TABLE `tenant` DROP CONSTRAINT `uq_tenant_ccd`, DROP COLUMN `country_id`, DROP COLUMN `company_id`, DROP COLUMN `department_id`.
4. ALTER TABLE `tenant` ADD COLUMN `tenant_name`, `country_name`, `company_name`, `department_name`, `alembic_version_at_create` (semua NOT NULL — aman karena tabel kosong).
5. ALTER TABLE `tenant` ADD CONSTRAINT `uq_tenant_ccd_names`.
6. ALTER TABLE `tenant_profile` ADD COLUMN `tenant_name`, `service_name`, `position_name` (NOT NULL — aman, tabel kosong).
7. ALTER TABLE `tenant_profile` ADD CONSTRAINT `uq_tenant_profile_tps_names`, ADD CONSTRAINT `ck_prompt_applied_length`, ADD INDEX `ix_tenant_profile_tenant_name`.

**Side effect translation_logs:** existing log rows kehilangan FK reference ke tenant/profile (di-SET NULL). Audit history teks (source_text, translated_text, cost) preserved; cuma identity link broken. Acceptable untuk sub-proyek scope — pre-K logs adalah pre-redesign data anyway.

**Downgrade:** `raise NotImplementedError("Sub-proyek K migration is irreversible by design.")`

---

## 5. Seed values (`scripts/seed_tenant_data.py` extended)

### 5.1 Mode: destructive for tenant + tenant_profile

Reference tables (`country`, `company`, `department`, `position`, `service`, `iso_languages`, `tenant_prompts`): tetap idempotent skip-if-exists (sudah seeded di sub-proyek I, tidak perlu re-create).

`tenant` + `tenant_profile`: TRUNCATE CASCADE lalu repopulate. Karena schema columns berubah, existing rows tidak compatible. Output: API keys printed to stdout sekali saat creation (sub-proyek I behavior preserved).

### 5.2 Tenant seed (57 rows)

**Source of country_name:** lookup `country` reference table by `company.company_country` (sub-proyek I stores country as denormalized string di company; sub-proyek K resolves it to canonical `country.country_name` for tenant snapshot). Fallback: kalau lookup miss, pakai `company.company_country` as-is + log warning.

**Source of alembic_version_at_create:** read at seed runtime dari Postgres meta:
```python
result = await session.execute(text("SELECT version_num FROM alembic_version"))
current_alembic_version = result.scalar_one()  # e.g. "006_schema_cleanup_iso_plumbing"
```

**Seed loop:**
```python
for company in companies:
    country = await country_repo.get_by_name(company.company_country)
    country_name = country.country_name if country else company.company_country
    for department in departments:
        tenant_name = f"{company.company_name} — {department.department_name} ({country_name})"
        api_key_plain = f"aitkey_{secrets.token_urlsafe(32)}"
        tenant = Tenant(
            tenant_id=make_id("tenant"),
            tenant_name=tenant_name,
            country_name=country_name,
            company_name=company.company_name,
            department_name=department.department_name,
            api_key_hash=hash_api_key(api_key_plain),
            alembic_version_at_create=current_alembic_version,
            jwt_active_token=None,
            jwt_refreshed_at=None,
        )
        session.add(tenant)
        print(f"[tenant created] {tenant_name}: {api_key_plain}")  # stdout once
```

### 5.3 Tenant_profile seed (57 rows, stratified)

Ordering deterministic: `sorted(tenants, key=lambda t: (t.company_name, t.department_name))`. Pattern assignment by index:

```python
ALLOWED_LANG_PATTERNS: list[list[str] | None] = [
    ["id", "en"],                    # 0-11
    ["ms", "en"],                    # 12-23
    ["th", "en"],                    # 24-34
    ["id", "ms", "th", "en"],        # 35-45
    None,                            # 46-56
]
PATTERN_BOUNDARIES = [12, 24, 35, 46, 57]

def pattern_for(index: int) -> list[str] | None:
    for i, boundary in enumerate(PATTERN_BOUNDARIES):
        if index < boundary:
            return ALLOWED_LANG_PATTERNS[i]
    raise ValueError(f"Index {index} out of bounds")

for index, tenant in enumerate(sorted_tenants):
    profile = TenantProfile(
        profile_id=make_id("profile"),
        tenant_name=tenant.tenant_name,
        position_name=first_position_for(department_name),  # convention: first listed
        service_name="general",                              # convention: default service
        allowed_language=pattern_for(index),
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    session.add(profile)
```

**Note:** position_name = first position listed for the department (sub-proyek I seed convention). service_name = `"general"` (sub-proyek I seed convention for default service).

---

## 6. Pipeline plumbing

### 6.1 iso_languages lookup utility

```python
# src/iso_languages/repository.py
class IsoLanguageRepository:
    _name_cache: dict[str, str] = {}  # module-level, populated on first call

    async def get_language_name(self, code: str) -> str | None:
        if not self._name_cache:
            await self._load_all()
        return self._name_cache.get(code)

    async def _load_all(self) -> None:
        result = await self._session.execute(select(IsoLanguage.code, IsoLanguage.name))
        for code, name in result.all():
            self._name_cache[code] = name
```

Fallback caller:
```python
# src/pipeline/stages.py (new helper)
async def resolve_lang_name(repo: IsoLanguageRepository, code: str) -> str:
    name = await repo.get_language_name(code)
    if name is None:
        logger.warning("iso_language_miss", code=code)
        return code
    return name
```

### 6.2 Pipeline stage: `validate_target_language`

```python
async def validate_target_language(ctx: PipelineContext) -> None:
    if ctx.tenant_profile.allowed_language is None:
        return  # NULL = all languages allowed
    if ctx.request.target_lang not in ctx.tenant_profile.allowed_language:
        raise LanguageNotAllowedError(
            target_lang=ctx.request.target_lang,
            allowed=ctx.tenant_profile.allowed_language,
        )
```

Position di stages list: after `validate_and_normalize`, before `cache_lookup`.

### 6.3 Pipeline stage: build Jinja context

```python
async def build_jinja_context(ctx: PipelineContext) -> None:
    service = await service_repo.get_by_name(ctx.tenant_profile.service_name)
    source_name = await resolve_lang_name(iso_repo, ctx.detected_source_lang or ctx.request.source_lang)
    target_name = await resolve_lang_name(iso_repo, ctx.request.target_lang)
    ctx.jinja_context = {
        "tenant_name": ctx.tenant.tenant_name,
        "country_name": ctx.tenant.country_name,
        "company_name": ctx.tenant.company_name,
        "department_name": ctx.tenant.department_name,
        "position_name": ctx.tenant_profile.position_name,
        "service_name": ctx.tenant_profile.service_name,
        "service_tone": service.tone,
        "service_target_audience": service.target_audience,
        "source_lang_code": ctx.detected_source_lang or ctx.request.source_lang,
        "source_lang_name": source_name,
        "target_lang_code": ctx.request.target_lang,
        "target_lang_name": target_name,
        "glossary_terms": ctx.resolved_glossary,
        "style_examples": ctx.resolved_examples,
        "text": ctx.normalized_text,
    }
```

### 6.4 Repository changes (drop FK-based relationships)

`src/tenant/repository.py` + `src/tenant_profile/repository.py`:
- Drop `joinedload(Tenant.country/company/department)` calls — denormalized columns sudah ada.
- Add `get_by_tenant_name(name) → Tenant` helper (used by tenant_profile queries that previously FK-joined).

`src/service/repository.py`:
- Existing `get_by_id(service_id) → Service` retained.
- Add `get_by_name(service_name) → Service` (used by Jinja context builder).

Same untuk `country` / `company` / `department` / `position` repositories: add `get_by_name(...)` helpers.

### 6.5 Error mapping (`src/api/middleware.py`)

```python
@app.exception_handler(LanguageNotAllowedError)
async def language_not_allowed_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "language_not_allowed",
            "detail": f"target_lang '{exc.target_lang}' not in allowed_language {exc.allowed}",
            "trace_id": request.state.trace_id,
        },
    )
```

---

## 7. Verification

### 7.1 End-to-end live smoke script

`scripts/test_e2e_persistence.py`:

```python
async def main():
    # Step 1: POST /translate
    api_key = os.environ["AITKEY_SMOKE"]  # first tenant from seed stdout
    response = await client.post(
        "/translate",
        json={"text": "Halo, selamat pagi", "source_lang": "id", "target_lang": "en"},
        headers={"X-Tenant-API-Key": api_key},
    )
    assert response.status_code == 200
    log_id = response.json()["log_id"]
    assert log_id is not None

    # Step 2: SELECT translation_logs WHERE log_id = ...
    row = await db.fetch_one("SELECT * FROM translation_logs WHERE log_id = $1", log_id)
    assert row is not None
    assert row["source_text"] == "Halo, selamat pagi"
    assert row["translated_text"] is not None
    assert row["cost_usd"] > 0
    assert row["cached"] is False

    # Step 3: GET Redis cache key
    cache_key = row["cache_key"]
    cached_value = await redis.get(cache_key)
    assert cached_value is not None  # JSON payload

    # Step 4: Replay same POST → cache hit
    response2 = await client.post("/translate", ...)
    assert response2.status_code == 200
    assert response2.json()["cached"] is True
    assert response2.elapsed_ms < 50

    # Step 5: Verify replay log row
    log_id2 = response2.json()["log_id"]
    row2 = await db.fetch_one("SELECT cached FROM translation_logs WHERE log_id = $1", log_id2)
    assert row2["cached"] is True

    print("✅ E2E persistence verified")
```

Run setelah migration + seed + dev server started.

### 7.2 Negative case (allowed_language enforcement)

```python
# Get tenant_profile dengan allowed_language = ["id", "en"]
response = await client.post(
    "/translate",
    json={"text": "Halo", "source_lang": "id", "target_lang": "ja"},  # ja NOT in allowed
    headers={"X-Tenant-API-Key": ...},
)
assert response.status_code == 400
assert response.json()["error_code"] == "language_not_allowed"

# Verify failed log row created
log_id = response.json().get("log_id")  # may be None if context too incomplete
if log_id:
    row = await db.fetch_one("SELECT status FROM translation_logs WHERE log_id = $1", log_id)
    assert row["status"] == "failed"
```

### 7.3 Unit tests (~25 new)

| Module | Test count | What |
|---|---|---|
| `tests/iso_languages/test_repository.py` | 5 | cache populate, hit, miss, fallback, restart-invalidation |
| `tests/pipeline/test_validate_target_language.py` | 4 | NULL bypass, allowed, denied, edge (empty list) |
| `tests/pipeline/test_jinja_context_builder.py` | 5 | all fields populated, service lookup, lang resolution, glossary/examples included, missing service warn |
| `tests/db/test_migration_006.py` | 2 | upgrade-from-005 smoke, downgrade raises NotImplementedError |
| `tests/scripts/test_seed_distribution.py` | 3 | pattern distribution correctness, ordering deterministic, alembic_version_at_create populated |
| `tests/tenant/test_repository_denormalized.py` | 3 | new column queries, get_by_name lookup, no joinedload |
| `tests/tenant_profile/test_repository_denormalized.py` | 3 | new column queries, get_by_name, prompt_applied validation |

### 7.4 Regression gate

Full `pytest` run: 114 pre-existing tests + 25 new = 139 target. CI must pass before merge.

---

## 8. ADRs (new)

- **ADR-053:** Tenant + tenant_profile denormalize ke snapshot name columns (drop FK to reference tables). Catalog tables retained untuk cascade UI + Jinja context lookup. Trade-off: audit-stable rename-doesn't-propagate vs ergonomic write-once vs FK-integrity loss. Snapshot preferred untuk translation audit context.
- **ADR-054:** `alembic_version_at_create` snapshot column di tenant. Set at seed/INSERT time by reading Postgres `alembic_version` meta table. Audit-cohort tracking. Not auto-updated.
- **ADR-055:** `prompt_applied` di-store sebagai array of `agent_type` strings (bukan `prompt_id`). Equivalent karena `tenant_prompts.agent_type` UNIQUE; jauh lebih readable di DB inspection. CHECK constraint length=3; ordering enforced di Pydantic.
- **ADR-056:** `allowed_language` stratified deterministic distribution across 5 patterns (12/12/11/11/11 dari 57 tenant_profiles). NULL = all allowed. Pipeline reject `target_lang` mismatches dengan HTTP 400 `language_not_allowed`.
- **ADR-057:** `iso_languages` lookup module-level in-memory cache (~40 rows), populated on first call. Process-restart invalidates. Fallback: code as-is + log warning kalau miss.
- **ADR-058:** Single Jinja context dict shared across 3 prompt templates (lang_detect_input, translate, lang_detect_output). Template author decides which fields relevant per agent.

ADRs akan ditambah ke `docs/adrs.md` dengan one-liner di CLAUDE.md sesuai pattern sub-proyek J.

---

## 9. Out of scope (deferred to future sub-projects)

- Replace `frontend-demo/src/services/mockApi.ts` dengan `realApi.ts` yang hit `/translate` real.
- Multi-position concurrent assignment per tenant_profile.
- Vector-search glossary retrieval.
- Operator-facing UI untuk edit `tenant_prompts.template`.
- `allowed_language` per-source/target asymmetric pairs (saat ini symmetric — kalau ID allowed, source+target keduanya bisa ID).
- Cron rotation untuk `tenant.jwt_active_token`.
- Audit log untuk reference table renames yang affect downstream snapshots.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Destructive re-seed wipes existing operator API keys | API keys printed to stdout ONLY on first seed run; operator MUST capture. Sub-proyek I sudah established this pattern. |
| Denormalized name columns drift dari catalog kalau reference renamed | Acceptable per §3.1 snapshot semantics. Future ADR-driven decision kalau drift becomes pain. |
| Module-level iso_languages cache stale after operator adds new row | Restart-required to refresh. Iso_languages adalah seed-time fixture per ADR — acceptable. |
| 114 existing tests rely on FK-based relationships | Gate: full pytest run; fix any breakages individually (likely small surface — most tests use TenantRepository, not raw model attrs). |
| LanguageNotAllowedError path tidak create log row kalau context too incomplete | Acceptable per ADR-027 record_log nullable log_id; pipeline still returns 400. |
| Live smoke script requires running dev server + valid API key from seed | Document prerequisites in script docstring; one-time setup. |
