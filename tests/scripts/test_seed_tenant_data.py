"""Phase I-4 seed integration tests.

Each seed step is exercised against the test DB (transaction-rollback per
test). The asserts check the count invariants (7 / 3 / 19 / 83 / 16 / 57 / 57)
plus the idempotency contract.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import (
    Company,
    Country,
    Department,
    IsoLanguage,
    Position,
    Service,
    Tenant,
    TenantProfile,
    TenantPrompt,
)

from scripts.seed_tenant_data import (
    seed_companies,
    seed_countries,
    seed_departments,
    seed_iso_languages,
    seed_positions,
    seed_services,
    seed_tenant_profiles,
    seed_tenant_prompts,
    seed_tenants,
)


async def _count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_seed_iso_languages(db_session: AsyncSession) -> None:
    added = await seed_iso_languages(db_session)
    assert added >= 20  # starter catalog has 40 entries; we tolerate >=20


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
    hashes = (await db_session.execute(select(Tenant.api_key_hash))).scalars().all()
    assert len(hashes) == len(set(hashes)) == 57


async def test_seed_creates_3_prompts(db_session: AsyncSession) -> None:
    await seed_tenant_prompts(db_session)
    rows = (await db_session.execute(select(TenantPrompt))).scalars().all()
    assert sorted(r.agent_type for r in rows) == [
        "lang_detect_input",
        "lang_detect_output",
        "translate",
    ]


async def test_seed_idempotent(db_session: AsyncSession) -> None:
    """Running the full seed twice must produce the same row counts."""
    country_ids = await seed_countries(db_session)
    company_ids = await seed_companies(db_session, country_ids)
    dept_ids = await seed_departments(db_session)
    position_ids = await seed_positions(db_session, dept_ids)
    service_ids = await seed_services(db_session)
    prompt_ids = await seed_tenant_prompts(db_session)
    tenant_ids = await seed_tenants(db_session, country_ids, company_ids, dept_ids)
    await seed_tenant_profiles(db_session, tenant_ids, position_ids, service_ids, prompt_ids)

    models = (
        Country,
        Company,
        Department,
        Position,
        Service,
        Tenant,
        TenantProfile,
        TenantPrompt,
        IsoLanguage,
    )
    counts_before = {m: await _count(db_session, m) for m in models}

    # Re-run every step.
    country_ids = await seed_countries(db_session)
    company_ids = await seed_companies(db_session, country_ids)
    dept_ids = await seed_departments(db_session)
    position_ids = await seed_positions(db_session, dept_ids)
    service_ids = await seed_services(db_session)
    prompt_ids = await seed_tenant_prompts(db_session)
    tenant_ids = await seed_tenants(db_session, country_ids, company_ids, dept_ids)
    await seed_tenant_profiles(db_session, tenant_ids, position_ids, service_ids, prompt_ids)

    counts_after = {m: await _count(db_session, m) for m in models}
    assert counts_before == counts_after
