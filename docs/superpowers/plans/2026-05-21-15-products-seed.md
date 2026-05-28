# 15 Aitegrity Products Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Phase 3 demo seed (`asuransi`/`asuransi-cs`) with 15 real Aitegrity product profiles via a self-sufficient, idempotent Python seed script. Operators get a curated profile catalog with industry-standard glossary terms and style examples per product.

**Architecture:** Single new script `scripts/seed_aitegrity_profiles.py` that ensures tenant + general profile exist (auto-creates if missing), soft-deletes existing demo profiles (per ADR-017), and creates 15 product profiles flat-inheriting from `general`. Product data lives inline as `AitegrityProductSpec @dataclass` instances. Tests use the same `db_session` fixture as Phase 3 repository tests.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0 async, existing `ProfileRepository`, pytest + pytest-asyncio.

**Commit policy:** Per user preference, NO commits during execution. Single combined commit at the end with 2-sentence recommendation + explicit user confirmation. **Never `git push`** — user pushes manually.

**Spec reference:** `docs/superpowers/specs/2026-05-21-15-products-seed-design.md`

---

## File Structure

**New files:**

| Path | Responsibility |
|------|----------------|
| `scripts/seed_aitegrity_profiles.py` | Seed script with `AitegrityProductSpec` dataclass, `AITEGRITY_PRODUCTS` list, `seed_all` async function, helpers, and `_main` CLI wrapper |
| `tests/scripts/__init__.py` | Package marker (empty) |
| `tests/scripts/test_aitegrity_product_specs.py` | 6 unit tests for data sanity (count, uniqueness, slug format, glossary range, examples, lang codes) |
| `tests/scripts/test_seed_aitegrity_profiles.py` | 3 integration tests against fixture DB (count + parent_id, idempotency, soft-delete) |

**Modified files:**

| Path | Change |
|------|--------|
| `CLAUDE.md` | Append ADR-030 (inline Python data structure for seed) to Decision log |

---

# Task 1: Test scaffolding

**Files:**
- Create: `tests/scripts/__init__.py`

- [ ] **Step 1.1: Create empty package marker**

Create `tests/scripts/__init__.py` with empty content (just file existence — pytest needs it as a package).

- [ ] **Step 1.2: Verify test discovery**

```bash
uv run pytest tests/scripts/ --collect-only
```

Expected: no errors, no tests collected (the directory exists but is empty). `pytest` happily reports "0 tests collected".

---

# Task 2: AitegrityProductSpec dataclass + 15 product definitions + sanity tests

**Files:**
- Create: `scripts/seed_aitegrity_profiles.py` (scaffolding + dataclass + product list)
- Create: `tests/scripts/test_aitegrity_product_specs.py`

This is TDD — write tests first, then implementation.

- [ ] **Step 2.1: Write failing sanity tests**

Create `tests/scripts/test_aitegrity_product_specs.py`:

```python
"""Data sanity tests for the AITEGRITY_PRODUCTS list.

These guard against common drift: someone accidentally removes a product,
typos a slug, forgets to add the EN→ID style example, etc. The tests don't
hit the DB — they only inspect the in-memory list.
"""

from __future__ import annotations

import re

from scripts.seed_aitegrity_profiles import AITEGRITY_PRODUCTS

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")


def test_specs_count_is_15() -> None:
    """Hard-coded count: catches accidental product removal."""
    assert len(AITEGRITY_PRODUCTS) == 15


def test_all_slugs_unique() -> None:
    slugs = [spec.slug for spec in AITEGRITY_PRODUCTS]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"


def test_all_slugs_kebab_case() -> None:
    for spec in AITEGRITY_PRODUCTS:
        assert _SLUG_RE.match(spec.slug), f"Slug {spec.slug!r} is not kebab-case"


def test_each_product_has_3_to_5_glossary_terms() -> None:
    for spec in AITEGRITY_PRODUCTS:
        count = len(spec.glossary)
        assert 3 <= count <= 5, (
            f"{spec.slug!r} has {count} glossary terms (expected 3–5)"
        )


def test_each_product_has_at_least_1_style_example() -> None:
    for spec in AITEGRITY_PRODUCTS:
        assert len(spec.style_examples) >= 1, (
            f"{spec.slug!r} has no style examples"
        )


def test_all_glossary_terms_en_to_id() -> None:
    """Initial seed is EN→ID only. Operators add other lang pairs via UI."""
    for spec in AITEGRITY_PRODUCTS:
        for term in spec.glossary:
            assert term.source_lang == "en", (
                f"{spec.slug!r} term {term.source_term!r} has source_lang={term.source_lang!r}"
            )
            assert term.target_lang == "id", (
                f"{spec.slug!r} term {term.source_term!r} has target_lang={term.target_lang!r}"
            )
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
uv run pytest tests/scripts/test_aitegrity_product_specs.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'scripts.seed_aitegrity_profiles'`.

- [ ] **Step 2.3: Create seed script scaffolding with dataclass and full 15-product list**

Create `scripts/seed_aitegrity_profiles.py`:

```python
"""Seed the 15 Aitegrity product profiles into the dev database.

Run with::

    uv run python scripts/seed_aitegrity_profiles.py

Self-sufficient (no need to run any prior seed script):
- Ensures tenant ``internal-company`` exists (creates if missing)
- Ensures profile ``general`` exists (creates with defaults if missing)
- Soft-deletes Phase 3 demo profiles ``asuransi`` + ``asuransi-cs`` if active
- Creates 15 product profiles (flat-inheriting from ``general``) with
  3–5 EN→ID glossary terms each and 1 EN→ID style example each

Idempotent — safe to re-run.

Per ADR-030, product data is defined inline as ``AitegrityProductSpec`` dataclass
instances rather than loaded from external YAML/JSON. Operators populate
ongoing glossary + example data via the Streamlit Profile page.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field

from src.profiles.schemas import GlossaryTermCreate, StyleExampleCreate


@dataclass(frozen=True)
class AitegrityProductSpec:
    """Static product definition consumed by ``seed_all``.

    ``frozen=True`` so the constant list cannot be accidentally mutated at
    runtime; tests assert specific terminology choices and we don't want
    silent override.
    """

    slug: str
    name: str
    description: str
    domain: str
    glossary: list[GlossaryTermCreate] = field(default_factory=list)
    style_examples: list[StyleExampleCreate] = field(default_factory=list)


# Constants reused across all specs to keep the list scannable.
_TONE = "professional formal"
_AUDIENCE = "corporate clients, compliance officers, legal/HR teams"


def _term(source: str, target: str) -> GlossaryTermCreate:
    """Shorthand for an EN→ID glossary term to keep the spec list compact."""
    return GlossaryTermCreate(
        source_term=source,
        source_lang="en",
        target_term=target,
        target_lang="id",
    )


def _example(source: str, target: str, tags: list[str] | None = None) -> StyleExampleCreate:
    """Shorthand for an EN→ID style example."""
    return StyleExampleCreate(
        source_text=source,
        target_text=target,
        source_lang="en",
        target_lang="id",
        tags=tags or [],
    )


AITEGRITY_PRODUCTS: list[AitegrityProductSpec] = [
    AitegrityProductSpec(
        slug="employment-background-screening",
        name="Employment Background Screening",
        description="Verifying job candidates' employment history, education, criminal records, and references prior to hiring.",
        domain="employment background screening",
        glossary=[
            _term("background check", "pemeriksaan latar belakang"),
            _term("employment verification", "verifikasi riwayat pekerjaan"),
            _term("education verification", "verifikasi pendidikan"),
            _term("criminal record", "catatan kriminal"),
            _term("reference check", "pengecekan referensi"),
        ],
        style_examples=[
            _example(
                "We have completed the background check for the candidate and found no discrepancies in the employment history.",
                "Kami telah menyelesaikan pemeriksaan latar belakang untuk kandidat dan tidak menemukan ketidaksesuaian dalam riwayat pekerjaan.",
                tags=["completion-report"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="whistleblowing-system",
        name="Whistleblowing System",
        description="A confidential channel for employees and stakeholders to report misconduct, fraud, or violations within an organization.",
        domain="whistleblowing and ethics reporting",
        glossary=[
            _term("whistleblower", "pelapor"),
            _term("anonymous report", "laporan anonim"),
            _term("retaliation", "pembalasan"),
            _term("internal investigation", "investigasi internal"),
            _term("misconduct", "pelanggaran"),
        ],
        style_examples=[
            _example(
                "Your report has been received and will be investigated confidentially. Retaliation against whistleblowers is strictly prohibited.",
                "Laporan Anda telah diterima dan akan diinvestigasi secara rahasia. Pembalasan terhadap pelapor sangat dilarang.",
                tags=["acknowledgement"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="due-diligence",
        name="Due Diligence",
        description="Investigation of a company, individual, or transaction to verify facts and assess risks before a business decision.",
        domain="corporate due diligence",
        glossary=[
            _term("due diligence", "uji tuntas"),
            _term("target company", "perusahaan target"),
            _term("beneficial owner", "pemilik manfaat"),
            _term("conflict of interest", "konflik kepentingan"),
            _term("risk assessment", "penilaian risiko"),
        ],
        style_examples=[
            _example(
                "The due diligence report identifies the beneficial owners and flags any potential conflicts of interest with the target company.",
                "Laporan uji tuntas mengidentifikasi pemilik manfaat dan menandai potensi konflik kepentingan dengan perusahaan target.",
                tags=["report-summary"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="mystery-shopping",
        name="Mystery Shopping",
        description="Undercover evaluation of customer service quality, product display, and operational standards through anonymous shoppers.",
        domain="mystery shopping and service evaluation",
        glossary=[
            _term("mystery shopper", "pembeli misterius"),
            _term("evaluation checklist", "daftar penilaian"),
            _term("customer experience", "pengalaman pelanggan"),
            _term("service standard", "standar layanan"),
        ],
        style_examples=[
            _example(
                "The mystery shopper noted that the staff did not greet customers within 30 seconds, falling short of the service standard.",
                "Pembeli misterius mencatat bahwa staf tidak menyapa pelanggan dalam 30 detik, di bawah standar layanan.",
                tags=["observation"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="asset-tracing",
        name="Asset Tracing",
        description="Locating and identifying hidden, misappropriated, or undisclosed assets across jurisdictions.",
        domain="asset tracing and recovery",
        glossary=[
            _term("asset tracing", "penelusuran aset"),
            _term("hidden assets", "aset tersembunyi"),
            _term("beneficial ownership", "kepemilikan manfaat"),
            _term("offshore account", "rekening luar negeri"),
            _term("asset recovery", "pemulihan aset"),
        ],
        style_examples=[
            _example(
                "The investigation revealed hidden assets held through nominee structures in three offshore jurisdictions.",
                "Investigasi mengungkap aset tersembunyi yang dipegang melalui struktur nominee di tiga yurisdiksi luar negeri.",
                tags=["finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="skip-tracing",
        name="Skip Tracing",
        description="Locating individuals who have moved, gone missing, or are intentionally avoiding contact (e.g., debtors, witnesses, heirs).",
        domain="skip tracing and subject location",
        glossary=[
            _term("skip tracing", "penelusuran orang"),
            _term("subject", "subjek"),
            _term("last known address", "alamat terakhir diketahui"),
            _term("locate", "menemukan"),
        ],
        style_examples=[
            _example(
                "Skip tracing identified the subject's current address through public records and social media verification.",
                "Penelusuran orang berhasil mengidentifikasi alamat terkini subjek melalui catatan publik dan verifikasi media sosial.",
                tags=["finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="fraud-investigation",
        name="Fraud Investigation",
        description="Investigating suspected fraudulent activity including financial fraud, internal theft, and procurement fraud.",
        domain="fraud investigation and forensic accounting",
        glossary=[
            _term("fraud", "penipuan"),
            _term("fraudulent activity", "aktivitas penipuan"),
            _term("perpetrator", "pelaku"),
            _term("evidence", "bukti"),
            _term("financial fraud", "penipuan keuangan"),
        ],
        style_examples=[
            _example(
                "The forensic review uncovered evidence of fraudulent invoices submitted by the perpetrator over a 14-month period.",
                "Tinjauan forensik mengungkap bukti faktur palsu yang diajukan pelaku selama periode 14 bulan.",
                tags=["forensic", "finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="insurance-investigation",
        name="Insurance Investigation",
        description="Investigation of insurance claims to detect fraud, verify legitimacy, and support claim adjudication.",
        domain="insurance claim investigation",
        glossary=[
            _term("insurance claim", "klaim asuransi"),
            _term("policyholder", "pemegang polis"),
            _term("claim adjuster", "penilai klaim"),
            _term("fraudulent claim", "klaim palsu"),
            _term("loss verification", "verifikasi kerugian"),
        ],
        style_examples=[
            _example(
                "Our investigation confirmed that the policyholder's claim was legitimate; loss verification supports the reported damages.",
                "Investigasi kami mengonfirmasi bahwa klaim pemegang polis sah; verifikasi kerugian mendukung kerusakan yang dilaporkan.",
                tags=["conclusion"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="market-survey",
        name="Market Survey",
        description="Primary research on market size, consumer behavior, competitor positioning, and pricing dynamics.",
        domain="market research and consumer insights",
        glossary=[
            _term("market research", "riset pasar"),
            _term("target market", "pasar sasaran"),
            _term("competitor analysis", "analisis pesaing"),
            _term("consumer behavior", "perilaku konsumen"),
        ],
        style_examples=[
            _example(
                "The market survey indicates that 62% of consumers in the target segment prefer the competitor's pricing tier.",
                "Riset pasar menunjukkan bahwa 62% konsumen di segmen sasaran lebih memilih tingkat harga pesaing.",
                tags=["finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="non-use-investigation",
        name="Non-Use Investigation",
        description="Investigating whether a registered trademark has been continuously used in commerce, as required to maintain registration.",
        domain="trademark non-use investigation",
        glossary=[
            _term("non-use", "tidak digunakan"),
            _term("trademark", "merek dagang"),
            _term("prior use", "penggunaan sebelumnya"),
            _term("commercial use", "penggunaan komersial"),
        ],
        style_examples=[
            _example(
                "Evidence collected shows that the trademark has not been used in commerce in Indonesia for the past three consecutive years.",
                "Bukti yang dikumpulkan menunjukkan bahwa merek dagang tidak digunakan dalam perdagangan di Indonesia selama tiga tahun berturut-turut.",
                tags=["finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="anti-counterfeit-investigation",
        name="Anti-Counterfeit Investigation",
        description="Identifying counterfeit goods in the market, locating manufacturers/distributors, and supporting enforcement actions.",
        domain="anti-counterfeit and brand protection",
        glossary=[
            _term("counterfeit", "barang palsu"),
            _term("genuine product", "produk asli"),
            _term("infringing goods", "barang yang melanggar"),
            _term("raid action", "penggerebekan"),
            _term("brand protection", "perlindungan merek"),
        ],
        style_examples=[
            _example(
                "Surveillance identified a warehouse distributing counterfeit products bearing the client's brand; a raid action is recommended.",
                "Pengawasan mengidentifikasi gudang yang mendistribusikan barang palsu dengan merek klien; tindakan penggerebekan direkomendasikan.",
                tags=["recommendation"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="parallel-trading",
        name="Parallel Trading",
        description="Investigating unauthorized importation and distribution of genuine products outside the authorized channels.",
        domain="parallel trade investigation",
        glossary=[
            _term("parallel trade", "perdagangan paralel"),
            _term("authorized distributor", "distributor resmi"),
            _term("gray market", "pasar abu-abu"),
            _term("unauthorized import", "impor tidak resmi"),
        ],
        style_examples=[
            _example(
                "The investigation traced the parallel imports to a distributor in Singapore reselling goods outside the authorized territory.",
                "Investigasi menelusuri impor paralel ke distributor di Singapura yang menjual kembali barang di luar wilayah resmi.",
                tags=["finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="abms",
        name="Anti-Bribery Management System (ABMS)",
        description="ISO 37001-aligned framework for preventing, detecting, and responding to bribery within an organization.",
        domain="anti-bribery compliance (ISO 37001)",
        glossary=[
            _term("anti-bribery", "anti-suap"),
            _term("bribery", "suap"),
            _term("facilitation payment", "pembayaran fasilitasi"),
            _term("gift policy", "kebijakan hadiah"),
        ],
        style_examples=[
            _example(
                "The audit found that the company's anti-bribery management system adequately addresses facilitation payments and gift policies in accordance with ISO 37001.",
                "Audit menemukan bahwa sistem manajemen anti-suap perusahaan secara memadai mengatur pembayaran fasilitasi dan kebijakan hadiah sesuai dengan ISO 37001.",
                tags=["audit-finding"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="kyc",
        name="Know Your Customer (KYC)",
        description="Customer identity verification and risk assessment for AML/CFT compliance and beneficial ownership transparency.",
        domain="KYC and customer due diligence",
        glossary=[
            _term("customer due diligence", "uji tuntas pelanggan"),
            _term("beneficial owner", "pemilik manfaat"),
            _term("identity verification", "verifikasi identitas"),
            _term("politically exposed person", "orang yang terekspos secara politik"),
        ],
        style_examples=[
            _example(
                "Enhanced customer due diligence is required when the beneficial owner is identified as a politically exposed person.",
                "Uji tuntas pelanggan yang ditingkatkan diperlukan ketika pemilik manfaat diidentifikasi sebagai orang yang terekspos secara politik.",
                tags=["policy"],
            ),
        ],
    ),
    AitegrityProductSpec(
        slug="trademark-investigation",
        name="Trademark Investigation",
        description="Investigating trademark infringement, conducting prior-use searches, and supporting opposition or cancellation actions.",
        domain="trademark investigation and IP enforcement",
        glossary=[
            _term("trademark", "merek dagang"),
            _term("infringement", "pelanggaran"),
            _term("prior use", "penggunaan sebelumnya"),
            _term("registration", "pendaftaran"),
            _term("opposition", "oposisi"),
        ],
        style_examples=[
            _example(
                "Our investigation confirmed prior use of the disputed mark by the third party since 2019, which supports the opposition filing.",
                "Investigasi kami mengonfirmasi penggunaan sebelumnya atas merek yang disengketakan oleh pihak ketiga sejak 2019, yang mendukung pengajuan oposisi.",
                tags=["finding"],
            ),
        ],
    ),
]
```

- [ ] **Step 2.4: Run sanity tests to verify they pass**

```bash
uv run pytest tests/scripts/test_aitegrity_product_specs.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 2.5: Lint + typecheck**

```bash
uv run ruff check scripts/seed_aitegrity_profiles.py tests/scripts/
uv run mypy scripts/seed_aitegrity_profiles.py
```

Expected: clean.

---

# Task 3: SeedSummary dataclass

**Files:**
- Modify: `scripts/seed_aitegrity_profiles.py` (insert SeedSummary class after `AitegrityProductSpec`)

Define this BEFORE the helpers (Task 4) so mypy resolves all forward references in declaration order.

- [ ] **Step 3.1: Insert `SeedSummary` dataclass right after `AitegrityProductSpec`**

Insert into `scripts/seed_aitegrity_profiles.py` immediately after the `AitegrityProductSpec` class definition:

```python
@dataclass
class SeedSummary:
    """Records what `seed_all` did, for the CLI summary print + test assertions."""

    deactivated: list[str] = field(default_factory=list)
    deactivated_already: list[str] = field(default_factory=list)
    products_created: list[str] = field(default_factory=list)
    products_skipped: list[str] = field(default_factory=list)

    def total_created(self) -> int:
        return len(self.products_created)

    def __str__(self) -> str:
        return (
            f"SeedSummary("
            f"deactivated={self.deactivated}, "
            f"already_inactive={self.deactivated_already}, "
            f"created={len(self.products_created)} "
            f"({', '.join(self.products_created) or '—'}), "
            f"skipped={len(self.products_skipped)} "
            f"({', '.join(self.products_skipped) or '—'})"
            f")"
        )
```

- [ ] **Step 3.2: Verify the file still imports cleanly**

```bash
uv run python -c "import scripts.seed_aitegrity_profiles"
uv run mypy scripts/seed_aitegrity_profiles.py
```

Expected: no errors. Mypy passes because `SeedSummary` is a normal dataclass with no forward references of its own.

---

# Task 4: Helpers — _deactivate_demo_profiles and _ensure_aitegrity_profile

**Files:**
- Modify: `scripts/seed_aitegrity_profiles.py` (add imports + append helpers)

The helpers are tested as part of `seed_all`'s integration tests in Task 5. We don't need separate unit tests because they're thin wrappers over `ProfileRepository`.

- [ ] **Step 4.1: Add imports needed by helpers**

Add to the import block at the top of `scripts/seed_aitegrity_profiles.py` (after the existing `from dataclasses import dataclass, field` line):

```python
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.profiles.repository import ProfileRepository
```

The `TYPE_CHECKING` guard avoids a circular import at module load time. The helpers' type annotations use the forward-reference string `"ProfileRepository"`.

- [ ] **Step 4.2: Append `_deactivate_demo_profiles` helper**

Append to `scripts/seed_aitegrity_profiles.py`:

```python
async def _deactivate_demo_profiles(
    repo: "ProfileRepository",
    tenant_id: uuid.UUID,
    summary: SeedSummary,
) -> None:
    """Soft-delete the Phase 3 demo profiles (asuransi + asuransi-cs).

    Idempotent: skips if the profile is absent or already inactive. Walks
    child first to mirror physical containment order, though soft-delete
    doesn't cascade (per ADR-017 — only is_active flips).
    """
    from src.profiles.schemas import ProfileUpdate

    for slug in ("asuransi-cs", "asuransi"):
        profile = await repo.get_profile_by_slug(tenant_id, slug)
        if profile is None:
            continue  # never existed (fresh DB), nothing to do
        if not profile.is_active:
            summary.deactivated_already.append(slug)
            continue
        await repo.update_profile(
            profile.id,
            ProfileUpdate(is_active=False),
            created_by="seed-aitegrity-products",
        )
        summary.deactivated.append(slug)
```

- [ ] **Step 4.3: Append `_ensure_aitegrity_profile` helper**

Append:

```python
async def _ensure_aitegrity_profile(
    repo: "ProfileRepository",
    tenant_id: uuid.UUID,
    general_id: uuid.UUID,
    spec: AitegrityProductSpec,
    summary: SeedSummary,
) -> None:
    """Create one product profile + its glossary + its style example if missing.

    Idempotent: if a profile with the given slug already exists, the helper
    skips ALL writes (glossary/examples included) — re-running the seed
    must not produce duplicate glossary terms.
    """
    from src.profiles.schemas import ProfileCreate

    existing = await repo.get_profile_by_slug(tenant_id, spec.slug)
    if existing is not None:
        summary.products_skipped.append(spec.slug)
        return

    profile = await repo.create_profile(
        tenant_id,
        ProfileCreate(
            slug=spec.slug,
            name=spec.name,
            description=spec.description,
            domain=spec.domain,
            tone=_TONE,
            target_audience=_AUDIENCE,
            parent_id=general_id,
        ),
    )
    for term in spec.glossary:
        await repo.add_glossary_term(profile.id, term)
    for example in spec.style_examples:
        await repo.add_style_example(profile.id, example)
    summary.products_created.append(spec.slug)
```

- [ ] **Step 4.4: Lint + typecheck after helpers added**

```bash
uv run ruff check scripts/seed_aitegrity_profiles.py
uv run mypy scripts/seed_aitegrity_profiles.py
```

Expected: clean.

---

# Task 5: `seed_all` orchestrator + integration tests

**Files:**
- Modify: `scripts/seed_aitegrity_profiles.py` (append `seed_all`)
- Create: `tests/scripts/test_seed_aitegrity_profiles.py`

TDD: tests first, then implementation.

- [ ] **Step 5.1: Write failing integration tests**

Create `tests/scripts/test_seed_aitegrity_profiles.py`:

```python
"""Integration tests for the seed_all flow.

Uses the existing db_session fixture (per-test session, rollback teardown).
Each test seeds its own tenant + general profile then runs seed_all.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_aitegrity_profiles import AITEGRITY_PRODUCTS, seed_all
from src.db.models import GlossaryTerm, Profile, ProfileVersion, StyleExample
from src.profiles.repository import ProfileRepository
from src.profiles.schemas import ProfileCreate


async def _bootstrap(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Create tenant + general profile, return (tenant_id, general_id)."""
    repo = ProfileRepository(session)
    tenant = await repo.create_tenant("internal-company")
    general = await repo.create_profile(
        tenant.id,
        ProfileCreate(
            slug="general",
            name="General",
            description="Default profile for arbitrary translation requests.",
            domain="general",
            tone="professional formal",
            target_audience="general public",
        ),
    )
    await session.flush()
    return tenant.id, general.id


async def _count(session: AsyncSession, model) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


async def test_seed_creates_16_active_profiles_with_general_as_parent(
    db_session: AsyncSession,
) -> None:
    tenant_id, general_id = await _bootstrap(db_session)

    summary = await seed_all(db_session, tenant_id=tenant_id, general_id=general_id)

    assert summary.total_created() == 15

    # Total profiles: 1 (general) + 15 (products) = 16
    profile_count = await _count(db_session, Profile)
    assert profile_count == 16

    # All 15 product profiles have parent_id == general_id and is_active=True
    rows = await db_session.execute(
        select(Profile).where(Profile.tenant_id == tenant_id, Profile.slug != "general")
    )
    products = list(rows.scalars().all())
    assert len(products) == 15
    for product in products:
        assert product.parent_id == general_id, f"{product.slug}: parent_id wrong"
        assert product.is_active is True, f"{product.slug}: not active"

    # Glossary count = sum of glossary counts in AITEGRITY_PRODUCTS
    expected_terms = sum(len(spec.glossary) for spec in AITEGRITY_PRODUCTS)
    actual_terms = await _count(db_session, GlossaryTerm)
    assert actual_terms == expected_terms

    # Style example count = sum across all specs
    expected_examples = sum(len(spec.style_examples) for spec in AITEGRITY_PRODUCTS)
    actual_examples = await _count(db_session, StyleExample)
    assert actual_examples == expected_examples


async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    tenant_id, general_id = await _bootstrap(db_session)

    summary_1 = await seed_all(db_session, tenant_id=tenant_id, general_id=general_id)
    profiles_after_1 = await _count(db_session, Profile)
    terms_after_1 = await _count(db_session, GlossaryTerm)
    examples_after_1 = await _count(db_session, StyleExample)

    summary_2 = await seed_all(db_session, tenant_id=tenant_id, general_id=general_id)

    # Second run creates nothing, skips everything
    assert summary_2.total_created() == 0
    assert len(summary_2.products_skipped) == 15

    # Counts unchanged
    assert await _count(db_session, Profile) == profiles_after_1
    assert await _count(db_session, GlossaryTerm) == terms_after_1
    assert await _count(db_session, StyleExample) == examples_after_1


async def test_seed_soft_deletes_existing_asuransi(db_session: AsyncSession) -> None:
    tenant_id, general_id = await _bootstrap(db_session)

    # Pre-seed asuransi as active (mimicking a dev DB that ran Phase 3's seed)
    repo = ProfileRepository(db_session)
    asuransi = await repo.create_profile(
        tenant_id,
        ProfileCreate(
            slug="asuransi",
            name="Insurance",
            domain="insurance",
            tone="professional reassuring",
            target_audience="insurance customers",
            parent_id=general_id,
        ),
    )
    initial_version = asuransi.version
    await db_session.flush()

    summary = await seed_all(db_session, tenant_id=tenant_id, general_id=general_id)

    assert "asuransi" in summary.deactivated

    # asuransi now is_active=False and version bumped
    refreshed_row = await db_session.execute(
        select(Profile).where(Profile.id == asuransi.id)
    )
    refreshed = refreshed_row.scalar_one()
    assert refreshed.is_active is False
    assert refreshed.version == initial_version + 1

    # ProfileVersion snapshot was written
    snapshots_row = await db_session.execute(
        select(func.count()).select_from(ProfileVersion).where(
            ProfileVersion.profile_id == asuransi.id
        )
    )
    assert snapshots_row.scalar_one() >= 1
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
uv run pytest tests/scripts/test_seed_aitegrity_profiles.py -v
```

Expected: ImportError on `seed_all` from `scripts.seed_aitegrity_profiles`.

- [ ] **Step 5.3: Implement `seed_all`**

Append to `scripts/seed_aitegrity_profiles.py`:

```python
async def seed_all(
    session: "AsyncSession",
    *,
    tenant_id: uuid.UUID,
    general_id: uuid.UUID,
) -> SeedSummary:
    """Idempotent: soft-deletes Phase 3 demo profiles, creates 15 product profiles.

    Caller is responsible for ``session.commit()``. ``seed_all`` only flushes
    via the repository pattern (no commit, no rollback). This matches the
    convention from ``src.profiles.repository`` and lets the CLI wrap the
    whole sequence in one transaction.
    """
    from src.profiles.repository import ProfileRepository

    repo = ProfileRepository(session)
    summary = SeedSummary()

    await _deactivate_demo_profiles(repo, tenant_id, summary)

    for spec in AITEGRITY_PRODUCTS:
        await _ensure_aitegrity_profile(repo, tenant_id, general_id, spec, summary)

    return summary
```

Also add the `AsyncSession` forward-reference import to the existing TYPE_CHECKING block:

```python
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.profiles.repository import ProfileRepository
```

- [ ] **Step 5.4: Run integration tests, verify they pass**

```bash
uv run pytest tests/scripts/test_seed_aitegrity_profiles.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5.5: Run full suite + lint + typecheck**

```bash
uv run pytest tests/ -x -q
uv run ruff check scripts/ tests/scripts/
uv run mypy scripts/seed_aitegrity_profiles.py
```

Expected: all clean; total test count = 192 + 6 (sanity) + 3 (integration) = 201.

---

# Task 6: `_main` CLI wrapper

**Files:**
- Modify: `scripts/seed_aitegrity_profiles.py` (append `_main` + entry point)

- [ ] **Step 6.1: Append `_main` and entry point**

Append to `scripts/seed_aitegrity_profiles.py`:

```python
async def _ensure_tenant_and_general(
    repo: "ProfileRepository",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Ensure ``internal-company`` tenant + ``general`` profile exist.

    Both are created with sensible defaults if missing — making this seed
    script self-sufficient (no need to run Phase 3's seed first).
    """
    from src.profiles.schemas import ProfileCreate

    tenant = await repo.get_tenant_by_name("internal-company")
    if tenant is None:
        tenant = await repo.create_tenant("internal-company")
        print(f"  created tenant 'internal-company' (id={tenant.id})")
    else:
        print(f"  tenant 'internal-company' already exists (id={tenant.id})")

    general = await repo.get_profile_by_slug(tenant.id, "general")
    if general is None:
        general = await repo.create_profile(
            tenant.id,
            ProfileCreate(
                slug="general",
                name="General",
                description="Default profile for arbitrary translation requests.",
                domain="general",
                tone=_TONE,
                target_audience=_AUDIENCE,
            ),
        )
        print(f"  created profile 'general' (id={general.id})")
    else:
        print(f"  profile 'general' already exists (id={general.id})")

    return tenant.id, general.id


async def _main() -> int:
    """CLI entry point. Sets up dependencies, runs seed, commits, prints summary."""
    from src.db.session import SessionLocal
    from src.profiles.repository import ProfileRepository

    async with SessionLocal() as session:
        repo = ProfileRepository(session)

        print("Bootstrapping tenant + general...")
        tenant_id, general_id = await _ensure_tenant_and_general(repo)

        print("\nSeeding 15 Aitegrity product profiles...")
        summary = await seed_all(session, tenant_id=tenant_id, general_id=general_id)

        await session.commit()

    print("\nSeed complete.")
    print(f"  Soft-deleted now:       {summary.deactivated or '—'}")
    print(f"  Already inactive:       {summary.deactivated_already or '—'}")
    print(f"  Products created:       {len(summary.products_created)} "
          f"({', '.join(summary.products_created) or '—'})")
    print(f"  Products skipped:       {len(summary.products_skipped)} "
          f"({', '.join(summary.products_skipped) or '—'})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
```

- [ ] **Step 6.2: Verify script imports cleanly**

```bash
uv run python -c "import scripts.seed_aitegrity_profiles"
```

Expected: no errors. If anything imports break (forward refs, circular), surface them now.

- [ ] **Step 6.3: Lint + typecheck final pass**

```bash
uv run ruff check scripts/seed_aitegrity_profiles.py tests/scripts/
uv run mypy scripts/seed_aitegrity_profiles.py
```

Expected: clean.

---

# Task 7: ADR-030 in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 7.1: Append ADR-030 to the Decision log section**

Find the "Decision log" section in `CLAUDE.md`. Append this line at the end of the ADR list:

```markdown
- ADR-030: `AitegrityProductSpec` di seed script defined inline sebagai `@dataclass` list, bukan eksternal YAML/JSON. Code IS data: type-checked by mypy, no parsing layer, refactor-safe di IDE. Trade-off: non-coder operators harus edit Python, tapi mereka populate ongoing data via Streamlit UI anyway sehingga external-file editing path tidak benar-benar dipakai.
```

- [ ] **Step 7.2: Verify CLAUDE.md still well-formed Markdown**

Spot-check by reading the Decision log section to confirm formatting consistency with the surrounding ADRs.

---

# Task 8: Final verification (user-facing manual smoke)

This is the only task that mutates the user's actual dev DB. The implementer/subagent should describe it but the **user** runs it.

- [ ] **Step 8.1: Run the full test suite one more time**

```bash
uv run pytest tests/ -x -q
uv run ruff check src/ tests/ scripts/
uv run mypy src/ scripts/seed_aitegrity_profiles.py
```

Expected: 201 tests pass, ruff + mypy clean. (Pre-existing ruff warning in `tests/eval/test_metrics.py` is unrelated and not our problem.)

- [ ] **Step 8.2: Document the manual smoke for the user**

After the implementer marks the task complete, the controller surfaces a manual smoke checklist for the user to run against their dev DB:

```bash
# 1. Run the seed against dev DB
uv run python scripts/seed_aitegrity_profiles.py

# 2. Verify 16 active profiles (or 18 total: 16 active + 2 inactive asuransi rows)
docker compose exec postgres psql -U aitrans -d aitrans_db -c \
  "SELECT slug, is_active FROM profiles ORDER BY is_active DESC, slug;"

# Expected:
#  general                          | t
#  abms                             | t
#  anti-counterfeit-investigation   | t
#  asset-tracing                    | t
#  ... (16 active rows total)
#  asuransi                         | f  -- soft-deleted
#  asuransi-cs                      | f  -- soft-deleted

# 3. Sanity-check Streamlit
# Start: docker compose ps; uv run uvicorn src.api.main:app --port 8000 --reload
# Then: uv run streamlit run demo/app.py
# Open the Translate page, pick profile "fraud-investigation",
# translate text "The forensic review uncovered evidence of fraudulent invoices."
# Expected output applies glossary: "tinjauan forensik", "bukti", "faktur palsu", "pelaku" appear

# 4. Verify a translation_logs row was written
docker compose exec postgres psql -U aitrans -d aitrans_db -c \
  "SELECT profile_slug, source_lang, target_lang, cache_hit, LEFT(translated_text, 80) FROM translation_logs ORDER BY started_at DESC LIMIT 1;"
```

- [ ] **Step 8.3: Final commit gate**

**Stop. Implementer/subagent does NOT commit.** Surface the recommendation to the user:

Suggested 2-sentence commit message:

> Sub-proyek D: add `scripts/seed_aitegrity_profiles.py` to soft-delete demo asuransi/asuransi-cs profiles and seed 15 Aitegrity product profiles (flat inheritance from `general`) with 3–5 EN→ID glossary terms + 1 style example each.
>
> 9 new tests (6 data sanity + 3 integration); script self-sufficient (auto-creates tenant + general if missing); ADR-030 documents the inline Python data choice.

User confirms; controller runs the commit; user pushes manually. No `git push` from any tooling.

---

## Open follow-ups (out of scope for this plan)

- Customizing tone/audience per product (e.g., ABMS/KYC → `quality_mode="thorough"`). Operators do this via Streamlit UI.
- Multi-language glossary expansion (EN→FR/JA/dst.). Operators add via UI when needed.
- Hard-delete asuransi rows after ≥6 months confirmed unused (separate later cleanup task).
- Phase status entry in CLAUDE.md describing sub-proyek D completion (matches the post-MVP pattern from sub-proyek B). Can be added in this commit or a follow-up.
