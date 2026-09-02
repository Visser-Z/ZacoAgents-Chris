"""Taking a document back out of a round, and the trail that says so.

Revision ID: 0003_withdrawal
Revises: 0002_resolution
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_withdrawal"
down_revision: str | None = "0002_resolution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "round_documents", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "round_documents",
        sa.Column("withdrawn_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("round_documents", sa.Column("withdrawn_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_round_documents_withdrawn_by",
        "round_documents",
        "users",
        ["withdrawn_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "round_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_round_events_round_id"), "round_events", ["round_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_round_events_round_id"), table_name="round_events")
    op.drop_table("round_events")
    op.drop_constraint("fk_round_documents_withdrawn_by", "round_documents", type_="foreignkey")
    op.drop_column("round_documents", "withdrawn_by_id")
    op.drop_column("round_documents", "withdrawn_reason")
    op.drop_column("round_documents", "withdrawn_at")
