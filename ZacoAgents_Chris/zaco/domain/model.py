"""The grain, and the counting rules that hang off it.

Section 3: **one workbook row is one combination of delivery, product and account sale.**

A consignment does not sell in one go. It sits on the floor and is sold off over days, and every
few days the agent closes an account sale covering whatever went in that run. So one consignment
commonly spans several account sales, and one account sale commonly settles several consignments.

Two consequences are enforced structurally here rather than left to callers to remember:

* A consignment cannot be one row, because its stock position changes between account sales.
* Any quantity belonging to the **delivery** rather than to the account sale -- what was sent,
  how long it took to clear -- must be counted **once per consignment**, never once per row.

The second is the one that quietly inflates every carton figure in the system if it is got
wrong, so `qty_sent` lives on `Consignment` and is deliberately absent from `Row`. Summing it
across rows is not merely discouraged; there is nothing on a row to sum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from zaco.domain.products import ProductIdentity
from zaco.ingest.problems import Problem
from zaco.ingest.records import DocumentKind

ZERO = Decimal("0")


class Evidence(StrEnum):
    """Where a figure came from, because it governs what may be said about it."""

    SALES = "sales"
    """Docket-level detail: Daily Sales Detail or a Consignment Report."""

    PAYMENT = "payment"
    """Payment side only: totals per account sale, with no dockets behind them."""

    STATEMENT = "statement"
    """An account sales statement: sale lines and a nett, but no docket numbers."""


@dataclass(frozen=True)
class Cartons:
    """What sold, what came back, and the net -- with absent kept apart from zero.

    Section 6: "The sale and the return both happened. Keep both as their own figures, held
    positive, so that a month which sold a lot and had some come back can be told apart from one
    that quietly sold less." And: "Absent is not zero. Where a source could not report returns at
    all, the figure is absent."

    So `returned` is `None` when the evidence is payment-side, which reports a sold quantity and
    cannot express a return. Zero means the source showed returns and there were none.
    """

    sold: Decimal
    returned: Decimal | None

    @property
    def net(self) -> Decimal:
        """What column J of the workbook needs, because K = H - J only balances on the net."""
        return self.sold - (self.returned or ZERO)

    @property
    def returns_reportable(self) -> bool:
        return self.returned is not None

    @classmethod
    def from_quantities(cls, quantities: list[Decimal], reportable: bool = True) -> Cartons:
        sold = sum((q for q in quantities if q > 0), ZERO)
        returned = -sum((q for q in quantities if q < 0), ZERO)
        return cls(sold=sold, returned=returned if reportable else None)

    @classmethod
    def unreported_returns(cls, sold: Decimal) -> Cartons:
        return cls(sold=sold, returned=None)


@dataclass
class DocketFact:
    """One sale off the floor, with where it was read from."""

    docket_number: str
    date_sold: date | None
    quantity: Decimal | None
    price: Decimal | None
    value: Decimal | None
    account_sale: str | None
    date_delivered: date | None = None
    date_paid: date | None = None
    source_kind: DocumentKind | None = None
    source_name: str | None = None

    @property
    def is_return(self) -> bool:
        return self.quantity is not None and self.quantity < 0

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """What makes this *the same sale*, seen through any document.

        Composite, because docket numbers are **not unique**: `PRE*B6E01C39001*06Z` appears in
        both supplied rounds for consignment `118312006Z` with a different date, quantity and
        account sale. Those are two genuine sales, so deduping on the docket number alone
        deletes a real R900 sale.

        The account sale is deliberately **not** part of it. A Consignment Report describes the
        same sales as a Daily Sales Detail but cannot name the account sale a docket was paid
        under -- so including it would make one sale look like two, and double every carton
        figure for any consignment covered by both documents. It is an attribute one document
        carries and another does not, not part of what the sale *is*.
        """
        return (
            self.docket_number,
            str(self.date_sold or ""),
            str(self.quantity if self.quantity is not None else ""),
            str(self.value if self.value is not None else ""),
        )

    @property
    def richness(self) -> int:
        """How much this telling of the sale carries. A richer one supersedes a poorer one."""
        return sum((self.account_sale is not None, self.date_paid is not None))


@dataclass
class Consignment:
    """One product within one delivery, sitting on the floor until it clears.

    `qty_sent` belongs here and **not** on `Row`: it is a property of the delivery, so counting
    it per row would multiply it by however many account sales the consignment happened to span.
    """

    consignment_id: str | None
    delivery_id: str | None
    product: ProductIdentity
    supplier_ref: str | None = None
    market: str | None = None
    agent: str | None = None
    qty_sent: Decimal | None = None
    qty_available: Decimal | None = None
    dockets: list[DocketFact] = field(default_factory=list)
    evidence: set[Evidence] = field(default_factory=set)

    @property
    def is_identifiable(self) -> bool:
        """Section 6: a consignment that cannot be identified cannot be tracked.

        Its rows are left alone rather than pooled with unrelated ones, so opening stock is never
        carried across two consignments that merely look similar.
        """
        return bool(self.consignment_id)

    @property
    def account_sales(self) -> list[str]:
        seen = {d.account_sale for d in self.dockets if d.account_sale}
        return sorted(seen)

    @property
    def unpaid_dockets(self) -> list[DocketFact]:
        """Sold, but not yet named by any account sale, so no row can be written for them."""
        return [d for d in self.dockets if not d.account_sale]

    @property
    def cartons(self) -> Cartons:
        reportable = bool(self.evidence & {Evidence.SALES, Evidence.STATEMENT})
        return Cartons.from_quantities(
            [d.quantity for d in self.dockets if d.quantity is not None], reportable
        )

    @property
    def value(self) -> Decimal:
        """Gross: cartons sold times unit price. The Nett arrives from the payment side."""
        return sum((d.value for d in self.dockets if d.value is not None), ZERO)

    @property
    def first_delivered(self) -> date | None:
        dates = [d.date_delivered for d in self.dockets if d.date_delivered]
        return min(dates) if dates else None

    @property
    def last_sold(self) -> date | None:
        dates = [d.date_sold for d in self.dockets if d.date_sold]
        return max(dates) if dates else None

    @property
    def days_on_market(self) -> int | None:
        """Belongs to the delivery, so it is counted once per consignment (section 9)."""
        if self.first_delivered is None or self.last_sold is None:
            return None
        return (self.last_sold - self.first_delivered).days


@dataclass
class Delivery:
    """One load of produce leaving Zaco for a market.

    `dn` is Zaco's own delivery note number, workbook column A. No report carries it, and one DN
    can cover several market deliveries, so it cannot be derived even in principle (section 7).
    It stays `None` until Phase 3 captures it.
    """

    delivery_id: str | None
    supplier_ref: str | None = None
    market: str | None = None
    agent: str | None = None
    consignments: list[Consignment] = field(default_factory=list)
    dn: str | None = None

    @property
    def producer_code(self) -> str | None:
        """The number before the asterisk. Zaco's own is 20026."""
        if not self.supplier_ref or "*" not in self.supplier_ref:
            return None
        return self.supplier_ref.split("*", 1)[0]

    @property
    def reference_half(self) -> str | None:
        """The half after the asterisk. Sometimes the DN, and often not (section 3)."""
        if not self.supplier_ref or "*" not in self.supplier_ref:
            return None
        return self.supplier_ref.split("*", 1)[1]

    @property
    def qty_sent(self) -> Decimal:
        """Summed once per consignment, which is the whole point of it living there."""
        return sum((c.qty_sent for c in self.consignments if c.qty_sent is not None), ZERO)


@dataclass
class Row:
    """One prospective workbook row: delivery x product x account sale.

    Carries no `qty_sent` and no `days_on_market`. Those belong to the delivery, and a row is not
    where they can be counted without multiplying them.
    """

    delivery_id: str | None
    consignment_id: str | None
    product: ProductIdentity
    account_sale: str
    market: str | None
    agent: str | None
    dockets: list[DocketFact] = field(default_factory=list)
    evidence: set[Evidence] = field(default_factory=set)

    @property
    def cartons(self) -> Cartons:
        reportable = bool(self.evidence & {Evidence.SALES, Evidence.STATEMENT})
        return Cartons.from_quantities(
            [d.quantity for d in self.dockets if d.quantity is not None], reportable
        )

    @property
    def value(self) -> Decimal:
        return sum((d.value for d in self.dockets if d.value is not None), ZERO)

    @property
    def price(self) -> Decimal | None:
        """Priced over the **net**, so that `J * L` recovers the money (section 6)."""
        net = self.cartons.net
        return None if net == ZERO else (self.value / net)

    @property
    def earliest_date(self) -> date | None:
        dates = [d.date_sold for d in self.dockets if d.date_sold]
        dates += [d.date_delivered for d in self.dockets if d.date_delivered]
        return min(dates) if dates else None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.delivery_id or "", self.product.key, self.account_sale)


@dataclass
class Disagreement:
    """Two documents describing one record differently (D12).

    The *record* is held back, never the file. Refusing a whole export because one account sale
    conflicts throws away every record in it that was fine, and the operator then has no way to
    proceed except to trust the one they happen to upload second.
    """

    subject_kind: str
    subject_key: str
    description: str
    differences: list[tuple[str, str, str]] = field(default_factory=list)
    """(what differs, what the first document said, what the second said)."""

    sources: tuple[str, str] = ("", "")


@dataclass
class SkippedDuplicate:
    """A record seen twice with every figure identical, so it was counted once.

    Recorded rather than logged. D12 is explicit that the skip must be *visible*: a silent skip
    and a lost record look exactly alike from the outside, and only one of them is fine.
    """

    subject_kind: str
    subject_key: str
    description: str
    source: str


@dataclass
class AccountSale:
    """A payment run the agent closed off. The workbook's STM No, column E."""

    number: str
    market: str | None = None
    agent: str | None = None
    date_paid: date | None = None
    nett: Decimal | None = None
    gross: Decimal | None = None
    total_deductions: Decimal | None = None
    deduction_vat: Decimal | None = None
    has_commodity_breakdown: bool = True
    sales_value: Decimal | None = None
    """What the payment side says was sold under it, where it says."""

    source_name: str | None = None
    """Which document this was first read from, so a disagreement can name both sides."""

    also_known_as: list[str] = field(default_factory=list)
    """Other references the same payment run was written under, kept so nothing is lost."""

    @property
    def display_number(self) -> str:
        """D7: the bare number where one exists, the full reference where it does not.

        `PRE*BT*382405` shows as `382405`, matching the operator's existing rows. Subtropico's
        `JOH*SUB*5644200/1` has no numeric form and keeps its suffix, because `5640001/1` and
        `5640001/2` are two separate April payment runs worth R5,100 and R3,230.
        """
        tail = self.number.rsplit("*", 1)[-1] if "*" in self.number else self.number
        return tail if tail.isdigit() else self.number

    @property
    def deduction_share(self) -> Decimal | None:
        """How much of the sale the agent kept. Section 10 judges this against Zaco's own normal."""
        if self.gross is None or self.gross == ZERO or self.nett is None:
            return None
        return (self.gross - self.nett) / self.gross


@dataclass
class StagedRound:
    """Everything one round of documents amounts to, before anything is written down."""

    deliveries: dict[str, Delivery] = field(default_factory=dict)
    account_sales: dict[str, AccountSale] = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    disagreements: list[Disagreement] = field(default_factory=list)
    skipped: list[SkippedDuplicate] = field(default_factory=list)
    products_seen: list[str] = field(default_factory=list)
    """Every product name this round's documents actually contained, as they wrote it.

    Product identity is global -- a name learned in one round is still that product in the next
    -- but the *questions* are not. This is what lets the queue ask only about the products in
    front of it while still resolving codes learned anywhere.
    """

    proven_links: list[tuple[str, str, str]] = field(default_factory=list)
    """(sales name, statement name, the evidence) for links an account sale proved."""

    carried_account_sales: set[str] = field(default_factory=set)
    """Account sales an earlier round already settled.

    Held so this round can be compared against them without their absence from *this* round's
    sales documents being reported as "paid, and nothing accounts for it" -- something already
    accounted for last month is not a loose end.
    """

    @property
    def consignments(self) -> list[Consignment]:
        return [c for d in self.deliveries.values() for c in d.consignments]

    @property
    def cartons_sent(self) -> Decimal:
        """Once per consignment. Summing `Row` instead would multiply this by the number of
        account sales each consignment spanned."""
        return sum((c.qty_sent for c in self.consignments if c.qty_sent is not None), ZERO)

    @property
    def cartons(self) -> Cartons:
        sold = sum((r.cartons.sold for r in self.rows), ZERO)
        reportable = [r.cartons for r in self.rows if r.cartons.returns_reportable]
        returned = sum((c.returned or ZERO for c in reportable), ZERO) if reportable else None
        return Cartons(sold=sold, returned=returned)

    @property
    def value(self) -> Decimal:
        return sum((r.value for r in self.rows), ZERO)

    @property
    def unpaid_dockets(self) -> list[tuple[Consignment, DocketFact]]:
        """Sold, but in no payment run yet. A row is delivery x product x account sale, so these
        cannot form one -- and section 8 requires the state be distinguishable."""
        return [(c, d) for c in self.consignments for d in c.unpaid_dockets]

    @property
    def unidentifiable_consignments(self) -> list[Consignment]:
        return [c for c in self.consignments if not c.is_identifiable]

    @property
    def docket_identities(self) -> set[tuple[str, str, str, str]]:
        """Every sale this round counted, so a later round can tell it has seen one before."""
        return {d.identity for c in self.consignments for d in c.dockets}
