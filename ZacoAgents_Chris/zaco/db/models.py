"""The durable record.

Phase 0 put accounts and invitations here. Phase 3 adds what was *decided*: the rounds
themselves, the product codes and links an operator captured, the approved delivery notes with
their provenance, and the records held back because two documents disagreed.

Every decision table carries who made it and when. That trail is the reason D14 rejects shared
domain accounts -- "chose the Farmers Trust export because X" is worth nothing if the record
says a domain decided.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
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


# --- Phase 3: the durable record of what was decided ------------------------------------------


class RoundStatus(StrEnum):
    STAGED = "staged"
    """Documents saved, queue open. Nothing may be appended."""

    RESOLVED = "resolved"
    """Every question answered. Ready for the workbook (Phase 4)."""

    ABANDONED = "abandoned"
    """Put aside without being appended. Kept, because deleting it hides that it happened."""


class Round(Base):
    """One batch of agent reports, saved so the queue survives signing out.

    The documents are stored as bytes and everything else is derived from them on demand rather
    than being written out as tables of deliveries and rows. The durable record is then *what
    the agent actually sent*, which is the only thing that cannot be recomputed; a correction to
    a reader improves the history instead of leaving stale derived rows behind it. Re-deriving
    nine files takes milliseconds, and the rows that must not move -- the ones appended to the
    workbook -- are pinned by the append itself.
    """

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default=RoundStatus.STAGED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    documents: Mapped[list[RoundDocument]] = relationship(
        back_populates="round",
        cascade="all, delete-orphan",
        order_by="RoundDocument.id",
        # RoundDocument points at rounds twice -- once for the round it belongs to and once for
        # the earlier round it duplicates -- so the path has to be named.
        foreign_keys="RoundDocument.round_id",
    )
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id])


class RoundDocument(Base):
    """One uploaded file, kept byte for byte.

    `content_sha256` is what makes an identical re-upload detectable across rounds (D12). It is
    the file's own bytes, so a re-export that differs only in its run timestamp is *not* caught
    here and falls through to record-level comparison, which is the correct place for it.
    """

    __tablename__ = "round_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(400))
    kind: Mapped[str] = mapped_column(String(50))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    duplicate_of_round_id: Mapped[int | None] = mapped_column(ForeignKey("rounds.id"), default=None)
    """Set when these exact bytes were already read in an earlier round.

    The file is still kept, because the re-upload is itself a thing that happened and a silent
    skip is indistinguishable from a lost file. It contributes nothing to this round's figures,
    and the round summary says so out loud (D12).
    """

    round: Mapped[Round] = relationship(back_populates="documents", foreign_keys=[round_id])


class ProductCode(Base):
    """The operator's own short code for one product name -- workbook column G.

    Keyed on the **normalised product name**, not on an identity key, because identity keys move
    when two names are merged and a code written against a key that later stops being the root
    would quietly stop applying. A name never moves.
    """

    __tablename__ = "product_codes"
    __table_args__ = (UniqueConstraint("name", name="uq_product_codes_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(400), index=True)
    short_code: Mapped[str] = mapped_column(String(200))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    captured_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    captured_by: Mapped[User | None] = relationship()


class ProductName(Base):
    """Every product name any round has ever contained, and which vocabulary wrote it.

    Product identity is global: a name learned reading one round is still that product when the
    next one arrives. Without this the registry only knows the round in front of it, and the two
    halves of a link -- the sales name and the statement name -- can never be offered together
    unless both happen to fall in the same upload.
    """

    __tablename__ = "product_names"
    __table_args__ = (UniqueConstraint("name", name="uq_product_names_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(400), index=True)
    raw: Mapped[str] = mapped_column(String(400))
    vocabulary: Mapped[str] = mapped_column(String(20))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductDecision(Base):
    """An operator's answer to "are these two names the same product?".

    Rejections are stored as well as acceptances. Without that the same resemblance is offered
    every round for ever, and a queue that asks a question already answered trains the operator
    to click through it.
    """

    __tablename__ = "product_decisions"
    __table_args__ = (UniqueConstraint("left_key", "right_key", name="uq_product_decision_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    left_key: Mapped[str] = mapped_column(String(400))
    right_key: Mapped[str] = mapped_column(String(400))
    accepted: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text, default="")
    is_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    """True when a document proved it rather than a person deciding it.

    Kept apart so an operator can see which links they were asked about and which were never a
    question -- and so a proof is not quietly presented as somebody's judgement.
    """

    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    decided_by: Mapped[User | None] = relationship()


class DeliveryNote(Base):
    """One delivery's approved delivery note number, and how it was arrived at (D9).

    `dn` is nullable on purpose. `None` with a provenance of `none_foreign_producer` is the
    recorded answer "no DN -- carried for producer 14013" (D11): the row is written with column
    A visibly empty and the reason attached, which is a different thing from nobody having
    reached this delivery yet. Nothing here is written without `approved_by_id`.
    """

    __tablename__ = "delivery_notes"
    __table_args__ = (UniqueConstraint("delivery_id", name="uq_delivery_notes_delivery"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(100), index=True)
    dn: Mapped[str | None] = mapped_column(String(50), default=None)
    provenance: Mapped[str] = mapped_column(String(40))
    reasoning: Mapped[str] = mapped_column(Text, default="")
    operator_reason: Mapped[str] = mapped_column(Text, default="")
    supplier_ref: Mapped[str | None] = mapped_column(String(100), default=None)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    approved_by: Mapped[User | None] = relationship()


class Suspension(Base):
    """A record two documents disagree about, held out of the round until a person decides (D12).

    The *record* is suspended, never the file: refusing a whole export because one account sale
    conflicts throws away every record that was fine. `reason` is mandatory at the API, because
    "chose the Farmers Trust export" is worth nothing next quarter without the why.
    """

    __tablename__ = "suspensions"
    __table_args__ = (UniqueConstraint("round_id", "subject_key", name="uq_suspension_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    subject_kind: Mapped[str] = mapped_column(String(40))
    subject_key: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    differences: Mapped[str] = mapped_column(Text, default="")
    chosen_source: Mapped[str | None] = mapped_column(String(400), default=None)
    reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    decided_by: Mapped[User | None] = relationship()

    @property
    def is_decided(self) -> bool:
        return self.decided_at is not None
