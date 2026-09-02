"""What a reader produces.

These are *what the document said*, not the domain model. Phase 2 turns them into deliveries,
consignments and workbook rows; keeping the two apart means a reader can be judged on whether it
read the page correctly, without any question of interpretation getting mixed in.

Two rules hold throughout:

* Anything the document did not carry is `None`, never a zero and never a default. Section 6 is
  explicit that absent is not zero -- a consignment report cannot express returns at all, and
  that has to stay distinguishable from a report that showed no returns.
* Where a document prints its own total, it is kept as `stated_*` alongside what the lines add
  up to. Reconciling the two is how a reader notices it has misread a page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from zaco.ingest.problems import Problem


class DocumentKind(StrEnum):
    DAILY_SALES_DETAIL = "daily_sales_detail"
    CONSIGNMENT_REPORT = "consignment_report"
    ACCOUNT_SALES_STATEMENT = "account_sales_statement"
    PAYMENT_DETAILS = "payment_details"
    NETT_PAYMENT_ADJUSTMENTS = "nett_payment_adjustments"


TITLES: dict[DocumentKind, str] = {
    DocumentKind.DAILY_SALES_DETAIL: "Daily Sales Detail",
    DocumentKind.CONSIGNMENT_REPORT: "Consignment Report",
    DocumentKind.ACCOUNT_SALES_STATEMENT: "Account sales statement",
    DocumentKind.PAYMENT_DETAILS: "Payment Details",
    DocumentKind.NETT_PAYMENT_ADJUSTMENTS: "Nett Payment Adjustments",
}


@dataclass
class DocumentScope:
    """What the export says it covers.

    Section 4: "A report states its own scope. If an export was narrowed to one market or one
    agent rather than run for everything, the system must say so, because the person who ran it
    usually believes they took the lot."

    Three states, not two. `ALL` is a stated full scope. A named market or agent is a stated
    narrow scope. A *blank* field -- which is what `ConsignmentReports_20260525-20260531.txt`
    actually contains -- states nothing at all, and is not the same as ALL.
    """

    market: str | None = None
    agent: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    run_at: datetime | None = None
    market_stated: bool = False
    agent_stated: bool = False

    @property
    def is_narrowed(self) -> bool:
        return bool(self.market) or bool(self.agent)

    @property
    def is_unstated(self) -> bool:
        return not self.market_stated and not self.agent_stated

    def describe(self) -> str:
        if self.is_narrowed:
            parts = [p for p in (self.market, self.agent) if p]
            return "Narrowed to " + " / ".join(parts)
        if self.is_unstated:
            return "Scope not stated"
        return "All markets and agents"


@dataclass
class Docket:
    """One sale off the floor. A negative quantity is a return (section 6)."""

    docket_number: str
    date_sold: date | None
    quantity: Decimal | None
    price: Decimal | None
    value: Decimal | None
    date_delivered: date | None = None
    date_paid: date | None = None
    payment_reference: str | None = None
    market_average: Decimal | None = None
    line_number: int | None = None

    @property
    def is_return(self) -> bool:
        return self.quantity is not None and self.quantity < 0


@dataclass
class ConsignmentBlock:
    """One product within one delivery, with whatever dockets the export carried for it."""

    consignment_id: str | None
    delivery_id: str | None
    product_name: str | None
    supplier_ref: str | None = None
    qty_sent: Decimal | None = None
    qty_amended_to: Decimal | None = None
    qty_available: Decimal | None = None
    market: str | None = None
    agent: str | None = None
    dockets: list[Docket] = field(default_factory=list)
    stated_total_quantity: Decimal | None = None
    stated_total_value: Decimal | None = None
    line_number: int | None = None

    @property
    def total_quantity(self) -> Decimal:
        return sum((d.quantity for d in self.dockets if d.quantity is not None), Decimal(0))

    @property
    def total_value(self) -> Decimal:
        return sum((d.value for d in self.dockets if d.value is not None), Decimal(0))


@dataclass
class Deduction:
    """One printed line of a statement's deductions table.

    The name matters as much as the amount: section 6 requires a deduction named for a fruit to
    land only on that fruit's rows, so `PLUMS LEVY` cannot be treated as a general cost.
    """

    name: str
    amount: Decimal | None
    vat: Decimal | None
    total: Decimal | None
    line_number: int | None = None


@dataclass
class StatementProduct:
    """One product block within an account sales statement."""

    product_name: str | None
    market_grn: str | None = None
    quantity_received: Decimal | None = None
    quantity_brought_forward: Decimal | None = None
    quantity_outstanding: Decimal | None = None
    agent_commission_percent: Decimal | None = None
    salesman: str | None = None
    dockets: list[Docket] = field(default_factory=list)
    stated_total_quantity: Decimal | None = None
    stated_total_value: Decimal | None = None
    line_number: int | None = None

    @property
    def total_value(self) -> Decimal:
        return sum((d.value for d in self.dockets if d.value is not None), Decimal(0))


@dataclass
class AccountSalesStatement:
    """One payment run the agent closed off, with the Nett stated once for the whole statement."""

    account_sale_number: str | None
    statement_date: date | None = None
    producer_code: str | None = None
    producer_name: str | None = None
    agent_delivery_note_number: str | None = None
    """The agent's own number, printed as `DELIVERY NOTE NO`. It is NOT Zaco's DN.

    It sits in the agent's 203xxx series, the same series as the payment reports' FMS IDs, while
    Zaco's delivery notes are 14xxx. Reading this into workbook column A produces a book that
    looks finished and is wrong in every row. Carried here so the system can show the operator
    what the page said, and refuse to use it.
    """
    reference_number: str | None = None
    date_received: date | None = None
    previous_account_sale_number: str | None = None
    products: list[StatementProduct] = field(default_factory=list)
    deductions: list[Deduction] = field(default_factory=list)
    gross_amount: Decimal | None = None
    nett_amount: Decimal | None = None
    vat_output_collected: Decimal | None = None
    total_sold: Decimal | None = None
    is_final_payment: bool = False
    line_number: int | None = None


@dataclass
class CommodityLine:
    """One commodity on a payment record: what was delivered, what sold, and its sales total."""

    commodity: str | None
    delivered: Decimal | None
    sold: Decimal | None
    sales_total: Decimal | None
    line_number_label: str | None = None
    supplier_ref: str | None = None
    line_number: int | None = None


@dataclass
class PaymentRecord:
    """One account sale as the payment side reports it: nett, deductions, VAT and gross."""

    account_sale_number: str | None
    fms_id: str | None = None
    supplier_ref: str | None = None
    date_paid: date | None = None
    nett_payment: Decimal | None = None
    total_deductions: Decimal | None = None
    deduction_vat: Decimal | None = None
    gross_payment: Decimal | None = None
    payment_reference: str | None = None
    market: str | None = None
    agent: str | None = None
    commodities: list[CommodityLine] = field(default_factory=list)
    stated_total_sales: Decimal | None = None
    line_number: int | None = None

    @property
    def has_commodity_breakdown(self) -> bool:
        """False for AccSale 382999, which carries a gross and a nett and nothing else.

        Section 8: such a record can never reconcile, and must be reported rather than letting
        its money vanish.
        """
        return bool(self.commodities)


@dataclass
class NettAdjustment:
    """One line of a Nett Payment Adjustments report: gross and nett, no product or quantity."""

    account_sale_number: str | None
    supplier_refs: list[str] = field(default_factory=list)
    """Plural because `20026*14705 & 14706` is one payment against two references."""
    date_paid: date | None = None
    gross_payment: Decimal | None = None
    total_deductions: Decimal | None = None
    deduction_vat: Decimal | None = None
    nett_payment: Decimal | None = None
    calculated_nett_adjustment: Decimal | None = None
    nett_adjustment: Decimal | None = None
    market: str | None = None
    agent: str | None = None
    line_number: int | None = None


@dataclass
class ParseResult:
    """Everything one document yielded, plus everything the reader could not make sense of."""

    kind: DocumentKind
    scope: DocumentScope
    problems: list[Problem] = field(default_factory=list)
    consignments: list[ConsignmentBlock] = field(default_factory=list)
    statements: list[AccountSalesStatement] = field(default_factory=list)
    payments: list[PaymentRecord] = field(default_factory=list)
    adjustments: list[NettAdjustment] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return (
            len(self.consignments)
            + len(self.statements)
            + len(self.payments)
            + len(self.adjustments)
        )

    @property
    def docket_count(self) -> int:
        from_consignments = sum(len(c.dockets) for c in self.consignments)
        from_statements = sum(len(p.dockets) for s in self.statements for p in s.products)
        return from_consignments + from_statements
