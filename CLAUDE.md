# AI Translation API — Project Context

## Visi
Backend API untuk AI Translation dengan dua produk:
1. Domain-aware translation per profile (department/produk berbeda punya glossary, tone, dan examples sendiri yang bisa dikonfigurasi dinamis tanpa redeploy)
2. Live webpage translation via JavaScript SDK yang nge-call API

## Tech stack
- Python 3.11+, FastAPI, async-native
- PostgreSQL 16 untuk data persistent
- Redis 7 untuk cache + queue
- Anthropic SDK untuk Claude provider (model default: claude-sonnet-4-6)
- Pydantic untuk schema validation
- SQLAlchemy 2.0 (async) + Alembic untuk DB ORM dan migrations
- pytest untuk testing (+ pytest-asyncio)
- ruff untuk linting, mypy untuk typing (strict mode)
- structlog untuk structured logging
- uv untuk dependency management
- Jinja2 untuk prompt templates

## Arsitektur tingkat tinggi

```
src/
├── api/              # FastAPI routes + middleware
├── pipeline/         # Translation pipeline orchestration
│   └── templates/    # Jinja2 prompt templates
├── providers/        # LLM provider abstraction
├── auth/             # argon2 hashing + JWT + middleware (sub-proyek I)
├── country/          # Country reference table + repository (sub-proyek I)
├── company/          # Company reference table (sub-proyek I)
├── department/       # Department reference table (sub-proyek I)
├── position/         # Position reference table (sub-proyek I)
├── service/          # Service reference table + glossary/examples (sub-proyek I)
├── tenant/           # Tenant junction (country, company, department) + auth (sub-proyek I)
├── tenant_profile/   # Tenant-profile nested junction (position, service) (sub-proyek I)
├── tenant_prompts/   # Tenant prompt templates (sub-proyek I)
├── iso_languages/    # ISO 639-1 reference list (sub-proyek I)
├── translation_logs/ # Translation log persistence (sub-proyek B)
├── cache/            # Redis caching layer
├── db/               # Database setup, ORM models, custom ID generator
├── config/           # Settings, logging setup
└── eval/             # Evaluation harness (Phase 6)
alembic/              # DB migrations (up to 005 — tenant junction redesign)
demo/                 # demo/webpage = Phase 7 JS SDK landing page only.
                      # demo/app.py (Streamlit) was deleted by sub-proyek J.
frontend-demo/        # Vite + React + TS + Tailwind + shadcn/ui SPA (sub-proyek J)
                      # Replaces former Streamlit UI; mock-only in v1.
sdk/                  # JavaScript SDK (Phase 7)
scripts/              # Utility scripts:
                      #   seed_tenant_data.py — populate ref tables + 57 tenants
                      #   run-demo.ps1 — PowerShell launcher for frontend-demo
tests/                # All tests, mirror src/ structure
eval/                 # Eval datasets, metrics, runner
docs/                 # Project documentation:
                      #   adrs.md — full ADR reasoning (CLAUDE.md hanya one-liners)
                      #   phase-status.md — detailed phase/sub-proyek implementation notes
```

## Prinsip desain inti
1. **Provider abstraction**: Anthropic SDK HANYA boleh diimport di `src/providers/claude.py`. Business logic lain pakai `TranslationProvider` Protocol.
2. **Profile as data**: schema multi-tenant ready (tenant_id wajib ada meski sekarang single tenant).
3. **Cache key composition**: `sha256(text + source_lang + target_lang + profile_slug + profile_version + model_id)`. Versioning otomatis invalidate cache lama saat profile berubah.
4. **Stateless API**: semua state di PostgreSQL atau Redis. Pod bisa scale horizontal.
5. **Stage isolation**: setiap stage pipeline adalah unit yang dapat di-test independen.
6. **Graceful degradation**: cache down ≠ crash. Service degrade ke uncached operation.

## Service & tenant system arsitektur (post sub-proyek I — current model)
- **Tenant** = junction (country, company, department) — sole auth entity per ADR-041. Built-in auth columns: `api_key_hash`, `jwt_active_token`, `jwt_refreshed_at`. 57 rows seeded.
- **Tenant_profile** = nested junction (tenant, position, service) per ADR-042. Has `prompt_applied: list[str]` for variable-length prompt mix-and-match.
- **Service** owns glossary + style_examples + tone + target_audience per ADR-043 (NOT tenant_profile — properties of the offering, not the operator).
- **Glossary terms**: source_term, source_lang, target_term, target_lang, context, is_forbidden, priority. Re-keyed to service_id.
- **Style examples**: source_text, target_text, lang pair, tags. Re-keyed to service_id.
- **Custom ID format** (ADR-040): all PKs are `{prefix}-{8hex}-{4hex}` strings (48 bits entropy).
- See `docs/adrs.md` ADR-041..046 for full reasoning of the schema redesign.

## Coding standards
- Type hints di semua function signatures (mypy strict mode lulus)
- Pydantic untuk semua external/API schemas
- Async/await untuk I/O operations (DB, Redis, HTTP)
- Structured logging via structlog (JSON output), bukan print
- Setiap module punya unit tests, pipeline punya integration tests
- Public functions punya docstring yang menjelaskan kenapa, bukan apa (kode sudah self-document apanya)
- No magic numbers — config dari env atau settings module
- Konvensi naming: snake_case untuk Python, kebab-case untuk slugs

## Coding style untuk learning
User adalah data scientist yang sedang belajar AI engineering. Tinggalkan docstring + inline comment yang menjelaskan KEPUTUSAN DESAIN, bukan sekadar apa kode lakukan. Contoh:
- ✗ Bad: `# loop through items` (obvious dari kode)
- ✓ Good: `# We retry transient errors with exponential backoff because Claude API occasionally returns 5xx during high load. Max 3 retries to avoid amplifying issues.`

## Decision log
64 ADRs ditrack. Full reasoning + tradeoff di **`docs/adrs.md`**. Quick index (judul saja):

- ADR-001..005: provider abstraction, profile single-inheritance, cache key includes profile_version, streaming postponed, glossary exact-match only
- ADR-006..010: Protocol vs ABC, retry policy hand-rolled, Decimal for money, quality_mode CHECK constraint, test DB NullPool
- ADR-011..015: ProfileVersion JSONB snapshot, cache key 128 bits + unit separator, cache layer graceful degradation, Jinja system_prompt_override, NFC unicode normalisation
- ADR-016..020: DI singleton vs per-request scoping, profile soft-delete, test commit no-op fixture, ErrorResponse envelope, eval metrics normalised to [0,1]
- ADR-021..025: glossary metric reuses pipeline.compliance, eval cost confirmation, SDK no-build ES2020, SDK TreeWalker (not innerHTML), SDK 2-tier client cache
- ADR-026..030: log stores full plaintext (PII trade-off), record_log swallow exceptions, error_detail regex sanitise, session.flush asyncio.Lock, product seed inline dataclass
- ADR-031..033: agent soft-fail (only translate propagates), AgenticActivity.result as JSONB dict, lang detect via Claude Haiku
- ADR-039..046: sub-proyek H discarded, custom ID format `{prefix}-{8hex}-{4hex}`, tenant junction (country/company/department), tenant_profile nested, service owns tone/glossary/examples, position FK department CASCADE, API key argon2-hashed, JWT lightweight (single active token)
- ADR-047..052: React replaces Streamlit, types mirror real /translate response, Tab 1 mock-only, PowerShell Chrome launcher, shadcn/ui base primitive, Integrity merah-putih branding + owl mark
- ADR-053..058: tenant denormalize (snapshot name cols), alembic_version_at_create snapshot, prompt_applied as agent_type strings (length 3 ordered), allowed_language stratified 5-pattern enforcement, iso_languages module-level cache, single flat Jinja context dict
- ADR-059..064: frontend adapter pattern (sub-proyek L), synthetic streaming via response-timing replay, Settings modal route, VITE_API_MODE env toggle, Vite dev proxy + CORS extension, 5 error_code → banner mapping

(ADR-034..038 skipped intentionally — sub-proyek H discarded per ADR-039.)

## Phase status
MVP **Phases 1–7** ✅ complete (verified 2026-05-20).

Post-MVP sub-projects:
- **Sub-proyek B** (Translation log table): ✅ 2026-05-21
- **Sub-proyek I** (Tenant junction redesign + auth): ✅ 2026-05-22 — 114 tests pass; migration 005 irreversible.
- **Sub-proyek J** (Frontend demo React redesign): ✅ 2026-05-22 — `frontend-demo/` SPA mock-only.
- **Sub-proyek K** (Schema cleanup + iso plumbing + end-to-end verification): ✅ 2026-05-22 — migration 006 (denormalize tenant + tenant_profile), seed redistributed 5 allowed_language patterns + uniform 3-step prompt_applied, iso_languages plumbed into pipeline (code→name), tenant_prompts Jinja context flat dict, language_not_allowed enforcement, end-to-end DB+Redis smoke verified.
- **Sub-proyek L** (Frontend-demo wired to real /translate, MVP): ✅ 2026-05-22 — realApi.ts adapter implements TranslateApi against backend, synthetic streaming preserves AgentPipeline UX, Settings modal configures credentials (localStorage), Vite dev proxy + VITE_API_MODE toggle (default mock), 5 error_code → banner mapping. End-to-end smoke verified.

Full implementation detail (file paths, test counts, known limitations, unblocks) di **`docs/phase-status.md`**.
