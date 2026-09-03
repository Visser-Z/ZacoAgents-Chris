"""What a round wrote into the operator's book, and when.

Revision ID: 0004_append
Revises: 0003_withdrawal
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_append"
down_revision: str | None = "0003_withdrawal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rounds", sa.Column("appended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rounds", sa.Column("appended_by_id", sa.Integer(), nullable=True))
    op.add_column("rounds", sa.Column("appended_first_row", sa.Integer(), nullable=True))
    op.add_column("rounds", sa.Column("appended_last_row", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_rounds_appended_by", "rounds", "users", ["appended_by_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_rounds_appended_by", "rounds", type_="foreignkey")
    op.drop_column("rounds", "appended_last_row")
    op.drop_column("rounds", "appended_first_row")
    op.drop_column("rounds", "appended_by_id")
    op.drop_column("rounds", "appended_at")
