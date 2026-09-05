"""Has the agent treated the money normally (section 10).

Zaco is not on the floor. The only leverage is what the reports say, so this module is as much
about stating what cannot be checked as about checking anything.

**Two questions are answerable, and one is not.** All three are returned together, from here,
as data. The not-answerable one is `NOT_ANSWERABLE` below and it is part of the result rather
than a line of prose in a template, because section 10 requires that conclusion to "travel with
the figures": a panel that reports only what it can check reads as a clean bill of health on the
thing it is blind to, and a statement that lives in a page can be lost the next time the page is
redesigned. It cannot be dropped from here without deleting a field.

**The normal is this business's own, and it is a median.** Section 10 asks for the comparison to
be against "what this business itself normally pays rather than against an outside benchmark".
Two further choices follow from that:

* The normal is taken across **the whole business, not per agent**. An agent judged against their
  own history is their own yardstick, so one who has always kept too much looks perfectly normal
  -- which is precisely the case worth catching.
* It is a **median, not a mean**. A mean is moved by the outlier it is being used to detect. On
  the supplied record the mean share kept is 18.3% and the median is 15.0%; against the mean, an
  account sale that kept 60% is 3.3x normal, and against the median 4x. The mean has already
  begun absorbing the thing it is meant to expose.

**A consignment that is still selling has not failed to sell.** This is the difference between a
figure and an accusation. On the supplied record one consignment of oranges last sold on
2026-06-05, the final day the record knows about, with 120 of 200 cartons still unsold -- and
those 120 are four fifths of everything its agent has not shifted. Counting them as produce that
failed to move would say something false about an agent whose fruit is simply still on the floor.
So a consignment whose last sale falls within `STILL_SELLING_DAYS` of the end of the record is
set aside, counted, and named, rather than judged.

**Nothing here is an accusation.** Section 10: "a high deduction has innocent explanations". So
every flag carries the figures that raised it -- gross, nett, what was kept, what normal would
have been and the difference in rand -- and the panel lists every account sale, flagged or not.
The threshold governs emphasis, never visibility. Hiding the ordinary ones would leave the reader
unable to see how ordinary the ordinary ones are, which is the whole basis for the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from zaco.domain.model import AccountSale, Consignment, StagedRound

ZERO = Decimal("0")

#: How far above the business's own normal a share kept has to sit before it is flagged. Half
#: again as much: on the supplied record the normal is 15%, and the two account sales that sit
#: modestly above it are keeping R5 and R13.70 more than normal on small sales, which a fixed
#: handling charge explains without anything being wrong. A share half again as large has changed
#: in kind rather than in degree.
MATERIALLY_ABOVE = Decimal("1.5")

#: Fewer than this many observations and an agent is not judged at all. Section 10: "Do not judge
#: either on a sample too small to have a normal." Four account sales cannot establish whether an
#: agent's deductions are typical of them, and a ranking built on one or two reads as a finding
#: when it is an artefact of how little there is.
ENOUGH_TO_JUDGE = 5

#: A consignment whose last sale falls within this many days of the last sale anywhere in the
#: record is treated as still selling. If the record ends the day after a consignment last sold,
#: nothing distinguishes "it finished" from "the documents stopped": no time has passed in which
#: it could have sold more. Two days, because the supplied agents close account sales every few
#: days, so a shorter gap is not evidence of anything.
STILL_SELLING_DAYS = 2

#: Section 10's not-answerable conclusion, kept as data so it travels with the figures.
NOT_ANSWERABLE = (
    "Whether the price recorded is the price the fruit actually made cannot be answered from "
    "these reports, and nothing on this panel should be read as saying it can. Every price here "
    "reaches Zaco through the agent's own documents, so comparing them compares the agent with "
    "themselves. Settling it would need what the fruit made on the floor that day for that grade, "
    "and no report Zaco receives carries it."
)

#: What the record does allow to be said about prices, which is less than it looks. Stated because
#: an unqualified "not answerable" invites the reader to supply their own reason for it.
PRICE_EVIDENCE = (
    "The one check the documents do support is whether a price moved between two tellings of the "
    "same product. It has almost no power here: most products in the record sold at a single "
    "price across one to three dockets, so a wrong price stated consistently is indistinguishable "
    "from a right one."
)


def median(values: list[Decimal]) -> Decimal | None:
    """The middle value, or the mean of the middle two. Empty gives nothing, never nought."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


@dataclass(frozen=True)
class Kept:
    """One account sale, and how its deductions compare with the business's own normal."""

    account_sale: str
    agent: str | None
    market: str | None
    gross: Decimal
    nett: Decimal
    kept: Decimal
    share: Decimal
    normal_share: Decimal | None
    date_paid: date | None
    has_commodity_breakdown: bool

    @property
    def normal_kept(self) -> Decimal | None:
        """What would have been kept at the business's normal share of the same gross."""
        return None if self.normal_share is None else self.gross * self.normal_share

    @property
    def excess(self) -> Decimal | None:
        """The rand difference from normal. The figure that says whether this matters."""
        normal = self.normal_kept
        return None if normal is None else self.kept - normal

    @property
    def times_normal(self) -> Decimal | None:
        if self.normal_share is None or self.normal_share == ZERO:
            return None
        return self.share / self.normal_share

    @property
    def is_flagged(self) -> bool:
        multiple = self.times_normal
        return multiple is not None and multiple >= MATERIALLY_ABOVE


@dataclass(frozen=True)
class NeverSold:
    """One agent's share of what Zaco sent them that has not sold, and whether it can be judged."""

    agent: str | None
    cartons_sent: Decimal
    cartons_net: Decimal
    consignments: int
    still_selling: int
    """Consignments set aside as unfinished, so not counted above. Named, never silently dropped."""

    still_selling_cartons: Decimal
    normal_share: Decimal | None

    @property
    def cartons_unsold(self) -> Decimal:
        return self.cartons_sent - self.cartons_net

    @property
    def share(self) -> Decimal | None:
        if self.cartons_sent == ZERO:
            return None
        return self.cartons_unsold / self.cartons_sent

    @property
    def is_judged(self) -> bool:
        return self.consignments >= ENOUGH_TO_JUDGE and self.share is not None

    @property
    def is_flagged(self) -> bool:
        share = self.share
        if not self.is_judged or share is None or self.normal_share in (None, ZERO):
            return False
        assert self.normal_share is not None
        return share / self.normal_share >= MATERIALLY_ABOVE

    @property
    def why_not_judged(self) -> str | None:
        """Section 10 asks for the sample rule; saying nothing would read as a pass."""
        if self.is_judged:
            return None
        if self.share is None:
            return "Nothing recorded as sent, so there is no share to take."
        finished = self.consignments
        if self.still_selling:
            return (
                f"{finished} finished consignment(s) once {self.still_selling} still selling "
                f"({self.still_selling_cartons:g} cartons) are set aside -- too few to have a "
                f"normal, so this agent is not judged on what did not sell."
            )
        return f"{finished} consignment(s) is too small a sample to have a normal."


@dataclass
class Conduct:
    """Everything section 10 can and cannot say, in one piece so none of it travels alone."""

    normal_share_kept: Decimal | None
    normal_never_sold: Decimal | None
    kept: list[Kept] = field(default_factory=list)
    never_sold: list[NeverSold] = field(default_factory=list)
    not_answerable: str = NOT_ANSWERABLE
    price_evidence: str = PRICE_EVIDENCE
    caveats: list[str] = field(default_factory=list)

    @property
    def flagged_kept(self) -> list[Kept]:
        return [k for k in self.kept if k.is_flagged]

    @property
    def flagged_never_sold(self) -> list[NeverSold]:
        return [n for n in self.never_sold if n.is_flagged]

    @property
    def has_a_normal(self) -> bool:
        return self.normal_share_kept is not None


def _still_selling(consignments: list[Consignment]) -> tuple[set[int], date | None]:
    """Which consignments the record simply stops in the middle of, by identity.

    Keyed on `id()` rather than the consignment id because an unidentifiable consignment has none
    and must still be set aside; two of them are not the same one merely for both being nameless.
    """
    sold = [c.last_sold for c in consignments if c.last_sold]
    if not sold:
        return set(), None
    ends = max(sold)
    cutoff = ends - timedelta(days=STILL_SELLING_DAYS)
    return {id(c) for c in consignments if c.last_sold and c.last_sold > cutoff}, ends


def _kept(sales: list[AccountSale], normal: Decimal | None) -> list[Kept]:
    lines = []
    for sale in sales:
        share = sale.deduction_share
        if share is None or sale.gross is None or sale.nett is None:
            continue
        lines.append(
            Kept(
                account_sale=sale.display_number,
                agent=sale.agent,
                market=sale.market,
                gross=sale.gross,
                nett=sale.nett,
                kept=sale.gross - sale.nett,
                share=share,
                normal_share=normal,
                date_paid=sale.date_paid,
                has_commodity_breakdown=sale.has_commodity_breakdown,
            )
        )
    # Worst first by rand, not by share: a share is what raises the question and money is what
    # decides whether it is worth asking. Ties broken on the account sale so the order is stable.
    return sorted(lines, key=lambda k: (-(k.excess or ZERO), k.account_sale))


def _never_sold(
    consignments: list[Consignment], open_ones: set[int], normal: Decimal | None
) -> list[NeverSold]:
    agents = sorted({c.agent or "" for c in consignments})
    lines = []
    for name in agents:
        mine = [c for c in consignments if (c.agent or "") == name]
        finished = [c for c in mine if id(c) not in open_ones and c.qty_sent is not None]
        open_mine = [c for c in mine if id(c) in open_ones]
        lines.append(
            NeverSold(
                agent=name or None,
                cartons_sent=sum((c.qty_sent or ZERO for c in finished), ZERO),
                cartons_net=sum((c.cartons.net for c in finished), ZERO),
                consignments=len(finished),
                still_selling=len(open_mine),
                still_selling_cartons=sum(
                    ((c.qty_sent or ZERO) - c.cartons.net for c in open_mine), ZERO
                ),
                normal_share=normal,
            )
        )
    return sorted(lines, key=lambda n: (not n.is_judged, -(n.share or ZERO), n.agent or ""))


def build(record: StagedRound) -> Conduct:
    """Section 10 over the whole recorded history.

    Both normals are taken from the same record being judged, which is what "this business
    itself" means -- and it is why a record with one agent in it produces a normal that agent
    defines. That is stated in the caveats rather than worked around, because the alternative is
    an outside benchmark, which section 10 rules out.
    """
    sales = sorted(record.account_sales.values(), key=lambda s: s.number)
    shares = [s.deduction_share for s in sales if s.deduction_share is not None]
    normal_kept = median([s for s in shares if s is not None])

    consignments = record.consignments
    open_ones, _ = _still_selling(consignments)
    finished = [c for c in consignments if id(c) not in open_ones and c.qty_sent is not None]
    sent = sum((c.qty_sent or ZERO for c in finished), ZERO)
    net = sum((c.cartons.net for c in finished), ZERO)
    normal_unsold = None if sent == ZERO else (sent - net) / sent

    conduct = Conduct(
        normal_share_kept=normal_kept,
        normal_never_sold=normal_unsold,
        kept=_kept(sales, normal_kept),
        never_sold=_never_sold(consignments, open_ones, normal_unsold),
    )
    conduct.caveats = _caveats(conduct, sales, open_ones)
    return conduct


def _caveats(conduct: Conduct, sales: list[AccountSale], open_ones: set[int]) -> list[str]:
    """What would otherwise have to be inferred from the absence of a flag."""
    caveats: list[str] = []
    if conduct.normal_share_kept is None:
        caveats.append(
            "Nothing in the record states both a gross and a nett, so this business has no "
            "normal to compare against and nothing here is judged."
        )
    elif len(sales) < ENOUGH_TO_JUDGE:
        caveats.append(
            f"The normal is taken from {len(sales)} account sale(s), which is too few to be a "
            f"normal. It is shown so the figures can be read, not so they can be judged."
        )

    agents = {s.agent for s in sales if s.agent}
    if len(agents) == 1:
        caveats.append(
            f"Every account sale with an agent on it is {next(iter(agents))}, so that agent "
            f"defines the normal it is being measured against and can only ever look typical."
        )

    unattributed = [s for s in sales if not s.agent]
    if unattributed:
        caveats.append(
            f"{len(unattributed)} account sale(s) name no agent, so their deductions count "
            f"towards the normal but cannot be attributed to anybody: "
            f"{', '.join(sorted(s.display_number for s in unattributed))}."
        )

    blind = [s for s in sales if not s.has_commodity_breakdown]
    if blind:
        caveats.append(
            f"{len(blind)} account sale(s) state a gross and a nett with no lines behind them, so "
            f"the share kept is known but what it was kept for is not: "
            f"{', '.join(sorted(s.display_number for s in blind))}."
        )

    if open_ones:
        caveats.append(
            f"{len(open_ones)} consignment(s) last sold within {STILL_SELLING_DAYS} day(s) of the "
            f"end of the record and are treated as still selling, so their unsold cartons are not "
            f"counted as produce that failed to move."
        )
    return caveats
