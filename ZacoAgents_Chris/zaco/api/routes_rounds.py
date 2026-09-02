"""Staging a round: what a set of documents amounts to together.

Still nothing stored. Phase 2 shows the operator the grain -- delivery, consignment, row -- and
what each figure is a figure *of*, so that the counting can be checked before any of it is
written into the book.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from zaco.api.routes_ingest import MAX_UPLOAD_BYTES
from zaco.api.schemas import (
    AccountSaleOut,
    CartonsOut,
    ConsignmentOut,
    DeliveryOut,
    ProblemOut,
    ProductOut,
    RowOut,
    StagedRoundOut,
    SuggestionOut,
    UnpaidDocketOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.db.models import User
from zaco.domain.build import build_round
from zaco.domain.model import Cartons, Consignment, Delivery, Row, StagedRound
from zaco.domain.products import ProductRegistry
from zaco.ingest.classifier import UnrecognisedDocumentError, read_document

router = APIRouter(prefix="/api/rounds", tags=["rounds"])
may_ingest = requires(Permission.INGEST)


@router.post("/stage", response_model=StagedRoundOut)
async def stage(
    files: list[UploadFile] = File(...), _: User = Depends(may_ingest)
) -> StagedRoundOut:
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No documents were uploaded.")

    documents = []
    for upload in files:
        data = await upload.read()
        name = upload.filename or "(unnamed)"
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
            )
        try:
            documents.append((name, read_document(data)))
        except UnrecognisedDocumentError as refusal:
            # One unreadable document refuses the whole round. Staging the rest would produce a
            # picture that looks complete and is not, which is worse than staging nothing.
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {
                    "filename": name,
                    "detail": f"{name}: {refusal}",
                    "scores": {k.value: v for k, v in refusal.scores.items()},
                },
            ) from refusal

    staged, registry = build_round(documents)
    return _to_out(staged, registry)


# --- rendering ---------------------------------------------------------------------------------


def _to_out(staged: StagedRound, registry: ProductRegistry) -> StagedRoundOut:
    rows_by_account_sale: dict[str, int] = {}
    for row in staged.rows:
        rows_by_account_sale[row.account_sale] = rows_by_account_sale.get(row.account_sale, 0) + 1

    return StagedRoundOut(
        sources=staged.sources,
        totals={
            "deliveries": str(len(staged.deliveries)),
            "consignments": str(len(staged.consignments)),
            "rows": str(len(staged.rows)),
            "account_sales": str(len(staged.account_sales)),
            # Once per consignment, never once per row. Labelled in the interface so the
            # difference is visible rather than assumed.
            "cartons_sent": _number(staged.cartons_sent),
            "value": _money(staged.value),
            "unpaid_dockets": str(len(staged.unpaid_dockets)),
            "products_unresolved": str(len(registry.unresolved)),
        },
        cartons=_cartons(staged.cartons),
        deliveries=[_delivery(d) for d in staged.deliveries.values()],
        rows=[_row(r) for r in staged.rows],
        account_sales=[
            AccountSaleOut(
                number=record.number,
                display_number=record.display_number,
                market=record.market,
                agent=record.agent,
                date_paid=record.date_paid,
                nett=_optional_money(record.nett),
                gross=_optional_money(record.gross),
                deduction_share=(
                    None
                    if record.deduction_share is None
                    else f"{record.deduction_share * 100:.1f}%"
                ),
                has_commodity_breakdown=record.has_commodity_breakdown,
                row_count=rows_by_account_sale.get(record.number, 0),
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
            for identity in registry.identities
        ],
        suggestions=[
            SuggestionOut(left=s.left, right=s.right, reason=s.reason)
            for s in registry.suggestions()
        ],
        unpaid_dockets=[
            UnpaidDocketOut(
                consignment_id=consignment.consignment_id,
                docket_number=docket.docket_number,
                date_sold=docket.date_sold,
                quantity=_optional_number(docket.quantity),
                value=_optional_money(docket.value),
            )
            for consignment, docket in staged.unpaid_dockets
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
    )


def _delivery(delivery: Delivery) -> DeliveryOut:
    return DeliveryOut(
        delivery_id=delivery.delivery_id,
        dn=delivery.dn,
        supplier_ref=delivery.supplier_ref,
        producer_code=delivery.producer_code,
        reference_half=delivery.reference_half,
        market=delivery.market,
        agent=delivery.agent,
        qty_sent=_number(delivery.qty_sent),
        consignments=[_consignment(c) for c in delivery.consignments],
    )


def _consignment(consignment: Consignment) -> ConsignmentOut:
    return ConsignmentOut(
        consignment_id=consignment.consignment_id,
        product=consignment.product.display_name,
        short_code=consignment.product.short_code,
        market=consignment.market,
        agent=consignment.agent,
        qty_sent=_optional_number(consignment.qty_sent),
        qty_available=_optional_number(consignment.qty_available),
        cartons=_cartons(consignment.cartons),
        value=_money(consignment.value),
        docket_count=len(consignment.dockets),
        account_sales=consignment.account_sales,
        days_on_market=consignment.days_on_market,
        is_identifiable=consignment.is_identifiable,
    )


def _row(row: Row) -> RowOut:
    return RowOut(
        delivery_id=row.delivery_id,
        consignment_id=row.consignment_id,
        product=row.product.display_name,
        short_code=row.product.short_code,
        account_sale=row.account_sale,
        account_sale_display=_display_account_sale(row.account_sale),
        market=row.market,
        agent=row.agent,
        cartons=_cartons(row.cartons),
        value=_money(row.value),
        price=_optional_money(row.price),
        earliest_date=row.earliest_date,
    )


def _display_account_sale(number: str) -> str:
    """D7: the bare number where one exists, the full reference where it does not."""
    tail = number.rsplit("*", 1)[-1] if "*" in number else number
    return tail if tail.isdigit() else number


def _cartons(cartons: Cartons) -> CartonsOut:
    return CartonsOut(
        sold=_number(cartons.sold),
        returned=_optional_number(cartons.returned),
        net=_number(cartons.net),
        returns_reportable=cartons.returns_reportable,
    )


def _number(value: Decimal) -> str:
    return f"{value:g}"


def _optional_number(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:g}"


def _money(value: Decimal) -> str:
    return f"R{value:,.2f}"


def _optional_money(value: Decimal | None) -> str | None:
    return None if value is None else f"R{value:,.2f}"
