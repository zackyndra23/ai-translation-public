"""Translation log table — observability and dashboard data source.

Revision ID: 002_translation_logs
Revises: 001_profile_schema
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "002_translation_logs"
down_revision: str | None = "001_profile_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_logs",
        # Identity
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=True),
        sa.Column("batch_index", sa.Integer(), nullable=True),
        # Multi-tenancy & profile snapshot
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_slug", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("quality_mode", sa.String(16), nullable=True),
        # Request
        sa.Column("source_lang", sa.String(8), nullable=False),
        sa.Column("target_lang", sa.String(8), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_length", sa.Integer(), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        # Response
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("translated_text_length", sa.Integer(), nullable=True),
        # Model & cost
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        # Pipeline outcome
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cache_key", sa.String(32), nullable=True),
        sa.Column("glossary_compliance_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("glossary_violations", JSONB(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        # Prompt template
        sa.Column(
            "prompt_template_name",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'translate'"),
        ),
        sa.Column("prompt_template_version", sa.String(32), nullable=True),
        # Forward columns for sub-proyek C
        sa.Column("detected_source_lang", sa.String(8), nullable=True),
        sa.Column("detected_output_lang", sa.String(8), nullable=True),
        sa.Column("source_lang_mismatch", sa.Boolean(), nullable=True),
        sa.Column("output_lang_mismatch", sa.Boolean(), nullable=True),
        # Open-ended metadata
        sa.Column("request_metadata", JSONB(), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("provider_duration_ms", sa.Integer(), nullable=True),
        # Constraints
        sa.CheckConstraint(
            "status IN ('success','failed')",
            name="ck_translation_logs_status",
        ),
        sa.CheckConstraint(
            "glossary_compliance_score IS NULL OR (glossary_compliance_score >= 0 AND glossary_compliance_score <= 1)",
            name="ck_translation_logs_compliance",
        ),
    )

    op.create_index(
        "ix_translation_logs_tenant_started",
        "translation_logs",
        ["tenant_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_translation_logs_tenant_profile_started",
        "translation_logs",
        ["tenant_id", "profile_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_translation_logs_failed_partial",
        "translation_logs",
        ["tenant_id", sa.text("started_at DESC")],
        postgresql_where=sa.text("status = 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_translation_logs_failed_partial", table_name="translation_logs")
    op.drop_index("ix_translation_logs_tenant_profile_started", table_name="translation_logs")
    op.drop_index("ix_translation_logs_tenant_started", table_name="translation_logs")
    op.drop_table("translation_logs")
