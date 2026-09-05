"""Headline figures, rankings, and what is worth taking on again (section 9).

Four choices are made here that section 9 leaves open. Each is a named constant or a stated
denominator rather than a number inside an expression, because "the signals, the weighting and
the banding are yours to choose and to justify".

**The return rate is returned over sold.** Not over the net. If 100 sold and 20 came back, the
share of sales that reversed is 20%, not the 25% that 20/80 gives. The brief says "be careful
what the rate is a share of", and the denominator is printed next to the rate so nobody has to
guess which was used. Consignments that *cannot report returns at all* are excluded from the
denominator rather than counted as nought -- absent is not zero (section 6) -- and the count of
those is stated.

**Rankings are banded A/B/C on cumulative value**, at 80% and 95%. That is the standard Pareto
split and it fits the supplied record: six of fifteen consignments carry 83% of the value, three
more reach 96%, and the remaining six are the long tail. Bands are computed from the data every
time rather than fixed at "top 5", so a record with a different shape bands differently.

**Sell-through and time on market belong to the delivery**, so they are computed per consignment
over its whole life and never per row. A consignment sells across rounds; a period filter selects
*which* consignments appear, and their figures still cover the whole consignment. Slicing those
two by date would report a line as half-sold because the window closed early.

**What to take on ranks on one ratio, not a blend.** Money per carton *sent* -- not per carton
sold. Section 9 says there is no budget in this and what is scarce is "market slots, handling and
supplier relationships spent on produce that then fails to move", so the denominator has to be
what was committed, not what happened to clear. That single ratio already carries both price and
sell-through, and a weighted blend of three signals would be less traceable, not more: every
score here has to trace to the figures shown beside it, and a ratio does that where a weighting
does not. Sell-through and return rate are shown alongside as context.

Once commission terms exist the same ranking runs on **what Zaco actually earned** per carton
sent, and the report says which of the two it used. Until then it is ranking on a proxy and says
so.

**What sold is counted from dockets, not from workbook rows.** A row is delivery x product x
account sale, so a docket no payment run has named yet forms no row -- and the supplied record
has one, R800 of grapes sold on 2026-06-02. Section 9 asks what *sold*, and a sale is a sale
before the agent closes a run against it, so counting rows would quietly drop it and the takings
would be R800 short of the record while looking complete. What has not been paid for is counted
here and stated separately, because it is money that has not arrived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from zaco.domain.model import Cartons, Consignment, DocketFact, Evidence, StagedRound

ZERO = Decimal("0")

#: Cumulative share of value at which the A band closes, then the B band. Pareto, computed from
#: the record each time rather than a fixed number of lines.
BAND_A = Decimal("0.80")
BAND_B = Decimal("0.95")

#: Below this many consignments a ranking is shown but not banded. Three lines cannot have a
#: "vital few" and a "long tail"; banding them would dress an arbitrary order as a finding.
ENOUGH_TO_BAND = 5


class Band(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    UNBANDED = "unbanded"


@dataclass(frozen=True)
class Period:
    """All time, or a window. `None` on both ends means everything in the record."""

    label: str
    start: date | None = None
    end: date | None = None

    def holds(self, when: date | None) -> bool:
        if when is None:
            return self.start is None and self.end is None
        if self.start is not None and when < self.start:
            return False
        return not (self.end is not None and when > self.end)

    @property
    def is_all_time(self) -> bool:
        return self.start is None and self.end is None


ALL_TIME = Period(label="All time")


@dataclass(frozen=True)
class Headline:
    """Cartons and takings over the period, with the rate's denominator stated."""

    cartons_sold: Decimal
    cartons_returned: Decimal | None
    cartons_net: Decimal
    takings: Decimal
    not_yet_paid: Decimal
    """Of the takings, how much no payment run has named yet. Sold, but not arrived."""

    return_rate: Decimal | None
    return_rate_basis: str
    consignments_that_cannot_report_returns: int
    docket_count: int

    @property
    def price_per_carton(self) -> Decimal | None:
        """What a carton fetched over the period. Over the net, because that is what was kept."""
        return None if self.cartons_net == ZERO else self.takings / self.cartons_net


@dataclass(frozen=True)
class ProductLine:
    """One product over the period, with its delivery-scoped figures marked as such."""

    product: str
    short_code: str | None
    cartons: Cartons
    value: Decimal
    band: Band
    share_of_value: Decimal
    cartons_sent: Decimal | None
    """Delivery-scoped: counted once per consignment, never per row."""

    days_on_market: int | None
    consignments: int

    @property
    def price_per_carton(self) -> Decimal | None:
        return None if self.cartons.net == ZERO else self.value / self.cartons.net

    @property
    def sell_through(self) -> Decimal | None:
        """What share of the cartons sent actually sold. `None` where nothing says what was sent."""
        if self.cartons_sent is None or self.cartons_sent == ZERO:
            return None
        return self.cartons.net / self.cartons_sent


@dataclass(frozen=True)
class Total:
    """A market's or an agent's share of the period."""

    name: str
    cartons_net: Decimal
    value: Decimal
    consignments: int


@dataclass(frozen=True)
class TakeOn:
    """One line, ranked by what it returned for each carton committed to it."""

    product: str
    basis: str
    per_carton_sent: Decimal | None
    cartons_sent: Decimal | None
    sell_through: Decimal | None
    return_rate: Decimal | None
    value: Decimal
    earned: Decimal | None
    note: str = ""


@dataclass
class Report:
    """Everything section 9 asks for over one period, with what it could not answer said."""

    period: Period
    headline: Headline
    products: list[ProductLine] = field(default_factory=list)
    markets: list[Total] = field(default_factory=list)
    agents: list[Total] = field(default_factory=list)
    take_on: list[TakeOn] = field(default_factory=list)
    take_on_basis: str = ""
    caveats: list[str] = field(default_factory=list)
    """Things this report cannot stand behind, carried with the figures rather than in a comment."""


@dataclass(frozen=True)
class Sold:
    """One consignment's sales inside a period, with the consignment behind them.

    Kept together because the figures pull from both: what sold is the dockets, and what was
    sent and how long it took to move are the consignment's and are never sliced by the period.
    """

    consignment: Consignment
    dockets: list[DocketFact]

    @property
    def cartons(self) -> Cartons:
        reportable = bool(self.consignment.evidence & {Evidence.SALES, Evidence.STATEMENT})
        return Cartons.from_quantities(
            [d.quantity for d in self.dockets if d.quantity is not None], reportable
        )

    @property
    def value(self) -> Decimal:
        return sum((d.value for d in self.dockets if d.value is not None), ZERO)

    @property
    def unpaid_value(self) -> Decimal:
        """Sold, with no payment run naming it yet. Real money that has not arrived."""
        return sum(
            (d.value for d in self.dockets if d.value is not None and not d.account_sale), ZERO
        )


def _sold_in(record: StagedRound, period: Period) -> list[Sold]:
    """Every consignment with a sale inside the period, carrying only that period's dockets."""
    found: list[Sold] = []
    seen: set[str] = set()
    for consignment in record.consignments:
        key = consignment.consignment_id or ""
        if key and key in seen:
            continue
        seen.add(key)
        dockets = [d for d in consignment.dockets if period.holds(d.date_sold)]
        if dockets:
            found.append(Sold(consignment=consignment, dockets=dockets))
    return found


def headline(sold: list[Sold]) -> Headline:
    """Cartons and takings, with returns kept apart from a quiet absence (section 6)."""
    cartons_sold = sum((s.cartons.sold for s in sold), ZERO)
    value = sum((s.value for s in sold), ZERO)
    reportable = [s for s in sold if s.cartons.returns_reportable]
    blind = len(sold) - len(reportable)

    returned: Decimal | None = None
    if reportable:
        returned = sum((s.cartons.returned or ZERO for s in reportable), ZERO)

    sold_where_reportable = sum((s.cartons.sold for s in reportable), ZERO)
    rate: Decimal | None = None
    if returned is not None and sold_where_reportable > ZERO:
        rate = returned / sold_where_reportable

    return Headline(
        cartons_sold=cartons_sold,
        cartons_returned=returned,
        cartons_net=cartons_sold - (returned or ZERO),
        takings=value,
        not_yet_paid=sum((s.unpaid_value for s in sold), ZERO),
        return_rate=rate,
        return_rate_basis=(
            "Returned cartons over cartons sold, across the consignments whose source can report "
            "a return at all. One that cannot is left out of both sides rather than counted as "
            "nought."
        ),
        consignments_that_cannot_report_returns=blind,
        docket_count=sum(len(s.dockets) for s in sold),
    )


def _band(shares: list[Decimal], enough: bool) -> list[Band]:
    """A, B or C by cumulative share of value, largest first."""
    if not enough:
        return [Band.UNBANDED] * len(shares)
    bands: list[Band] = []
    running = ZERO
    for share in shares:
        running += share
        if running <= BAND_A:
            bands.append(Band.A)
        elif running <= BAND_B:
            bands.append(Band.B)
        else:
            bands.append(Band.C)
    return bands


def products(sold: list[Sold]) -> list[ProductLine]:
    """Per product, with the delivery-scoped figures taken once per consignment."""
    grouped: dict[str, list[Sold]] = {}
    for s in sold:
        grouped.setdefault(s.consignment.product.key, []).append(s)

    values = {key: sum((s.value for s in ss), ZERO) for key, ss in grouped.items()}
    total = sum(values.values(), ZERO)
    order = sorted(grouped, key=lambda key: (-values[key], key))
    shares = [values[key] / total if total > ZERO else ZERO for key in order]
    bands = _band(shares, len(order) >= ENOUGH_TO_BAND)

    lines: list[ProductLine] = []
    for key, share, band in zip(order, shares, bands, strict=True):
        ss = grouped[key]
        # Delivery-scoped, and absent poisons the total rather than shrinking it (section 6).
        sent: Decimal | None = ZERO
        for s in ss:
            if s.consignment.qty_sent is None:
                sent = None
                break
            sent = (sent or ZERO) + s.consignment.qty_sent
        days = [
            s.consignment.days_on_market for s in ss if s.consignment.days_on_market is not None
        ]
        lines.append(
            ProductLine(
                product=ss[0].consignment.product.display_name,
                short_code=ss[0].consignment.product.short_code,
                cartons=_cartons(ss),
                value=values[key],
                band=band,
                share_of_value=share,
                cartons_sent=sent,
                # The longest, not the mean: how long a line took to move is its tail.
                days_on_market=max(days) if days else None,
                consignments=len(ss),
            )
        )
    return lines


def _cartons(sold: list[Sold]) -> Cartons:
    total = sum((s.cartons.sold for s in sold), ZERO)
    reportable = [s for s in sold if s.cartons.returns_reportable]
    if not reportable:
        return Cartons.unreported_returns(total)
    return Cartons(sold=total, returned=sum((s.cartons.returned or ZERO for s in reportable), ZERO))


def _totals(sold: list[Sold], of: str) -> list[Total]:
    grouped: dict[str, list[Sold]] = {}
    for s in sold:
        grouped.setdefault(getattr(s.consignment, of) or "(not stated)", []).append(s)
    found = [
        Total(
            name=name,
            cartons_net=sum((s.cartons.net for s in ss), ZERO),
            value=sum((s.value for s in ss), ZERO),
            consignments=len(ss),
        )
        for name, ss in grouped.items()
    ]
    return sorted(found, key=lambda t: (-t.value, t.name))


def take_on(
    lines: list[ProductLine], earned: dict[str, Decimal] | None
) -> tuple[list[TakeOn], str]:
    """Which lines are worth accepting again, and which of the two bases was used."""
    realised = bool(earned)
    basis = (
        "What Zaco earned, per carton sent"
        if realised
        else "Gross value, per carton sent -- a proxy, because no commission terms are recorded yet"
    )

    found: list[TakeOn] = []
    for line in lines:
        money = (earned or {}).get(line.product) if realised else line.value
        per_carton = (
            None
            if money is None or line.cartons_sent in (None, ZERO)
            else money / (line.cartons_sent or ZERO)
        )
        found.append(
            TakeOn(
                product=line.product,
                basis=basis,
                per_carton_sent=per_carton,
                cartons_sent=line.cartons_sent,
                sell_through=line.sell_through,
                return_rate=(
                    None
                    if not line.cartons.returns_reportable or line.cartons.sold == ZERO
                    else (line.cartons.returned or ZERO) / line.cartons.sold
                ),
                value=line.value,
                earned=(earned or {}).get(line.product) if realised else None,
                note=(
                    ""
                    if per_carton is not None
                    else "Nothing says how many cartons were sent, so this line cannot be ranked."
                ),
            )
        )
    # Unrankable lines last, and shown rather than dropped: a line missing from a ranking reads
    # as one that did badly.
    return (
        sorted(found, key=lambda t: (t.per_carton_sent is None, -(t.per_carton_sent or ZERO))),
        basis,
    )


def build(
    record: StagedRound, period: Period = ALL_TIME, earned: dict[str, Decimal] | None = None
) -> Report:
    """The whole of section 9 over one period."""
    sold = _sold_in(record, period)
    lines = products(sold)
    ranked, basis = take_on(lines, earned)
    head = headline(sold)

    caveats: list[str] = []
    if head.not_yet_paid > ZERO:
        caveats.append(
            f"R{head.not_yet_paid:,.2f} of what sold is not yet in any payment run. It is in "
            f"the takings, because it sold, and it is not money that has arrived."
        )
    if len(lines) < ENOUGH_TO_BAND:
        caveats.append(
            f"{len(lines)} product line(s) is too few to band. A ranking is shown; the vital few "
            f"and the long tail are not separated, because at this size that would be an "
            f"arbitrary cut dressed as a finding."
        )
    known_days = [line for line in lines if line.days_on_market is not None]
    if known_days and all(line.days_on_market == 1 for line in known_days):
        caveats.append(
            "Every consignment that can report it moved in a day, so time on market separates "
            "nothing here. It is shown, and it is not a signal on this record."
        )
    if head.consignments_that_cannot_report_returns:
        caveats.append(
            f"{head.consignments_that_cannot_report_returns} consignment(s) come from a source "
            f"that cannot express a return at all. They are outside the return rate on both "
            f"sides rather than counted as having had none."
        )
    unknown_sent = [line.product for line in lines if line.cartons_sent is None]
    if unknown_sent:
        caveats.append(
            f"{len(unknown_sent)} product line(s) have no recorded quantity sent, so their "
            f"sell-through is unknown rather than nought and they cannot be ranked on what a "
            f"carton returned: {', '.join(sorted(unknown_sent)[:3])}"
            + ("..." if len(unknown_sent) > 3 else "")
        )
    if not earned:
        caveats.append(
            "No commission terms are recorded, so what to take on is ranked on gross value, "
            "which is the market's money and not Zaco's. It is a proxy for what Zaco would earn, "
            "and the ranking changes once terms exist."
        )

    return Report(
        period=period,
        headline=head,
        products=lines,
        markets=_totals(sold, "market"),
        agents=_totals(sold, "agent"),
        take_on=ranked,
        take_on_basis=basis,
        caveats=caveats,
    )


def month_of(day: date) -> Period:
    """The calendar month containing `day`."""
    start = day.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return Period(label=f"{start:%B %Y}", start=start, end=end)


def week_of(day: date) -> Period:
    """The Monday-to-Sunday week containing `day`.

    Monday because the agents' exports are named for date ranges that start on one, and a week
    that disagreed with the exports would put a docket in a different week from the file it
    arrived in.
    """
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return Period(label=f"Week of {start:%d %b %Y}", start=start, end=end)


def period_named(name: str, on: date | None = None) -> Period:
    """`all`, `month` or `week`, anchored on a day. Anything else is refused rather than guessed."""
    if name == "all":
        return ALL_TIME
    if on is None:
        raise ValueError("A month or a week needs a day to sit around.")
    if name == "month":
        return month_of(on)
    if name == "week":
        return week_of(on)
    raise ValueError(f"{name!r} is not a period this report knows. Use all, month or week.")
