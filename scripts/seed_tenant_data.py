"""Seed the sub-proyek I junction schema with operator-facing data.

Run with::

    uv run python scripts/seed_tenant_data.py

Idempotent (skip-if-exists per row). Tenant API keys are generated freshly
on every first-time-create and printed to stdout; redirect the output to a
secure file the first time you run this.

Seed flow (10 steps, in order):

 1. ISO languages (40 entries)
 2. Countries (7)
 3. Companies (3) - FK country (by name)
 4. Departments (19)
 5. Positions (83) - FK department
 6. Services (16: general + 15 Aitegrity products) - with tone/audience
 7. Glossary terms + style examples per service
 8. Tenant prompts (3: lang_detect_input, lang_detect_output, translate)
 9. Tenants (57 = 3 companies x 19 departments) - generates API keys, prints plaintext
10. Tenant profiles (57 = 1 default per tenant)
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.hashing import generate_api_key, hash_api_key
from src.config.logging import get_logger
from src.db.ids import make_id
from src.db.models import (
    Company,
    Country,
    Department,
    GlossaryTerm,
    IsoLanguage,
    Position,
    Service,
    StyleExample,
    Tenant,
    TenantProfile,
    TenantPrompt,
)
from src.db.session import SessionLocal
from src.iso_languages.seed_data import ISO_LANGUAGES

# Module-level logger so the catalog-lookup fallback in ``seed_tenants`` can
# surface a structured warning (``seed.country_catalog_miss``) per spec §5.2.
# A miss means the country reference table did not contain the denormalized
# string carried by ``company.company_country`` — we fall back to that string
# as-is and let ops investigate via the structured log.
log = get_logger(__name__)

# ---- Static catalog ------------------------------------------------------

COUNTRIES: list[str] = [
    "Indonesia",
    "Malaysia",
    "Thailand",
    "Vietnam",
    "Germany",
    "France",
    "Switzerland",
]

COMPANIES: list[tuple[str, str]] = [
    ("PT Integrity Indonesia", "Indonesia"),
    ("Jasa Integritas Malaysia Sdn. Bhd.", "Malaysia"),
    ("Integrity Thailand Ltd", "Thailand"),
]

DEPARTMENTS: list[str] = [
    "Accounting",
    "Brand Protection",
    "Brand Protection and Integrity Services",
    "Business Expansion & Marketing",
    "Design & Development",
    "Due Dilligence and Corporate Enquiries",
    "Employment Background Screening",
    "General Affairs",
    "Human Resources",
    "Information Technology",
    "Innovatech Solution",
    "Investigation",
    "Management",
    "Operations",
    "Quality",
    "Sales",
    "Sertifikasi Bio Data",
    "Surveillance",
    "Whistleblowing",
]

# 83 positions distributed across the 19 departments. Each tuple is
# (position_name, department_name). Position-department pairs are the
# canonical organisational mapping; the FK enforces that a position name
# can be re-used across departments only as distinct rows.
POSITION_DEPARTMENT_PAIRS: list[tuple[str, str]] = [
    # Accounting (5)
    ("Accounting Supervisor", "Accounting"),
    ("Finance & Tax Officer", "Accounting"),
    ("AR Specialist", "Accounting"),
    ("AP Specialist", "Accounting"),
    ("Accounting Manager", "Accounting"),
    # Brand Protection (4)
    ("Field Researcher", "Brand Protection"),
    ("Brand Protection Officer", "Brand Protection"),
    ("Brand Protection Analyst", "Brand Protection"),
    ("Brand Protection Manager", "Brand Protection"),
    # Brand Protection and Integrity Services (4)
    ("Analyst", "Brand Protection and Integrity Services"),
    ("Senior Analyst", "Brand Protection and Integrity Services"),
    ("Project Lead", "Brand Protection and Integrity Services"),
    ("Service Manager", "Brand Protection and Integrity Services"),
    # Business Expansion & Marketing (4)
    ("Business Development Officer", "Business Expansion & Marketing"),
    ("Marketing Specialist", "Business Expansion & Marketing"),
    ("Marketing Manager", "Business Expansion & Marketing"),
    ("BD Manager", "Business Expansion & Marketing"),
    # Design & Development (4)
    ("UX Designer", "Design & Development"),
    ("Frontend Developer", "Design & Development"),
    ("Backend Developer", "Design & Development"),
    ("Tech Lead", "Design & Development"),
    # Due Dilligence and Corporate Enquiries (5)
    ("Analyst - Due Diligence", "Due Dilligence and Corporate Enquiries"),
    ("Senior Analyst - Due Diligence", "Due Dilligence and Corporate Enquiries"),
    ("Due Diligence Researcher", "Due Dilligence and Corporate Enquiries"),
    ("Due Diligence Manager", "Due Dilligence and Corporate Enquiries"),
    ("Corporate Enquiries Officer", "Due Dilligence and Corporate Enquiries"),
    # Employment Background Screening (5)
    ("Verification Officer", "Employment Background Screening"),
    ("Senior Verifier", "Employment Background Screening"),
    ("Reference Checker", "Employment Background Screening"),
    ("EBS Analyst", "Employment Background Screening"),
    ("EBS Manager", "Employment Background Screening"),
    # General Affairs (4)
    ("GA Officer", "General Affairs"),
    ("Facilities Coordinator", "General Affairs"),
    ("Office Administrator", "General Affairs"),
    ("GA Manager", "General Affairs"),
    # Human Resources (5)
    ("HR Officer", "Human Resources"),
    ("Recruiter", "Human Resources"),
    ("HR Business Partner", "Human Resources"),
    ("L&D Specialist", "Human Resources"),
    ("HR Manager", "Human Resources"),
    # Information Technology (5)
    ("IT Support", "Information Technology"),
    ("System Administrator", "Information Technology"),
    ("DevOps Engineer", "Information Technology"),
    ("Security Engineer", "Information Technology"),
    ("IT Manager", "Information Technology"),
    # Innovatech Solution (4)
    ("Innovation Lead", "Innovatech Solution"),
    ("Solution Architect", "Innovatech Solution"),
    ("Product Manager", "Innovatech Solution"),
    ("Data Scientist", "Innovatech Solution"),
    # Investigation (5)
    ("Field Investigator", "Investigation"),
    ("Senior Investigator", "Investigation"),
    ("Investigator - Asset Tracing", "Investigation"),
    ("Investigator - Fraud", "Investigation"),
    ("Investigation Manager", "Investigation"),
    # Management (4)
    ("Director", "Management"),
    ("General Manager", "Management"),
    ("Country Manager", "Management"),
    ("Chief Executive Officer", "Management"),
    # Operations (5)
    ("Operations Officer", "Operations"),
    ("Operations Coordinator", "Operations"),
    ("Operations Analyst", "Operations"),
    ("Senior Operations Specialist", "Operations"),
    ("Operations Manager", "Operations"),
    # Quality (4)
    ("Quality Assurance Officer", "Quality"),
    ("QC Inspector", "Quality"),
    ("Senior QA Specialist", "Quality"),
    ("Quality Manager", "Quality"),
    # Sales (4)
    ("Sales Executive", "Sales"),
    ("Account Manager", "Sales"),
    ("Senior Sales Executive", "Sales"),
    ("Sales Manager", "Sales"),
    # Sertifikasi Bio Data (4)
    ("Sertifikasi Officer", "Sertifikasi Bio Data"),
    ("Senior Verifier - Bio Data", "Sertifikasi Bio Data"),
    ("Bio Data Coordinator", "Sertifikasi Bio Data"),
    ("Sertifikasi Manager", "Sertifikasi Bio Data"),
    # Surveillance (5)
    ("Field Surveillance Officer", "Surveillance"),
    ("Surveillance Analyst", "Surveillance"),
    ("Senior Surveillance Operative", "Surveillance"),
    ("Surveillance Team Lead", "Surveillance"),
    ("Surveillance Manager", "Surveillance"),
    # Whistleblowing (3)
    ("Whistleblowing Officer", "Whistleblowing"),
    ("Ethics & Compliance Officer", "Whistleblowing"),
    ("Whistleblowing Manager", "Whistleblowing"),
]


# ---- Sub-proyek K stratified allowed_language distribution ----------------
#
# We seed 57 tenant_profile rows. Distribute their ``allowed_language`` across
# 5 patterns so the e2e smoke (and any future stratified audit) has at least
# one profile per pattern without having to wire bespoke seed flags. The
# 12/12/11/11/11 split sums to 57 (3 companies x 19 departments).
#
# Index ranges (half-open) are deliberately written so each pattern's count
# is obvious at a glance and the boundary array can be reused in tests
# (``test_seed_distribution.py``) to verify behavior.
ALLOWED_LANG_PATTERNS: list[list[str] | None] = [
    ["id", "en"],  # indices 0..11   (12 rows)
    ["ms", "en"],  # indices 12..23  (12 rows)
    ["th", "en"],  # indices 24..34  (11 rows)
    ["id", "ms", "th", "en"],  # indices 35..45  (11 rows)
    None,  # indices 46..56  (11 rows) - NULL = all allowed
]
PATTERN_BOUNDARIES: list[int] = [12, 24, 35, 46, 57]


def _pattern_for_index(index: int) -> list[str] | None:
    """Return the stratified ``allowed_language`` pattern for tenant_profile index ``i``.

    Raises ``ValueError`` if ``index`` is outside the 57-row distribution —
    defensive against caller bugs since silent fall-through would yield an
    incorrect pattern for the off-by-one tenant.
    """
    # Explicit negative-index guard. Python's ``if index < boundary`` would
    # silently accept ``-1`` and return the first pattern, which is exactly
    # the off-by-one class of bug this function is meant to surface.
    if index < 0:
        raise ValueError(f"Index {index} out of bounds for 57-row distribution (negative)")
    for i, boundary in enumerate(PATTERN_BOUNDARIES):
        if index < boundary:
            return ALLOWED_LANG_PATTERNS[i]
    raise ValueError(f"Index {index} out of bounds for 57-row distribution")


# Canonical 3-step prompt_applied order (ADR-055 ordered length-3). Lives
# here as a single source of truth so the seed never drifts from the
# Pydantic validator in ``src.tenant_profile.schemas``.
EXPECTED_PROMPT_APPLIED_AGENT_TYPES: list[str] = [
    "lang_detect_input",
    "translate",
    "lang_detect_output",
]


# Aitegrity service catalog (general + 15 product specialisations).
# Tone/audience fields apply to every service; mirrored from
# ADR-030 ("Code is Data") defaults in the discarded sub-proyek D seed.
_TONE = "professional formal"
_AUDIENCE = "corporate clients, compliance officers, legal/HR teams"


@dataclass(frozen=True)
class _Term:
    source: str
    target: str
    source_lang: str = "en"
    target_lang: str = "id"


@dataclass(frozen=True)
class _Example:
    source: str
    target: str
    source_lang: str = "en"
    target_lang: str = "id"
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ServiceSpec:
    name: str
    description: str
    domain: str
    glossary: list[_Term] = field(default_factory=list)
    examples: list[_Example] = field(default_factory=list)


SERVICES: list[_ServiceSpec] = [
    _ServiceSpec(
        name="general",
        description="General-purpose translation profile used as the default for tenants with no specialised service assigned.",
        domain="general",
    ),
    _ServiceSpec(
        name="Employment Background Screening",
        description="Verifying job candidates' employment history, education, criminal records, and references prior to hiring.",
        domain="employment background screening",
        glossary=[
            _Term("background check", "pemeriksaan latar belakang"),
            _Term("employment verification", "verifikasi riwayat pekerjaan"),
            _Term("education verification", "verifikasi pendidikan"),
            _Term("criminal record", "catatan kriminal"),
            _Term("reference check", "pengecekan referensi"),
        ],
        examples=[
            _Example(
                "We have completed the background check for the candidate and found no discrepancies in the employment history.",
                "Kami telah menyelesaikan pemeriksaan latar belakang untuk kandidat dan tidak menemukan ketidaksesuaian dalam riwayat pekerjaan.",
                tags=["completion-report"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Whistleblowing System",
        description="A confidential channel for employees and stakeholders to report misconduct, fraud, or violations within an organization.",
        domain="whistleblowing and ethics reporting",
        glossary=[
            _Term("whistleblower", "pelapor"),
            _Term("anonymous report", "laporan anonim"),
            _Term("retaliation", "pembalasan"),
            _Term("internal investigation", "investigasi internal"),
            _Term("misconduct", "pelanggaran"),
        ],
        examples=[
            _Example(
                "Your report has been received and will be investigated confidentially. Retaliation against whistleblowers is strictly prohibited.",
                "Laporan Anda telah diterima dan akan diinvestigasi secara rahasia. Pembalasan terhadap pelapor sangat dilarang.",
                tags=["acknowledgement"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Due Diligence",
        description="Investigation of a company, individual, or transaction to verify facts and assess risks before a business decision.",
        domain="corporate due diligence",
        glossary=[
            _Term("due diligence", "uji tuntas"),
            _Term("target company", "perusahaan target"),
            _Term("beneficial owner", "pemilik manfaat"),
            _Term("conflict of interest", "konflik kepentingan"),
            _Term("risk assessment", "penilaian risiko"),
        ],
        examples=[
            _Example(
                "The due diligence report identifies the beneficial owners and flags any potential conflicts of interest with the target company.",
                "Laporan uji tuntas mengidentifikasi pemilik manfaat dan menandai potensi konflik kepentingan dengan perusahaan target.",
                tags=["report-summary"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Mystery Shopping",
        description="Undercover evaluation of customer service quality, product display, and operational standards through anonymous shoppers.",
        domain="mystery shopping and service evaluation",
        glossary=[
            _Term("mystery shopper", "pembeli misterius"),
            _Term("evaluation checklist", "daftar penilaian"),
            _Term("customer experience", "pengalaman pelanggan"),
            _Term("service standard", "standar layanan"),
        ],
        examples=[
            _Example(
                "The mystery shopper noted that the staff did not greet customers within 30 seconds, falling short of the service standard.",
                "Pembeli misterius mencatat bahwa staf tidak menyapa pelanggan dalam 30 detik, di bawah standar layanan.",
                tags=["observation"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Asset Tracing",
        description="Locating and identifying hidden, misappropriated, or undisclosed assets across jurisdictions.",
        domain="asset tracing and recovery",
        glossary=[
            _Term("asset tracing", "penelusuran aset"),
            _Term("hidden assets", "aset tersembunyi"),
            _Term("beneficial ownership", "kepemilikan manfaat"),
            _Term("offshore account", "rekening luar negeri"),
            _Term("asset recovery", "pemulihan aset"),
        ],
        examples=[
            _Example(
                "The investigation revealed hidden assets held through nominee structures in three offshore jurisdictions.",
                "Investigasi mengungkap aset tersembunyi yang dipegang melalui struktur nominee di tiga yurisdiksi luar negeri.",
                tags=["finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Skip Tracing",
        description="Locating individuals who have moved, gone missing, or are intentionally avoiding contact (e.g., debtors, witnesses, heirs).",
        domain="skip tracing and subject location",
        glossary=[
            _Term("skip tracing", "penelusuran orang"),
            _Term("subject", "subjek"),
            _Term("last known address", "alamat terakhir diketahui"),
            _Term("locate", "menemukan"),
        ],
        examples=[
            _Example(
                "Skip tracing identified the subject's current address through public records and social media verification.",
                "Penelusuran orang berhasil mengidentifikasi alamat terkini subjek melalui catatan publik dan verifikasi media sosial.",
                tags=["finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Fraud Investigation",
        description="Investigating suspected fraudulent activity including financial fraud, internal theft, and procurement fraud.",
        domain="fraud investigation and forensic accounting",
        glossary=[
            _Term("fraud", "penipuan"),
            _Term("fraudulent activity", "aktivitas penipuan"),
            _Term("perpetrator", "pelaku"),
            _Term("evidence", "bukti"),
            _Term("financial fraud", "penipuan keuangan"),
        ],
        examples=[
            _Example(
                "The forensic review uncovered evidence of fraudulent invoices submitted by the perpetrator over a 14-month period.",
                "Tinjauan forensik mengungkap bukti faktur palsu yang diajukan pelaku selama periode 14 bulan.",
                tags=["forensic", "finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Insurance Investigation",
        description="Investigation of insurance claims to detect fraud, verify legitimacy, and support claim adjudication.",
        domain="insurance claim investigation",
        glossary=[
            _Term("insurance claim", "klaim asuransi"),
            _Term("policyholder", "pemegang polis"),
            _Term("claim adjuster", "penilai klaim"),
            _Term("fraudulent claim", "klaim palsu"),
            _Term("loss verification", "verifikasi kerugian"),
        ],
        examples=[
            _Example(
                "Our investigation confirmed that the policyholder's claim was legitimate; loss verification supports the reported damages.",
                "Investigasi kami mengonfirmasi bahwa klaim pemegang polis sah; verifikasi kerugian mendukung kerusakan yang dilaporkan.",
                tags=["conclusion"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Market Survey",
        description="Primary research on market size, consumer behavior, competitor positioning, and pricing dynamics.",
        domain="market research and consumer insights",
        glossary=[
            _Term("market research", "riset pasar"),
            _Term("target market", "pasar sasaran"),
            _Term("competitor analysis", "analisis pesaing"),
            _Term("consumer behavior", "perilaku konsumen"),
        ],
        examples=[
            _Example(
                "The market survey indicates that 62% of consumers in the target segment prefer the competitor's pricing tier.",
                "Riset pasar menunjukkan bahwa 62% konsumen di segmen sasaran lebih memilih tingkat harga pesaing.",
                tags=["finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Non-Use Investigation",
        description="Investigating whether a registered trademark has been continuously used in commerce, as required to maintain registration.",
        domain="trademark non-use investigation",
        glossary=[
            _Term("non-use", "tidak digunakan"),
            _Term("trademark", "merek dagang"),
            _Term("prior use", "penggunaan sebelumnya"),
            _Term("commercial use", "penggunaan komersial"),
        ],
        examples=[
            _Example(
                "Evidence collected shows that the trademark has not been used in commerce in Indonesia for the past three consecutive years.",
                "Bukti yang dikumpulkan menunjukkan bahwa merek dagang tidak digunakan dalam perdagangan di Indonesia selama tiga tahun berturut-turut.",
                tags=["finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Anti-Counterfeit Investigation",
        description="Identifying counterfeit goods in the market, locating manufacturers/distributors, and supporting enforcement actions.",
        domain="anti-counterfeit and brand protection",
        glossary=[
            _Term("counterfeit", "barang palsu"),
            _Term("genuine product", "produk asli"),
            _Term("infringing goods", "barang yang melanggar"),
            _Term("raid action", "penggerebekan"),
            _Term("brand protection", "perlindungan merek"),
        ],
        examples=[
            _Example(
                "Surveillance identified a warehouse distributing counterfeit products bearing the client's brand; a raid action is recommended.",
                "Pengawasan mengidentifikasi gudang yang mendistribusikan barang palsu dengan merek klien; tindakan penggerebekan direkomendasikan.",
                tags=["recommendation"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Parallel Trading",
        description="Investigating unauthorized importation and distribution of genuine products outside the authorized channels.",
        domain="parallel trade investigation",
        glossary=[
            _Term("parallel trade", "perdagangan paralel"),
            _Term("authorized distributor", "distributor resmi"),
            _Term("gray market", "pasar abu-abu"),
            _Term("unauthorized import", "impor tidak resmi"),
        ],
        examples=[
            _Example(
                "The investigation traced the parallel imports to a distributor in Singapore reselling goods outside the authorized territory.",
                "Investigasi menelusuri impor paralel ke distributor di Singapura yang menjual kembali barang di luar wilayah resmi.",
                tags=["finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Anti-Bribery Management System",
        description="ISO 37001-aligned framework for preventing, detecting, and responding to bribery within an organization.",
        domain="anti-bribery compliance (ISO 37001)",
        glossary=[
            _Term("anti-bribery", "anti-suap"),
            _Term("bribery", "suap"),
            _Term("facilitation payment", "pembayaran fasilitasi"),
            _Term("gift policy", "kebijakan hadiah"),
        ],
        examples=[
            _Example(
                "The audit found that the company's anti-bribery management system adequately addresses facilitation payments and gift policies in accordance with ISO 37001.",
                "Audit menemukan bahwa sistem manajemen anti-suap perusahaan secara memadai mengatur pembayaran fasilitasi dan kebijakan hadiah sesuai dengan ISO 37001.",
                tags=["audit-finding"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Know Your Customer (KYC)",
        description="Customer identity verification and risk assessment for AML/CFT compliance and beneficial ownership transparency.",
        domain="KYC and customer due diligence",
        glossary=[
            _Term("customer due diligence", "uji tuntas pelanggan"),
            _Term("beneficial owner", "pemilik manfaat"),
            _Term("identity verification", "verifikasi identitas"),
            _Term("politically exposed person", "orang yang terekspos secara politik"),
        ],
        examples=[
            _Example(
                "Enhanced customer due diligence is required when the beneficial owner is identified as a politically exposed person.",
                "Uji tuntas pelanggan yang ditingkatkan diperlukan ketika pemilik manfaat diidentifikasi sebagai orang yang terekspos secara politik.",
                tags=["policy"],
            ),
        ],
    ),
    _ServiceSpec(
        name="Trademark Investigation",
        description="Investigating trademark infringement, conducting prior-use searches, and supporting opposition or cancellation actions.",
        domain="trademark investigation and IP enforcement",
        glossary=[
            _Term("trademark", "merek dagang"),
            _Term("infringement", "pelanggaran"),
            _Term("prior use", "penggunaan sebelumnya"),
            _Term("registration", "pendaftaran"),
            _Term("opposition", "oposisi"),
        ],
        examples=[
            _Example(
                "Our investigation confirmed prior use of the disputed mark by the third party since 2019, which supports the opposition filing.",
                "Investigasi kami mengonfirmasi penggunaan sebelumnya atas merek yang disengketakan oleh pihak ketiga sejak 2019, yang mendukung pengajuan oposisi.",
                tags=["finding"],
            ),
        ],
    ),
]


# Jinja templates seeded into tenant_prompts. The pipeline currently
# renders from the filesystem template (src/pipeline/templates/translate.jinja),
# so these DB rows are reserved for a future "operator-edits-the-prompt"
# admin UI. Seeding them now means the table has the expected 3 rows for
# any downstream code that reads them.
_TRANSLATE_TEMPLATE = """\
<role>
You are a professional translator working for {{ tenant.company.company_name }}'s
{{ tenant.department.department_name }} department in {{ tenant.country.country_name }},
serving the {{ tenant_profile.position.position_name }} role.
You specialise in {{ tenant_profile.service.service_name }} content.
</role>

<task>
Translate from {{ source_lang_name }} ({{ source_lang }}) to {{ target_lang_name }} ({{ target_lang }}).

Rules:
- Output ONLY the translated text. No labels, no explanation.
- Preserve placeholders like {variable} or %s exactly.
- Honour every glossary entry above.

Text:
{{ text }}
</task>
"""

_LANG_DETECT_TEMPLATE = """\
You are a language identifier. Reply with ONLY the ISO 639-1 code of
the language of the input text. Examples: 'en' for English, 'id' for
Indonesian, 'fr' for French. No quotes, no explanation, just the
2-letter lowercase code.
"""


# ---- Seed steps -----------------------------------------------------------


async def seed_iso_languages(session: AsyncSession) -> int:
    """Insert ISO 639 entries; skip ones already present. Return count inserted."""
    existing = (await session.execute(select(IsoLanguage.code))).scalars().all()
    have = set(existing)
    inserted = 0
    for entry in ISO_LANGUAGES:
        if entry.code in have:
            continue
        session.add(IsoLanguage(code=entry.code, name=entry.name, native_name=entry.native_name))
        inserted += 1
    await session.flush()
    return inserted


async def seed_countries(session: AsyncSession) -> dict[str, str]:
    """Insert any missing countries; return mapping ``country_name -> country_id``."""
    rows = (await session.execute(select(Country))).scalars().all()
    out: dict[str, str] = {c.country_name: c.country_id for c in rows}
    for name in COUNTRIES:
        if name in out:
            continue
        cid = make_id("country")
        session.add(Country(country_id=cid, country_name=name))
        out[name] = cid
    await session.flush()
    return out


async def seed_companies(session: AsyncSession, country_ids: dict[str, str]) -> dict[str, str]:
    """Insert any missing companies; return ``company_name -> company_id``."""
    rows = (await session.execute(select(Company))).scalars().all()
    out: dict[str, str] = {c.company_name: c.company_id for c in rows}
    for company_name, country_name in COMPANIES:
        if company_name in out:
            continue
        if country_name not in country_ids:
            raise RuntimeError(
                f"Country {country_name!r} required by company {company_name!r} is missing"
            )
        cid = make_id("company")
        session.add(
            Company(
                company_id=cid,
                company_name=company_name,
                company_country=country_name,
            )
        )
        out[company_name] = cid
    await session.flush()
    return out


async def seed_departments(session: AsyncSession) -> dict[str, str]:
    """Insert any missing departments; return ``department_name -> department_id``."""
    rows = (await session.execute(select(Department))).scalars().all()
    out: dict[str, str] = {d.department_name: d.department_id for d in rows}
    for name in DEPARTMENTS:
        if name in out:
            continue
        did = make_id("department")
        session.add(Department(department_id=did, department_name=name))
        out[name] = did
    await session.flush()
    return out


async def seed_positions(
    session: AsyncSession, department_ids: dict[str, str]
) -> dict[tuple[str, str], str]:
    """Insert any missing positions; return ``(position_name, department_name) -> position_id``."""
    rows = (await session.execute(select(Position))).scalars().all()
    # Reverse-lookup department name from id for the cache key.
    dept_name_by_id = {v: k for k, v in department_ids.items()}
    out: dict[tuple[str, str], str] = {
        (p.position_name, dept_name_by_id[p.department_id]): p.position_id for p in rows
    }
    for position_name, dept_name in POSITION_DEPARTMENT_PAIRS:
        if (position_name, dept_name) in out:
            continue
        if dept_name not in department_ids:
            raise RuntimeError(
                f"Department {dept_name!r} required by position {position_name!r} is missing"
            )
        pid = make_id("position")
        session.add(
            Position(
                position_id=pid,
                position_name=position_name,
                department_id=department_ids[dept_name],
            )
        )
        out[(position_name, dept_name)] = pid
    await session.flush()
    return out


async def seed_services(session: AsyncSession) -> dict[str, str]:
    """Insert any missing services (with glossary + examples). Return ``service_name -> service_id``."""
    rows = (await session.execute(select(Service))).scalars().all()
    out: dict[str, str] = {s.service_name: s.service_id for s in rows}
    for spec in SERVICES:
        if spec.name in out:
            continue
        sid = make_id("service")
        session.add(
            Service(
                service_id=sid,
                service_name=spec.name,
                description=spec.description,
                domain=spec.domain,
                tone=_TONE,
                target_audience=_AUDIENCE,
            )
        )
        out[spec.name] = sid
    await session.flush()
    # Glossary + examples (per service). Idempotent skip by (service_id, source_term, source_lang, target_lang).
    existing_glossary = (
        await session.execute(
            select(
                GlossaryTerm.service_id,
                GlossaryTerm.source_term,
                GlossaryTerm.source_lang,
                GlossaryTerm.target_lang,
            )
        )
    ).all()
    seen_glossary = {tuple(row) for row in existing_glossary}
    existing_examples = (
        await session.execute(
            select(
                StyleExample.service_id,
                StyleExample.source_text,
                StyleExample.source_lang,
                StyleExample.target_lang,
            )
        )
    ).all()
    seen_examples = {tuple(row) for row in existing_examples}
    for spec in SERVICES:
        sid = out[spec.name]
        for term in spec.glossary:
            key = (sid, term.source, term.source_lang, term.target_lang)
            if key in seen_glossary:
                continue
            session.add(
                GlossaryTerm(
                    service_id=sid,
                    source_term=term.source,
                    source_lang=term.source_lang,
                    target_term=term.target,
                    target_lang=term.target_lang,
                )
            )
            seen_glossary.add(key)
        for ex in spec.examples:
            key_e = (sid, ex.source, ex.source_lang, ex.target_lang)
            if key_e in seen_examples:
                continue
            session.add(
                StyleExample(
                    service_id=sid,
                    source_text=ex.source,
                    source_lang=ex.source_lang,
                    target_text=ex.target,
                    target_lang=ex.target_lang,
                    tags=ex.tags or None,
                )
            )
            seen_examples.add(key_e)
    await session.flush()
    return out


async def seed_tenant_prompts(session: AsyncSession) -> dict[str, str]:
    """Insert any missing prompts; return ``agent_type -> prompt_id``."""
    rows = (await session.execute(select(TenantPrompt))).scalars().all()
    out: dict[str, str] = {p.agent_type: p.prompt_id for p in rows}
    seeds = [
        (
            "translate",
            _TRANSLATE_TEMPLATE,
            "Main translation prompt rendered with tenant/profile/glossary context.",
        ),
        (
            "lang_detect_input",
            _LANG_DETECT_TEMPLATE,
            "Source-language detection for an inbound user request.",
        ),
        (
            "lang_detect_output",
            _LANG_DETECT_TEMPLATE,
            "Target-language detection for the produced translation.",
        ),
    ]
    for agent_type, template, desc in seeds:
        if agent_type in out:
            continue
        pid = make_id("prompt")
        session.add(
            TenantPrompt(
                prompt_id=pid,
                agent_type=agent_type,
                template=template,
                description=desc,
            )
        )
        out[agent_type] = pid
    await session.flush()
    return out


async def _read_alembic_head(session: AsyncSession) -> str:
    """Read the current head revision from the Postgres ``alembic_version`` meta table.

    Sub-proyek K stamps every newly inserted tenant row with this value so
    audit can answer "tenant ini dibuat saat schema versi X" per ADR-054.
    Repository ``create()`` takes the version as an injected kwarg rather
    than reading the meta table itself — keeps the repo decoupled from
    migration infrastructure and makes the stamp explicit at every call site.

    Returns ``"unknown"`` if the meta table is absent. The test suite builds
    its schema via ``Base.metadata.create_all`` (not Alembic), so the table
    is missing in tests — we tolerate that gracefully via an information-schema
    pre-check (a missing table on a regular SELECT would abort the outer
    transaction, which would clobber the seed rows already added in the same
    session). Real prod/dev runs always have the table because Alembic creates
    it on first ``upgrade``.
    """
    exists_q = text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
    )
    exists = (await session.execute(exists_q)).scalar_one_or_none()
    if not exists:
        return "unknown"
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    return str(result.scalar_one())


def _compose_tenant_name(company_name: str, department_name: str, country_name: str) -> str:
    """Compose the canonical ``tenant.tenant_name`` display string.

    Format: ``"{company} — {department} ({country})"``. Em-dash separator,
    country in parens. Matches :func:`src.tenant.repository.compose_tenant_name`
    — the seed inlines the helper rather than importing to keep the script
    importable in environments where the repository module's deps (argon2)
    might not yet be installed (unlikely now, but cheap to preserve).
    """
    return f"{company_name} — {department_name} ({country_name})"


async def seed_tenants(
    session: AsyncSession,
    country_ids: dict[str, str],
    company_ids: dict[str, str],
    department_ids: dict[str, str],
) -> dict[tuple[str, str, str], str]:
    """Insert any missing tenants. Return ``(country, company, department) -> tenant_id``.

    Sub-proyek K: tenant uses denormalized ``country_name``/``company_name``/
    ``department_name`` (no FK ID columns). Composes ``tenant_name`` from those
    three snapshots. Each row is stamped with the current Postgres
    ``alembic_version`` (``alembic_version_at_create`` per ADR-054).

    The ``country_ids``/``company_ids``/``department_ids`` kwargs are
    retained on the signature for **backwards compatibility** with the
    test fixtures that call this function with positional args — the
    denormalized seed no longer needs them, but breaking the signature
    would cascade into rewriting every existing seed test.

    Newly created tenants get a freshly generated API key, printed to
    stdout. The plaintext is returned ONCE per ADR-045; operators MUST
    capture stdout on the first run since idempotent re-runs do not
    regenerate keys for existing rows.
    """
    # Read the alembic head ONCE per invocation — the value is stable for
    # the duration of the seed run.
    alembic_version = await _read_alembic_head(session)

    rows = (await session.execute(select(Tenant))).scalars().all()
    out: dict[tuple[str, str, str], str] = {
        (t.country_name, t.company_name, t.department_name): t.tenant_id for t in rows
    }
    for company_name, country_name in COMPANIES:
        # Spec §5.2: country_name for the tenant snapshot must come from the
        # ``country`` reference table (sub-proyek I stores country as a
        # denormalized string on ``company``; sub-proyek K resolves it to
        # the canonical catalog string before snapshotting onto the tenant).
        # Falls back to the company-side string as-is on a catalog miss so
        # the seed never hard-fails on a missing reference row — ops gets a
        # structured warning instead.
        country_row = (
            await session.execute(select(Country).where(Country.country_name == country_name))
        ).scalar_one_or_none()
        if country_row is None:
            log.warning(
                "seed.country_catalog_miss",
                country_name=country_name,
                fallback="company.company_country",
            )
            canonical_country_name = country_name
        else:
            canonical_country_name = country_row.country_name
        for dept_name in DEPARTMENTS:
            key = (canonical_country_name, company_name, dept_name)
            if key in out:
                continue
            tid = make_id("tenant")
            plaintext = generate_api_key()
            tenant_name = _compose_tenant_name(company_name, dept_name, canonical_country_name)
            session.add(
                Tenant(
                    tenant_id=tid,
                    tenant_name=tenant_name,
                    country_name=canonical_country_name,
                    company_name=company_name,
                    department_name=dept_name,
                    alembic_version_at_create=alembic_version,
                    api_key_hash=hash_api_key(plaintext),
                )
            )
            out[key] = tid
            print(f"  CREATED tenant {tenant_name}: tenant_id={tid}, API_KEY={plaintext}")
    await session.flush()
    return out


async def seed_tenant_profiles(
    session: AsyncSession,
    tenant_ids: dict[tuple[str, str, str], str],
    position_ids: dict[tuple[str, str], str],
    service_ids: dict[str, str],
    prompt_ids: dict[str, str],
) -> int:
    """Create 57 default tenant_profiles with stratified ``allowed_language`` + uniform 3-step ``prompt_applied``.

    Sub-proyek K rewrite:
      - Idempotency key is ``tenant_name`` (the denormalized column), since
        the FK ``tenant_id`` column is gone.
      - Tenants are ordered deterministically by ``(company_name, department_name)``
        so the same physical row always lands at the same index — required
        for reproducible distribution audits and for the e2e smoke probe
        to predictably find a profile that accepts ``id``→``en``.
      - ``allowed_language`` follows the 12/12/11/11/11 stratification from
        :data:`ALLOWED_LANG_PATTERNS` via :func:`_pattern_for_index`.
      - ``prompt_applied`` is uniform :data:`EXPECTED_PROMPT_APPLIED_AGENT_TYPES`
        (3 ``agent_type`` strings, ordered) so the DB-level length-3 CHECK
        and the Pydantic ordered-equality validator both pass.

    The ``tenant_ids``/``position_ids``/``service_ids``/``prompt_ids`` kwargs
    are retained on the signature for backwards-compat with existing test
    fixtures; the denormalized seed reads what it needs off the persisted
    Tenant rows + the static ``POSITION_DEPARTMENT_PAIRS`` catalog.

    Returns the count of newly inserted rows.
    """
    have_names = set((await session.execute(select(TenantProfile.tenant_name))).scalars().all())
    inserted = 0

    # Per-dept index of the first position name in our static list. Each
    # department's *first* position becomes the default profile's role —
    # consistent with sub-proyek I's convention.
    first_position_for_dept: dict[str, str] = {}
    for position_name, dept_name in POSITION_DEPARTMENT_PAIRS:
        first_position_for_dept.setdefault(dept_name, position_name)

    # Pull persisted tenants and sort deterministically. Sorting by
    # (company_name, department_name) — NOT by tenant_id — guarantees the
    # index→pattern mapping is reproducible across runs and machines.
    # Without deterministic ordering, the random tenant_id values would
    # scramble the distribution and break the smoke probe's profile lookup.
    tenants = (await session.execute(select(Tenant))).scalars().all()
    sorted_tenants = sorted(tenants, key=lambda t: (t.company_name, t.department_name))

    for index, tenant in enumerate(sorted_tenants):
        if tenant.tenant_name in have_names:
            continue
        position_name_opt = first_position_for_dept.get(tenant.department_name)
        if position_name_opt is None:
            raise RuntimeError(f"No position defined for department {tenant.department_name!r}")
        position_name = position_name_opt
        allowed = _pattern_for_index(index)
        session.add(
            TenantProfile(
                profile_id=make_id("profile"),
                tenant_name=tenant.tenant_name,
                service_name="general",
                position_name=position_name,
                allowed_language=allowed,
                # Copy the canonical list — never share the module-level list
                # reference between rows; SQLAlchemy may mutate the underlying
                # array binding and would corrupt later rows in the loop.
                prompt_applied=list(EXPECTED_PROMPT_APPLIED_AGENT_TYPES),
            )
        )
        inserted += 1
        have_names.add(tenant.tenant_name)
    await session.flush()
    return inserted


# ---- Main -----------------------------------------------------------------


async def _main() -> int:
    async with SessionLocal() as session:
        print("== Sub-proyek I seed ==")
        n_iso = await seed_iso_languages(session)
        print(f"[1/10] iso_languages: +{n_iso} (target {len(ISO_LANGUAGES)})")

        country_ids = await seed_countries(session)
        print(f"[2/10] countries: total {len(country_ids)}")

        company_ids = await seed_companies(session, country_ids)
        print(f"[3/10] companies: total {len(company_ids)}")

        dept_ids = await seed_departments(session)
        print(f"[4/10] departments: total {len(dept_ids)}")

        position_ids = await seed_positions(session, dept_ids)
        print(f"[5/10] positions: total {len(position_ids)}")

        service_ids = await seed_services(session)
        print(f"[6/10] services + glossary + examples: total {len(service_ids)} services")

        prompt_ids = await seed_tenant_prompts(session)
        print(f"[7/10] tenant_prompts: total {len(prompt_ids)}")

        tenant_ids = await seed_tenants(session, country_ids, company_ids, dept_ids)
        print(f"[8/10] tenants: total {len(tenant_ids)}")

        n_profiles = await seed_tenant_profiles(
            session, tenant_ids, position_ids, service_ids, prompt_ids
        )
        print(f"[9/10] tenant_profiles: +{n_profiles}")

        await session.commit()
        print("[10/10] commit OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
