# Design — Translation Log Table (Sub-proyek B)

> **Tanggal**: 2026-05-21
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: B dari decomposisi enhancement post-MVP
> **Depends on**: tidak ada — foundation sub-project
> **Unblocks**: C (language-detection mismatch storage), F (analytics dashboard)

---

## 1. Konteks & motivasi

Saat ini setiap call ke `/translate` tidak meninggalkan jejak persistent di database. Kalau translation gagal atau hasilnya jelek di production, tidak ada cara untuk trace input/output/cost-nya selain membaca structlog JSON yang ephemeral. Sub-proyek B menambahkan tabel `translation_logs` yang merekam setiap event translate (sukses + gagal) sebagai foundation untuk:

- **Observability & debug**: replay input yang trigger error, hitung error rate per profile/language pair, korelasi via `trace_id`.
- **Cost & usage telemetry**: agregasi `cost_usd` & token counts untuk dashboard analytics.
- **Audit trail**: mana profile version yang dipakai saat call X, glossary compliance score-nya berapa, cache hit/miss.
- **Foundation untuk sub-proyek lain**: C butuh tempat simpan language-mismatch flag; F butuh tabel sebagai source data dashboard.

## 2. Goals & non-goals

**Goals:**

- Tiap call `/translate` (single atau batch item) menghasilkan tepat satu row di `translation_logs`, baik sukses maupun gagal.
- Schema cukup lengkap untuk mendukung dashboard analytics (sub-proyek F) tanpa migration tambahan.
- Forward-compat untuk sub-proyek C: kolom language-detection sudah ada (nullable), tinggal di-populate nanti.
- Graceful degradation: kalau DB log write gagal, translate response tetap sukses (match pattern cache ADR-013).
- Korelasi via `trace_id` antara structlog event, response body, dan row tabel.

**Non-goals:**

- Bukan event-sourced log atau audit log full-CRUD (CRUD profile/glossary punya `profile_versions` tersendiri).
- Bukan backfill historical data (log baru mulai dari saat migration jalan).
- Bukan repository read methods (sub-proyek F yang implement; di sub-proyek ini hanya stub `NotImplementedError`).
- Bukan retention policy / TTL / partitioning (keep forever untuk MVP).
- Bukan dashboard UI (sub-proyek F).
- Bukan external observability stack (OpenTelemetry, Prometheus); deferred ke production-readiness.

## 3. Keputusan utama

### 3.1 Capture scope: full plaintext

`source_text` dan `translated_text` disimpan utuh (TEXT, no truncation). Trade-off:

- ✓ Max debug power, bisa replay dan diff exact.
- ✗ PII surface area: kalau DB breach atau dashboard di-akses operator tidak otorisasi, data tenant exposed.
- **Mitigasi**: ADR baru yang flag concern; dashboard hanya untuk operator internal; future `log_full_text=false` flag bisa di-add reactively kalau pelanggan eksternal butuh redaction.

→ **ADR-026** (lihat §8).

### 3.2 Write semantics: pipeline stage, sync, tolerant of failure

- **Lokasi**: stage baru `record_log` di `src/pipeline/stages.py`, jalan di **`finally`** block dari `TranslationPipeline.run()`. Selalu jalan baik di success path maupun error path.
- **Sync**: stage await `repo.create()` sebelum `pipeline.run()` return; response keluar setelah log row durable.
- **Tolerant**: kalau `SQLAlchemyError` atau Pydantic `ValidationError`, `record_log` swallow + `structlog.warn(...)`. `ctx.log_id=None`, response field `log_id` keluar `null`. Translate tidak gagal karena log gagal.
- **Konsisten across entry points**: pipeline stage berarti API, eval harness, future background worker — semuanya otomatis ter-log tanpa duplicate write logic di tiap caller.

→ **ADR-027** (lihat §8).

### 3.3 Forward columns untuk sub-proyek C ditambahkan sekarang (nullable)

`detected_source_lang`, `detected_output_lang`, `source_lang_mismatch`, `output_lang_mismatch` masuk migration `002` sekarang sebagai NULL columns. C akan populate. Alasannya hindari migration berantai untuk kolom-kolom yang sudah jelas akan ada — biaya nya hanya beberapa kolom nullable yang kosong sementara.

### 3.4 Retention: keep forever (untuk MVP)

No TTL, no partitioning. Disk usage di skala demo negligible. Tambah retention reactively kalau volume naik. Tidak butuh keputusan sekarang.

### 3.5 Alternatif yang dipertimbangkan & ditolak

| Alternatif | Alasan rejected |
|---|---|
| Split tables (metadata + content separately, joined via FK) | Kompleksitas vs benefit tidak match di MVP scale (<10k rows/hari). Dashboard query butuh JOIN. Bisa di-refactor reactively. |
| Event-sourced log (append-only events + projection views) | Overkill operasional untuk MVP. |
| Postgres metadata + external metrics (OpenTelemetry/Prometheus) | Masuk untuk production hardening; sekarang tabel Postgres queryable lebih urgent. |
| API middleware write (bukan pipeline stage) | Cleaner separation, tapi eval harness tidak ke-log dan future non-API caller butuh re-implement. Konsistensi pipeline-level menang. |
| Async background task (`asyncio.create_task`) write | Risiko log hilang saat server restart. ~5–20 ms saved per call tidak sebanding. |
| Strict write (translate fail kalau log fail) | DB jadi SPOF untuk translate API. Bertentangan dengan pattern cache ADR-013. |
| `log_id` di `ErrorResponse` envelope | Middleware tidak akses ke `PipelineContext` setelah pipeline raise; butuh exception-bagging yang non-trivial. `trace_id` sudah ada di error envelope dan di log row — korelasi cukup. |

## 4. Schema

```sql
CREATE TABLE translation_logs (
  -- Identity
  id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id                 TEXT         NOT NULL,
  batch_id                 UUID         NULL,
  batch_index              INT          NULL,

  -- Multi-tenancy & profile snapshot
  tenant_id                UUID         NOT NULL REFERENCES tenants(id),
  profile_id               UUID         NOT NULL REFERENCES profiles(id),
  profile_slug             VARCHAR(64)  NOT NULL,             -- denormalized
  profile_version          INT          NOT NULL,             -- raw int, no FK
  quality_mode             VARCHAR(16)  NULL,                 -- denormalized

  -- Request
  source_lang              VARCHAR(8)   NOT NULL,
  target_lang              VARCHAR(8)   NOT NULL,
  source_text              TEXT         NOT NULL,
  source_text_length       INT          NOT NULL,
  source_text_hash         VARCHAR(64)  NOT NULL,             -- sha256(source_text); VARCHAR not CHAR (no padding semantics needed for fixed-length hex)

  -- Response (NULL on error)
  translated_text          TEXT         NULL,
  translated_text_length   INT          NULL,

  -- Model & cost
  model_id                 VARCHAR(64)  NOT NULL,
  input_tokens             INT          NULL,                 -- NULL on cache hit & pre-provider error
  output_tokens            INT          NULL,
  cost_usd                 NUMERIC(12,6) NULL,                -- Decimal per ADR-008

  -- Pipeline outcome
  status                   VARCHAR(16)  NOT NULL,             -- 'success' | 'failed'
  cache_hit                BOOLEAN      NOT NULL DEFAULT FALSE,
  cache_key                VARCHAR(32)  NULL,                 -- 128-bit truncated per ADR-012
  glossary_compliance_score NUMERIC(5,4) NULL,
  glossary_violations      JSONB        NULL,
  error_code               VARCHAR(64)  NULL,
  error_detail             TEXT         NULL,                 -- sanitized + truncated 2000 char

  -- Prompt template
  prompt_template_name     VARCHAR(64)  NOT NULL DEFAULT 'translate',
  prompt_template_version  VARCHAR(32)  NULL,

  -- Forward columns untuk sub-proyek C
  detected_source_lang     VARCHAR(8)   NULL,
  detected_output_lang     VARCHAR(8)   NULL,
  source_lang_mismatch     BOOLEAN      NULL,
  output_lang_mismatch     BOOLEAN      NULL,

  -- Open-ended metadata
  request_metadata         JSONB        NULL,                 -- SDK version, user_agent, page_url, etc.

  -- Timing
  started_at               TIMESTAMPTZ  NOT NULL,
  completed_at             TIMESTAMPTZ  NOT NULL,
  duration_ms              INT          NOT NULL,
  provider_duration_ms     INT          NULL,                 -- NULL on cache hit / pre-provider error

  CONSTRAINT translation_logs_status_chk    CHECK (status IN ('success', 'failed')),
  CONSTRAINT translation_logs_compliance_chk CHECK (glossary_compliance_score BETWEEN 0 AND 1)
);

CREATE INDEX ix_translation_logs_tenant_started
  ON translation_logs (tenant_id, started_at DESC);

CREATE INDEX ix_translation_logs_tenant_profile_started
  ON translation_logs (tenant_id, profile_id, started_at DESC);

CREATE INDEX ix_translation_logs_failed_partial
  ON translation_logs (tenant_id, started_at DESC)
  WHERE status = 'failed';
```

### Catatan kolom non-obvious

- **`profile_slug` & `quality_mode` denormalized**: dashboard `GROUP BY` jadi single-table scan. Truth at time of call dipertahankan kalau profile di-rename.
- **`profile_version` raw int, no FK**: `profile_versions` table hanya menyimpan snapshot versi lampau; versi current tidak punya row. FK akan paksa optional join.
- **`status` constraint hanya 'success' | 'failed'**: cache hit bukan status terpisah — pakai `cache_hit=true`. Future `'partial'` bisa di-add via ALTER constraint (ADR-009 compatible).
- **Partial index untuk failed rows**: error monitoring jarang melibatkan banyak data; partial index murah.
- **`source_text_hash`**: query "berapa kali text X di-translate" jadi index-hit, bukan full-text scan.
- **`duration_ms` pre-computed**: dashboard tidak perlu hitung `EXTRACT(EPOCH FROM ...)` per row.
- **`input_tokens`/`output_tokens`/`cost_usd` NULL on cache hit**: NULL = "tidak panggil provider", lebih akurat semantik dibanding 0.

## 5. Komponen

| # | Component | Path | Responsibility |
|---|-----------|------|----------------|
| 1 | `TranslationLog` ORM model | `src/db/models.py` | SQLAlchemy 2.0 `Mapped[]`, mirror schema §4 |
| 2 | `TranslationLogCreate` Pydantic | `src/translation_logs/schemas.py` | Internal write boundary; built oleh `record_log` stage dari `PipelineContext` |
| 3 | `TranslationLogRead` Pydantic | `src/translation_logs/schemas.py` | Read boundary placeholder; dipakai sub-proyek F |
| 4 | `TranslationLogRepository` | `src/translation_logs/repository.py` | `async def create(payload) -> UUID`. Read methods (`recent`, `by_profile`, `aggregate_cost`) = stub `raise NotImplementedError` untuk dipakai sub-proyek F |
| 5 | `sanitize_error` helper | `src/translation_logs/sanitize.py` | Regex redact `sk-ant-…` dan `Bearer …` patterns; truncate 2000 char |
| 6 | `record_log` stage | `src/pipeline/stages.py` | Async; bangun payload dari context, call `repo.create()`. Catch `SQLAlchemyError` + `ValidationError` → warn + swallow. Set `ctx.log_id` saat sukses |
| 7 | `PipelineContext` extensions | `src/pipeline/pipeline.py` (atau modul context yang ada) | Tambah `started_at`, `completed_at`, `cache_key`, `provider_duration_ms`, `error_code`, `error_detail`, `log_id`, `batch_id`, `batch_index`, `request_metadata` |
| 8 | `TranslationPipeline.run()` finally block | `src/pipeline/pipeline.py` | Wrap stage orchestration di `try / except / finally`. Pada `finally`: set `completed_at` + `duration_ms`, call `record_log`. Pada `except`: set error fields lalu re-raise |
| 9 | `TranslateResponse.log_id` | `src/api/schemas.py` | Field `log_id: UUID \| None` di response single + batch item |
| 10 | Dependency factory | `src/api/dependencies.py` | `get_translation_log_repository(session)` per-request. Inject ke `TranslationPipeline` constructor (tambah parameter) |
| 11 | Batch endpoint update | `src/api/routes/translate.py` | Generate `batch_id = uuid4()` sekali sebelum loop. Pass `batch_id` + `batch_index` ke tiap `PipelineRequest` / `PipelineContext` |
| 12 | Alembic migration | `alembic/versions/002_translation_logs.py` | `CREATE TABLE` + 3 indexes. No data backfill |

### Pseudocode pipeline orchestration

```python
class TranslationPipeline:
    async def run(self, request: PipelineRequest) -> PipelineResult:
        ctx = PipelineContext.from_request(request, started_at=utcnow())
        try:
            for stage in STAGES:
                await stage(ctx, self._deps)
            ctx.status = "success"
        except Exception as exc:
            ctx.status = "failed"
            ctx.error_code = getattr(exc, "error_code", type(exc).__name__)
            ctx.error_detail = sanitize_error(str(exc))
            raise
        finally:
            ctx.completed_at = utcnow()
            ctx.duration_ms = int((ctx.completed_at - ctx.started_at).total_seconds() * 1000)
            await record_log(ctx, self._log_repo)  # tolerant; never raises
        return PipelineResult.from_context(ctx)
```

## 6. Data flow

Per-stage view: who menulis field apa ke `PipelineContext`.

| Stage | Field yang di-set | Catatan |
|-------|-------------------|---------|
| (pipeline entry) | `trace_id`, `started_at`, `tenant_id`, `profile_slug`, `source_lang`, `target_lang`, `source_text` (raw), `batch_id`, `batch_index`, `request_metadata` | Field minimal supaya `record_log` bisa run walau stage validate gagal |
| `validate_and_normalize` | `source_text` (NFC), `source_text_length`, `source_text_hash` | |
| `load_resolved_profile` | `profile_id`, `profile_version`, `quality_mode` | `ProfileNotFound` → finally jalan, tapi `record_log` skip write (profile_id NOT NULL di schema; payload tidak bisa dibangun). Stage degradasi diam: log warning saja, tidak ada row tertulis. |
| `cache_lookup` | `cache_key`, `cache_hit`, kalau hit: `translated_text`, `translated_text_length`, `glossary_compliance_score`, `glossary_violations` | |
| `preprocess` | (internal) | |
| `build_prompt` | `prompt_template_name`, `prompt_template_version` | |
| `translate` | `model_id`, `translated_text`, `translated_text_length`, `input_tokens`, `output_tokens`, `cost_usd`, `provider_duration_ms` | Pre-provider errors → `input_tokens` & co. tetap NULL |
| `postprocess_and_verify` | `glossary_compliance_score`, `glossary_violations` | |
| `cache_write` | (no-op untuk log) | |
| `record_log` (finally) | `completed_at`, `duration_ms`, `status`, `log_id` | Swallow semua DB error |

**Tiga path utama yang harus ter-test:**

1. **Success cache-miss**: semua field populated kecuali error & forward-C columns.
2. **Cache hit**: `cache_hit=True`, `model_id` = current default model (cache entry tidak simpan model_id), `input_tokens`/`output_tokens`/`cost_usd` = NULL.
3. **Error path**: `status='failed'`, `error_code` + `error_detail` populated, `translated_text` NULL.

## 7. Error handling

| Skenario | Behavior |
|----------|----------|
| `SQLAlchemyError` saat `record_log` | Swallow + structlog warn. `ctx.log_id=None`. Translate response tetap success. |
| Pydantic `ValidationError` saat build `TranslationLogCreate` | Swallow + warn dengan context yang ada. `log_id=None`. |
| Batch partial failure | Tiap item independent `TranslationPipeline.run`; setiap pipeline call produce 1 log row (success atau failed). Shared `batch_id`. |
| Migration window | `CREATE TABLE` zero-downtime. In-flight requests selama migration dapat `UndefinedTableError` → swallowed sebagai SQLAlchemyError. |
| Sensitive content di error message | `sanitize_error` strip `sk-ant-…` & `Bearer …`, truncate 2000 char. Reactive, expand kalau pattern baru muncul. |
| PII di `error_detail` (echo back source_text) | Sudah di-store full plaintext di kolom dedicated, tidak menambah surface area baru. |
| Concurrent inserts | INSERT-only, no row-lock contention. |

## 8. ADR additions

| ID | Topic |
|----|-------|
| **ADR-026** | Translation log menyimpan `source_text` & `translated_text` full plaintext. PII trade-off diterima untuk MVP (single-tenant, operator internal); mitigasi reaktif berupa future redaction flag + dashboard access control kalau pelanggan eksternal onboard. |
| **ADR-027** | `record_log` swallows `SQLAlchemyError` + `ValidationError`; `log_id` nullable di response untuk signal write failure. Cache-pattern degradation (ADR-013) extended ke log layer. |
| **ADR-028** | `error_detail` sanitization via regex minimal (`sk-ant-…`, `Bearer …`), expand reactively bukan upfront. |

ADR baru di-append ke "Decision log" section di `CLAUDE.md`.

## 9. Testing strategy

### Unit tests (`tests/translation_logs/`)

- `test_repository_create_returns_uuid`
- `test_repository_create_sets_defaults`
- `test_sanitize_strips_anthropic_key`
- `test_sanitize_strips_bearer_token`
- `test_sanitize_truncates_to_2000`
- `test_record_log_stage_success`
- `test_record_log_stage_swallows_db_error`
- `test_record_log_stage_swallows_validation_error`

### Pipeline integration (`tests/pipeline/test_pipeline_logging.py`)

Real Postgres + mocked provider untuk determinisme.

- `test_pipeline_writes_log_on_success`
- `test_pipeline_writes_log_on_cache_hit`
- `test_pipeline_writes_log_on_provider_error`
- `test_pipeline_writes_log_on_profile_not_found`
- `test_pipeline_continues_when_log_write_fails`
- `test_pipeline_log_includes_forward_c_columns_null`
- `test_pipeline_log_sanitizes_error_detail`

### Batch (`tests/pipeline/test_pipeline_batch_logging.py`)

- `test_batch_creates_one_row_per_item`
- `test_batch_partial_failure_logs_both`

### API (`tests/api/test_translate_logging.py`)

- `test_translate_response_includes_log_id`
- `test_batch_response_includes_log_id_per_item`
- `test_translate_failure_does_not_expose_log_id_in_envelope`

### Migration smoke (`tests/db/test_translation_logs_migration.py`)

- `test_migration_creates_table_and_indexes`
- `test_migration_downgrade_drops_cleanly`

## 10. Open questions / follow-ups

Tidak ada open questions material — semua keputusan utama settled di brainstorm.

**Follow-ups dalam sub-proyek ini** (kalau perlu later, bukan blocker untuk plan):

- `prompt_template_version` di-leave NULL untuk MVP. Cara populate (git SHA, hash file `translate.jinja`, atau version manual di Jinja metadata) jadi sub-task terpisah saat template versioning beneran dibutuhkan.

**Follow-ups untuk sub-proyek lain** (di-handoff via spec mereka):

- **Sub-proyek C** akan populate `detected_source_lang`, `detected_output_lang`, `source_lang_mismatch`, `output_lang_mismatch`.
- **Sub-proyek F** akan implement `TranslationLogRepository.recent`, `by_profile`, `aggregate_cost`, dan build dashboard view yang baca dari tabel ini.

## 11. References

- `CLAUDE.md` — project context, existing ADR list (terutama ADR-008, ADR-012, ADR-013, ADR-017, ADR-019).
- `docs/technical.md` — current technical overview (Phase 1–7 MVP).
- `src/pipeline/pipeline.py`, `src/pipeline/stages.py` — pipeline integration target.
- `src/profiles/repository.py` — pola repository yang akan diikuti.
- `alembic/versions/001_profile_schema.py` — pola migration yang akan diikuti.
