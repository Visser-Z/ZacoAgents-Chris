"""Every sale off the floor, dated (for section 9 over time).

Section 9's reporting computes **one period per request**, and each request re-derives the whole
record from its documents. A month-by-month chart built on it would be twelve full re-parses, and
it still could not answer a daily question: `period_named` knows `all`, `month` and `week`, and
there is no day.

So this endpoint sends the dockets instead of an aggregate, and lets the client bucket them. That
is a smaller promise, not a bigger one -- it says what sold and when, and nothing about what any
of it means. Figures cross as numbers here rather than strings, under the `render.plot` rule: this
exists to be drawn, the money anybody is owed is on the workbook row, and nothing is settled
against a chart.

Dockets with no sale date are **included and counted separately**. Dropping them would quietly
shrink the total a reader compares against section 9's headline; putting them on a time axis at
some invented date would be worse.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from zaco.api.render import plot
from zaco.api.schemas import DocketOut, DocketsOut
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.db.base import get_db
from zaco.db.models import User
from zaco.resolve import service

router = APIRouter(prefix="/api/dockets", tags=["reports"])

may_view = requires(Permission.VIEW_REPORTS)


@router.get("", response_model=DocketsOut)
def dockets(
    db: Session = Depends(get_db),
    _: User = Depends(may_view),
) -> DocketsOut:
    """Every docket in the settled record, once each.

    Sourced from `record_so_far`, which walks the settled rounds in order and does not count a
    docket a previous round already counted -- the same protection section 9 relies on, and the
    reason the two agree on what sold.
    """
    record = service.record_so_far(db)

    out: list[DocketOut] = []
    for consignment in record.consignments:
        for docket in consignment.dockets:
            out.append(
                DocketOut(
                    docket_number=docket.docket_number,
                    date_sold=docket.date_sold,
                    date_delivered=docket.date_delivered,
                    date_paid=docket.date_paid,
                    quantity=plot(docket.quantity),
                    value=plot(docket.value),
                    price=plot(docket.price),
                    product=consignment.product.display_name,
                    short_code=consignment.product.short_code,
                    consignment_id=consignment.consignment_id,
                    market=consignment.market,
                    agent=consignment.agent,
                    account_sale=docket.account_sale,
                    is_return=docket.is_return,
                )
            )

    # Ordered by sale date, undated last. A client that plots them in receipt order draws a line
    # that wanders backwards through time.
    out.sort(key=lambda d: (d.date_sold is None, d.date_sold or "", d.docket_number))
    sold = [d.date_sold for d in out if d.date_sold]

    return DocketsOut(
        dockets=out,
        rounds_covered=len(service.settled_rounds(db)),
        first_sale=min(sold) if sold else None,
        last_sale=max(sold) if sold else None,
        undated=sum(1 for d in out if d.date_sold is None),
    )
