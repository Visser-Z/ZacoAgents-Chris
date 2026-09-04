"""Suppliers, agreed terms, and what is owed (section 8, D13).

Two permissions, deliberately apart. `RECORD_TERMS` may create a supplier and agree a commission;
`VIEW_REPORTS` may read what that produces. Recording terms decides what a farmer is paid, and
reading a report does not.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.api.render import money, optional_money
from zaco.api.schemas import (
    Message,
    PaymentIn,
    SettlementLineOut,
    SettlementOut,
    SupplierIn,
    SupplierOut,
    SupplierTotalOut,
    TermsIn,
    TermsOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.db.base import get_db
from zaco.db.models import CommissionTerm, Supplier, SupplierPayment, User
from zaco.resolve import service
from zaco.resolve.settle import Line

router = APIRouter(prefix="/api", tags=["settlement"])

may_record = requires(Permission.RECORD_TERMS)
may_view = requires(Permission.VIEW_REPORTS)

ZERO = Decimal("0")


def _supplier(found: Supplier) -> SupplierOut:
    return SupplierOut(
        id=found.id,
        name=found.name,
        contact=found.contact,
        note=found.note,
        is_active=found.is_active,
        created_by=found.created_by.email if found.created_by else None,
    )


def _terms(found: CommissionTerm) -> TermsOut:
    return TermsOut(
        id=found.id,
        consignment_id=found.consignment_id,
        supplier_id=found.supplier_id,
        supplier=found.supplier.name,
        percent=f"{found.percent:.3f}".rstrip("0").rstrip("."),
        note=found.note,
        agreed_by=found.agreed_by.email if found.agreed_by else None,
        agreed_at=found.agreed_at,
    )


def _line(line: Line) -> SettlementLineOut:
    return SettlementLineOut(
        consignment_id=line.consignment_id,
        product=line.product,
        delivery_id=line.delivery_id,
        supplier=line.supplier,
        percent=None if line.percent is None else f"{line.percent:g}",
        nett=optional_money(line.nett),
        zaco_keeps=optional_money(line.zaco_keeps),
        owed_to_supplier=optional_money(line.owed_to_supplier),
        cartons_sold=f"{line.cartons_sold:g}",
        cartons_sent=None if line.cartons_sent is None else f"{line.cartons_sent:g}",
        cartons_unsold=None if line.cartons_unsold is None else f"{line.cartons_unsold:g}",
        blocked_by=line.blocked_by,
    )


@router.get("/suppliers", response_model=list[SupplierOut])
def suppliers(db: Session = Depends(get_db), _: User = Depends(may_view)) -> list[SupplierOut]:
    found = db.execute(select(Supplier).order_by(Supplier.name)).scalars().all()
    return [_supplier(s) for s in found]


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def add_supplier(
    body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(may_record)
) -> SupplierOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A supplier needs a name.")
    if db.execute(select(Supplier).where(Supplier.name == name)).scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"There is already a supplier called {name}. Two suppliers with one name would make "
            f"every settlement against either of them ambiguous.",
        )
    found = Supplier(
        name=name, contact=body.contact.strip(), note=body.note.strip(), created_by=user
    )
    db.add(found)
    db.flush()
    return _supplier(found)


@router.get("/terms", response_model=list[TermsOut])
def terms(db: Session = Depends(get_db), _: User = Depends(may_view)) -> list[TermsOut]:
    found = db.execute(select(CommissionTerm).order_by(CommissionTerm.consignment_id)).scalars()
    return [_terms(t) for t in found]


@router.post("/terms", response_model=TermsOut, status_code=status.HTTP_201_CREATED)
def agree_terms(
    body: TermsIn, db: Session = Depends(get_db), user: User = Depends(may_record)
) -> TermsOut:
    """Agree Zaco's percentage of the Nett for one delivery line.

    Bounded at 0 to 100 because a percentage outside that is not a rate anybody agreed; it is a
    typing slip that would pay a supplier a negative amount or more than the money that arrived.
    """
    consignment = body.consignment_id.strip()
    if not consignment:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Terms are agreed per delivery line, so they need a consignment.",
        )
    if not (ZERO <= body.percent <= Decimal(100)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{body.percent} is not a share of the Nett. It has to be between 0 and 100.",
        )
    supplier = db.get(Supplier, body.supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such supplier.")

    existing = db.execute(
        select(CommissionTerm).where(CommissionTerm.consignment_id == consignment)
    ).scalar_one_or_none()
    if existing is not None:
        existing.supplier = supplier
        existing.percent = body.percent
        existing.note = body.note.strip()
        existing.agreed_by = user
        db.flush()
        return _terms(existing)

    found = CommissionTerm(
        consignment_id=consignment,
        supplier=supplier,
        percent=body.percent,
        note=body.note.strip(),
        agreed_by=user,
    )
    db.add(found)
    db.flush()
    return _terms(found)


@router.post("/supplier-payments", response_model=Message, status_code=status.HTTP_201_CREATED)
def record_payment(
    body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(may_record)
) -> Message:
    """Record that a supplier was paid. Section 12: money is recorded, never moved."""
    supplier = db.get(Supplier, body.supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such supplier.")
    db.add(
        SupplierPayment(
            supplier=supplier,
            amount=body.amount,
            reference=body.reference.strip(),
            note=body.note.strip(),
            recorded_by=user,
        )
    )
    db.flush()
    return Message(detail=f"Recorded {money(body.amount)} paid to {supplier.name}.")


@router.get("/settlement", response_model=SettlementOut)
def settlement(db: Session = Depends(get_db), _: User = Depends(may_view)) -> SettlementOut:
    """What each supplier earned, is owed, has been paid, and handed over that never sold."""
    found = service.settlement(db)

    paid_out: dict[str, Decimal] = {}
    for payment in db.execute(select(SupplierPayment)).scalars():
        paid_out[payment.supplier.name] = paid_out.get(payment.supplier.name, ZERO) + payment.amount

    earned: dict[str, Decimal] = {}
    unsold: dict[str, Decimal | None] = {}
    counted: dict[str, int] = {}
    for line in found.settled:
        name = line.supplier or "(no supplier)"
        earned[name] = earned.get(name, ZERO) + (line.owed_to_supplier or ZERO)
        counted[name] = counted.get(name, 0) + 1
        # Absent stays absent: one consignment with an unknown quantity sent makes the whole
        # supplier's unsold figure unknown, rather than quietly smaller than it is.
        if name not in unsold:
            unsold[name] = line.cartons_unsold
        elif line.cartons_unsold is None or unsold[name] is None:
            unsold[name] = None
        else:
            unsold[name] = (unsold[name] or ZERO) + line.cartons_unsold

    by_supplier = [
        SupplierTotalOut(
            supplier=name,
            earned=money(total),
            paid=money(paid_out.get(name, ZERO)),
            owed=money(total - paid_out.get(name, ZERO)),
            cartons_unsold=None if unsold.get(name) is None else f"{unsold[name]:g}",
            consignments=counted[name],
        )
        for name, total in sorted(earned.items())
    ]

    return SettlementOut(
        settled=[_line(line) for line in found.settled],
        awaiting_terms=[_line(line) for line in found.awaiting_terms],
        awaiting_payment=[_line(line) for line in found.awaiting_payment],
        by_supplier=by_supplier,
        total_owed=money(found.total_owed),
        total_kept=money(found.total_kept),
        coverage=found.coverage,
        suppliers=suppliers(db, _),
        terms=terms(db, _),
    )
