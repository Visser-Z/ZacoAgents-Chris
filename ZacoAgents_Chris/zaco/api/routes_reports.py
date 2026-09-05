"""Reporting over the recorded history (section 9).

Every figure crosses the wire as a string, so no client can turn a Decimal into a float on the
way to a screen -- the same rule the rest of the API keeps. Ratios are rendered here rather than
in the page, so two clients cannot disagree about what "1.64%" was a share of.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from zaco.api.render import money, number, optional_money
from zaco.api.schemas import (
    GroupTotalOut,
    HeadlineOut,
    ProductLineOut,
    ReportOut,
    TakeOnOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.db.base import get_db
from zaco.db.models import User
from zaco.reporting.reports import Band, ProductLine, Report, TakeOn, Total, period_named
from zaco.resolve import service

router = APIRouter(prefix="/api/reports", tags=["reports"])

may_view = requires(Permission.VIEW_REPORTS)

#: How a band is described where it is shown. The letters alone say nothing to somebody who has
#: not read the code.
BANDS: dict[str, str] = {
    Band.A.value: "The vital few -- together the first 80% of the takings",
    Band.B.value: "The next 15%",
    Band.C.value: "The long tail -- the last 5% between them",
    Band.UNBANDED.value: "Too few lines to separate a vital few from a long tail",
}


def _percent(value: Decimal | None) -> str | None:
    """A ratio as a percentage to two places. Display only -- never a figure anything is settled
    against, which is why rounding it here is safe where rounding a Nett share is not."""
    if value is None:
        return None
    return f"{(value * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def _line(line: ProductLine) -> ProductLineOut:
    return ProductLineOut(
        product=line.product,
        short_code=line.short_code,
        band=line.band.value,
        share_of_value=_percent(line.share_of_value) or "-",
        value=money(line.value),
        cartons_sold=number(line.cartons.sold),
        cartons_returned=(None if line.cartons.returned is None else number(line.cartons.returned)),
        cartons_net=number(line.cartons.net),
        price_per_carton=optional_money(line.price_per_carton),
        cartons_sent=None if line.cartons_sent is None else number(line.cartons_sent),
        sell_through=_percent(line.sell_through),
        days_on_market=line.days_on_market,
        consignments=line.consignments,
    )


def _total(total: Total) -> GroupTotalOut:
    return GroupTotalOut(
        name=total.name,
        cartons_net=number(total.cartons_net),
        value=money(total.value),
        consignments=total.consignments,
    )


def _take_on(item: TakeOn) -> TakeOnOut:
    return TakeOnOut(
        product=item.product,
        per_carton_sent=optional_money(item.per_carton_sent),
        cartons_sent=None if item.cartons_sent is None else number(item.cartons_sent),
        sell_through=_percent(item.sell_through),
        return_rate=_percent(item.return_rate),
        value=money(item.value),
        earned=optional_money(item.earned),
        note=item.note,
    )


def _report(built: Report, coverage: str) -> ReportOut:
    head = built.headline
    return ReportOut(
        period=built.period.label,
        is_all_time=built.period.is_all_time,
        start=built.period.start,
        end=built.period.end,
        headline=HeadlineOut(
            cartons_sold=number(head.cartons_sold),
            cartons_returned=(
                None if head.cartons_returned is None else number(head.cartons_returned)
            ),
            cartons_net=number(head.cartons_net),
            takings=money(head.takings),
            not_yet_paid=money(head.not_yet_paid),
            price_per_carton=optional_money(head.price_per_carton),
            return_rate=_percent(head.return_rate),
            return_rate_basis=head.return_rate_basis,
            consignments_that_cannot_report_returns=head.consignments_that_cannot_report_returns,
            docket_count=head.docket_count,
        ),
        products=[_line(x) for x in built.products],
        markets=[_total(x) for x in built.markets],
        agents=[_total(x) for x in built.agents],
        take_on=[_take_on(x) for x in built.take_on],
        take_on_basis=built.take_on_basis,
        commission_coverage=coverage,
        caveats=built.caveats,
        bands=BANDS,
    )


@router.get("", response_model=ReportOut)
def reports(
    period: str = Query("all", description="all, month or week"),
    on: date | None = Query(None, description="The day a month or week sits around"),
    db: Session = Depends(get_db),
    _: User = Depends(may_view),
) -> ReportOut:
    """Section 9 over all time, a month or a week.

    An unknown period is refused rather than quietly treated as all time -- a report labelled
    with a window it did not apply is worse than no report.
    """
    try:
        window = period_named(period, on or date.today())
    except ValueError as refusal:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(refusal)) from refusal

    built, coverage = service.report(db, window)
    return _report(built, coverage)
