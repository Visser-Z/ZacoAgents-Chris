"""A way back into an account, and a trail of what was done to one.

Accounts have had no recovery path at all: the first admin is seeded only on an empty database
and an existing password is never reset, so an account whose password is gone was gone with it.
`password_resets` is that way back, in two states -- somebody asking, and somebody with the
standing to do it handing over a one-time link.

`account_events` is the trail. Rounds have had one since Phase 3; accounts, which decide the
identity behind every entry in it, have not. An email change in particular rewrites who a person
appears to be across the whole record, and it should not be possible to do that quietly.

Revision ID: 0006_account_care
Revises: 0005_settlement
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_account_care"
down_revision: str | None = "0005_settlement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Null while the row is only a request. A request grants nothing.
        sa.Column("token", sa.String(64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_by_id", sa.Integer(), nullable=True),
        sa.Column("issued_via", sa.String(60), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token", name="uq_password_resets_token"),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])

    op.create_table(
        "account_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("by_id", sa.Integer(), nullable=True),
        # Named rather than left blank: the recovery command acts with nobody's account, and a
        # blank actor reads as an unattributed change rather than an unattributable one.
        sa.Column("by_label", sa.String(120), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_account_events_user_id", "account_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_account_events_user_id", table_name="account_events")
    op.drop_table("account_events")
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
