"""Tenant junction redesign: drop legacy profile/tenant/log tables, create new junction-style schema.

Drops sub-proyek B/D/G+C tables (tenants, profiles, glossary_terms, style_examples,
profile_versions, translation_logs) and replaces them with a normalised junction
schema: country, company, department, position, service, iso_languages, tenant_prompts,
glossary_terms, style_examples, tenant, tenant_profile, and translation_logs (recreated).

Revision ID: 005_tenant_junction
Revises: 004_agentic_activities
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# revision identifiers, used by Alembic.
revision: str = "005_tenant_junction"
down_revision: str | None = "004_agentic_activities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Step 1: Drop legacy sub-proyek B/D/G+C tables in FK-child-first order.
    # We drop named indexes explicitly before dropping the tables that own them
    # to avoid "index does not exist" errors on repeated runs in CI.
    # -------------------------------------------------------------------------

    # translation_logs depends on profiles + tenants — drop first.
    op.drop_index("ix_translation_logs_failed_partial", table_name="translation_logs")
    op.drop_index("ix_translation_logs_tenant_profile_started", table_name="translation_logs")
    op.drop_index("ix_translation_logs_tenant_started", table_name="translation_logs")
    op.drop_table("translation_logs")

    op.drop_index("ix_style_examples_profile_langs", table_name="style_examples")
    op.drop_table("style_examples")

    op.drop_index("ix_glossary_terms_profile_langs", table_name="glossary_terms")
    op.drop_table("glossary_terms")

    op.drop_index("ix_profile_versions_profile_id", table_name="profile_versions")
    op.drop_table("profile_versions")

    op.drop_index("ix_profiles_tenant_id", table_name="profiles")
    op.drop_table("profiles")

    op.drop_table("tenants")

    # -------------------------------------------------------------------------
    # Step 2: Create reference / lookup tables.
    # These are pure lookup tables with no FK dependencies on each other, so
    # creation order within this block is flexible.
    # -------------------------------------------------------------------------

    # country — geographic context for a tenant.
    op.create_table(
        "country",
        sa.Column("country_id", sa.String(30), primary_key=True),
        sa.Column("country_name", sa.String(60), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # company — legal entity; belongs to a country (denormalised as a string
    # rather than FK to keep seed data simple and avoid cascade complexity).
    op.create_table(
        "company",
        sa.Column("company_id", sa.String(30), primary_key=True),
        sa.Column("company_name", sa.String(100), unique=True, nullable=False),
        sa.Column("company_country", sa.String(60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # department — org unit; independent of company so multiple companies can
    # share the same department taxonomy (e.g., "Customer Service").
    op.create_table(
        "department",
        sa.Column("department_id", sa.String(30), primary_key=True),
        sa.Column("department_name", sa.String(80), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # position — role within a department; (position_name, department_id) is the
    # natural business key enforced by the unique constraint.
    op.create_table(
        "position",
        sa.Column("position_id", sa.String(30), primary_key=True),
        sa.Column("position_name", sa.String(120), nullable=False),
        sa.Column(
            "department_id",
            sa.String(30),
            sa.ForeignKey("department.department_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("position_name", "department_id", name="uq_position_name_department"),
    )

    # service — translation profile template (domain, tone, audience).
    # Replaces the old per-profile blob with a shared service definition that
    # multiple tenant_profile rows can reference.
    op.create_table(
        "service",
        sa.Column("service_id", sa.String(30), primary_key=True),
        sa.Column("service_name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(100), nullable=True),
        sa.Column("tone", sa.String(255), nullable=True),
        sa.Column("target_audience", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # iso_languages — lookup table for supported languages; code is the BCP-47
    # tag (e.g., "en", "id", "zh-Hans").  No created_at — seeded at deploy time,
    # not operator-managed.
    op.create_table(
        "iso_languages",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("native_name", sa.String(100), nullable=True),
    )

    # tenant_prompts — operator-overrideable prompt templates per agent type.
    # A CHECK constraint (not an ENUM) guards agent_type so adding new agent
    # types only requires a CHECK migration rather than an ALTER TYPE DDL.
    op.create_table(
        "tenant_prompts",
        sa.Column("prompt_id", sa.String(30), primary_key=True),
        sa.Column("agent_type", sa.String(40), unique=True, nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(255), server_default="system"),
        sa.CheckConstraint(
            "agent_type IN ('lang_detect_input','lang_detect_output','translate')",
            name="ck_tenant_prompts_agent_type",
        ),
    )

    # -------------------------------------------------------------------------
    # Step 3: Glossary + style examples (FK to service).
    # Moved from profile-scoped to service-scoped so glossary terms are shared
    # across all tenant_profiles that use the same service, avoiding duplication.
    # -------------------------------------------------------------------------

    op.create_table(
        "glossary_terms",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "service_id",
            sa.String(30),
            sa.ForeignKey("service.service_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_term", sa.String(255), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=False),
        sa.Column("target_term", sa.String(255), nullable=False),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("is_forbidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_glossary_terms_service_langs",
        "glossary_terms",
        ["service_id", "source_lang", "target_lang"],
    )

    op.create_table(
        "style_examples",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "service_id",
            sa.String(30),
            sa.ForeignKey("service.service_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.String(8), nullable=False),
        # Native ARRAY instead of JSONB for tags: query patterns are simple
        # membership checks, not nested structure; ARRAY is cheaper for those.
        sa.Column("tags", ARRAY(sa.String(255)), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_style_examples_service_langs",
        "style_examples",
        ["service_id", "source_lang", "target_lang"],
    )

    # -------------------------------------------------------------------------
    # Step 4: Tenant — the junction that binds country + company + department.
    # The (country_id, company_id, department_id) triple is the natural business
    # key; the unique constraint enforces that and the surrogate `tenant_id` is
    # the FK target for child tables.
    # api_key_hash stores a bcrypt/sha256 hash, never the raw key.
    # jwt_* columns support optional JWT session tokens issued by the API.
    # -------------------------------------------------------------------------

    op.create_table(
        "tenant",
        sa.Column("tenant_id", sa.String(30), primary_key=True),
        sa.Column(
            "country_id",
            sa.String(30),
            sa.ForeignKey("country.country_id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(30),
            sa.ForeignKey("company.company_id"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sa.String(30),
            sa.ForeignKey("department.department_id"),
            nullable=False,
        ),
        sa.Column("api_key_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("jwt_active_token", sa.Text(), nullable=True),
        sa.Column("jwt_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("country_id", "company_id", "department_id", name="uq_tenant_ccd"),
    )
    # Index on api_key_hash speeds up the per-request API key lookup without
    # relying solely on the unique index (which is larger due to unique enforcement).
    op.create_index("ix_tenant_api_key_hash", "tenant", ["api_key_hash"])

    # -------------------------------------------------------------------------
    # Step 5: Tenant profile — nested junction binding tenant + position + service.
    # One tenant_profile row = "user at this company/department/position uses
    # this service's translation settings".
    # allowed_language: null means all languages permitted; non-null is a whitelist.
    # prompt_applied: array of tenant_prompts.prompt_id overrides active for this profile.
    # -------------------------------------------------------------------------

    op.create_table(
        "tenant_profile",
        sa.Column("profile_id", sa.String(30), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(30),
            sa.ForeignKey("tenant.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "position_id",
            sa.String(30),
            sa.ForeignKey("position.position_id"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            sa.String(30),
            sa.ForeignKey("service.service_id"),
            nullable=False,
        ),
        sa.Column("allowed_language", ARRAY(sa.String(8)), nullable=True),
        sa.Column(
            "prompt_applied",
            ARRAY(sa.String(30)),
            nullable=False,
            server_default=sa.text("ARRAY[]::VARCHAR(30)[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "position_id", "service_id", name="uq_tenant_profile_tps"),
    )
    op.create_index("ix_tenant_profile_tenant_id", "tenant_profile", ["tenant_id"])

    # -------------------------------------------------------------------------
    # Step 6: Translation logs — recreated with new FK shape.
    # Key differences from the old schema:
    #   - tenant_id / profile_id are VARCHAR(30), not UUID (match new surrogate PKs)
    #   - FKs use SET NULL on delete (logs are audit records; orphan rows are fine)
    #   - Columns rationalised: removed legacy profile_slug/version/compliance fields,
    #     added agentic_activities JSONB + rendered_prompt (already present as
    #     add-column in 003/004 — unified here in the canonical column list)
    # -------------------------------------------------------------------------

    op.create_table(
        "translation_logs",
        sa.Column(
            "log_id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.String(30),
            sa.ForeignKey("tenant.tenant_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "profile_id",
            sa.String(30),
            sa.ForeignKey("tenant_profile.profile_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=True),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detected_source_lang", sa.String(8), nullable=True),
        sa.Column("detected_output_lang", sa.String(8), nullable=True),
        sa.Column("source_lang_mismatch", sa.Boolean(), nullable=True),
        sa.Column("output_lang_mismatch", sa.Boolean(), nullable=True),
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
        sa.Column("agentic_activities", JSONB(), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cache_key", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("trace_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_index", sa.Integer(), nullable=True),
        sa.Column("request_metadata", JSONB(), nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Composite index: most dashboard queries filter by tenant and sort by time.
    op.create_index(
        "ix_translation_logs_tenant_started",
        "translation_logs",
        ["tenant_id", sa.text("started_at DESC")],
    )
    # Partial index: failure-investigation queries need fast access to failed rows only.
    op.create_index(
        "ix_translation_logs_failed",
        "translation_logs",
        [sa.text("started_at DESC")],
        postgresql_where=sa.text("status = 'failed'"),
    )


def downgrade() -> None:
    # Sub-proyek I migration is irreversible by design: the old tables (tenants,
    # profiles, profile_versions) are replaced by a fundamentally different schema.
    # Restoring them would require manually reconstructing FK relationships and
    # data that no longer exists in the new layout.
    raise NotImplementedError("Sub-proyek I migration is irreversible by design.")
