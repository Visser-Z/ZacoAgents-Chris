"""Saving a round and answering its questions (section 7).

Every answer arrives here with a signed-in person behind it. There is no endpoint that applies
a proposal, accepts a suggestion or fills in a delivery note on its own -- the system's whole
job at this stage is to say what it does not know and to hold still until told.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.api import render
from zaco.api.routes_ingest import MAX_UPLOAD_BYTES
from zaco.api.schemas import (
    AccountSaleOut,
    AlertOut,
    ApproveDnIn,
    BulkDnIn,
    CaptureCodeIn,
    DecideSuspensionIn,
    DeliveryNoteOut,
    DeliveryOut,
    DocumentOut,
    EventOut,
    LinkDecisionIn,
    Message,
    ProblemOut,
    ProductOut,
    QueueItemOut,
    ReasonIn,
    ResolvedRowOut,
    RoundOut,
    RoundSummaryOut,
    StockOut,
    SuspensionOut,
    TestOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.db.base import get_db
from zaco.db.models import (
    DeliveryNote,
    Round,
    RoundDocument,
    RoundStatus,
    Suspension,
    User,
    utcnow,
)
from zaco.domain.model import Delivery, Row
from zaco.ingest.classifier import UnrecognisedDocumentError
from zaco.resolve import service
from zaco.resolve.dn import DnProvenance
from zaco.resolve.queue import Item
from zaco.resolve.service import ResolvedRound

router = APIRouter(prefix="/api/rounds", tags=["resolution"])
products = APIRouter(prefix="/api/products", tags=["resolution"])

may_ingest = requires(Permission.INGEST)
may_resolve = requires(Permission.RESOLVE)


def _round_or_404(db: Session, round_id: int) -> Round:
    found = db.get(Round, round_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No round {round_id}.")
    return found


def _editable(round_: Round) -> Round:
    if round_.status != RoundStatus.STAGED.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Round {round_.id} is {round_.status}. Answers are only taken while it is staged.",
        )
    return round_


# --- saving and listing ------------------------------------------------------------------------


@router.post("", response_model=RoundOut, status_code=status.HTTP_201_CREATED)
async def create(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(may_ingest),
) -> RoundOut:
    """Save one round of documents and open its queue."""
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No documents were uploaded.")

    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        content = await upload.read()
        name = upload.filename or "(unnamed)"
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
            )
        uploads.append((name, content))

    try:
        round_, _ = service.save_round(db, user, uploads)
    except UnrecognisedDocumentError as refusal:
        # One unreadable document refuses the whole round, exactly as staging does. A round
        # saved without it would look complete and would not be.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "detail": str(refusal),
                "scores": {k.value: v for k, v in refusal.scores.items()},
            },
        ) from refusal

    return _render(db, service.load(db, round_))


@router.get("", response_model=list[RoundSummaryOut])
def index(db: Session = Depends(get_db), _: User = Depends(may_ingest)) -> list[RoundSummaryOut]:
    rounds = db.execute(select(Round).order_by(Round.id.desc())).scalars().all()
    return [_summary(db, r) for r in rounds]


@router.get("/{round_id}", response_model=RoundOut)
def show(round_id: int, db: Session = Depends(get_db), _: User = Depends(may_ingest)) -> RoundOut:
    return _render(db, service.load(db, _round_or_404(db, round_id)))


# --- taking a document back out ------------------------------------------------------------------


def _document_or_404(db: Session, round_: Round, document_id: int) -> RoundDocument:
    found = db.get(RoundDocument, document_id)
    if found is None or found.round_id != round_.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Round {round_.id} has no document {document_id}."
        )
    return found


def _reason(body: ReasonIn, message: str) -> str:
    text = body.reason.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)
    return text


@router.post("/{round_id}/documents/{document_id}/withdraw", response_model=RoundOut)
def withdraw_document(
    round_id: int,
    document_id: int,
    body: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Take a wrongly uploaded document out of the round's figures, keeping the file.

    Needed because being readable is not the same as belonging here: another business's payment
    export, or last quarter's run, is a perfectly good Payment Details report and the classifier
    has no reason to refuse it.
    """
    round_ = _editable(_round_or_404(db, round_id))
    document = _document_or_404(db, round_, document_id)
    if document.is_withdrawn:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{document.filename} is already out of this round."
        )
    reason = _reason(
        body,
        "Say why this document is being taken out. Its rows are about to leave the round, and "
        "whoever compares the figures next month needs to know they were removed on purpose.",
    )
    service.withdraw_document(db, round_, user, document, reason)
    return _render(db, service.load(db, round_))


@router.post("/{round_id}/documents/{document_id}/restore", response_model=RoundOut)
def restore_document(
    round_id: int,
    document_id: int,
    body: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Put a withdrawn document back. Its figures return exactly as they were."""
    round_ = _editable(_round_or_404(db, round_id))
    document = _document_or_404(db, round_, document_id)
    if not document.is_withdrawn:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{document.filename} is already part of this round."
        )
    service.restore_document(db, round_, user, document, body.reason.strip())
    return _render(db, service.load(db, round_))


@router.post("/{round_id}/reopen", response_model=RoundOut)
def reopen(
    round_id: int,
    body: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Put a closed or set-aside round back to staged, so a document can be taken out of it.

    The mistake is usually only noticed later, so refusing to reopen would leave a wrong document
    in the figures permanently. A round already appended to the workbook is the exception: an
    append cannot be unwritten, so the book is corrected by rolling it back, not the round.
    """
    round_ = _round_or_404(db, round_id)
    if round_.appended_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Round {round_.id} was appended to the workbook on "
            f"{round_.appended_at:%d %b %Y}, writing rows "
            f"{round_.appended_first_row}-{round_.appended_last_row}. Rows are appended, never "
            "rebuilt, so reopening it would leave the round and the book disagreeing. Correct "
            "the book by rolling it back to a saved version instead.",
        )
    if round_.status == RoundStatus.STAGED.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Round {round_.id} is already open, so there is nothing to reopen.",
        )
    reason = _reason(body, "Say why this round is being reopened.")
    later = service.rounds_after(db, round_)
    service.reopen_round(db, round_, user, reason)
    rendered = _render(db, service.load(db, round_))
    if later:
        names = ", ".join(f"#{r.id}" for r in later)
        rendered.alerts.append(
            AlertOut(
                subject=f"round {round_.id}",
                message=(
                    f"While this round is open, round(s) {names} are derived without it: their "
                    "opening stock starts earlier and sales this round already counted are no "
                    "longer skipped as duplicates. Closing it again puts that back."
                ),
            )
        )
    return rendered


@router.post("/{round_id}/abandon", response_model=RoundOut)
def abandon(
    round_id: int,
    body: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Put a whole round aside -- the case where every file in it was the wrong one.

    Kept rather than deleted, and its documents stop blocking a re-upload, so the same files can
    be loaded again properly once the right ones are to hand.
    """
    round_ = _editable(_round_or_404(db, round_id))
    reason = _reason(body, "Say why this round is being put aside.")
    service.abandon_round(db, round_, user, reason)
    return _render(db, service.load(db, round_))


@router.post("/{round_id}/delivery-notes/{delivery_id}/release", response_model=RoundOut)
def release_delivery_note(
    round_id: int,
    delivery_id: str,
    body: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Give an approved delivery note number back to the series.

    Only reachable for a delivery no round contains any more. Approved numbers are keyed on the
    delivery rather than the round and every one of them is avoided when a fresh number is
    minted, so a note left behind by a withdrawal quietly holds a number out of the `14xxx`
    series for a delivery that no longer exists.
    """
    round_ = _editable(_round_or_404(db, round_id))
    resolved = service.load(db, round_)
    note = next((n for n in resolved.orphaned_notes if n.delivery_id == delivery_id), None)
    if note is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No delivery note is stranded on {delivery_id}. A note is only released once the "
            "delivery it was approved for has left the round.",
        )
    reason = _reason(
        body,
        "Say why this approved number is being given back. It was approved by a person, and the "
        "record has to show why it stopped applying.",
    )
    service.release_delivery_note(db, round_, user, note, reason)
    return _render(db, service.load(db, round_))


# --- answering ---------------------------------------------------------------------------------


@products.post("/code", response_model=Message)
def capture_code(
    body: CaptureCodeIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> Message:
    """Record Zaco's own short code for a product, against every name it answers to.

    Not scoped to a round, because the answer is not. A code captured while working through one
    round applies to every round after it, which is what stops the same eleven questions being
    asked again next week.
    """
    code = body.short_code.strip()
    if not code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A short code cannot be blank.")
    names = service.capture_code(db, user, body.product_key, code)
    return Message(
        detail=f"{code} recorded against {len(names)} name(s). It will not be asked for again."
    )


@products.post("/link", response_model=Message)
def decide_link(
    body: LinkDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> Message:
    """Accept or reject a suggested product link. A rejection is remembered as firmly."""
    service.decide_link(db, user, body.left, body.right, body.accepted, body.reason.strip())
    if body.accepted:
        return Message(
            detail="Recorded as the same product; their short codes now travel together."
        )
    return Message(detail="Recorded as different products. This pair will not be suggested again.")


@router.post("/{round_id}/delivery-notes", response_model=RoundOut)
def approve_delivery_note(
    round_id: int,
    body: ApproveDnIn,
    delivery_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Approve one delivery's DN, or record that it deliberately has none."""
    round_ = _editable(_round_or_404(db, round_id))
    resolved = service.load(db, round_)
    _approve_one(db, user, resolved, delivery_id, body.dn, body.provenance, body.reason)
    return _render(db, service.load(db, round_))


@router.post("/{round_id}/delivery-notes/bulk", response_model=RoundOut)
def approve_delivery_notes(
    round_id: int,
    body: BulkDnIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """One delivery note across several deliveries -- the one-truck case.

    A reason is required, because assigning one number to three deliveries is a judgement about
    what physically happened and is not visible in any document.
    """
    round_ = _editable(_round_or_404(db, round_id))
    if not body.reason.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Say why these deliveries share one delivery note. Nothing in the documents says so, "
            "and whoever reads the book next needs the reason as much as the number.",
        )
    resolved = service.load(db, round_)
    for delivery_id in body.delivery_ids:
        _approve_one(db, user, resolved, delivery_id, body.dn, body.provenance, body.reason)
    return _render(db, service.load(db, round_))


def _approve_one(
    db: Session,
    user: User,
    resolved: ResolvedRound,
    delivery_id: str,
    dn: str | None,
    provenance_value: str,
    reason: str,
) -> DeliveryNote:
    delivery = resolved.staged.deliveries.get(delivery_id)
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Round has no delivery {delivery_id}.")
    try:
        provenance = DnProvenance(provenance_value)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown provenance {provenance_value!r}."
        ) from exc

    cleaned = (dn or "").strip() or None
    if cleaned is None and provenance is not DnProvenance.NONE_FOREIGN_PRODUCER:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A blank delivery note is only an answer when it is a recorded one. Choose "
            "'no DN — carried for another producer' if that is what this is, so the reason "
            "travels with the row instead of it looking unfinished.",
        )
    if provenance is DnProvenance.NONE_FOREIGN_PRODUCER and not reason.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Recording that a delivery has no delivery note needs a reason. A blank column A "
            "with nothing behind it is indistinguishable from one nobody got to.",
        )

    proposal = resolved.proposals.get(delivery_id)
    reasoning = proposal.reasoning if proposal else "No proposal was made for this delivery."
    if proposal and cleaned and proposal.dn == cleaned and provenance is DnProvenance.OPERATOR:
        # Approving the proposal as it stands keeps the proposal's own provenance, so the book
        # can later say the number came from a supplier reference rather than from a person.
        provenance = proposal.provenance or provenance

    return service.approve_dn(
        db,
        user,
        delivery_id,
        cleaned,
        provenance,
        reasoning,
        operator_reason=reason.strip(),
        supplier_ref=delivery.supplier_ref,
    )


@router.post("/{round_id}/suspensions/{suspension_id}", response_model=RoundOut)
def decide_suspension(
    round_id: int,
    suspension_id: int,
    body: DecideSuspensionIn,
    db: Session = Depends(get_db),
    user: User = Depends(may_resolve),
) -> RoundOut:
    """Settle a disagreement between two documents. The reason is not optional (D12)."""
    round_ = _editable(_round_or_404(db, round_id))
    suspension = db.get(Suspension, suspension_id)
    if suspension is None or suspension.round_id != round_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No suspension {suspension_id}.")
    suspension.chosen_source = body.chosen_source.strip()
    suspension.reason = body.reason.strip()
    suspension.decided_by = user
    suspension.decided_at = utcnow()
    db.flush()
    return _render(db, service.load(db, round_))


@router.post("/{round_id}/resolve", response_model=RoundOut)
def resolve(
    round_id: int, db: Session = Depends(get_db), user: User = Depends(may_resolve)
) -> RoundOut:
    """Close the queue. Refused while anything is unanswered (D5)."""
    round_ = _editable(_round_or_404(db, round_id))
    resolved = service.load(db, round_)
    if not resolved.is_clear:
        raise HTTPException(status.HTTP_409_CONFLICT, resolved.blocking_reason or "Queue is open.")
    round_.status = RoundStatus.RESOLVED.value
    round_.resolved_by = user
    round_.resolved_at = utcnow()
    db.flush()
    return _render(db, service.load(db, round_))


# --- rendering ---------------------------------------------------------------------------------


def _summary(db: Session, round_: Round) -> RoundSummaryOut:
    documents = (
        db.execute(select(RoundDocument).where(RoundDocument.round_id == round_.id)).scalars().all()
    )
    return RoundSummaryOut(
        id=round_.id,
        label=round_.label,
        status=round_.status,
        created_at=round_.created_at,
        created_by=round_.created_by.email if round_.created_by else None,
        document_count=len(documents),
        duplicate_count=len(
            [d for d in documents if d.duplicate_of_round_id is not None and not d.is_withdrawn]
        ),
        withdrawn_count=len([d for d in documents if d.is_withdrawn]),
    )


def _document(document: RoundDocument) -> DocumentOut:
    if document.is_withdrawn:
        state = "withdrawn"
    elif document.duplicate_of_round_id is not None:
        state = "duplicate"
    else:
        state = "counted"
    return DocumentOut(
        id=document.id,
        filename=document.filename,
        kind=document.kind,
        byte_count=document.byte_count,
        state=state,
        duplicate_of_round_id=document.duplicate_of_round_id,
        withdrawn_reason=document.withdrawn_reason,
        withdrawn_by=document.withdrawn_by.email if document.withdrawn_by else None,
        withdrawn_at=document.withdrawn_at,
    )


def _row(resolved: ResolvedRound, row: Row) -> ResolvedRowOut:
    note = resolved.approved.get(row.delivery_id or "")
    position = resolved.ledger.for_row(row)
    blocked = []
    if note is None:
        blocked.append("no approved delivery note")
    if row.product.short_code is None:
        blocked.append("no product short code")
    return ResolvedRowOut(
        delivery_id=row.delivery_id,
        consignment_id=row.consignment_id,
        product=row.product.display_name,
        short_code=row.product.short_code,
        account_sale=row.account_sale,
        account_sale_display=render.display_account_sale(row.account_sale),
        market=row.market,
        agent=row.agent,
        cartons=render.cartons(row.cartons),
        value=render.money(row.value),
        price=None if row.price is None else render.money(row.price),
        earliest_date=row.earliest_date,
        dn=note.dn if note else None,
        dn_provenance=note.provenance if note else None,
        grouping_date=resolved.grouping_dates.get(note.dn) if note and note.dn else None,
        stock=(
            None
            if position is None
            else StockOut(
                opening=render.optional_number(position.opening),
                sold=render.number(position.sold),
                closing=render.optional_number(position.closing),
                is_carried_forward=position.is_carried_forward,
                note=position.note,
            )
        ),
        is_writable=not blocked,
        blocked_by=blocked,
    )


def _delivery(resolved: ResolvedRound, delivery: Delivery) -> DeliveryOut:
    note = resolved.approved.get(delivery.delivery_id or "")
    return DeliveryOut(
        delivery_id=delivery.delivery_id,
        dn=note.dn if note else None,
        supplier_ref=delivery.supplier_ref,
        producer_code=delivery.producer_code,
        reference_half=delivery.reference_half,
        market=delivery.market,
        agent=delivery.agent,
        qty_sent=render.number(delivery.qty_sent),
        consignments=[render.consignment(c) for c in delivery.consignments],
    )


def _render(db: Session, resolved: ResolvedRound) -> RoundOut:
    staged = resolved.staged
    rows_by_sale: dict[str, int] = {}
    for row in staged.rows:
        rows_by_sale[row.account_sale] = rows_by_sale.get(row.account_sale, 0) + 1

    documents = sorted(resolved.round.documents, key=lambda d: d.id)
    alerts = (
        [AlertOut(subject=d.filename, message=d.message) for d in resolved.duplicates]
        + [AlertOut(subject=s.subject_key, message=s.description) for s in staged.skipped]
        + [
            AlertOut(
                subject=d.filename,
                message=(
                    f"Taken out of this round by "
                    f"{d.withdrawn_by.email if d.withdrawn_by else 'somebody since removed'}: "
                    f"“{d.withdrawn_reason}”. The file is kept; nothing in these figures "
                    "comes from it."
                ),
            )
            for d in documents
            if d.is_withdrawn
        ]
        + [
            AlertOut(
                subject=n.delivery_id,
                message=(
                    f"Delivery note {n.dn or '(none recorded)'} is still approved for delivery "
                    f"{n.delivery_id}, which no longer appears in this round. Until it is "
                    "released, that number stays out of the series and cannot be proposed for "
                    "anything else."
                ),
            )
            for n in resolved.orphaned_notes
        ]
    )

    book = {
        "state": "read" if resolved.book.is_readable else "not read",
        "rows": str(resolved.book.row_count),
        "delivery_notes_linked": str(len(resolved.book.links)),
        "detail": resolved.book.problem
        or (
            f"The book has {resolved.book.row_count} row(s) and links "
            f"{len(resolved.book.links)} account sale(s) to a delivery note. "
            + (
                "None of them appears in this round, so nothing could be reused; the join pays "
                "once a payment run in the book turns up in the data again."
                if not any(
                    a.display_number in resolved.book.links for a in staged.account_sales.values()
                )
                else "Those are reused rather than proposed afresh."
            )
        ),
    }

    return RoundOut(
        summary=_summary(db, resolved.round),
        totals=service.totals(resolved),
        cartons=render.cartons(staged.cartons),
        is_clear=resolved.is_clear,
        blocking_reason=resolved.blocking_reason,
        book=book,
        queue=[_item(i) for i in resolved.items],
        suspensions=[
            SuspensionOut(
                id=s.id,
                subject_kind=s.subject_kind,
                subject_key=s.subject_key,
                description=s.description,
                differences=s.differences,
                chosen_source=s.chosen_source,
                reason=s.reason,
                is_decided=s.is_decided,
                decided_by=s.decided_by.email if s.decided_by else None,
                decided_at=s.decided_at,
            )
            for s in resolved.suspensions
        ],
        alerts=alerts,
        delivery_notes=[
            DeliveryNoteOut(
                delivery_id=n.delivery_id,
                dn=n.dn,
                provenance=n.provenance,
                reasoning=n.reasoning,
                operator_reason=n.operator_reason,
                approved_by=n.approved_by.email if n.approved_by else None,
                approved_at=n.approved_at,
            )
            for n in sorted(resolved.approved.values(), key=lambda n: n.delivery_id)
        ],
        rows=[_row(resolved, r) for r in staged.rows],
        deliveries=[_delivery(resolved, d) for d in staged.deliveries.values()],
        account_sales=[
            AccountSaleOut(
                number=record.number,
                display_number=record.display_number,
                market=record.market,
                agent=record.agent,
                date_paid=record.date_paid,
                nett=None if record.nett is None else render.money(record.nett),
                gross=None if record.gross is None else render.money(record.gross),
                deduction_share=(
                    None
                    if record.deduction_share is None
                    else f"{record.deduction_share * 100:.1f}%"
                ),
                has_commodity_breakdown=record.has_commodity_breakdown,
                row_count=rows_by_sale.get(record.number, 0),
            )
            for record in staged.account_sales.values()
        ],
        products=[
            ProductOut(
                key=identity.key,
                display_name=identity.display_name,
                short_code=identity.short_code,
                vocabularies=sorted(v.value for v in identity.vocabularies),
                names=[n.raw for n in identity.names.values()],
                merge_reasons=identity.merge_reasons,
            )
            for identity in resolved.registry.identities
        ],
        problems=[
            ProblemOut(
                severity=p.severity.value,
                message=p.message,
                line_number=p.line_number,
                line=p.line,
            )
            for p in staged.problems
        ],
        stock_notes=resolved.ledger.notes,
        documents=[_document(d) for d in documents],
        events=[
            EventOut(
                action=e.action,
                subject=e.subject,
                reason=e.reason,
                at=e.at,
                by=e.by.email if e.by else None,
            )
            for e in sorted(resolved.round.events, key=lambda e: e.id)
        ],
        orphaned_delivery_notes=[
            DeliveryNoteOut(
                delivery_id=n.delivery_id,
                dn=n.dn,
                provenance=n.provenance,
                reasoning=n.reasoning,
                operator_reason=n.operator_reason,
                approved_by=n.approved_by.email if n.approved_by else None,
                approved_at=n.approved_at,
            )
            for n in resolved.orphaned_notes
        ],
    )


def _item(item: Item) -> QueueItemOut:
    return QueueItemOut(
        kind=item.kind.value,
        key=item.key,
        title=item.title,
        question=item.question,
        reasoning=item.reasoning,
        evidence=item.evidence,
        proposal=item.proposal,
        provenance=item.provenance,
        tests=[TestOut(name=t.name, passed=t.passed, detail=t.detail) for t in item.tests],
        counter_evidence=item.counter_evidence,
        choices=item.choices,
        companions=item.companions,
        requires_reason=item.requires_reason,
    )
