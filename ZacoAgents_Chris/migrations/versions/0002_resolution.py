"""Rounds, and the decisions taken about them.

Revision ID: 0002_resolution
Revises: 0001_accounts
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_resolution"
down_revision: str | None = "0001_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rounds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="staged"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "round_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=400), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("duplicate_of_round_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["duplicate_of_round_id"], ["rounds.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_round_documents_round_id"), "round_documents", ["round_id"])
    op.create_index(
        op.f("ix_round_documents_content_sha256"), "round_documents", ["content_sha256"]
    )

    op.create_table(
        "product_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("short_code", sa.String(length=200), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("captured_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["captured_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_product_codes_name"),
    )
    op.create_index(op.f("ix_product_codes_name"), "product_codes", ["name"])

    op.create_table(
        "product_names",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("raw", sa.String(length=400), nullable=False),
        sa.Column("vocabulary", sa.String(length=20), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_product_names_name"),
    )
    op.create_index(op.f("ix_product_names_name"), "product_names", ["name"])

    op.create_table(
        "product_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("left_key", sa.String(length=400), nullable=False),
        sa.Column("right_key", sa.String(length=400), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_evidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("left_key", "right_key", name="uq_product_decision_pair"),
    )

    op.create_table(
        "delivery_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("delivery_id", sa.String(length=100), nullable=False),
        sa.Column("dn", sa.String(length=50), nullable=True),
        sa.Column("provenance", sa.String(length=40), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("operator_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("supplier_ref", sa.String(length=100), nullable=True),
        sa.Column(
            "approved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", name="uq_delivery_notes_delivery"),
    )
    op.create_index(op.f("ix_delivery_notes_delivery_id"), "delivery_notes", ["delivery_id"])

    op.create_table(
        "suspensions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("subject_kind", sa.String(length=40), nullable=False),
        sa.Column("subject_key", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("differences", sa.Text(), nullable=False, server_default=""),
        sa.Column("chosen_source", sa.String(length=400), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "subject_key", name="uq_suspension_subject"),
    )
    op.create_index(op.f("ix_suspensions_round_id"), "suspensions", ["round_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_suspensions_round_id"), table_name="suspensions")
    op.drop_table("suspensions")
    op.drop_index(op.f("ix_delivery_notes_delivery_id"), table_name="delivery_notes")
    op.drop_table("delivery_notes")
    op.drop_table("product_decisions")
    op.drop_index(op.f("ix_product_names_name"), table_name="product_names")
    op.drop_table("product_names")
    op.drop_index(op.f("ix_product_codes_name"), table_name="product_codes")
    op.drop_table("product_codes")
    op.drop_index(op.f("ix_round_documents_content_sha256"), table_name="round_documents")
    op.drop_index(op.f("ix_round_documents_round_id"), table_name="round_documents")
    op.drop_table("round_documents")
    op.drop_table("rounds")
