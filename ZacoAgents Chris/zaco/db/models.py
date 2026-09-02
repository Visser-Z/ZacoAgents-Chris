"""Phase 0 tables: accounts and invitations.

Later phases add the durable record itself (deliveries, consignments, dockets, account sales,
appended rows and their provenance). Kept in one module while it is small.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from zaco.auth.permissions import Permission, parse
from zaco.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    invitations: Mapped[list[Invitation]] = relationship(
        back_populates="invited_by", foreign_keys="Invitation.invited_by_id"
    )

    @property
    def granted(self) -> set[Permission]:
        return parse(self.permissions)

    def can(self, permission: Permission) -> bool:
        granted = self.granted
        # Admin implies the ability to administer, not the ability to do everyone's job:
        # a deliberate choice so that "who appended this" stays a real answer.
        return self.is_active and permission in granted


class Invitation(Base):
    """An invitation is always to a specific email address, never to a domain (D14)."""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("token", name="uq_invitations_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token: Mapped[str] = mapped_column(String(64))
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    invited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    invited_by: Mapped[User | None] = relationship(
        back_populates="invitations", foreign_keys=[invited_by_id]
    )

    @property
    def is_open(self) -> bool:
        if self.accepted_at is not None:
            return False
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires > utcnow()
