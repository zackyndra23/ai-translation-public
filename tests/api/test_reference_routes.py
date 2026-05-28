"""Tests for the public cascade endpoints (sub-proyek I)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Company, Country, Department, IsoLanguage
from src.iso_languages.repository import clear_catalog_cache


async def test_countries_returns_seeded(api_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            Country(country_id="country-aaaaaaaa-1111", country_name="Atlantis"),
            Country(country_id="country-bbbbbbbb-2222", country_name="Boravia"),
        ]
    )
    await db_session.flush()
    resp = await api_client.get("/countries")
    assert resp.status_code == 200
    names = [c["country_name"] for c in resp.json()]
    assert "Atlantis" in names and "Boravia" in names


async def test_companies_filter_by_country(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add_all(
        [
            Company(
                company_id="company-aaaa1111-aaaa",
                company_name="ACorp",
                company_country="Atlantis",
            ),
            Company(
                company_id="company-bbbb2222-bbbb",
                company_name="BCorp",
                company_country="Boravia",
            ),
        ]
    )
    await db_session.flush()
    resp = await api_client.get("/companies", params={"country": "Atlantis"})
    assert resp.status_code == 200
    names = [c["company_name"] for c in resp.json()]
    assert names == ["ACorp"]


async def test_departments_list_all(api_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            Department(department_id="department-1111-aaaa", department_name="HR"),
            Department(department_id="department-2222-bbbb", department_name="Finance"),
        ]
    )
    await db_session.flush()
    resp = await api_client.get("/departments")
    assert resp.status_code == 200
    names = sorted(d["department_name"] for d in resp.json())
    assert "Finance" in names and "HR" in names


async def test_iso_languages_list(api_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            IsoLanguage(code="en", name="English"),
            IsoLanguage(code="id", name="Indonesian", native_name="Bahasa Indonesia"),
        ]
    )
    await db_session.flush()
    clear_catalog_cache()  # avoid leaking state from other tests
    resp = await api_client.get("/iso-languages")
    assert resp.status_code == 200
    codes = sorted([le["code"] for le in resp.json()])
    assert "en" in codes and "id" in codes
