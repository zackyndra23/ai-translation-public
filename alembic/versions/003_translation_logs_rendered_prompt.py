"""Add rendered_prompt column to translation_logs.

Revision ID: 003_translation_logs_rendered_prompt
Revises: 002_translation_logs
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_rendered_prompt"
down_revision: str | None = "002_translation_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable so existing rows keep working; new rows populated from
    # ctx.rendered_prompt (or ctx.cached_result.prompt_applied on cache hit).
    op.add_column(
        "translation_logs",
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("translation_logs", "rendered_prompt")
