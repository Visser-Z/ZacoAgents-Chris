"""Has the agent treated the money normally (section 10).

One endpoint returning one object, because section 10 requires the not-answerable conclusion to
travel with the figures. Splitting the checks and the caveat across two calls would let a client
fetch the reassuring half on its own, which is the failure the requirement is written to prevent.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from zaco.api.render import money, number, optional_money
from zaco.api.schemas import ConductOut, KeptOut, NeverSoldOut
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.conduct.conduct import Conduct, Kept, NeverSold
from zaco.db.base import get_db
from zaco.db.models import User
from zaco.resolve import service

router = APIRouter(prefix="/api/conduct", tags=["conduct"])

may_view = requires(Permission.VIEW_REPORTS)


def _percent(value: Decimal | None) -> str | None:
    """Display only. Never a figure anything is settled against."""
    if value is None:
        return None
    return f"{(value * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def _multiple(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}x"


def _kept(line: Kept) -> KeptOut:
    return KeptOut(
        account_sale=line.account_sale,
        agent=line.agent,
        market=line.market,
        gross=money(line.gross),
        nett=money(line.nett),
        kept=money(line.kept),
        share=_percent(line.share) or "-",
        normal_share=_percent(line.normal_share),
        normal_kept=optional_money(line.normal_kept),
        excess=optional_money(line.excess),
        times_normal=_multiple(line.times_normal),
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
        share=_percent(line.share),
        consignments=line.consignments,
        still_selling=line.still_selling,
        still_selling_cartons=number(line.still_selling_cartons),
        is_judged=line.is_judged,
        is_flagged=line.is_flagged,
        why_not_judged=line.why_not_judged,
    )


def _out(found: Conduct) -> ConductOut:
    return ConductOut(
        normal_share_kept=_percent(found.normal_share_kept),
        normal_never_sold=_percent(found.normal_never_sold),
        kept=[_kept(x) for x in found.kept],
        never_sold=[_never_sold(x) for x in found.never_sold],
        not_answerable=found.not_answerable,
        price_evidence=found.price_evidence,
        caveats=found.caveats,
        flagged_count=len(found.flagged_kept) + len(found.flagged_never_sold),
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
