"""TenantRepository — sub-proyek K denormalized form (CRUD + auth).

Drops FK-based ``country_id``/``company_id``/``department_id``; uses *_name
snapshot columns instead. Lookups by name. ``create`` composes the display
``tenant_name`` automatically and stamps an injected ``alembic_version``
into ``alembic_version_at_create`` per ADR-054.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.hashing import generate_api_key, hash_api_key, verify_api_key
from src.db.ids import make_id
from src.db.models import Tenant
from src.tenant.schemas import TenantCreate, TenantCreatedResponse, TenantRead


def compose_tenant_name(*, company_name: str, department_name: str, country_name: str) -> str:
    """Compose the canonical ``tenant.tenant_name`` (UNIQUE) display string.

    Format: ``"{company} — {department} ({country})"``. Em-dash separator,
    country in parens. Keeps the name human-readable and self-documenting
    so log greps and admin UIs can show one identifier instead of three.
    """
    return f"{company_name} — {department_name} ({country_name})"


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[TenantRead]:
        result = await self._session.execute(select(Tenant))
        return [TenantRead.model_validate(t) for t in result.scalars().all()]

    async def get_by_id(self, tenant_id: str) -> TenantRead | None:
        row = await self._session.get(Tenant, tenant_id)
        return TenantRead.model_validate(row) if row else None

    async def get_by_name(self, tenant_name: str) -> TenantRead | None:
        """Look up a tenant by its composed ``tenant_name``.

        Used by the pipeline resolver to walk from a denormalized
        ``tenant_profile.tenant_name`` snapshot back to the tenant row when
        rendering Jinja context. Returns ``None`` if no row matches —
        callers decide whether that's an error (resolver) or a soft miss.
        """
        result = await self._session.execute(
            select(Tenant).where(Tenant.tenant_name == tenant_name)
        )
        row = result.scalar_one_or_none()
        return TenantRead.model_validate(row) if row else None

    async def resolve_by_ccd(
        self,
        country_name: str,
        company_name: str,
        department_name: str,
    ) -> TenantRead | None:
        """Look up tenant by the ``(country_name, company_name, department_name)`` composite.

        Sub-proyek K refactor: takes names, not IDs. The unique constraint
        ``uq_tenant_ccd_names`` guarantees at most one match.
        """
        result = await self._session.execute(
            select(Tenant).where(
                Tenant.country_name == country_name,
                Tenant.company_name == company_name,
                Tenant.department_name == department_name,
            )
        )
        row = result.scalar_one_or_none()
        return TenantRead.model_validate(row) if row else None

    async def create(self, payload: TenantCreate, *, alembic_version: str) -> TenantCreatedResponse:
        """Insert a tenant with auto-composed ``tenant_name`` + caller-supplied alembic version.

        ``alembic_version`` is injected by the caller (seed scripts read it
        from the Postgres ``alembic_version`` meta table). Letting the
        repository read the meta table itself would couple it to migration
        infrastructure — injection keeps the boundary clean and makes the
        stamp explicit at every call site.
        """
        plaintext_key = generate_api_key()
        tenant_name = compose_tenant_name(
            company_name=payload.company_name,
            department_name=payload.department_name,
            country_name=payload.country_name,
        )
        row = Tenant(
            tenant_id=make_id("tenant"),
            tenant_name=tenant_name,
            country_name=payload.country_name,
            company_name=payload.company_name,
            department_name=payload.department_name,
            alembic_version_at_create=alembic_version,
            api_key_hash=hash_api_key(plaintext_key),
        )
        self._session.add(row)
        await self._session.flush()
        return TenantCreatedResponse(
            **TenantRead.model_validate(row).model_dump(),
            api_key_plaintext=plaintext_key,
        )

    async def verify_api_key(self, plaintext: str) -> str | None:
        """Find the tenant whose ``api_key_hash`` matches ``plaintext``.

        Iterates candidate tenants and argon2-verifies. For 57 rows this is
        acceptable; future scale optimization via key-prefix indexing
        (per ADR-045) is deferred. Returns ``tenant_id`` or ``None``.
        """
        result = await self._session.execute(select(Tenant))
        for tenant in result.scalars().all():
            if verify_api_key(plaintext, tenant.api_key_hash):
                return tenant.tenant_id
        return None

    async def set_active_jwt(self, tenant_id: str, jwt_token: str) -> None:
        row = await self._session.get(Tenant, tenant_id)
        if row is None:
            raise ValueError(f"Tenant {tenant_id} not found")
        row.jwt_active_token = jwt_token
        row.jwt_refreshed_at = datetime.now(UTC)
        await self._session.flush()

    async def get_active_jwt(self, tenant_id: str) -> str | None:
        row = await self._session.get(Tenant, tenant_id)
        return row.jwt_active_token if row else None
