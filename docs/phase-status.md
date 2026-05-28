# Phase & Sub-proyek Implementation Status

Full implementation detail (file paths, test counts, known limitations, unblocks) per phase/sub-proyek.

CLAUDE.md hanya menyimpan ringkasan satu-baris. Detail lengkap ada di sini.

---

## MVP Phases

### Phase 1 — Foundation, repo scaffolding, dev environment
**Status:** ✅ complete (commit `feb473f`, verified 2026-05-20)

- Tooling: `uv`, ruff, mypy (strict), pytest (asyncio_mode=auto), pre-commit
- Infra: docker-compose (postgres:16 + redis:7, both with healthchecks)
- Skeleton: `src/{api,config,db,...}` packages with `__init__.py`; `tests/`; `alembic/` (async)
- Live: `/health` endpoint passes 2 tests + manual HTTP probe

### Phase 2 — LLM Provider Abstraction Layer
**Status:** ✅ complete (commit `ee38a28`, verified 2026-05-20)

- `src/providers/{base,errors,pricing,claude,retrying,factory}.py` — Protocol-based abstraction, anthropic SDK confined to `claude.py` per ADR-001
- Error hierarchy: `TransientError` (retryable, incl. `RateLimitError`) vs `PermanentError` (incl. `AuthError`, `CapabilityError`)
- `RetryingProvider`: exponential backoff (1s, 2s, 4s), max 3 retries; honours upstream `Retry-After` on 429
- `PRICING_TABLE` for Opus/Sonnet/Haiku 4.x; `Decimal` everywhere for money
- 46 unit tests (mocked SDK), 1 live smoke test (`scripts/test_claude_provider.py`)

### Phase 3 — Profile System (models, repository, resolver, glossary)
**Status:** ✅ complete (verified 2026-05-20)

- Migration `alembic/versions/001_profile_schema.py` creates `tenants`, `profiles` (self-referential), `glossary_terms`, `style_examples`, `profile_versions`. UUID PKs via `gen_random_uuid()` (Postgres 16 built-in).
- `src/db/models.py` — SQLAlchemy 2.0 `Mapped[]` style. `quality_mode` is a plain `String` + `CHECK` constraint (NOT a Postgres ENUM — extending an ENUM requires DDL).
- `src/profiles/schemas.py` — Pydantic v2 with `Create`/`Read`/`Update` triplets and `ResolvedProfile`/`ResolvedGlossaryTerm`/`ResolvedStyleExample` (each resolved row carries `origin_profile_slug` for audit).
- `src/profiles/repository.py` — async CRUD over tenants / profiles / glossary / examples. `update_profile` writes a snapshot to `profile_versions` BEFORE mutating, then bumps `version`. PATCH semantics via `model_fields_set`.
- `src/profiles/resolver.py` — inheritance walk, `MAX_INHERITANCE_DEPTH=4`, cycle detection, glossary merged child-wins-on-conflict (key: `(lower(source_term), source_lang, target_lang)`), examples additive (deduped by exact identity). `resolution_chain` ordered leaf → root.
- `src/profiles/glossary.py` — exact-substring selection, ranked by `priority desc` then `len(source_term) desc`, truncated to `max_terms` (default 20). TODO comment marks the Phase-2-of-glossary handoff to lemma + vector matching.
- `scripts/seed_sample_profile.py` — idempotent seed of `internal-company` tenant with `general → asuransi → asuransi-cs` chain.
- 28 new tests (8 glossary unit, 11 repository, 9 resolver). Test DB `aitrans_test` with `NullPool` to avoid asyncpg event-loop affinity issues; transaction rollback per test.

**Note:** Schema redesigned by sub-proyek I (migration 005). `profiles` table dropped; replaced by `tenant + tenant_profile + service`. Code references in this section reflect pre-sub-proyek-I state; see Sub-proyek I below for current model.

### Phase 4 — Translation Pipeline + Redis Cache
**Status:** ✅ complete (verified 2026-05-20)

- `src/cache/{base,key,redis_cache}.py` — `CacheBackend` Protocol; `compute_cache_key` (sha256 truncated to 128 bits, unit-separator-joined to avoid concatenation collisions); `RedisCache` with graceful degradation (all `RedisError` swallowed, degraded-state latch logs warning once not per-call).
- `src/pipeline/schemas.py` — `PipelineRequest` / `PipelineResult` Pydantic boundary objects.
- `src/pipeline/templates/translate.jinja` — Jinja2 prompt with `<role>` / `<style_guide>` / `<glossary>` (required + forbidden split) / `<examples>` / `<task>` sections. Used as `system_prompt_override` on the provider.
- `src/pipeline/compliance.py` — `compute_glossary_compliance` returns `(score, violations)` where score is `1.0 - violations/checks` (1.0 when nothing applicable). Case-insensitive substring match; does NOT refuse output, only signals.
- `src/pipeline/stages.py` — 8 single-purpose async stages (validate_and_normalize, load_resolved_profile, cache_lookup, preprocess, build_prompt, translate, postprocess_and_verify, cache_write) each logging a structured event. `PipelineContext` dataclass threads state.
- `src/pipeline/pipeline.py` — `TranslationPipeline` orchestrator with `trace_id` per request, short-circuit on cache hit, top-level error logging.
- 34 new tests (10 cache key, 13 redis_cache, 7 compliance, 11 stages, 4 integration). Live smoke (`scripts/test_pipeline.py`) hit the API once at $0.001545 and replayed in 0.7ms (2215× speedup).

### Phase 5 — REST API + Streamlit demo UI
**Status:** ✅ complete (verified 2026-05-20)

- `src/api/dependencies.py` — FastAPI Depends factories. Cache + provider + template env are process singletons via `@lru_cache`; resolver + pipeline + repository are per-request. `get_current_tenant` returns the default `internal-company` tenant (no auth in MVP); 503 with actionable message if the tenant is missing.
- `src/api/schemas.py` — boundary models (`TranslateRequest/Response`, `BatchTranslateRequest/Response`, `ErrorResponse`, `HealthResponse`, `DeepHealthResponse`). Profile schemas re-exported from `src/profiles/schemas.py`.
- `src/api/middleware.py` — exception handlers map provider errors (`RateLimitError → 429 + Retry-After`, `TransientError → 503`, `PermanentError → 400`, `AuthError → 500`, `CapabilityError → 400`), resolver errors (`ProfileNotFound → 404`, inheritance issues → 500), and `ValueError → 400`. Every error body carries `error_code`, `detail`, and the request's `trace_id`.
- `src/api/routes/health.py` — `GET /health` (liveness, no I/O); `GET /health/deep` (readiness: probes Postgres + Redis + provider config, returns per-dep status).
- `src/api/routes/translate.py` — `POST /translate` and `POST /translate/batch` (parallel via `asyncio.gather`, per-item partial-success semantics).
- `src/api/routes/profiles.py` — 10 endpoints: list/create/read/update/soft-delete profiles, glossary list/add/delete, examples list/add. Soft delete flips `is_active=False` + bumps version (cache auto-invalidates).
- `src/api/main.py` — wires routers, CORS allowlist (`localhost:8501` + `localhost:8001`), `TraceIdMiddleware`, exception handlers.
- `demo/app.py` — Streamlit UI with 3 pages: Translate (profile + lang picker + result with cache/cost/glossary metrics), Profiles (browse, inspect resolved chain, add glossary terms / style examples inline), About.
- 17 new API tests (2 health, 6 translate incl. batch partial-success, 9 profiles). Tests neutralise `session.commit` (no-op replacement) so route-level commits don't leak past the per-test rollback.

**Note:** `demo/app.py` (Streamlit) deleted by sub-proyek J; React SPA in `frontend-demo/` is the current operator UI.

### Phase 6 — Basic evaluation harness
**Status:** ✅ complete (verified 2026-05-20)

- `eval/datasets/golden_v1.jsonl` — 28 entries spanning EN↔ID general/asuransi/asuransi-cs + EN→MS/JA/ZH variety; difficulty easy/medium/hard; length short/medium/long.
- `eval/metrics/base.py` — `Metric` Protocol normalising every score to `[0.0, 1.0]`.
- `eval/metrics/chrf.py` — sacrebleu CHRF wrapper; multi-reference picks best match.
- `eval/metrics/glossary_compliance.py` — thin adapter that delegates to `src.pipeline.compliance.compute_glossary_compliance` so eval scores and runtime telemetry can never drift apart.
- `eval/metrics/registry.py` — name → class map + `get_metric(name)` with `UnknownMetricError`.
- `eval/run.py` — argparse CLI with `--dataset/--profile/--target-lang/--metrics/--limit/--yes`. Cost preview + confirmation prompt before spending real money. Per-entry try/except so a bad item doesn't sink the run. Aggregates: mean/p50/p95 per metric + stratified by language pair / profile / difficulty. Outputs Markdown to stdout and `{timestamp}_{dataset}.json` to `eval/results/`.
- `eval/report.py` — `format_report(aggregates)` Markdown formatter (overall + stratified tables + failures section).
- 12 metric tests; live smoke run with `--limit 3 --yes` produced a clean Markdown report and JSON dump.

### Phase 7 — Live Webpage Translation SDK
**Status:** ✅ complete (verified 2026-05-20)

- `sdk/src/translator.js` — standalone ES2020 script, no build step. Exports `Translator` + `TranslatorClientCache` to window.
  - `collectTextNodes(root)` walks the DOM via TreeWalker, yields targets for text nodes AND translatable attributes (`alt`, `title`, `placeholder`, `<meta name=description>`, `og:title`/`og:description`).
  - Skip rules: `SKIP_TAGS` ({SCRIPT, STYLE, CODE, PRE, KBD, SAMP, TEXTAREA, NOSCRIPT}), `[data-no-translate]`, `[translate="no"]`, already-tagged `[data-translated]`.
  - Block-aware grouping via `_blockKey()` tags each block with `data-tr-block` so batches keep paragraph context.
  - `batchGroups`: greedy bin-pack honouring `MAX_BATCH_ITEMS=50` + `MAX_BATCH_CHARS=4000`; prefers block boundaries when batches near char limit.
  - `sortByVisibility`: viewport-visible batches go first via `getBoundingClientRect` scoring.
  - `translateBatch`: splits cache hits from misses; only the misses hit `/translate/batch`; populates client cache from successful results.
  - `applyTranslations`: preserves original leading/trailing whitespace on text nodes so inline layout isn't disturbed.
  - `observeMutations`: MutationObserver with 250ms debounce, filters out attribute-only and `data-translated`-tagging mutations.
  - `ClientCache`: two-tier (in-memory LRU + localStorage), djb2-hashed key includes profile version (fetched lazily at first translate via `GET /profiles/{slug}`), all errors degrade silently.
- `demo/webpage/index.html` + `demo/webpage/load-sdk.html` — sample English insurance landing page (~6 KB) with header, hero, three product cards, about, contact form, footer. Includes opt-out section (`data-no-translate`), `<code>` blocks (skip via SKIP_TAGS), `<meta>` description + og tags, `title` + `alt` + `placeholder` attrs.
- `demo/webpage/serve.py` — `ThreadingHTTPServer` on `:8001` serving `demo/webpage/` and proxying `/sdk/*` to repo's `sdk/` directory; URL-prefix path-traversal defence; `Cache-Control: no-store` for dev iteration.
- `demo/webpage/README.md` — quickstart + manual verification checklist (progressive translation, form + alt + meta + opt-out + cache hit behavior).
- No automated SDK tests in MVP per spec; live verification is manual via browser at `http://localhost:8001/load-sdk.html`.

---

**MVP complete (Phases 1–7).** The codebase now spans: foundation tooling, Claude provider abstraction, profile/glossary/examples data model, translation pipeline with Redis caching, REST API + Streamlit ops UI, basic eval harness, and live webpage SDK.

---

## Post-MVP Sub-proyek

(Started 2026-05-21.)

### Sub-proyek B — Translation log table
**Status:** ✅ complete (verified 2026-05-21, commits `d209c4e` → `8db34d2` → Phase 3 pending)

- Migration `alembic/versions/002_translation_logs.py` creates `translation_logs` table with denormalized `profile_slug`/`quality_mode` columns, forward-compat nullable columns for sub-proyek C (`detected_source_lang`, `detected_output_lang`, `source_lang_mismatch`, `output_lang_mismatch`), and 3 indexes including a partial index `WHERE status = 'failed'`. FKs cascade-delete on tenant/profile.
- `src/translation_logs/{schemas,repository,sanitize}.py` — `TranslationLogCreate`/`TranslationLogRead` Pydantic v2 models (status as `Literal["success", "failed"]`); `TranslationLogRepository.create()` inserts a row, read methods (`recent`/`by_profile`/`aggregate_cost`) are `NotImplementedError` stubs handed off to sub-proyek F. `sanitize_error` redacts `sk-ant-…` + `Bearer …` patterns and truncates to 2000 chars; a `_SESSION_LOCKS` dict serializes concurrent flushes per session (ADR-029).
- `src/pipeline/stages.py` `record_log` stage + `_build_log_payload` helper run inside the pipeline's `finally` block on every call (success, cache hit, failure). All exceptions swallowed (ADR-027); pipeline result carries `log_id` (`None` when write failed or context too incomplete).
- `src/pipeline/pipeline.py` `TranslationPipeline.translate()` refactored to `try / except / finally`; `__init__` now accepts optional `log_repo: TranslationLogRepository | None`. `PipelineRequest` extended with `batch_id`/`batch_index`/`request_metadata`; `PipelineResult` extended with `log_id`; `PipelineContext` extended with wall-clock `started_at` (required) plus orchestrator/log fields.
- `src/api/routes/translate.py` generates one `batch_id` per `/translate/batch` request; per-item `batch_index` (0..n-1) threaded through `PipelineRequest`. `TranslateResponse.log_id` and `BatchTranslateResultItem.log_id` expose the row id; clients correlate failed calls via the existing `ErrorResponse.trace_id`.
- `src/api/dependencies.py` `get_log_repository` factory provides per-request `TranslationLogRepository` injected into `get_pipeline`.
- **38 new tests** (7 sanitize, 5 schemas, 6 repository, 7 record_log stage, 7 pipeline logging integration, 2 batch logging, 4 API). Live smoke pending Task 10.
- **Known limitations:** `_SESSION_LOCKS` dict grows unbounded (bounded in practice by alive-request count); cleaner future fix is per-batch-item session. SAWarning `"Session.add() during flush"` surfaces in 2 API batch tests due to the patched-commit fixture interacting with record_log's flush — benign, no behavior impact.
- **Unblocks:** sub-proyek C (lang detection — populate forward columns), sub-proyek F (dashboard — implement read methods).

### Sub-proyek I — Tenant Junction Redesign + Auth
**Status:** ✅ complete (verified 2026-05-22)

- Migration `alembic/versions/005_tenant_junction_redesign.py` drops sub-proyek B/D/G+C tables (`translation_logs`, `style_examples`, `glossary_terms`, `profile_versions`, `profiles`, `tenants`) and creates 12 new tables: 5 reference tables (`country`, `company`, `department`, `position`, `service`), `glossary_terms` + `style_examples` re-keyed to `service_id`, `tenant` (junction of country/company/department with built-in auth columns), `tenant_profile` (nested junction of position/service per tenant), `tenant_prompts` (re-keyed by `prompt_id`), `iso_languages`, recreated `translation_logs` with retyped FK columns (VARCHAR(30) instead of UUID). Irreversible by design — `downgrade()` raises NotImplementedError.
- `src/db/ids.py` — `make_id(prefix)` generates custom `{prefix}-{8hex}-{4hex}` IDs (ADR-040), 48 bits entropy, all PKs use this format.
- `src/auth/{hashing,jwt,middleware,dependencies}.py` — argon2 password hashing (ADR-045), HS256 JWT with `tenant.jwt_active_token` (ADR-046), FastAPI middleware accepting `Authorization: Bearer <jwt>` OR `X-Tenant-API-Key: aitkey_…`, `get_current_tenant_id` dependency. Master API key (`api_key_master` setting) bypasses per-tenant auth for dev/Streamlit.
- 9 reference packages: `src/{country,company,department,position,service,tenant,tenant_profile,tenant_prompts,iso_languages}/{schemas,repository}.py` — Pydantic Create/Read pairs + async CRUD with cascade-aware queries (e.g. `CompanyRepository.list_by_country`, `PositionRepository.list_by_department`).
- `src/api/routes/auth.py` (POST `/auth/refresh-jwt`) + `src/api/routes/reference.py` (cascade: `/countries`, `/companies?country_id=`, `/departments`, `/departments/{id}/positions`, `/services`, `/tenants/by-cdd`, `/tenant-profiles`, `/iso-languages`).
- `scripts/seed_tenant_data.py` (replaces all earlier seed scripts): idempotent skip-if-exists per row; seeds ~40 iso_languages, 7 countries, 3 companies, 19 departments, 83 positions, 16 services (15 Aitegrity products + general, with tone/audience populated), 3 tenant_prompts (Jinja templates for lang_detect_input/lang_detect_output/translate), 57 tenants (3 companies × 19 departments × 1 country, API keys printed to stdout ONLY on creation), 57 default tenant_profiles (1 per tenant with position=first listed for dept, service=general).
- `src/pipeline/agents/translate.py` re-templated to consume new ORM (`tenant.company.company_name`, `tenant_profile.position.position_name`, `tenant_profile.service.service_name + tone + target_audience`). Pipeline resolver loads tenant + tenant_profile with `joinedload` for country/company/department/position/service.
- `demo/app.py` rewritten (608 → 168 lines) — cascading sidebar (Country → Company → Department → Position → Service → source lang → target lang); master API key bypass for dev convenience.
- **114 tests pass.** Breakdown: 17 sub-proyek I new (auth hashing/jwt/middleware/routes, ID generator, reference routes, seed validation) + 97 carried over from earlier phases (still green after schema redesign).
- **Known limitations:** `_SESSION_LOCKS` dict from sub-proyek B still grows unbounded (carry-over); pyjwt warns "InsecureKeyLengthWarning" for default 16-char dev JWT secret (production needs ≥32 chars); API key verification iterates candidates with bcrypt-verify (acceptable for 57 tenants, future scale needs key-prefix indexing); seed script does NOT re-print API keys on idempotent re-run — operator MUST capture keys on first run.
- **Unblocks:** sub-proyek J (frontend-demo React redesign — spec + plan committed 4772f1c / b70fa80), future sub-projects for real auth flow UI (login, token refresh).

### Sub-proyek J — Frontend Demo React Redesign
**Status:** ✅ complete (verified 2026-05-22, commits `257ec4e` initial + `c05b7a9` peer-deps fix + `a4a9e6e` Integrity rebrand per ADR-052)

- `frontend-demo/` — new Vite 8 + React 18 + TypeScript 5 (strict) + Tailwind 3 + shadcn/ui 4.x (Button/Card/Tabs/Select/Badge/Dialog/Tooltip) + Framer Motion 11 + Vitest 2 + ESLint + Prettier SPA replacing Streamlit `demo/app.py` (deleted). Branded "AI Translation by Integrity" with merah-putih palette + owl mark (ADR-052).
- `src/services/{types,mockApi,languageDetector,pricing}.ts` — typed contract that mirrors expected sub-proyek I `/translate` response shape (ADR-048, cheap mock-to-real swap). `mockApi` simulates parallel agent orchestration: lang_detect_input + translate agents fire `agent_started` within ~50ms, lang_detect completes 120–280ms, translate completes 500–2200ms (scales by model — Haiku fastest, Opus slowest). Cache hit short-circuits at 3ms latency.
- `src/hooks/{useDebouncedValue,useElapsedTimer,useTypewriter,useTranslationFlow}.ts` — state machine (`useTranslationFlow`) with `idle → running → done | error` transitions, per-agent status updates driven by `onAgentEvent` callbacks, `reqIdRef` cancellation pattern for rapid re-starts. `useTypewriter` uses `setInterval` (not setTimeout chain) for `vi.advanceTimersByTime` compatibility.
- `src/components/` — TopBar (sticky + active tenant Select dropdown), TenantManagement (form + table, mock-only per ADR-049), TranslationPlayground (LanguageBar with swap button + Input/OutputBox + LanguageMismatchBanner with shake on first appear + TranslateButton with cyan→violet gradient), AgentPipeline (SVG diagram with Framer dot-flow via `offsetPath` + per-agent cards with metrics + summary footer with parallel-savings calculation), PayloadViewer (collapsible JSON viewer with custom span-based syntax highlighter — no external highlight.js dep).
- `scripts/run-demo.ps1` — PowerShell launcher (ADR-050): locates `chrome.exe` via `$env:CHROME_PATH` + 3 standard install paths fallback, runs Vite in foreground with output visible, background `Start-Job` polls `localhost:5173` and opens Chrome on first 200 OK.
- **22 tests** (6 languageDetector + 4 mockApi + 2 useDebouncedValue + 2 useTypewriter + 4 useTranslationFlow + 2 LanguageMismatchBanner + 2 JsonHighlighter). Lint clean (`--max-warnings 0`), tsc clean, build produces `dist/`. Live smoke: HTTP 200 from dev server, HTML loads with Polyglot AI title + dark mode + fonts.
- **Known limitations / future work:** Mock-only — `services/realApi.ts` not implemented (deferred to future sub-project that wires to sub-proyek I `/translate` with auth via `Authorization: Bearer <jwt>` or `X-Tenant-API-Key`). Mandarin/Arabic/Portuguese/Russian language detection not supported in `languageDetector.ts` v1 (empty stopword sets — add on-demand). Browser launcher Windows-only (PowerShell). Pre-existing duplicate `src/lib/cn.ts` + `src/lib/utils.ts` (shadcn standard pattern, both export identical `cn` function). Vite 8 build emits `tw-animate-css` "Unknown @utility" warnings — cosmetic, build succeeds. Component tests for LanguageBar/InputBox/OutputBox/AgentPipeline not written (integration-tested through manual smoke checklist per spec §9.3).
- **Unblocks:** stakeholder-grade product demos; future operator portal can fork the scaffold for cascade-based admin UI; future SSE/WebSocket streaming integration (current adapter pattern future-proof in `services/types.ts` `TranslateApi` interface).

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

### Sub-proyek L — Frontend-Demo ↔ Real Backend Wiring (MVP)
**Status:** ✅ complete (verified 2026-05-22)

- `frontend-demo/src/services/errors.ts` — `ApiError` (with `error_code`/`detail`/`traceId` + `isLanguageNotAllowed`/`isAuth`/`isRateLimited`/`isTransient` predicates) + `NetworkError` (wraps underlying fetch failure cause). `isAuth()` matches what backend actually emits: `missing_credentials` (no auth header) + `provider_auth_failed` (Anthropic SDK rejected key) plus forward-compat slots `authentication_failed` + `tenant_not_found`.
- `frontend-demo/src/services/apiClient.ts` — thin fetch wrapper. Injects `X-Tenant-API-Key`. Parses backend `{error_code, detail, trace_id}` envelope. Wraps network failures in `NetworkError`.
- `frontend-demo/src/services/responseAdapter.ts` — `BackendTranslateResponse` type mirror + `adaptResponse(backend) → TranslateResponse` + `adaptActivity(backend) → AgenticActivity`. Defensive casts on `model_id` + `source_lang/target_lang` (fallback to sonnet/en for unknown values). Reconstructs glossary `violations[]` from `metadata.glossary_violations` count.
- `frontend-demo/src/services/realApi.ts` — `makeRealApi({baseUrl, apiKey})` factory implementing `TranslateApi`. Fires `agent_started` for both agents at request start, POSTs `/translate`, on success replays `agent_completed` events spaced by `activity.latency_ms` (cache hit short-circuits replay). On error fires `agent_failed` for both before throwing `ApiError`.
- `frontend-demo/src/services/apiSelector.ts` — `getTranslateApi()` picks mock vs real per `VITE_API_MODE` env + localStorage settings presence. Re-evaluated every call (no module-init cache) so Settings Save takes effect without reload.
- `frontend-demo/src/hooks/useApiSettings.ts` — `ApiSettings` interface + localStorage-backed hook (`baseUrl`, `apiKey`, `profileId`, `tenantId` + `isConfigured` predicate). Key `aitegrity_api_settings`.
- `frontend-demo/src/components/SettingsModal.tsx` — shadcn Dialog with 4 inputs (baseUrl, apiKey password-masked with show/hide toggle, profileId, tenantId). Save button persists to localStorage. Dialog description displays current `VITE_API_MODE`.
- `frontend-demo/src/components/TopBar.tsx` — added Settings gear button (lucide-react `Settings` icon) with red-dot indicator when `VITE_API_MODE === 'real'` AND not configured.
- `frontend-demo/src/components/TranslationPlayground/index.tsx` — renders amber/crimson banner ABOVE Card on ApiError/NetworkError with copy-on-click trace_id. Reads `profile_id`/`tenant_id` from useApiSettings when in real mode, otherwise falls back to mock tenant.id.
- `frontend-demo/src/App.tsx` — manages SettingsModal open state. Auto-opens on first launch when real mode + not configured.
- `frontend-demo/vite.config.ts` — added `/api/*` proxy → `http://localhost:8000`.
- `frontend-demo/.env.local.example` — `VITE_API_MODE=mock` + `VITE_API_BASE_URL=/api` template.
- `src/api/main.py` — CORS allowlist extended to `localhost:5173` + `127.0.0.1:5173`; removed defunct `localhost:8501` entries.
- **21+ new tests** (5 errors + 4 settings + 2 SettingsModal + 4 apiClient + 10 responseAdapter + 4 realApi + 3 apiSelector). Pre-existing 22 + new = ~50 vitest tests pass. Backend pytest 141 still green.
- **Known limitations / future work:** API key in localStorage XSS-exposed (acceptable per ADR-026 demo trade-off, production needs session-based auth). No JWT login/refresh flow (deferred). Real cascade UI replacing Tab 1 still deferred per ADR-049. SSE/WebSocket real streaming deferred — synthetic replay is the v1 approximation.
- **Unblocks:** stakeholder demos against real LLM responses. Future sub-projects: SSE streaming endpoint + frontend consumer; operator portal with cascade UI + JWT login; multi-account credential switching.
