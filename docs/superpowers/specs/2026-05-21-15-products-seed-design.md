# Design — Seed 15 Aitegrity Products (Sub-proyek D)

> **Tanggal**: 2026-05-21
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: D dari decomposisi post-MVP
> **Depends on**: tidak ada (data-only sub-project)
> **Unblocks**: E (UI overhaul yang butuh konten real per produk)

---

## 1. Konteks & motivasi

Demo seed Phase 3 (`asuransi` + `asuransi-cs`) ditulis sebagai placeholder untuk validasi profile inheritance system, bukan representasi produk Aitegrity yang sebenarnya. Untuk stakeholder demo dan untuk operator yang akan curate glossary jangka panjang, profile catalog harus reflect 15 produk Aitegrity yang real:

1. Employment Background Screening (EBS)
2. Whistleblowing System
3. Due Diligence
4. Mystery Shopping
5. Asset Tracing
6. Skip Tracing
7. Fraud Investigation
8. Insurance Investigation
9. Market Survey
10. Non-Use Investigation
11. Anti-Counterfeit Investigation
12. Parallel Trading
13. Anti-Bribery Management System (ABMS)
14. Know Your Customer (KYC)
15. Trademark Investigation

Plus profile `general` (existing, untreated) sebagai default untuk request yang tidak menentukan profile spesifik.

## 2. Goals & non-goals

**Goals:**
- 16 profiles aktif di DB: `general` + 15 produk Aitegrity, semua flat-inheriting dari `general`.
- Existing demo profiles (`asuransi`, `asuransi-cs`) soft-deleted (ADR-017 pattern) — audit trail preserved, translation_logs FK preserved.
- Tiap produk punya 3–5 glossary terms (EN→ID, terminologi industry-standard) + ≥1 style example untuk warm-start translation quality.
- Seed script idempotent, manually run by operator, safe untuk re-run.

**Non-goals:**
- Bukan multi-language glossary expansion (FR/JA/dsb.) — initial seed EN→ID saja; operator add via UI later.
- Bukan automatic schema migration (data work, bukan DDL).
- Bukan removal of `general` profile or modification of its existing data.
- Bukan tone/audience customization per product (semua standardized `"professional formal"` untuk MVP; operator refine via UI).
- Bukan deletion of existing translation_logs that reference `asuransi`/`asuransi-cs` — those rows stay valid post soft-delete.

## 3. Keputusan utama

### 3.1 Soft-delete asuransi/asuransi-cs (ADR-017 pattern)

Set `is_active=False` + bump version. Profile + glossary + examples + version snapshots preserved. Translation_logs lama valid (FK preserved). Streamlit profile list filters `is_active=True` by default sehingga demo profiles tidak appear.

**Alternatives rejected:** hard delete cascades ke translation_logs (ondelete CASCADE) — destroys audit history. Leave alongside clutters operator UI. Repurpose (rename) confuses historical log debugging (slug denormalised di logs would refer to old name).

### 3.2 Flat inheritance — 15 → general

Semua 15 produk `parent_id = general.id`. 1-level inheritance.

**Alternatives rejected:** Grouped 2-level (investigation/compliance/survey/misc → general → 15 produk) adds 4 intermediate profiles untuk maintain. Cache invalidation lebih kompleks (bump category version invalidates all children). Shared glossary at category level powerful tapi tidak ada demand yet — operator dapat duplicate terms across products via UI if needed. Standalone (no parent) wastes the inheritance system entirely.

### 3.3 Researched glossary + style example per product

3–5 EN→ID glossary terms per product, plus 1 style example. Terminology aligned dengan istilah industry-standard dalam forensic/compliance Indonesia. Operator bisa refine atau add languages via Streamlit UI.

**Alternatives rejected:** Empty seed punya nol demo value untuk stakeholder. Generic placeholder ("subject" → "subjek") terlalu repetitif across investigation products dan tidak showcase product-specific terminology.

### 3.4 Inline Python data structure (no external YAML/JSON)

`AitegrityProductSpec` `@dataclass` di `scripts/seed_aitegrity_profiles.py`, list-defined inline. Type-checked by mypy, refactor-safe in IDE, no parsing layer.

**Alternative rejected:** External YAML/JSON gives non-coder edit access, tapi operators populate ongoing data via Streamlit UI anyway — YAML editing path isn't actually used.

## 4. Schema/Data — 15 produk lengkap

Tone standardized: `tone="professional formal"`, `target_audience="corporate clients, compliance officers, legal/HR teams"`, `quality_mode="balanced"` (default), `parent_id=general_id`.

Format setiap entry: `slug`, `name`, `description`, `domain`, glossary list (EN→ID), style example (EN→ID).

### 4.1 Employment Background Screening

- **slug**: `employment-background-screening`
- **name**: `Employment Background Screening`
- **description**: `Verifying job candidates' employment history, education, criminal records, and references prior to hiring.`
- **domain**: `employment background screening`
- **Glossary** (5):
  - `background check` → `pemeriksaan latar belakang`
  - `employment verification` → `verifikasi riwayat pekerjaan`
  - `education verification` → `verifikasi pendidikan`
  - `criminal record` → `catatan kriminal`
  - `reference check` → `pengecekan referensi`
- **Style example**:
  - EN: `We have completed the background check for the candidate and found no discrepancies in the employment history.`
  - ID: `Kami telah menyelesaikan pemeriksaan latar belakang untuk kandidat dan tidak menemukan ketidaksesuaian dalam riwayat pekerjaan.`

### 4.2 Whistleblowing System

- **slug**: `whistleblowing-system`
- **name**: `Whistleblowing System`
- **description**: `A confidential channel for employees and stakeholders to report misconduct, fraud, or violations within an organization.`
- **domain**: `whistleblowing and ethics reporting`
- **Glossary** (5):
  - `whistleblower` → `pelapor`
  - `anonymous report` → `laporan anonim`
  - `retaliation` → `pembalasan`
  - `internal investigation` → `investigasi internal`
  - `misconduct` → `pelanggaran`
- **Style example**:
  - EN: `Your report has been received and will be investigated confidentially. Retaliation against whistleblowers is strictly prohibited.`
  - ID: `Laporan Anda telah diterima dan akan diinvestigasi secara rahasia. Pembalasan terhadap pelapor sangat dilarang.`

### 4.3 Due Diligence

- **slug**: `due-diligence`
- **name**: `Due Diligence`
- **description**: `Investigation of a company, individual, or transaction to verify facts and assess risks before a business decision.`
- **domain**: `corporate due diligence`
- **Glossary** (5):
  - `due diligence` → `uji tuntas`
  - `target company` → `perusahaan target`
  - `beneficial owner` → `pemilik manfaat`
  - `conflict of interest` → `konflik kepentingan`
  - `risk assessment` → `penilaian risiko`
- **Style example**:
  - EN: `The due diligence report identifies the beneficial owners and flags any potential conflicts of interest with the target company.`
  - ID: `Laporan uji tuntas mengidentifikasi pemilik manfaat dan menandai potensi konflik kepentingan dengan perusahaan target.`

### 4.4 Mystery Shopping

- **slug**: `mystery-shopping`
- **name**: `Mystery Shopping`
- **description**: `Undercover evaluation of customer service quality, product display, and operational standards through anonymous shoppers.`
- **domain**: `mystery shopping and service evaluation`
- **Glossary** (4):
  - `mystery shopper` → `pembeli misterius`
  - `evaluation checklist` → `daftar penilaian`
  - `customer experience` → `pengalaman pelanggan`
  - `service standard` → `standar layanan`
- **Style example**:
  - EN: `The mystery shopper noted that the staff did not greet customers within 30 seconds, falling short of the service standard.`
  - ID: `Pembeli misterius mencatat bahwa staf tidak menyapa pelanggan dalam 30 detik, di bawah standar layanan.`

### 4.5 Asset Tracing

- **slug**: `asset-tracing`
- **name**: `Asset Tracing`
- **description**: `Locating and identifying hidden, misappropriated, or undisclosed assets across jurisdictions.`
- **domain**: `asset tracing and recovery`
- **Glossary** (5):
  - `asset tracing` → `penelusuran aset`
  - `hidden assets` → `aset tersembunyi`
  - `beneficial ownership` → `kepemilikan manfaat`
  - `offshore account` → `rekening luar negeri`
  - `asset recovery` → `pemulihan aset`
- **Style example**:
  - EN: `The investigation revealed hidden assets held through nominee structures in three offshore jurisdictions.`
  - ID: `Investigasi mengungkap aset tersembunyi yang dipegang melalui struktur nominee di tiga yurisdiksi luar negeri.`

### 4.6 Skip Tracing

- **slug**: `skip-tracing`
- **name**: `Skip Tracing`
- **description**: `Locating individuals who have moved, gone missing, or are intentionally avoiding contact (e.g., debtors, witnesses, heirs).`
- **domain**: `skip tracing and subject location`
- **Glossary** (4):
  - `skip tracing` → `penelusuran orang`
  - `subject` → `subjek`
  - `last known address` → `alamat terakhir diketahui`
  - `locate` → `menemukan`
- **Style example**:
  - EN: `Skip tracing identified the subject's current address through public records and social media verification.`
  - ID: `Penelusuran orang berhasil mengidentifikasi alamat terkini subjek melalui catatan publik dan verifikasi media sosial.`

### 4.7 Fraud Investigation

- **slug**: `fraud-investigation`
- **name**: `Fraud Investigation`
- **description**: `Investigating suspected fraudulent activity including financial fraud, internal theft, and procurement fraud.`
- **domain**: `fraud investigation and forensic accounting`
- **Glossary** (5):
  - `fraud` → `penipuan`
  - `fraudulent activity` → `aktivitas penipuan`
  - `perpetrator` → `pelaku`
  - `evidence` → `bukti`
  - `financial fraud` → `penipuan keuangan`
- **Style example**:
  - EN: `The forensic review uncovered evidence of fraudulent invoices submitted by the perpetrator over a 14-month period.`
  - ID: `Tinjauan forensik mengungkap bukti faktur palsu yang diajukan pelaku selama periode 14 bulan.`

### 4.8 Insurance Investigation

- **slug**: `insurance-investigation`
- **name**: `Insurance Investigation`
- **description**: `Investigation of insurance claims to detect fraud, verify legitimacy, and support claim adjudication.`
- **domain**: `insurance claim investigation`
- **Glossary** (5):
  - `insurance claim` → `klaim asuransi`
  - `policyholder` → `pemegang polis`
  - `claim adjuster` → `penilai klaim`
  - `fraudulent claim` → `klaim palsu`
  - `loss verification` → `verifikasi kerugian`
- **Style example**:
  - EN: `Our investigation confirmed that the policyholder's claim was legitimate; loss verification supports the reported damages.`
  - ID: `Investigasi kami mengonfirmasi bahwa klaim pemegang polis sah; verifikasi kerugian mendukung kerusakan yang dilaporkan.`

### 4.9 Market Survey

- **slug**: `market-survey`
- **name**: `Market Survey`
- **description**: `Primary research on market size, consumer behavior, competitor positioning, and pricing dynamics.`
- **domain**: `market research and consumer insights`
- **Glossary** (4):
  - `market research` → `riset pasar`
  - `target market` → `pasar sasaran`
  - `competitor analysis` → `analisis pesaing`
  - `consumer behavior` → `perilaku konsumen`
- **Style example**:
  - EN: `The market survey indicates that 62% of consumers in the target segment prefer the competitor's pricing tier.`
  - ID: `Riset pasar menunjukkan bahwa 62% konsumen di segmen sasaran lebih memilih tingkat harga pesaing.`

### 4.10 Non-Use Investigation

- **slug**: `non-use-investigation`
- **name**: `Non-Use Investigation`
- **description**: `Investigating whether a registered trademark has been continuously used in commerce, as required to maintain registration.`
- **domain**: `trademark non-use investigation`
- **Glossary** (4):
  - `non-use` → `tidak digunakan`
  - `trademark` → `merek dagang`
  - `prior use` → `penggunaan sebelumnya`
  - `commercial use` → `penggunaan komersial`
- **Style example**:
  - EN: `Evidence collected shows that the trademark has not been used in commerce in Indonesia for the past three consecutive years.`
  - ID: `Bukti yang dikumpulkan menunjukkan bahwa merek dagang tidak digunakan dalam perdagangan di Indonesia selama tiga tahun berturut-turut.`

### 4.11 Anti-Counterfeit Investigation

- **slug**: `anti-counterfeit-investigation`
- **name**: `Anti-Counterfeit Investigation`
- **description**: `Identifying counterfeit goods in the market, locating manufacturers/distributors, and supporting enforcement actions.`
- **domain**: `anti-counterfeit and brand protection`
- **Glossary** (5):
  - `counterfeit` → `barang palsu`
  - `genuine product` → `produk asli`
  - `infringing goods` → `barang yang melanggar`
  - `raid action` → `penggerebekan`
  - `brand protection` → `perlindungan merek`
- **Style example**:
  - EN: `Surveillance identified a warehouse distributing counterfeit products bearing the client's brand; a raid action is recommended.`
  - ID: `Pengawasan mengidentifikasi gudang yang mendistribusikan barang palsu dengan merek klien; tindakan penggerebekan direkomendasikan.`

### 4.12 Parallel Trading

- **slug**: `parallel-trading`
- **name**: `Parallel Trading`
- **description**: `Investigating unauthorized importation and distribution of genuine products outside the authorized channels.`
- **domain**: `parallel trade investigation`
- **Glossary** (4):
  - `parallel trade` → `perdagangan paralel`
  - `authorized distributor` → `distributor resmi`
  - `gray market` → `pasar abu-abu`
  - `unauthorized import` → `impor tidak resmi`
- **Style example**:
  - EN: `The investigation traced the parallel imports to a distributor in Singapore reselling goods outside the authorized territory.`
  - ID: `Investigasi menelusuri impor paralel ke distributor di Singapura yang menjual kembali barang di luar wilayah resmi.`

### 4.13 Anti-Bribery Management System (ABMS)

- **slug**: `abms`
- **name**: `Anti-Bribery Management System (ABMS)`
- **description**: `ISO 37001-aligned framework for preventing, detecting, and responding to bribery within an organization.`
- **domain**: `anti-bribery compliance (ISO 37001)`
- **Glossary** (4):
  - `anti-bribery` → `anti-suap`
  - `bribery` → `suap`
  - `facilitation payment` → `pembayaran fasilitasi`
  - `gift policy` → `kebijakan hadiah`
- **Style example**:
  - EN: `The audit found that the company's anti-bribery management system adequately addresses facilitation payments and gift policies in accordance with ISO 37001.`
  - ID: `Audit menemukan bahwa sistem manajemen anti-suap perusahaan secara memadai mengatur pembayaran fasilitasi dan kebijakan hadiah sesuai dengan ISO 37001.`

### 4.14 Know Your Customer (KYC)

- **slug**: `kyc`
- **name**: `Know Your Customer (KYC)`
- **description**: `Customer identity verification and risk assessment for AML/CFT compliance and beneficial ownership transparency.`
- **domain**: `KYC and customer due diligence`
- **Glossary** (4):
  - `customer due diligence` → `uji tuntas pelanggan`
  - `beneficial owner` → `pemilik manfaat`
  - `identity verification` → `verifikasi identitas`
  - `politically exposed person` → `orang yang terekspos secara politik`
- **Style example**:
  - EN: `Enhanced customer due diligence is required when the beneficial owner is identified as a politically exposed person.`
  - ID: `Uji tuntas pelanggan yang ditingkatkan diperlukan ketika pemilik manfaat diidentifikasi sebagai orang yang terekspos secara politik.`

### 4.15 Trademark Investigation

- **slug**: `trademark-investigation`
- **name**: `Trademark Investigation`
- **description**: `Investigating trademark infringement, conducting prior-use searches, and supporting opposition or cancellation actions.`
- **domain**: `trademark investigation and IP enforcement`
- **Glossary** (5):
  - `trademark` → `merek dagang`
  - `infringement` → `pelanggaran`
  - `prior use` → `penggunaan sebelumnya`
  - `registration` → `pendaftaran`
  - `opposition` → `oposisi`
- **Style example**:
  - EN: `Our investigation confirmed prior use of the disputed mark by the third party since 2019, which supports the opposition filing.`
  - ID: `Investigasi kami mengonfirmasi penggunaan sebelumnya atas merek yang disengketakan oleh pihak ketiga sejak 2019, yang mendukung pengajuan oposisi.`

### 4.16 Terminology notes

Beberapa pilihan terminologi yang sengaja dipilih (untuk transparansi audit):
- `gray market` → `pasar abu-abu` (bukan "pasar gelap" yang artinya black market/illegal)
- `KYC`, `ABMS`, `ISO 37001`, `PEP` — industry-standard abbreviations, di-leave English
- `due diligence` → `uji tuntas` (standar Bank Indonesia / OJK)
- `non-use` → `tidak digunakan` (bukan "non-penggunaan" yang kaku)
- `opposition` (trademark) → `oposisi` (term hukum trademark Indonesia, bukan "keberatan" yang generic)
- `whistleblower` → `pelapor` (term umum dalam UU Perlindungan Saksi/Korban Indonesia)

Operators dapat refine via Streamlit UI kalau ada istilah internal Aitegrity yang preferred.

## 5. Komponen

| # | Component | Path | Responsibility |
|---|-----------|------|----------------|
| 1 | `AitegrityProductSpec` dataclass | `scripts/seed_aitegrity_profiles.py` | Frozen `@dataclass`: slug, name, description, domain, glossary terms list, style examples list |
| 2 | `AITEGRITY_PRODUCTS` constant | same file | List of 15 `AitegrityProductSpec` instances |
| 3 | `seed_all` async function | same file | Testable entrypoint: takes session + tenant_id + general_id, runs deactivate + seed. Returns `SeedSummary` for logging |
| 4 | `_deactivate_demo_profiles` helper | same file | Soft-delete asuransi + asuransi-cs if active. Idempotent |
| 5 | `_ensure_aitegrity_profile` helper | same file | Create one product profile + glossary + style example if not exists |
| 6 | `_main` CLI wrapper | same file | Construct session via `SessionLocal`, resolve tenant_id + general_id, call `seed_all`, print summary, commit |
| 7 | Unit tests | `tests/scripts/test_aitegrity_product_specs.py` | Data sanity (counts, uniqueness, format) |
| 8 | Integration tests | `tests/scripts/test_seed_aitegrity_profiles.py` | seed_all behaviour against fixture DB |

### 5.1 Pseudocode `seed_all`

```python
async def seed_all(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    general_id: uuid.UUID,
) -> SeedSummary:
    """Idempotent: soft-deletes demo profiles, creates 15 Aitegrity products.

    Caller responsible for session.commit(). seed_all only flushes within
    the session via the repository pattern.
    """
    repo = ProfileRepository(session)
    summary = SeedSummary()

    await _deactivate_demo_profiles(repo, tenant_id, summary)

    for spec in AITEGRITY_PRODUCTS:
        await _ensure_aitegrity_profile(repo, tenant_id, general_id, spec, summary)

    return summary
```

### 5.2 Self-sufficient seed script

`seed_aitegrity_profiles.py` is self-sufficient — operator tidak perlu run script lain dulu. `_main` ensures:
- Tenant `internal-company` exists (creates if missing)
- Profile `general` exists (creates if missing, with the same defaults as the original Phase 3 seed)
- Soft-delete `asuransi` + `asuransi-cs` if present and active (skip if absent or already inactive)
- 15 product profiles seeded via `_ensure_aitegrity_profile`

This eliminates the "run script A first, then script B" friction for new contributors. The Phase 3 `scripts/seed_sample_profile.py` is left as historical reference but no longer needed for new dev setups.

| Scenario | Result |
|----------|--------|
| Fresh dev DB (nothing exists) | Creates tenant + general + 15 products (skips soft-delete step) |
| Existing dev DB (general + asuransi seeded) | Soft-deletes asuransi tree + creates 15 products |
| Re-run on same DB | Skips all (idempotent), prints summary |

## 6. Migration semantics

### 6.1 Soft-delete flow

For each of `["asuransi-cs", "asuransi"]` (child first to mirror physical order, though not strictly required since soft-delete doesn't cascade):

```python
profile = await repo.get_profile_by_slug(tenant_id, slug)
if profile is None:
    continue  # never existed, nothing to do
if not profile.is_active:
    continue  # already soft-deleted, skip
await repo.update_profile(
    profile.id,
    ProfileUpdate(is_active=False),
    created_by="seed-aitegrity-products",
)
```

`update_profile` writes a `ProfileVersion` snapshot **before** mutating, then bumps `version` and flips `is_active`. Audit trail captures the "moment of deactivation" state.

### 6.2 Cache invalidation

- Profile version bump → cache keys including old `profile_version` become orphaned
- Orphaned entries expire via 30-day TTL (ADR-013 cache config)
- No manual Redis flush needed

### 6.3 Translation_logs preservation

- Soft-delete doesn't cascade to logs (FK `ondelete CASCADE` only fires on hard delete)
- Existing log rows referencing `asuransi`/`asuransi-cs` profile_id stay valid
- Dashboard read queries (sub-proyek F future) can `WHERE profile_slug NOT IN ('asuransi', 'asuransi-cs')` if mau exclude demo data

### 6.4 Idempotency

- `_ensure_profile` (existing helper) checks slug uniqueness before insert
- Glossary + style examples only added on first creation (matches existing Phase 3 pattern)
- Re-running script is no-op once seeded; only prints summary

## 7. Error handling

| Skenario | Behavior |
|----------|----------|
| Tenant `internal-company` belum ada | `_main` auto-creates it (self-sufficient script per §5.2). |
| Profile `general` belum ada | `_main` auto-creates it dengan defaults (`tone="professional formal"`, dst.). |
| Profile asuransi tidak ada (fresh DB) | OK — soft-delete step is skipped. |
| Profile dengan slug Aitegrity sudah ada (manual created by operator) | Skip glossary/example creation. Print warning. Don't duplicate terms. |
| Session.commit fails di `_main` | Print error, return non-zero exit code. Operator inspects + reruns. |
| Glossary term insert fails mid-loop | Session rollback by `async with` context manager. Partial state cleaned up. Operator reruns; idempotent helper skips already-created products. |

## 8. Testing strategy

### 8.1 Unit tests — data sanity (`tests/scripts/test_aitegrity_product_specs.py`)

- `test_specs_count_is_15`
- `test_all_slugs_unique`
- `test_all_slugs_kebab_case` — regex `^[a-z][a-z0-9-]*[a-z0-9]$`
- `test_each_product_has_3_to_5_glossary_terms`
- `test_each_product_has_at_least_1_style_example`
- `test_all_glossary_terms_en_to_id`

### 8.2 Integration tests — seed flow (`tests/scripts/test_seed_aitegrity_profiles.py`)

- `test_seed_creates_16_active_profiles_with_general_as_parent` — runs `seed_all` against fixture DB, asserts 16 profiles, all 15 product profiles have `parent_id == general_id` and `is_active=True`
- `test_seed_is_idempotent` — runs twice, asserts profile/glossary/example counts unchanged on second run
- `test_seed_soft_deletes_existing_asuransi` — pre-seeds asuransi profile as active, runs `seed_all`, asserts `is_active=False` AND `version` bumped (snapshot exists in `profile_versions`)

### 8.3 Manual smoke

1. `uv run python scripts/seed_aitegrity_profiles.py`
2. `curl -s http://localhost:8000/profiles | jq 'length'` → 18 (16 active + 2 inactive)
3. `curl -s http://localhost:8000/profiles | jq '[.[] | select(.is_active)] | length'` → 16
4. Buka Streamlit, pilih `fraud-investigation`, translate `"The forensic review uncovered evidence of fraudulent invoices."` → expect glossary terms `tinjauan forensik`, `bukti`, `faktur palsu`, `pelaku` muncul di output

## 9. ADR additions

| ID | Topic |
|----|-------|
| **ADR-030** | `AitegrityProductSpec` data defined inline in Python (`@dataclass` list at top of seed script) rather than external YAML/JSON. Code IS data here — type-checked by mypy, no parsing layer, refactor-safe in IDE. Trade-off: non-coder operators must edit Python, but they populate ongoing data via Streamlit UI anyway. |

ADR-030 di-append ke "Decision log" section di `CLAUDE.md` saat implementation.

## 10. Open questions / follow-ups

Tidak ada open questions material — semua keputusan utama settled di brainstorm.

**Follow-ups (out of scope for sub-proyek D):**
- Sub-proyek E (UI overhaul) bisa pakai produk catalog ini untuk showcase
- Future: tone/audience customization per product (kalau ABMS/KYC butuh "thorough" mode, EBS butuh "balanced", dsb.) — operator-driven via UI
- Future: multi-language glossary (EN→FR, EN→JA, dst.) — operator add via UI when needed
- Future: hard-delete asuransi rows kalau confirmed unused for ≥6 months

## 11. References

- `CLAUDE.md` — ADR-017 (profile soft-delete), ADR-002 (single inheritance), ADR-013 (cache graceful degradation)
- `scripts/seed_sample_profile.py` — Phase 3 seed pattern being extended
- `src/profiles/repository.py` — `ProfileRepository.update_profile` (the soft-delete mechanism)
- `src/db/models.py` — `Profile.is_active` column + `ProfileVersion` snapshot table
