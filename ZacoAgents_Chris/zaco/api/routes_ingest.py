"""Reading a document and reporting what it says.

Phase 1 reads and reports; nothing is stored yet. That is deliberate -- the readers can be
judged on whether they read the page correctly before any question of interpretation, staging or
deduplication is mixed in.

A refused document returns 422 with the explanation section 4 asks for, and the confidence each
of the five readers had, so the operator can see *why* it was not recognised rather than being
told only that it was not.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from zaco.api.schemas import (
    InspectionOut,
    ProblemOut,
    RecordPreview,
    ScopeOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.db.models import User
from zaco.ingest.classifier import UnrecognisedDocumentError, read_document, score
from zaco.ingest.records import TITLES, DocumentKind, ParseResult
from zaco.ingest.values import read_text

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
may_ingest = requires(Permission.INGEST)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@router.get("/kinds", response_model=dict[str, str])
def kinds(_: User = Depends(may_ingest)) -> dict[str, str]:
    """The five report kinds this system handles. Section 12: no others are supported."""
    return {kind.value: title for kind, title in TITLES.items()}


@router.post("/inspect", response_model=InspectionOut)
async def inspect(
    file: UploadFile = File(...),
    expected: str | None = Form(default=None),
    _: User = Depends(may_ingest),
) -> InspectionOut:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )

    declared = _read_expected(expected)
    try:
        result = read_document(data, expected=declared)
    except UnrecognisedDocumentError as refusal:
        # The filename is never used to identify a document, so it is not used to rescue one
        # either. Refuse, and say what each reader made of it.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "filename": file.filename or "(unnamed)",
                "detail": str(refusal),
                "scores": {k.value: v for k, v in refusal.scores.items()},
            },
        ) from refusal

    from zaco.ingest.problems import ProblemLog

    text = read_text(data, ProblemLog())
    return _to_inspection(file.filename or "(unnamed)", result, score(text))


def _read_expected(expected: str | None) -> DocumentKind | None:
    if not expected:
        return None
    try:
        return DocumentKind(expected)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{expected!r} is not one of the five report kinds."
        ) from exc


def _to_inspection(
    filename: str, result: ParseResult, scores: dict[DocumentKind, float]
) -> InspectionOut:
    return InspectionOut(
        filename=filename,
        kind=result.kind.value,
        kind_title=TITLES[result.kind],
        confidence=scores.get(result.kind, 0.0),
        scores={k.value: v for k, v in scores.items()},
        scope=ScopeOut(
            description=result.scope.describe(),
            market=result.scope.market,
            agent=result.scope.agent,
            date_from=result.scope.date_from,
            date_to=result.scope.date_to,
            run_at=result.scope.run_at,
            is_narrowed=result.scope.is_narrowed,
            is_unstated=result.scope.is_unstated,
        ),
        counts={
            "consignments": len(result.consignments),
            "dockets": result.docket_count,
            "statements": len(result.statements),
            "payments": len(result.payments),
            "adjustments": len(result.adjustments),
        },
        problems=[
            ProblemOut(
                severity=p.severity.value,
                message=p.message,
                line_number=p.line_number,
                line=p.line,
            )
            for p in result.problems
        ],
        preview=_preview(result),
    )


def _preview(result: ParseResult) -> list[RecordPreview]:
    rows: list[RecordPreview] = []

    for block in result.consignments:
        flags = []
        returns = [d for d in block.dockets if d.is_return]
        if returns:
            flags.append(f"{len(returns)} return(s)")
        if not block.market:
            flags.append("market not stated")
        if not block.supplier_ref:
            flags.append("no supplier ref")
        if any(d.payment_reference is None for d in block.dockets):
            flags.append("no account sale named")
        rows.append(
            RecordPreview(
                label=block.consignment_id or block.delivery_id or "(unidentified)",
                detail=block.product_name or "(no product named)",
                figures={
                    "Delivery": block.delivery_id or "-",
                    "Supplier Ref": block.supplier_ref or "-",
                    "Qty sent": _figure(block.qty_sent),
                    "Dockets": str(len(block.dockets)),
                    "Net cartons": _figure(block.total_quantity),
                    "Value": _money(block.total_value),
                    "Agent": block.agent or "-",
                },
                flags=flags,
            )
        )

    for statement in result.statements:
        rows.append(
            RecordPreview(
                label=statement.account_sale_number or "(no account sale number)",
                detail=", ".join(p.product_name or "?" for p in statement.products)
                or "(no products)",
                figures={
                    "Gross": _money(statement.gross_amount),
                    "Nett": _money(statement.nett_amount),
                    "Deductions": ", ".join(
                        f"{d.name} {_money(d.total)}" for d in statement.deductions
                    )
                    or "-",
                    "Agent delivery note": statement.agent_delivery_note_number or "-",
                    "Previous account sale": statement.previous_account_sale_number or "-",
                },
                flags=(
                    ["agent's own delivery note number, not Zaco's DN"]
                    if statement.agent_delivery_note_number
                    else []
                ),
            )
        )

    for payment in result.payments:
        rows.append(
            RecordPreview(
                label=payment.account_sale_number or "(no account sale number)",
                detail=", ".join(c.commodity or "?" for c in payment.commodities)
                or "(no commodity breakdown)",
                figures={
                    "Nett": _money(payment.nett_payment),
                    "Gross": _money(payment.gross_payment),
                    "Deductions": _money(payment.total_deductions),
                    "Paid": str(payment.date_paid or "-"),
                    "Agent": payment.agent or "-",
                },
                flags=[] if payment.has_commodity_breakdown else ["can never reconcile"],
            )
        )

    for adjustment in result.adjustments:
        rows.append(
            RecordPreview(
                label=adjustment.account_sale_number or "(no account sale number)",
                detail="no product or quantity in this report kind",
                figures={
                    "Supplier Refs": ", ".join(adjustment.supplier_refs) or "-",
                    "Gross": _money(adjustment.gross_payment),
                    "Nett": _money(adjustment.nett_payment),
                    "Paid": str(adjustment.date_paid or "-"),
                },
                flags=(
                    ["one payment against several references"]
                    if len(adjustment.supplier_refs) > 1
                    else []
                ),
            )
        )

    return rows


def _figure(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:g}"


def _money(value: Decimal | None) -> str:
    return "-" if value is None else f"R{value:,.2f}"
