"""Reference endpoints for the cascading Streamlit form (public)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.company.repository import CompanyRepository
from src.company.schemas import CompanyRead
from src.country.repository import CountryRepository
from src.country.schemas import CountryRead
from src.department.repository import DepartmentRepository
from src.department.schemas import DepartmentRead
from src.iso_languages.repository import IsoLanguageRepository
from src.iso_languages.schemas import IsoLanguageRead
from src.position.repository import PositionRepository
from src.position.schemas import PositionRead
from src.service.repository import ServiceRepository
from src.service.schemas import ServiceRead
from src.tenant.repository import TenantRepository
from src.tenant.schemas import TenantRead
from src.tenant_profile.repository import TenantProfileRepository
from src.tenant_profile.schemas import TenantProfileRead

router = APIRouter(tags=["reference"])


@router.get("/countries", response_model=list[CountryRead])
async def list_countries(db: AsyncSession = Depends(get_db)) -> list[CountryRead]:
    return await CountryRepository(db).list()


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(
    country: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyRead]:
    repo = CompanyRepository(db)
    return await repo.list_by_country(country) if country else await repo.list()


@router.get("/departments", response_model=list[DepartmentRead])
async def list_departments(db: AsyncSession = Depends(get_db)) -> list[DepartmentRead]:
    return await DepartmentRepository(db).list()


@router.get("/departments/{department_id}/positions", response_model=list[PositionRead])
async def list_positions_for_department(
    department_id: str, db: AsyncSession = Depends(get_db)
) -> list[PositionRead]:
    return await PositionRepository(db).list_by_department(department_id)


@router.get("/services", response_model=list[ServiceRead])
async def list_services(db: AsyncSession = Depends(get_db)) -> list[ServiceRead]:
    return await ServiceRepository(db).list()


@router.get("/iso-languages", response_model=list[IsoLanguageRead])
async def list_iso_languages(db: AsyncSession = Depends(get_db)) -> list[IsoLanguageRead]:
    return await IsoLanguageRepository(db).list()


@router.get("/tenants/by-ccd", response_model=TenantRead)
async def resolve_tenant(
    country_id: str = Query(...),
    company_id: str = Query(...),
    department_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    """Resolve a tenant from (country, company, department) IDs.

    Sub-proyek K denormalized tenant rows by *_name. We keep the route's
    ID-based query parameters (frontend cascade uses IDs) and hop through
    the reference catalogs to obtain the names before calling the repo's
    new by-name lookup. Any missing catalog row → 404.
    """
    country = await CountryRepository(db).get_by_id(country_id)
    company = await CompanyRepository(db).get_by_id(company_id)
    department = await DepartmentRepository(db).get_by_id(department_id)
    if country is None or company is None or department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown reference id in ({country_id}, {company_id}, {department_id})",
        )
    tenant = await TenantRepository(db).resolve_by_ccd(
        country_name=country.country_name,
        company_name=company.company_name,
        department_name=department.department_name,
    )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tenant for ({country_id}, {company_id}, {department_id})",
        )
    return tenant


@router.get("/tenants/{tenant_id}/tenant-profiles", response_model=list[TenantProfileRead])
async def list_tenant_profiles(
    tenant_id: str,
    position_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[TenantProfileRead]:
    """List a tenant's profiles. Optional ``position_id`` narrows by position.

    Sub-proyek K: ``TenantProfileRepository.list_by_tenant_name`` is the new
    entry point. We hop from ``tenant_id`` → ``tenant_name`` and (when
    provided) ``position_id`` → ``position_name`` before calling it.
    Missing tenant → 404; missing position → empty list (consistent with
    the old behavior of an unmatched composite returning no rows).
    """
    tenant = await TenantRepository(db).get_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id!r} not found",
        )
    position_name: str | None = None
    if position_id:
        position = await PositionRepository(db).get_by_id(position_id)
        if position is None:
            return []
        position_name = position.position_name
    return await TenantProfileRepository(db).list_by_tenant_name(
        tenant.tenant_name, position_name=position_name
    )
