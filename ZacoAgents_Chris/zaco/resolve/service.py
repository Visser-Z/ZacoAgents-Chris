"""Putting a round together: documents in, questions out, answers remembered.

A round is saved as the **documents themselves**, and everything else is derived from them each
time it is looked at. The durable record is then what the agent actually sent, which is the one
thing that cannot be recomputed, and a correction to a reader improves the whole history instead
of leaving stale derived rows behind it.

What *is* stored is the part no document contains: the codes and links an operator captured, the
delivery notes they approved, and the disagreements they settled. Those are answers to
questions, they carry a person's name, and they are applied to every round from then on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.config import get_settings
from zaco.db.models import (
    DeliveryNote,
    ProductCode,
    ProductDecision,
    ProductName,
    Round,
    RoundDocument,
    RoundStatus,
    Suspension,
    User,
)
from zaco.domain.build import build_round, load_short_codes
from zaco.domain.model import ZERO, AccountSale, StagedRound
from zaco.domain.products import ProductRegistry, Vocabulary, normalise
from zaco.ingest.classifier import UnrecognisedDocumentError, read_document
from zaco.resolve import book as book_reader
from zaco.resolve import queue as queue_builder
from zaco.resolve.book import BookKnowledge
from zaco.resolve.dn import DnProvenance, Proposal, propose
from zaco.resolve.stock import StockLedger, build_ledger

#: Zaco's own producer code, as every supplier reference in the supplied data writes it. A
#: delivery under any other producer code is somebody else's produce, which is a question
#: rather than a fact (D11).
ZACO_PRODUCER_CODE = "20026"

WORKBOOK_NAME = "account-sales-book.xlsx"


def workbook_path() -> Path:
    return get_settings().workbook_dir / WORKBOOK_NAME


# --- saving ------------------------------------------------------------------------------------


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass
class SavedDocument:
    filename: str
    kind: str
    duplicate_of: int | None = None


def save_round(
    db: Session, user: User, uploads: list[tuple[str, bytes]], label: str = ""
) -> tuple[Round, list[SavedDocument]]:
    """Store one round's documents, marking any that were read in an earlier round.

    Byte-identical re-uploads are kept but contribute nothing (D12). Discarding them instead
    would leave the record unable to show that the re-upload happened, which is exactly the
    thing an operator later wants to check.
    """
    round_ = Round(label=label, status=RoundStatus.STAGED.value, created_by=user)
    db.add(round_)
    db.flush()

    seen_here: dict[str, str] = {}
    saved: list[SavedDocument] = []
    for filename, content in uploads:
        sha = digest(content)
        try:
            result = read_document(content)
        except UnrecognisedDocumentError as refusal:
            # Name the file. With five uploaded at once, "one of these is unreadable" leaves the
            # operator opening each of them to find out which.
            raise UnrecognisedDocumentError(f"{filename}: {refusal}", refusal.scores) from refusal

        earlier = db.execute(
            select(RoundDocument)
            .join(Round, RoundDocument.round_id == Round.id)
            .where(
                RoundDocument.content_sha256 == sha,
                RoundDocument.duplicate_of_round_id.is_(None),
                Round.status != RoundStatus.ABANDONED.value,
                Round.id != round_.id,
            )
            .limit(1)
        ).scalar_one_or_none()

        duplicate_of = earlier.round_id if earlier is not None else None
        if duplicate_of is None and sha in seen_here:
            # The same file offered twice in one upload. Same rule, same round.
            duplicate_of = round_.id

        db.add(
            RoundDocument(
                round_id=round_.id,
                filename=filename,
                kind=result.kind.value,
                content_sha256=sha,
                byte_count=len(content),
                content=content,
                duplicate_of_round_id=duplicate_of,
            )
        )
        seen_here.setdefault(sha, filename)
        saved.append(SavedDocument(filename, result.kind.value, duplicate_of))

    db.flush()
    return round_, saved


# --- reading back ------------------------------------------------------------------------------


@dataclass
class DuplicateAlert:
    """A document that was stored and deliberately not counted."""

    filename: str
    earlier_round_id: int
    message: str


@dataclass
class ResolvedRound:
    """One round as it currently stands: the figures, the questions, and what was answered."""

    round: Round
    staged: StagedRound
    registry: ProductRegistry
    ledger: StockLedger
    book: BookKnowledge
    proposals: dict[str, Proposal] = field(default_factory=dict)
    approved: dict[str, DeliveryNote] = field(default_factory=dict)
    items: list[queue_builder.Item] = field(default_factory=list)
    duplicates: list[DuplicateAlert] = field(default_factory=list)
    suspensions: list[Suspension] = field(default_factory=list)
    grouping_dates: dict[str, date] = field(default_factory=dict)

    @property
    def open_items(self) -> list[queue_builder.Item]:
        return self.items

    @property
    def is_clear(self) -> bool:
        """Whether anything still stands between this round and the workbook (D5)."""
        return not self.items and not [s for s in self.suspensions if not s.is_decided]

    @property
    def blocking_reason(self) -> str | None:
        if self.is_clear:
            return None
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.kind.value] = counts.get(item.kind.value, 0) + 1
        undecided = len([s for s in self.suspensions if not s.is_decided])
        if undecided:
            counts["disagreement"] = undecided
        parts = [f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(counts.items())]
        return (
            "Nothing can be appended while the queue is open: "
            + ", ".join(parts)
            + " still unanswered."
        )


def _stored_codes(db: Session) -> dict[str, str]:
    return {row.name: row.short_code for row in db.execute(select(ProductCode)).scalars()}


def _decisions(db: Session) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    accepted: list[tuple[str, str, str]] = []
    rejected: list[tuple[str, str]] = []
    for row in db.execute(select(ProductDecision)).scalars():
        if row.accepted:
            accepted.append((row.left_key, row.right_key, row.reason))
        else:
            rejected.append((row.left_key, row.right_key))
    return accepted, rejected


def build_registry(db: Session) -> ProductRegistry:
    """A registry that already knows every answer given so far, and every name ever seen.

    `lookup/product-codes.json` is a **seed**, read at boot and never written back. It is an
    input the operator supplied, and a system that edits its own inputs leaves a trail nobody
    can follow. Anything captured since is held in the database and wins where the two differ.

    Names from earlier rounds are pre-registered so identity is global rather than per-round.
    Without that, the sales name and the statement name for one fruit can only ever be offered
    as a link when both happen to land in the same upload -- and the plums, whose sales fall in
    one round and whose statement falls in the next, never would.
    """
    codes = {normalise(k): v for k, v in load_short_codes().items()}
    codes.update(_stored_codes(db))
    accepted, rejected = _decisions(db)
    registry = ProductRegistry(short_codes=codes, rejected_links=rejected)

    for row in db.execute(select(ProductName)).scalars():
        registry.observe(row.raw, Vocabulary(row.vocabulary))
    for left, right, reason in accepted:
        if registry.identity_for(left) and registry.identity_for(right):
            registry.link(left, right, reason=reason)
    return registry


def remember_names(db: Session, staged: StagedRound, registry: ProductRegistry) -> None:
    """Record any product name this round introduced, so later rounds start knowing it."""
    known = {row.name for row in db.execute(select(ProductName)).scalars()}
    for raw in staged.products_seen:
        key = normalise(raw)
        if key in known:
            continue
        identity = registry.identity_for(raw)
        vocabulary = Vocabulary.SALES
        if identity is not None:
            name = identity.names.get(key)
            if name is not None:
                vocabulary = name.vocabulary
        db.add(ProductName(name=key, raw=raw, vocabulary=vocabulary.value))
        known.add(key)
    db.flush()


def remember_proven_links(db: Session, staged: StagedRound) -> None:
    """Write down a link a document proved, so the proof outlives the round that carried it.

    Account sale 382405 names both `CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)` and
    `CHOT 1L HT25 CHERRY OTHER` for R400. That statement is in one round only; the cherries go
    on selling in the next. Re-proving the link each round would mean the cherries losing their
    short code the moment the statement that proved it is no longer in front of us.
    """
    for sales_name, statement_name, evidence in staged.proven_links:
        left_key, right_key = sorted((normalise(sales_name), normalise(statement_name)))
        existing = db.execute(
            select(ProductDecision).where(
                ProductDecision.left_key == left_key, ProductDecision.right_key == right_key
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            ProductDecision(
                left_key=left_key,
                right_key=right_key,
                accepted=True,
                reason=evidence,
                is_evidence=True,
            )
        )
    db.flush()


def _documents(round_: Round) -> list[tuple[str, bytes]]:
    return [(d.filename, d.content) for d in round_.documents if d.duplicate_of_round_id is None]


@dataclass
class History:
    """What the rounds before this one already account for."""

    balances: dict[str, Decimal] = field(default_factory=dict)
    """Closing stock per consignment, so the next round opens where the last one left off."""

    counted: set[tuple[str, str, str, str]] = field(default_factory=set)
    """Every sale already counted, so an overlapping export cannot count one twice."""

    settled: dict[str, AccountSale] = field(default_factory=dict)
    """Every account sale already settled, so a restated one is compared rather than duplicated."""


def history(db: Session, before: Round) -> History:
    """Re-derive every resolved round before this one, in order.

    Re-derived rather than read from a balances table, because a balance is a consequence of the
    documents and not a fact of its own -- a table of them can drift from what the documents say,
    and nothing would look wrong. Two rounds of nine files is milliseconds; if that stops being
    true the answer is to cache this, not to write the number down.
    """
    earlier = (
        db.execute(
            select(Round)
            .where(Round.status == RoundStatus.RESOLVED.value, Round.id < before.id)
            .order_by(Round.id)
        )
        .scalars()
        .all()
    )
    past = History()
    for previous in earlier:
        registry = build_registry(db)
        staged, _ = build_round(
            [(name, read_document(content)) for name, content in _documents(previous)],
            registry,
            past.counted,
            dict(past.settled),
        )
        ledger = build_ledger(staged.rows, staged.consignments, past.balances)
        past.balances.update(ledger.closing)
        past.counted |= staged.docket_identities
        for number, record in staged.account_sales.items():
            record.source_name = record.source_name or f"round {previous.id}"
            past.settled.setdefault(number, record)
    return past


def load(db: Session, round_: Round) -> ResolvedRound:
    """Everything about one round: its figures, its open questions and its answers.

    This reads, and it also writes down two things it learned on the way: product names it had
    not seen before, and links a document proved. Both are facts rather than judgements, and
    both are useless if they expire with the round that carried them.
    """
    past = history(db, round_)
    registry = build_registry(db)
    staged, _ = build_round(
        [(name, read_document(content)) for name, content in _documents(round_)],
        registry,
        past.counted,
        past.settled,
    )
    remember_names(db, staged, registry)
    remember_proven_links(db, staged)

    duplicates = [
        DuplicateAlert(
            filename=d.filename,
            earlier_round_id=d.duplicate_of_round_id or round_.id,
            message=(
                f"{d.filename} is byte for byte a document already read in round "
                f"{d.duplicate_of_round_id}. It was kept but counted nothing, so this round "
                "adds no rows from it."
            ),
        )
        for d in round_.documents
        if d.duplicate_of_round_id is not None
    ]

    book = book_reader.read(workbook_path())
    approved = {
        note.delivery_id: note
        for note in db.execute(
            select(DeliveryNote).where(
                DeliveryNote.delivery_id.in_([d for d in staged.deliveries if d])
            )
        ).scalars()
    }

    # Every delivery note ever approved, so a mint cannot reissue one from an earlier round.
    spoken_for = {dn for dn in db.execute(select(DeliveryNote.dn)).scalars() if dn}
    proposals = _propose_all(staged, book, approved, spoken_for)
    suspensions = _sync_suspensions(db, round_, staged)

    ledger = build_ledger(staged.rows, staged.consignments, past.balances)

    # Only the products this round actually contains. Identity is global; the questions are
    # not, and blocking a round on a product that appears nowhere in it would be unanswerable.
    in_round = {
        identity.key
        for raw in staged.products_seen
        if (identity := registry.identity_for(raw)) is not None
    }
    items = queue_builder.sort_queue(
        queue_builder.product_link_items(registry, in_round)
        + queue_builder.product_code_items(registry, staged, book.short_codes, in_round)
        + queue_builder.delivery_note_items(staged, proposals, set(approved), ZACO_PRODUCER_CODE)
    )

    return ResolvedRound(
        round=round_,
        staged=staged,
        registry=registry,
        ledger=ledger,
        book=book,
        proposals=proposals,
        approved=approved,
        items=items,
        duplicates=duplicates,
        suspensions=suspensions,
        grouping_dates=grouping_dates(staged, approved),
    )


def _propose_all(
    staged: StagedRound,
    book: BookKnowledge,
    approved: dict[str, DeliveryNote],
    spoken_for: set[str],
) -> dict[str, Proposal]:
    """Propose a DN for every delivery, never reusing a number already spoken for.

    `spoken_for` is every delivery note ever approved, not just this round's. Scoping it to the
    round in front of us would let a mint reissue a number an earlier round had already given to
    a different delivery -- two loads under one delivery note, in the book the business settles
    money against, with nothing looking wrong.

    `taken` then grows as the loop runs, so two deliveries that both need minting in the same
    round get two different numbers rather than the same one twice.
    """
    producer_codes = {d.producer_code for d in staged.deliveries.values() if d.producer_code} | {
        ZACO_PRODUCER_CODE
    }
    taken = set(book.delivery_notes) | spoken_for | {n.dn for n in approved.values() if n.dn}

    proposals: dict[str, Proposal] = {}
    for delivery in staged.deliveries.values():
        if not delivery.delivery_id or delivery.delivery_id in approved:
            continue
        sales = sorted(
            {
                staged.account_sales[s].display_number
                for c in delivery.consignments
                for s in c.account_sales
                if s in staged.account_sales
            }
        )
        proposal = propose(
            delivery.delivery_id,
            delivery.supplier_ref,
            producer_codes=producer_codes,
            taken=taken,
            workbook_links=book.links,
            account_sales=sales,
            zaco_producer_code=ZACO_PRODUCER_CODE,
        )
        proposals[delivery.delivery_id] = proposal
        if proposal.dn:
            taken.add(proposal.dn)
    return proposals


def _sync_suspensions(db: Session, round_: Round, staged: StagedRound) -> list[Suspension]:
    """Record every disagreement this round contains, without disturbing settled ones."""
    existing = {
        s.subject_key: s
        for s in db.execute(select(Suspension).where(Suspension.round_id == round_.id)).scalars()
    }
    for disagreement in staged.disagreements:
        if disagreement.subject_key in existing:
            continue
        differences = "; ".join(
            f"{name}: {left} vs {right}" for name, left, right in disagreement.differences
        )
        suspension = Suspension(
            round_id=round_.id,
            subject_kind=disagreement.subject_kind,
            subject_key=disagreement.subject_key,
            description=f"{disagreement.description} ({' / '.join(disagreement.sources)})",
            differences=differences,
        )
        db.add(suspension)
        existing[disagreement.subject_key] = suspension
    db.flush()
    return sorted(existing.values(), key=lambda s: s.subject_key)


def grouping_dates(staged: StagedRound, approved: dict[str, DeliveryNote]) -> dict[str, date]:
    """The date every row under one DN is grouped on: the earliest across all of them.

    Section 7 calls for one date per delivery note, not one per row, so that a book filtered by
    date shows a delivery once. Taken as the earliest because that is when the load left, and a
    later account sale for the same load does not make the delivery later.
    """
    dates: dict[str, list[date]] = {}
    for row in staged.rows:
        note = approved.get(row.delivery_id or "")
        if note is None or not note.dn or row.earliest_date is None:
            continue
        dates.setdefault(note.dn, []).append(row.earliest_date)
    return {dn: min(values) for dn, values in dates.items() if values}


# --- answering ---------------------------------------------------------------------------------


def capture_code(db: Session, user: User, product_key: str, short_code: str) -> list[str]:
    """Record the operator's code against every name the product answers to.

    Writing it against all of them is what stops the same fruit being asked about again next
    round because a different document called it by its other name.
    """
    registry = build_registry(db)
    identity = registry.identity_for(product_key)
    names = sorted(identity.names) if identity else [normalise(product_key)]

    for name in names:
        row = db.execute(select(ProductCode).where(ProductCode.name == name)).scalar_one_or_none()
        if row is None:
            db.add(ProductCode(name=name, short_code=short_code, captured_by=user))
        else:
            row.short_code = short_code
            row.captured_by = user
    db.flush()
    return names


def decide_link(
    db: Session, user: User, left: str, right: str, accepted: bool, reason: str
) -> ProductDecision:
    """Accept or reject a suggested product link. A rejection is remembered too."""
    left_key, right_key = sorted((normalise(left), normalise(right)))
    row = db.execute(
        select(ProductDecision).where(
            ProductDecision.left_key == left_key, ProductDecision.right_key == right_key
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProductDecision(left_key=left_key, right_key=right_key, accepted=accepted)
        db.add(row)
    row.accepted = accepted
    row.reason = reason
    row.decided_by = user
    db.flush()
    return row


def approve_dn(
    db: Session,
    user: User,
    delivery_id: str,
    dn: str | None,
    provenance: DnProvenance,
    reasoning: str,
    operator_reason: str = "",
    supplier_ref: str | None = None,
) -> DeliveryNote:
    """Write an approved delivery note. Nothing reaches this without a person calling it."""
    note = db.execute(
        select(DeliveryNote).where(DeliveryNote.delivery_id == delivery_id)
    ).scalar_one_or_none()
    if note is None:
        note = DeliveryNote(delivery_id=delivery_id)
        db.add(note)
    note.dn = dn
    note.provenance = provenance.value
    note.reasoning = reasoning
    note.operator_reason = operator_reason
    note.supplier_ref = supplier_ref
    note.approved_by = user
    db.flush()
    return note


def totals(resolved: ResolvedRound) -> dict[str, str]:
    staged = resolved.staged
    return {
        "deliveries": str(len(staged.deliveries)),
        "consignments": str(len(staged.consignments)),
        "rows": str(len(staged.rows)),
        "account_sales": str(len(staged.account_sales)),
        "cartons_sent": f"{staged.cartons_sent:g}",
        "cartons_net": f"{staged.cartons.net:g}",
        "value": f"R{staged.value:,.2f}",
        "open_questions": str(len(resolved.items)),
        "delivery_notes_approved": str(len([n for n in resolved.approved.values()])),
        "products_unresolved": str(len(resolved.registry.unresolved)),
        "carried_forward": str(
            len([p for p in resolved.ledger.positions.values() if p.is_carried_forward])
        ),
        "closing_stock": f"{sum(resolved.ledger.closing.values(), ZERO):g}",
    }
