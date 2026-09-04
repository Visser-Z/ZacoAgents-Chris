"""Suppliers, the commission agreed per delivery line, and what has been paid out.

Everything above the Nett line the agent's reports state. Everything below it exists only here:
the agents see Zaco as the supplier and know nothing about the farmers behind it (section 8).

Seeded with nothing, deliberately (D13). A supplier exists because a person entered one.

Revision ID: 0005_settlement
Revises: 0004_append
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_settlement"
down_revision: str | None = "0004_append"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("name", name="uq_suppliers_name"),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    op.create_table(
        "commission_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consignment_id", sa.String(100), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        # NUMERIC, not float: a rate that multiplies money must not be approximate.
        sa.Column("percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agreed_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agreed_by_id"], ["users.id"], ondelete="SET NULL"),
        # One delivery line has one set of terms. Two would mean two settlements for one lot.
        sa.UniqueConstraint("consignment_id", name="uq_commission_consignment"),
    )
    op.create_index("ix_commission_terms_consignment", "commission_terms", ["consignment_id"])

    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("supplier_payments")
    op.drop_index("ix_commission_terms_consignment", table_name="commission_terms")
    op.drop_table("commission_terms")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
