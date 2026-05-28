"""Schema validation for sub-proyek K denormalized tenant."""

from __future__ import annotations

from src.tenant.schemas import TenantCreate, TenantRead


def test_tenant_create_accepts_denormalized_names() -> None:
    payload = TenantCreate(
        country_name="Indonesia",
        company_name="PT Integrity Indonesia",
        department_name="Sales",
    )
    assert payload.country_name == "Indonesia"
    assert payload.company_name == "PT Integrity Indonesia"
    assert payload.department_name == "Sales"


def test_tenant_read_includes_tenant_name_and_alembic_version() -> None:
    # Construct from a plain dict (simulating ORM .__dict__).
    raw = {
        "tenant_id": "tenant-aaaaaaaa-aaaa",
        "tenant_name": "PT Integrity Indonesia — Sales (Indonesia)",
        "country_name": "Indonesia",
        "company_name": "PT Integrity Indonesia",
        "department_name": "Sales",
        "alembic_version_at_create": "006_schema_cleanup",
        "created_at": "2026-05-22T00:00:00Z",
    }
    read = TenantRead.model_validate(raw)
    assert read.tenant_name == "PT Integrity Indonesia — Sales (Indonesia)"
    assert read.alembic_version_at_create == "006_schema_cleanup"
