"""Has the agent treated the money normally (section 10).

One endpoint returning one object, because section 10 requires the not-answerable conclusion to
travel with the figures. Splitting the checks and the caveat across two calls would let a client
fetch the reassuring half on its own, which is the failure the requirement is written to prevent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from zaco.api.render import money, multiple, number, optional_money, percent, plot
from zaco.api.schemas import (
    ConductChartOut,
    ConductOut,
    KeptOut,
    KeptPointOut,
    NeverSoldOut,
    ThresholdsOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.conduct.conduct import (
    ENOUGH_TO_JUDGE,
    MATERIALLY_ABOVE,
    STILL_SELLING_DAYS,
    Conduct,
    Kept,
    NeverSold,
)
from zaco.db.base import get_db
from zaco.db.models import User
from zaco.resolve import service

router = APIRouter(prefix="/api/conduct", tags=["conduct"])

may_view = requires(Permission.VIEW_REPORTS)


def _kept(line: Kept) -> KeptOut:
    return KeptOut(
        account_sale=line.account_sale,
        agent=line.agent,
        market=line.market,
        gross=money(line.gross),
        nett=money(line.nett),
        kept=money(line.kept),
        share=percent(line.share) or "-",
        normal_share=percent(line.normal_share),
        normal_kept=optional_money(line.normal_kept),
        excess=optional_money(line.excess),
        times_normal=multiple(line.times_normal),
        is_flagged=line.is_flagged,
        date_paid=line.date_paid,
        has_commodity_breakdown=line.has_commodity_breakdown,
    )


def _never_sold(line: NeverSold) -> NeverSoldOut:
    return NeverSoldOut(
        agent=line.agent,
        cartons_sent=number(line.cartons_sent),
        cartons_net=number(line.cartons_net),
        cartons_unsold=number(line.cartons_unsold),
        share=percent(line.share),
        consignments=line.consignments,
        still_selling=line.still_selling,
        still_selling_cartons=number(line.still_selling_cartons),
        is_judged=line.is_judged,
        is_flagged=line.is_flagged,
        why_not_judged=line.why_not_judged,
    )


def _chart(found: Conduct) -> ConductChartOut:
    """Section 10's one genuinely chartable thing: every share kept against the business's normal.

    The order is the one `_kept` already chose -- worst by rand first -- so the chart and the
    table beside it cannot disagree about which line is the worst.
    """
    return ConductChartOut(
        kept=[
            KeptPointOut(
                label=x.account_sale,
                share=float(x.share),
                excess=plot(x.excess),
                gross=float(x.gross),
                is_flagged=x.is_flagged,
            )
            for x in found.kept
        ],
        normal_share_kept=plot(found.normal_share_kept),
    )


def _out(found: Conduct) -> ConductOut:
    return ConductOut(
        normal_share_kept=percent(found.normal_share_kept),
        normal_never_sold=percent(found.normal_never_sold),
        kept=[_kept(x) for x in found.kept],
        never_sold=[_never_sold(x) for x in found.never_sold],
        not_answerable=found.not_answerable,
        price_evidence=found.price_evidence,
        caveats=found.caveats,
        flagged_count=len(found.flagged_kept) + len(found.flagged_never_sold),
        thresholds=ThresholdsOut(
            materially_above=float(MATERIALLY_ABOVE),
            enough_to_judge=ENOUGH_TO_JUDGE,
            still_selling_days=STILL_SELLING_DAYS,
        ),
        chart=_chart(found),
    )


@router.get("", response_model=ConductOut)
def conduct(
    db: Session = Depends(get_db),
    _: User = Depends(may_view),
) -> ConductOut:
    """Section 10 over the whole record. No period filter, deliberately.

    A normal is what an agent does over time, so slicing it by month would answer a different
    question with the same words -- and would make the sample rule meaningless, since almost every
    window is too small to have a normal.
    """
    return _out(service.conduct(db))
