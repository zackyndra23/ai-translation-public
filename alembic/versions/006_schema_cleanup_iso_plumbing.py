"""Sub-proyek K: schema cleanup — denormalize tenant + tenant_profile + alembic_version_at_create snapshot.

TRUNCATE tenant CASCADE clears tenant + tenant_profile (FK ondelete CASCADE)
and sets translation_logs.tenant_id/profile_id to NULL (FK ondelete SET NULL).
Then drop FK columns and add denormalized snapshot columns. Re-seed handled
separately in scripts/seed_tenant_data.py.

Revision ID: 006_schema_cleanup
Revises: 005_tenant_junction
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_schema_cleanup"
down_revision: str | None = "005_tenant_junction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Step 1: Wipe existing tenant + tenant_profile rows.
    # ADD NOT NULL columns to a populated table errors out without a
    # default. Easiest path: clear the table and let the seed script
    # repopulate with the new shape afterwards.
    # ------------------------------------------------------------------
    # Precondition: every inbound FK to `tenant` must have `ON DELETE CASCADE`
    # (tenant_profile.tenant_id) or `ON DELETE SET NULL` (translation_logs.tenant_id).
    # If a future migration adds a `tenant_id` FK with `ON DELETE RESTRICT`/`NO ACTION`,
    # this CASCADE will fail. Verify before adding new inbound FKs.
    op.execute("TRUNCATE TABLE tenant CASCADE")

    # ------------------------------------------------------------------
    # Step 2: Drop tenant_profile FK columns + composite UNIQUE + index.
    # Dropping a column auto-drops its FK constraint in Postgres.
    # ------------------------------------------------------------------
    op.drop_constraint("uq_tenant_profile_tps", "tenant_profile", type_="unique")
    op.drop_index("ix_tenant_profile_tenant_id", table_name="tenant_profile")
    op.drop_column("tenant_profile", "tenant_id")
    op.drop_column("tenant_profile", "position_id")
    op.drop_column("tenant_profile", "service_id")

    # ------------------------------------------------------------------
    # Step 3: Drop tenant FK columns + composite UNIQUE.
    # ------------------------------------------------------------------
    op.drop_constraint("uq_tenant_ccd", "tenant", type_="unique")
    op.drop_column("tenant", "country_id")
    op.drop_column("tenant", "company_id")
    op.drop_column("tenant", "department_id")

    # ------------------------------------------------------------------
    # Step 4: Add tenant denormalized snapshot columns + alembic version.
    # NOT NULL safe because table is empty.
    # ------------------------------------------------------------------
    op.add_column("tenant", sa.Column("tenant_name", sa.String(150), nullable=False))
    op.add_column("tenant", sa.Column("country_name", sa.String(60), nullable=False))
    op.add_column("tenant", sa.Column("company_name", sa.String(100), nullable=False))
    op.add_column("tenant", sa.Column("department_name", sa.String(80), nullable=False))
    op.add_column(
        "tenant",
        sa.Column("alembic_version_at_create", sa.String(60), nullable=False),
    )
    op.create_unique_constraint("uq_tenant_name", "tenant", ["tenant_name"])
    op.create_unique_constraint(
        "uq_tenant_ccd_names",
        "tenant",
        ["country_name", "company_name", "department_name"],
    )

    # ------------------------------------------------------------------
    # Step 5: Add tenant_profile denormalized columns + CHECK + index.
    # ------------------------------------------------------------------
    op.add_column("tenant_profile", sa.Column("tenant_name", sa.String(150), nullable=False))
    op.add_column("tenant_profile", sa.Column("service_name", sa.String(100), nullable=False))
    op.add_column("tenant_profile", sa.Column("position_name", sa.String(120), nullable=False))
    op.create_unique_constraint(
        "uq_tenant_profile_tps_names",
        "tenant_profile",
        ["tenant_name", "position_name", "service_name"],
    )
    op.create_check_constraint(
        "ck_prompt_applied_length",
        "tenant_profile",
        "array_length(prompt_applied, 1) = 3",
    )
    op.create_index("ix_tenant_profile_tenant_name", "tenant_profile", ["tenant_name"])

    # ------------------------------------------------------------------
    # Step 6: Drop the now-empty default on prompt_applied (length-0
    # default would violate CHECK). We rely on application-level seed
    # to populate length-3 arrays explicitly.
    # ------------------------------------------------------------------
    op.alter_column("tenant_profile", "prompt_applied", server_default=None)


def downgrade() -> None:
    raise NotImplementedError(
        "Sub-proyek K migration is irreversible by design. "
        "Restoring the FK-based schema would require manual data reconstruction."
    )
