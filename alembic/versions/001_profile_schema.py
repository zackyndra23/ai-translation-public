"""Initial profile schema: tenants, profiles, glossary_terms, style_examples, profile_versions.

Revision ID: 001_profile_schema
Revises:
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_profile_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``gen_random_uuid()`` is a built-in in Postgres 16; no pgcrypto needed.
    # Using a server-side UUID default means inserts from psql / migrations
    # also get correctly-shaped ids without going through the ORM.

    op.create_table(
        "tenants",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "profiles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("tone", sa.String(255), nullable=False),
        sa.Column("target_audience", sa.String(255), nullable=False),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "quality_mode",
            sa.String(20),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column("model_preference", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_profile_tenant_slug"),
        sa.CheckConstraint(
            "quality_mode IN ('fast','balanced','thorough')",
            name="ck_profile_quality_mode",
        ),
    )
    op.create_index("ix_profiles_tenant_id", "profiles", ["tenant_id"])

    op.create_table(
        "glossary_terms",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_term", sa.String(255), nullable=False),
        sa.Column("source_lang", sa.String(5), nullable=False),
        sa.Column("target_term", sa.String(255), nullable=False),
        sa.Column("target_lang", sa.String(5), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("is_forbidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_glossary_terms_profile_langs",
        "glossary_terms",
        ["profile_id", "source_lang", "target_lang"],
    )

    op.create_table(
        "style_examples",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(5), nullable=False),
        sa.Column("target_lang", sa.String(5), nullable=False),
        # JSONB instead of native ARRAY so we can index with GIN later if
        # tag-based retrieval needs to scale.
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_style_examples_profile_langs",
        "style_examples",
        ["profile_id", "source_lang", "target_lang"],
    )

    op.create_table(
        "profile_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("profile_id", "version", name="uq_profile_version"),
    )
    op.create_index("ix_profile_versions_profile_id", "profile_versions", ["profile_id"])


def downgrade() -> None:
    # Drop in reverse order to respect FK dependencies.
    op.drop_index("ix_profile_versions_profile_id", table_name="profile_versions")
    op.drop_table("profile_versions")
    op.drop_index("ix_style_examples_profile_langs", table_name="style_examples")
    op.drop_table("style_examples")
    op.drop_index("ix_glossary_terms_profile_langs", table_name="glossary_terms")
    op.drop_table("glossary_terms")
    op.drop_index("ix_profiles_tenant_id", table_name="profiles")
    op.drop_table("profiles")
    op.drop_table("tenants")
