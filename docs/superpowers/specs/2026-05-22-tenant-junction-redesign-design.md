# Design — Tenant Junction Redesign + Auth (Sub-proyek I)

> **Tanggal**: 2026-05-22
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: I — bundling Items 1-8 from user feedback after sub-proyek H attempt
> **Replaces**: sub-proyek H (Phases 1-5 stashed; the rename + expansion strategy was rejected in favour of a clean junction-style redesign)
> **Depends on**: sub-proyek B (translation_logs forward columns), D (Aitegrity products as service catalog), G+C (agents + tenant_id flow)
> **Unblocks**: dashboard sub-proyek F; future operator self-service portal

---

## 1. Konteks & motivasi

Sub-proyek H mencoba rename + expand model `profile` → `tenant_profile` dengan menambah dimensional fields (company, department, role, service). Setelah implementasi penuh (Phases 1-5), user review menyatakan model itu **salah secara konseptual**:

- "Tenant" tidak cukup dimodelkan sebagai `(company, department)` composite — operator perlu lebih banyak dimensi (country, position, service).
- Glossary + style examples seharusnya per-service, bukan per-tenant_profile (banyak service-level glossary di-repeat across profiles).
- Tone/audience seharusnya pre-defined per-service (not per-profile config).
- API key authentication should be deployed across all endpoints — defer-to-J yang awalnya disetujui sekarang dibundel di I karena tightly couples dengan tenant identity.

Sub-proyek I restructures the model as a **junction-style data layout**:

- 5 reference tables (country, company, department, position, service) hold the dimensional values.
- `tenant` table is a junction of (country, company, department) — each row represents one organizational unit. 57 rows seeded (3 companies × 19 departments).
- `tenant_profile` table is a nested junction of (position, service) per tenant. 57 rows seeded (1 default per tenant).
- `tenant_prompts` table re-keyed by `prompt_id` (was `agent_type` PK).
- Glossary + examples FK-attached to `service`.
- Tone/audience moved to `service` table.
- Tenant auth (API key + JWT) baked into the tenant table.

## 2. Goals & non-goals

**Goals:**
- Drop sub-proyek H tables; rebuild a clean junction-style schema.
- Implement 5 new reference tables + tenant junction + tenant_profile junction + tenant_prompts re-keyed.
- Move tone/audience/glossary/examples to service.
- API key + JWT auth on tenant; middleware on all non-public endpoints.
- Seed: 7 countries, 3 companies, 19 departments, 83 positions, 16 services, 57 tenants (with API keys), 57 tenant_profiles, 3 prompts, ~40 iso_languages.
- Streamlit form cascade: Country → Company → Department → Position → Service → Glossary preview → Source → Target.
- Custom human-readable ID format `{prefix}-{8hex}-{4hex}` for all PKs.

**Non-goals:**
- Bukan multi-position concurrent assignment (1 profile = 1 position per row; multiple profiles per tenant for multi-position needs).
- Bukan operator-facing prompt-edit UI (admin endpoint `tenant_prompts.update` reserved for future).
- Bukan full RBAC; auth is tenant-scoped (every tenant can do everything its tenant_profiles allow).
- Bukan automatic daily JWT cron — MVP uses on-demand `POST /auth/refresh-jwt`. Cron-driven rotation deferred.
- Bukan tenant.name composite display field (`tenant.tenant_id` is the identifier; UI composes display from FK joins).
- Bukan position-department mapping junction table (position has direct `department_id` FK; one position belongs to exactly one department per current data).
- Bukan recovery flow for forgotten API key (operator re-issues via admin endpoint; old key invalidated).

## 3. Keputusan utama

### 3.1 Junction tables instead of denormalized rename

`tenant` table is a junction of 3 reference tables (`country` + `company` + `department`). `tenant_profile` is nested junction of (`position` + `service`) attached to a tenant. Compare to sub-proyek H which denormalized everything into `tenant` + `tenant_profile` directly. Junctions allow:
- Reusing reference values without duplication
- Query-by-dimension naturally (e.g., "all tenants in Indonesia")
- Validated FK relationships at DB level

**Alternative rejected**: continue sub-proyek H denormalized approach. Rejected per user signal that the conceptual model needs to mirror real organizational dimensions.

### 3.2 Custom ID format `{prefix}-{8hex}-{4hex}`

All PKs use this format. Generated via `f"{prefix}-{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[8:12]}"`. 48 bits entropy (collision-safe for MVP scale per ADR-012 precedent of truncated cache keys). Trade-off: more readable than full UUID, less standard. Helper function in `src/db/ids.py`.

Prefix conventions:
- `country-XXXXXXXX-XXXX`
- `company-XXXXXXXX-XXXX`
- `department-XXXXXXXX-XXXX`
- `position-XXXXXXXX-XXXX`
- `service-XXXXXXXX-XXXX`
- `tenant-XXXXXXXX-XXXX`
- `profile-XXXXXXXX-XXXX`
- `prompt-XXXXXXXX-XXXX`

### 3.3 Tone, audience, glossary, examples → moved to `service`

Per user choice: tone/audience are characteristic of a service (Fraud Investigation has consistent forensic tone regardless of which company/department/position runs it). Glossary terms similarly belong per-service (a "fraud" glossary applies anywhere a service is offered). Reduces data duplication; future service-level prompt customization more natural.

**Alternative rejected**: tone/audience per-position (Data Scientist tone differs from CEO tone). Rejected because positions across services are too heterogeneous to share tone; service is the more stable scope.

### 3.4 Position has `department_id` FK

Position table includes `department_id NOT NULL REFERENCES department`. 83 rows × 1 department each. Enforces the position-department mapping at DB level (per user list: "Analyst - Brand Protection" and "Analyst - Due Diligence" are different rows because they belong to different departments).

**Alternative rejected**: position global (3-col as user literally spec'd) — rejected because the 83 position-department pairs imply enforced association.

### 3.5 Tenant auth: API key (argon2 hashed) + lightweight JWT

API key generated on tenant creation, plaintext returned ONCE, only hash persisted. JWT issued on `POST /auth/refresh-jwt`, stored in `tenant.jwt_active_token`. Middleware accepts either:
- `Authorization: Bearer <jwt>` (faster, signature + expiry verify)
- `X-Tenant-API-Key: aitkey_...` (always valid until tenant deleted)

**Public endpoints** (no auth): `/health`, `/health/deep`, `/countries`, `/companies?country=`, `/departments`, `/iso-languages`, `/auth/refresh-jwt` (API key required, not JWT).

Per ADR-046, MVP-grade auth — not production-grade. User acknowledged: "aku pahamnya ya cuma jaga sementara".

### 3.6 Discard sub-proyek H migrations + stash code

Migrations 005-007 from sub-proyek H deleted from disk. Code (Phases 1-5 work) preserved in `git stash` snapshot named "sub-proyek H Phases 1-5 + Bucket 1 (pre-redesign snapshot)". Bucket 1 UI fixes (Items 1-4) lost — will be re-applied on top of sub-proyek I.

Migration starts fresh at 005 (number reused since sub-proyek H 005 is no longer referenced).

**Alternative rejected**: keep sub-proyek H migrations + add new 008+. Rejected because the deletes-then-creates would produce a huge churn diff and confuse future readers. Cleaner to revert + start fresh.

### 3.7 Single tenant_profile seeded per tenant; operators expand via UI

57 tenant_profiles seeded (1 per tenant). Default: position = first listed position for tenant's department, service = `general`, allowed_language = NULL, prompt_applied = [translate_prompt_id]. Operators add additional profiles (other positions / services) via UI.

**Alternative rejected**: full Cartesian seed (e.g., 83 positions × 16 services = 1,328 per tenant × 57 tenants = 75K+ rows). Rejected as data bloat; most combos unused.

### 3.8 Translation logs survive via tenant_id + profile_id column retype

`translation_logs` keeps its rows. The `tenant_id` + `tenant_profile_id` columns are retyped from UUID to VARCHAR(30) and re-FK-attached to the new tenant + tenant_profile tables. Existing log rows from sub-proyek B/D/G+C lose FK validity (the UUIDs they reference no longer exist), so we either:
- DROP + recreate translation_logs (simpler, accepts data loss)
- ALTER + leave orphan FK references (preserves rows but breaks integrity)

For MVP simplicity: DROP + recreate. Audit logs from earlier are not load-bearing.

## 4. Data model

### 4.1 Reference tables

```sql
CREATE TABLE country (
  country_id      VARCHAR(30) PRIMARY KEY,
  country_name    VARCHAR(60) UNIQUE NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 7 rows: Indonesia, Malaysia, Thailand, Vietnam, Germany, France, Switzerland

CREATE TABLE company (
  company_id      VARCHAR(30) PRIMARY KEY,
  company_name    VARCHAR(100) UNIQUE NOT NULL,
  company_country VARCHAR(60) NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 3 rows

CREATE TABLE department (
  department_id   VARCHAR(30) PRIMARY KEY,
  department_name VARCHAR(80) UNIQUE NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 19 rows

CREATE TABLE position (
  position_id     VARCHAR(30) PRIMARY KEY,
  position_name   VARCHAR(120) NOT NULL,
  department_id   VARCHAR(30) NOT NULL REFERENCES department(department_id) ON DELETE CASCADE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (position_name, department_id)
);
-- 83 rows

CREATE TABLE service (
  service_id      VARCHAR(30) PRIMARY KEY,
  service_name    VARCHAR(100) UNIQUE NOT NULL,
  description     TEXT,
  domain          VARCHAR(100),
  tone            VARCHAR(255),
  target_audience VARCHAR(255),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 16 rows: general + 15 Aitegrity products
```

### 4.2 Glossary + style examples (FK to service)

```sql
CREATE TABLE glossary_terms (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id      VARCHAR(30) NOT NULL REFERENCES service(service_id) ON DELETE CASCADE,
  source_term     VARCHAR(255) NOT NULL,
  source_lang     VARCHAR(8) NOT NULL,
  target_term     VARCHAR(255) NOT NULL,
  target_lang     VARCHAR(8) NOT NULL,
  context         TEXT,
  is_forbidden    BOOLEAN NOT NULL DEFAULT FALSE,
  priority        INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_glossary_terms_service_langs ON glossary_terms (service_id, source_lang, target_lang);

CREATE TABLE style_examples (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id      VARCHAR(30) NOT NULL REFERENCES service(service_id) ON DELETE CASCADE,
  source_text     TEXT NOT NULL,
  source_lang     VARCHAR(8) NOT NULL,
  target_text     TEXT NOT NULL,
  target_lang     VARCHAR(8) NOT NULL,
  tags            VARCHAR(255)[],
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_style_examples_service_langs ON style_examples (service_id, source_lang, target_lang);
```

### 4.3 Tenant (junction + auth)

```sql
CREATE TABLE tenant (
  tenant_id          VARCHAR(30) PRIMARY KEY,
  country_id         VARCHAR(30) NOT NULL REFERENCES country(country_id),
  company_id         VARCHAR(30) NOT NULL REFERENCES company(company_id),
  department_id      VARCHAR(30) NOT NULL REFERENCES department(department_id),
  api_key_hash       VARCHAR(128) UNIQUE NOT NULL,
  jwt_active_token   TEXT,
  jwt_refreshed_at   TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (country_id, company_id, department_id)
);
CREATE INDEX ix_tenant_api_key_hash ON tenant (api_key_hash);
-- 57 rows seeded
```

### 4.4 Tenant profile (junction)

```sql
CREATE TABLE tenant_profile (
  profile_id         VARCHAR(30) PRIMARY KEY,
  tenant_id          VARCHAR(30) NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
  position_id        VARCHAR(30) NOT NULL REFERENCES position(position_id),
  service_id         VARCHAR(30) NOT NULL REFERENCES service(service_id),
  allowed_language   VARCHAR(8)[],
  prompt_applied     VARCHAR(30)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(30)[],
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, position_id, service_id)
);
CREATE INDEX ix_tenant_profile_tenant_id ON tenant_profile (tenant_id);
-- 57 rows seeded
```

### 4.5 Tenant prompts (re-keyed)

```sql
CREATE TABLE tenant_prompts (
  prompt_id          VARCHAR(30) PRIMARY KEY,
  agent_type         VARCHAR(40) UNIQUE NOT NULL,
  template           TEXT NOT NULL,
  description        TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by         VARCHAR(255) DEFAULT 'system',
  CONSTRAINT ck_tenant_prompts_agent_type CHECK (
    agent_type IN ('lang_detect_input','lang_detect_output','translate')
  )
);
-- 3 rows
```

### 4.6 ISO languages (unchanged from sub-proyek H Phase 3)

```sql
CREATE TABLE iso_languages (
  code         VARCHAR(8) PRIMARY KEY,
  name         VARCHAR(60) NOT NULL,
  native_name  VARCHAR(100)
);
-- ~40 rows
```

### 4.7 Translation logs (recreated with new FK types)

```sql
DROP TABLE translation_logs;
CREATE TABLE translation_logs (
  log_id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                  VARCHAR(30) REFERENCES tenant(tenant_id) ON DELETE SET NULL,
  profile_id                 VARCHAR(30) REFERENCES tenant_profile(profile_id) ON DELETE SET NULL,
  source_text                TEXT NOT NULL,
  source_lang                VARCHAR(8),
  target_lang                VARCHAR(8) NOT NULL,
  translated_text            TEXT,
  status                     VARCHAR(20) NOT NULL,
  -- sub-proyek B forward columns:
  detected_source_lang       VARCHAR(8),
  detected_output_lang       VARCHAR(8),
  source_lang_mismatch       BOOLEAN,
  output_lang_mismatch       BOOLEAN,
  -- sub-proyek G+C columns:
  rendered_prompt            TEXT,
  agentic_activities         JSONB,
  -- core observability:
  model_id                   VARCHAR(100),
  input_tokens               INT,
  output_tokens              INT,
  cost_usd                   NUMERIC(12, 6),
  cached                     BOOLEAN NOT NULL DEFAULT FALSE,
  cache_key                  VARCHAR(64),
  latency_ms                 NUMERIC(10, 2),
  trace_id                   UUID,
  batch_id                   UUID,
  batch_index                INT,
  request_metadata           JSONB,
  error_code                 VARCHAR(60),
  error_detail               TEXT,
  started_at                 TIMESTAMPTZ NOT NULL,
  completed_at               TIMESTAMPTZ
);
CREATE INDEX ix_translation_logs_tenant_started ON translation_logs (tenant_id, started_at DESC);
CREATE INDEX ix_translation_logs_failed ON translation_logs (started_at DESC) WHERE status = 'failed';
```

### 4.8 Relationship diagram

```
country (7) ──┐
              │
company (3) ──┼──→ tenant (57) ──────→ tenant_profile (57)
              │       │                       │
department(19)┘       ├── api_key_hash       ├── position_id ──→ position (83) ──→ department_id (FK)
                      ├── jwt_active_token   ├── service_id ───→ service (16)
                      └─ jwt_refreshed_at    ├── allowed_language[]
                                             └── prompt_applied[]

service (16) ───→ glossary_terms (N)
                  style_examples (N)

tenant_prompts (3 rows: lang_detect_input, lang_detect_output, translate)
iso_languages (~40 rows)

translation_logs (1:N from tenant + tenant_profile via FK; SET NULL on delete)
```

## 5. Migration strategy (Phase I-1)

**Pre-migration cleanup** (operator-run, NOT in alembic):

```bash
# Revert sub-proyek H migrations
uv run alembic downgrade 004_agentic_activities

# Delete sub-proyek H migration files from disk (they're preserved in git stash)
rm alembic/versions/005_rename_profile_to_tenant_profile.py
rm alembic/versions/006_expand_tenant_and_tenant_profile.py
rm alembic/versions/007_tenant_prompts_and_iso_languages.py
```

**Migration 005-NEW** (`alembic/versions/005_tenant_junction_redesign.py`):

```python
"""Tenant junction redesign — sub-proyek I.

Revision ID: 005_tenant_junction
Revises: 004_agentic_activities
"""
def upgrade() -> None:
    # 1. Drop sub-proyek B / D / G+C tables (in FK order)
    op.drop_table("translation_logs")
    op.drop_table("style_examples")
    op.drop_table("glossary_terms")
    op.drop_table("profile_versions")
    op.drop_table("profiles")
    op.drop_table("tenants")

    # 2. Create reference tables
    op.create_table("country", ...)
    op.create_table("company", ...)
    op.create_table("department", ...)
    op.create_table("position", ...)  # with department_id FK
    op.create_table("service", ...)
    op.create_table("iso_languages", ...)
    op.create_table("tenant_prompts", ...)

    # 3. Create glossary + examples (FK to service)
    op.create_table("glossary_terms", ...)
    op.create_table("style_examples", ...)

    # 4. Create tenant (junction + auth)
    op.create_table("tenant", ...)

    # 5. Create tenant_profile (nested junction)
    op.create_table("tenant_profile", ...)

    # 6. Recreate translation_logs with new FK column types
    op.create_table("translation_logs", ...)


def downgrade() -> None:
    # Reverse order; warns about data loss
    raise NotImplementedError("Sub-proyek I migration is irreversible by design.")
```

## 6. Seed (Phase I-4)

**`scripts/seed_tenant_data.py`** (replaces all earlier seed scripts):

Seed sequence:
1. ISO languages (~40 rows from `src/iso_languages/seed_data.py`)
2. Countries (7 rows)
3. Companies (3 rows, with FK to country)
4. Departments (19 rows)
5. Positions (83 rows with department_id FK per user's mapping list)
6. Services (16 rows: `general` + 15 Aitegrity products with tone + audience populated from old AITEGRITY_PRODUCTS)
7. Tenant prompts (3 rows with new Jinja templates)
8. Tenants (57 rows: 3 companies × 19 departments × 1 country each. API key generated, plaintext printed to stdout, hash stored)
9. Tenant profiles (57 rows: 1 per tenant, default position = first listed for dept, default service = general, allowed_language = NULL, prompt_applied = [translate_prompt_id])
10. Glossary terms + style examples (from AITEGRITY_PRODUCTS, FK to service)

Script idempotent (skip-if-exists per row). API key plaintext appears ONLY in seed stdout — operator should redirect to a secure file.

**Translate prompt** (in seed):

```jinja
<role>
You are a professional translator working for {{ tenant.company.company_name }}'s
{{ tenant.department.department_name }} department in {{ tenant.country.country_name }},
serving the {{ tenant_profile.position.position_name }} role.
You specialise in {{ tenant_profile.service.service_name }} ({{ tenant_profile.service.domain }}) content.
</role>

<style_guide>
Tone: {{ tenant_profile.service.tone }}
Target audience: {{ tenant_profile.service.target_audience }}
</style_guide>

{% if glossary_terms %}<glossary>
Use these specific translations:
{% for term in glossary_terms %}- "{{ term.source_term }}" -> "{{ term.target_term }}"
{% endfor %}</glossary>

{% endif %}{% if examples %}<examples>
{% for ex in examples %}Source: {{ ex.source_text }}
Translation: {{ ex.target_text }}

{% endfor %}</examples>

{% endif %}<task>
Translate from {{ source_lang_name }} ({{ source_lang }}) to {{ target_lang_name }} ({{ target_lang }}).

Rules:
- Output ONLY the translated text. No labels, no explanation.
- Preserve placeholders like {variable} or %s exactly.
- Honour every glossary entry above.

Text:
{{ text }}
</task>
```

**Lang detect prompt** (same template for input + output):

```
You are a language identifier. Reply with ONLY the ISO 639-1 code of
the language of the input text. Examples: 'en' for English, 'id' for
Indonesian, 'fr' for French. No quotes, no explanation, just the
2-letter lowercase code.
```

## 7. Auth design (Phase I-3)

### 7.1 API key flow

- Tenant creation: `secrets.token_urlsafe(32)` → plaintext `aitkey_<base64>`. Argon2 hash stored. Plaintext returned ONCE.
- Verification: middleware iterates candidate tenants (bcrypt-verify each api_key_hash against header value) until match. For 57 tenants this is acceptable; future optimization via key prefix indexing if scale grows.
- Header: `X-Tenant-API-Key: aitkey_<base64>`
- Failure: 401 with `error_code="invalid_api_key"`

### 7.2 JWT flow

- `POST /auth/refresh-jwt` (API key required):
  - Generate JWT: `payload = {sub: tenant_id, iat: now, exp: now + 24h}`, sign with `settings.jwt_secret` (HS256)
  - Update `tenant.jwt_active_token = token`, `tenant.jwt_refreshed_at = now`
  - Return `{jwt_active_token, expires_at}`
- Verification: middleware decodes JWT, checks signature + expiry, matches against `tenant.jwt_active_token` (a mismatch means the token was superseded by a refresh)
- Header: `Authorization: Bearer <jwt>`

### 7.3 Middleware

`src/api/middleware.py` adds `auth_middleware`:
- Bypass for `PUBLIC_PATHS = {"/health", "/health/deep", "/countries", "/iso-languages", "/auth/refresh-jwt"}` plus prefix-matched `/companies` + `/departments`.
- Try Bearer JWT first (cheaper than bcrypt verify).
- Fall back to API key header.
- On success: `request.state.tenant_id = ...`.
- On failure: 401 Unauthorized.

### 7.4 Settings additions

```python
class Settings(BaseSettings):
    ...
    jwt_secret: str = Field(default="dev-jwt-secret-replace-in-env", min_length=16)
    api_key_master: str = Field(default="aitkey_master_dev", description="Streamlit + admin endpoints master key (dev only).")
```

### 7.5 Tenant creation admin endpoint (out of MVP scope but reserved)

`POST /admin/tenants` would create new tenant rows + return API key plaintext. For MVP, only seed creates tenants — operator captures keys from seed stdout.

## 8. Streamlit form (Phase I-5)

**Cascading sidebar** (A → H):

```
Sidebar:
  A. Country         (dropdown, 7 options from /countries)
  B. Company         (dropdown, filtered by country)
  C. Department      (dropdown, filtered by global departments)
  → tenant resolved via GET /tenants/by-cdd?country_id=X&company_id=Y&department_id=Z
  D. Position        (dropdown, filtered by department from GET /departments/{dept_id}/positions)
  E. Service         (dropdown, all 16 from /services)
  → tenant_profile resolved (or auto-created if matching combo doesn't exist? — out of scope; operator must seed)
  F. Glossary preview (read-only count for selected service)
  G. Source Language (filtered by tenant_profile.allowed_language; ISO catalog via /iso-languages)
  H. Target Language (same filter)

Sidebar bottom: "🔑 Authenticated as tenant: <tenant_id_short>"

Main column:
  Source text area + Translate button.
  Post-translate: mismatch banner + agent flow viz + translation + metadata expander.
```

**Streamlit auth**: dev mode uses `settings.api_key_master` (env var). Future: per-tenant API key on tenant selection.

**New API endpoints** (Phase I-3):
- `GET /countries` — public
- `GET /companies?country_id=X` — public
- `GET /departments` — public
- `GET /departments/{department_id}/positions` — authenticated
- `GET /services` — authenticated
- `GET /tenants/by-cdd?country_id=X&company_id=Y&department_id=Z` — authenticated (returns tenant_id + jwt_active_token if refresh needed)
- `GET /tenants/{tenant_id}/tenant-profiles?position_id=X` — authenticated
- `POST /auth/refresh-jwt` — API key required
- `POST /tenant-profiles` — authenticated (operator creates new profile combos)

## 9. Agent refactor (Phase I-3)

Agents continue to load templates via `TenantPromptRepository` (now keyed by agent_type unique constraint but PK changed to prompt_id). The repository's `get(agent_type)` API surface unchanged from sub-proyek H Phase 3.

TranslateAgent's Jinja rendering changes to consume the new tenant + tenant_profile schema:

```python
rendered_prompt = self._template.render(
    tenant=ctx.resolved_tenant,                          # tenant ORM (country, company, department)
    tenant_profile=ctx.resolved_tenant_profile,          # tenant_profile ORM (position, service)
    source_lang=source_lang_code,
    source_lang_name=source_lang_name,
    target_lang=ctx.request.target_lang,
    target_lang_name=target_lang_name,
    glossary_terms=ctx.selected_glossary,                # fetched from service.glossary_terms
    examples=ctx.selected_examples,                      # fetched from service.style_examples
    text=ctx.normalized_text,
)
```

`tenant` resolution: pipeline stage loads tenant by ID, joins country/company/department via SQLAlchemy `joinedload`. Same for tenant_profile + position + service.

## 10. Error handling

| Scenario | Behavior |
|----------|----------|
| Migration 005-NEW partial fail | Single-transaction; rollback. Operator reruns. |
| Seed partial run | Idempotent skip-if-exists per row. |
| API key header missing on protected endpoint | 401 Unauthorized + `error_code="missing_credentials"` |
| Invalid API key | 401 + `error_code="invalid_api_key"` |
| JWT expired or mismatched | Fall through to API key check. If both fail, 401. |
| Tenant lookup miss (deleted between auth + handler) | 404 + `error_code="tenant_not_found"` |
| Position-department mismatch in tenant_profile create | DB FK rejects; 400 + `error_code="invalid_position_for_department"` |
| Streamlit cascading produces empty dropdown | UI shows warning, disables translate button. |
| Translation log INSERT fails | Swallowed per ADR-027 carry-over; pipeline result.log_id=None |

## 11. Testing strategy

**Per-phase test scope** (~30 new tests, baseline ~200 after sub-proyek H discard → ~230 total):

- **Phase I-1 (migration)**: `test_migration_005_drops_old_creates_new` — apply against fresh DB, verify 9 new tables exist + old ones gone.
- **Phase I-2 (ORM + schemas)**: `test_*_id_format` — verify custom ID generator produces `prefix-XXXXXXXX-XXXX`. `test_tenant_composite_uniqueness`, `test_tenant_profile_junction_uniqueness`, `test_position_department_fk_required`. ~8 schema tests.
- **Phase I-3 (repos + endpoints + auth)**:
  - `test_country_repository_list`, `test_company_filter_by_country`, `test_department_list_global`, `test_position_filter_by_department`, `test_service_list_all`. ~5 repo tests.
  - `test_auth_middleware_rejects_missing_key`, `test_auth_middleware_accepts_api_key`, `test_auth_middleware_accepts_bearer_jwt`, `test_jwt_refresh_persists_active_token`, `test_jwt_mismatch_falls_back_to_api_key`. ~5 auth tests.
  - `test_cascade_endpoint_*` (countries → companies → departments → positions). ~4 cascade tests.
- **Phase I-4 (seed)**: `test_seed_creates_7_countries`, `test_seed_creates_3_companies`, `test_seed_creates_19_departments`, `test_seed_creates_83_positions`, `test_seed_creates_16_services`, `test_seed_creates_57_tenants_with_unique_api_keys`, `test_seed_creates_57_tenant_profiles`, `test_seed_idempotent`. ~8 seed tests.
- **Phase I-5 (Streamlit smoke)**: minimal automated test for new endpoints + manual smoke checklist for cascading UI.

**Manual smoke (post-Phase-I-5)**:
1. `uv run alembic downgrade 004 && rm alembic/versions/005_rename... && uv run alembic upgrade head`
2. `uv run python scripts/seed_tenant_data.py` → operator captures API keys from stdout
3. Restart uvicorn + Streamlit
4. Streamlit: pick Indonesia → PT Integrity Indonesia → EBS → first EBS position → general → en → id
5. Translate: "The forensic review uncovered fraudulent invoices."
6. Verify agent flow with new template placeholders resolved (PT Indonesia / EBS / first position / general / forensic tone).
7. Query: `SELECT t.company_id, c.company_name, d.department_name, p.position_name, s.service_name FROM translation_logs tl JOIN tenant t ON tl.tenant_id = t.tenant_id JOIN company c ON t.company_id = c.company_id JOIN department d ON t.department_id = d.department_id JOIN tenant_profile tp ON tl.profile_id = tp.profile_id JOIN position p ON tp.position_id = p.position_id JOIN service s ON tp.service_id = s.service_id ORDER BY tl.started_at DESC LIMIT 1;`

## 12. ADR additions

| ID | Topic |
|----|-------|
| **ADR-039** | Sub-proyek H discarded (migrations 005-007 deleted, code stashed). Sub-proyek I starts fresh from migration 004. Reason: H model was conceptually rejected by user; clean restart cheaper than incremental fix. |
| **ADR-040** | Custom ID format `{prefix}-{8hex}-{4hex}` for all PKs. 48 bits entropy (lifetime collision-safe at MVP scale, per ADR-012 precedent). More readable than full UUID, suitable for log greps + admin operations. Helper in `src/db/ids.py`. |
| **ADR-041** | Tenant = junction of (country, company, department) with built-in auth columns (api_key_hash, jwt_active_token, jwt_refreshed_at). Composite unique constraint. 57 rows in current seed (3 × 19 × 1 country each). |
| **ADR-042** | Tenant_profile = nested junction of (position, service) per tenant. `prompt_applied` is array of prompt_ids (variable-length config per profile). |
| **ADR-043** | Tone, target_audience, glossary, style_examples all moved to `service` table. Reflects that these properties are characteristics of the service offering, not of the operator (company/department/position) running it. |
| **ADR-044** | Position has `department_id NOT NULL FK`. Enforces user's 83 position-department mapping at DB level. Alternative (global position + junction table) rejected for over-normalization. |
| **ADR-045** | API key argon2-hashed. Plaintext returned ONCE during creation (seed stdout or admin endpoint response); never persisted. Argon2 vs bcrypt chosen for resistance to ASIC + GPU attacks per current OWASP guidance. |
| **ADR-046** | JWT lightweight design — `tenant.jwt_active_token` stores currently-valid token. Mismatched/expired falls back to API key auth. MVP-grade ("aku pahamnya ya cuma jaga sementara"); production-grade JWT rotation + key management deferred. |

ADRs land in CLAUDE.md "Decision log" during Phase I-1 migration commit.

## 13. Open questions / follow-ups

**Out of scope for sub-proyek I:**
- Full ISO 639-1 catalog expansion (currently ~40 entries).
- Operator-facing prompt-edit UI.
- Per-tenant_profile prompt override.
- Multi-position concurrent assignment (currently 1 profile = 1 position; multiple profiles per tenant covers it via separate rows).
- Automated daily JWT cron rotation (manual `POST /auth/refresh-jwt` for MVP).
- Tenant creation admin endpoint.
- API key rotation flow (seed creates; future admin endpoint regenerates).
- Dashboard sub-proyek F implementation (now reads from tenant + tenant_profile junction JOINs).
- Re-applying Bucket 1 UI fixes (Items 1-4 from sub-proyek G+C) on top of sub-proyek I — Streamlit form rewrite supersedes most, but agent box + Haiku settings need carry-over.

## 14. References

- `CLAUDE.md` — existing ADRs (ADR-012 cache key truncation precedent, ADR-013 graceful degradation, ADR-017 soft-delete, ADR-027 record_log swallow, ADR-031 agent soft-fail).
- `docs/superpowers/specs/2026-05-21-tenant-profile-rename-and-expansion-design.md` — sub-proyek H spec (now superseded; preserved for context on what was rejected and why).
- Git stash: `On main: sub-proyek H Phases 1-5 + Bucket 1 (pre-redesign snapshot)` — preserves rejected code for reference.
- Sub-proyek B (translation_logs forward columns).
- Sub-proyek D (15 Aitegrity products + tone/audience now moved to service).
- Sub-proyek G+C (agentic_activities JSONB, lang detection).
