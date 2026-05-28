"""Add agentic_activities JSONB column to translation_logs.

Revision ID: 004_agentic_activities
Revises: 003_rendered_prompt
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004_agentic_activities"
down_revision: str | None = "003_rendered_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "translation_logs",
        sa.Column("agentic_activities", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("translation_logs", "agentic_activities")
