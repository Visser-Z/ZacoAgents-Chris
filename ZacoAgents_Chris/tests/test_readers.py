"""The readers, against the real exports in `data/`.

Two things are asserted throughout, because they are what section 13 assesses:

* the figures come out right, checked against each document's *own printed totals* -- if a
  reader misread a page, the page itself says so
* what a document does not carry comes out as `None`, never as zero and never as a default
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from zaco.ingest.classifier import read_document
from zaco.ingest.problems import Severity
from zaco.ingest.records import DocumentKind, ParseResult

DATA = Path(__file__).resolve().parent.parent / "data"

DAILY_ROUND_1 = "DailySalesDetail_20260525-20260531.csv"
DAILY_ROUND_2 = "DailySalesDetail_20260601-20260608.csv"
CONSIGNMENTS = "ConsignmentReports_20260525-20260531.txt"
STATEMENT_ONE_PRODUCT = "AccountSales_382405.txt"
STATEMENT_TWO_PRODUCTS = "AccountSales_382900.txt"
PAYMENTS_CSV = "PaymentDetails_20260529-20260602.csv"
PAYMENTS_TXT = "PaymentDetails_20260603-20260608.txt"
PAYMENTS_NARROWED = "PaymentDetails_20260603-20260608_FarmersTrust.csv"
ADJUSTMENTS = "NettPaymentAdjustments_202604.txt"


def read(name: str) -> ParseResult:
    return read_document((DATA / name).read_bytes())


def messages(result: ParseResult, severity: Severity | None = None) -> str:
    items = (
        result.problems
        if severity is None
        else [p for p in result.problems if p.severity is severity]
    )
    return " | ".join(p.message for p in items)


# --- Every supplied file reads, as the kind it actually is -------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        (DAILY_ROUND_1, DocumentKind.DAILY_SALES_DETAIL),
        (DAILY_ROUND_2, DocumentKind.DAILY_SALES_DETAIL),
        (CONSIGNMENTS, DocumentKind.CONSIGNMENT_REPORT),
        (STATEMENT_ONE_PRODUCT, DocumentKind.ACCOUNT_SALES_STATEMENT),
        (STATEMENT_TWO_PRODUCTS, DocumentKind.ACCOUNT_SALES_STATEMENT),
        (PAYMENTS_CSV, DocumentKind.PAYMENT_DETAILS),
        (PAYMENTS_TXT, DocumentKind.PAYMENT_DETAILS),
        (PAYMENTS_NARROWED, DocumentKind.PAYMENT_DETAILS),
        (ADJUSTMENTS, DocumentKind.NETT_PAYMENT_ADJUSTMENTS),
    ],
)
def test_each_supplied_file_reads_as_its_own_kind(name: str, kind: DocumentKind) -> None:
    assert read(name).kind is kind


@pytest.mark.parametrize(
    "name",
    [
        DAILY_ROUND_1,
        DAILY_ROUND_2,
        CONSIGNMENTS,
        STATEMENT_ONE_PRODUCT,
        STATEMENT_TWO_PRODUCTS,
        PAYMENTS_CSV,
        PAYMENTS_TXT,
        PAYMENTS_NARROWED,
        ADJUSTMENTS,
    ],
)
def test_no_supplied_file_produces_an_error(name: str) -> None:
    result = read(name)
    assert not [p for p in result.problems if p.severity is Severity.ERROR], messages(result)


@pytest.mark.parametrize(
    "name",
    [
        DAILY_ROUND_1,
        DAILY_ROUND_2,
        CONSIGNMENTS,
        STATEMENT_ONE_PRODUCT,
        STATEMENT_TWO_PRODUCTS,
        PAYMENTS_CSV,
        PAYMENTS_TXT,
        PAYMENTS_NARROWED,
        ADJUSTMENTS,
    ],
)
def test_no_line_of_any_supplied_file_goes_unrecognised(name: str) -> None:
    """A reader that silently skips what it cannot read is the failure section 13 assesses."""
    result = read(name)
    unread = [p for p in result.problems if "not recognised" in p.message]
    assert not unread, "\n".join(f"line {p.line_number}: {p.line}" for p in unread)


# --- Daily Sales Detail -------------------------------------------------------------------------


def test_round_one_reads_despite_every_line_being_double_quoted() -> None:
    result = read(DAILY_ROUND_1)
    assert len(result.consignments) == 6
    assert result.docket_count == 8


def test_round_two_reads_despite_the_byte_order_mark() -> None:
    result = read(DAILY_ROUND_2)
    assert len(result.consignments) == 9
    assert "byte order mark" in messages(result)


def test_every_consignment_agrees_with_its_own_printed_total() -> None:
    for name in (DAILY_ROUND_1, DAILY_ROUND_2, CONSIGNMENTS):
        for block in read(name).consignments:
            assert block.total_quantity == block.stated_total_quantity, (
                f"{name} {block.consignment_id}"
            )
            assert block.total_value == block.stated_total_value, f"{name} {block.consignment_id}"


def test_a_return_is_kept_negative_and_marked() -> None:
    block = _consignment(read(DAILY_ROUND_1), "118069901Z")
    returns = [d for d in block.dockets if d.is_return]
    assert len(returns) == 1
    assert returns[0].quantity == Decimal("-1")
    assert returns[0].value == Decimal("-200.00")
    # Net of the return, which is what column J of the workbook needs.
    assert block.total_quantity == Decimal("2")


def test_the_market_is_left_empty_when_the_export_prints_destination() -> None:
    # Round 1 labels the Subtropico block `Destination` where the market name belongs. Filling
    # it in from the agent would be inventing a fact the document does not carry.
    grapes = _consignment(read(DAILY_ROUND_1), "118246503Z")
    assert grapes.market is None
    assert grapes.agent == "Subtropico (Jhb)"
    assert "Destination" in messages(read(DAILY_ROUND_1), Severity.WARNING)


def test_a_null_payment_reference_names_no_account_sale() -> None:
    # `PRE*BT*0` with date paid `0000-00-00`. A row is delivery x product x account sale, so
    # this docket cannot form one yet -- and `0` must never become a statement number.
    grapes = _consignment(read(DAILY_ROUND_2), "118246503Z")
    docket = grapes.dockets[0]
    assert docket.payment_reference is None
    assert docket.date_paid is None
    assert "not yet in any payment run" in messages(read(DAILY_ROUND_2))


def test_a_blank_supplier_ref_is_absent_not_a_reference_of_zero() -> None:
    nectarines = _consignment(read(DAILY_ROUND_1), "118170502Z")
    assert nectarines.supplier_ref is None


def test_the_same_docket_number_recurs_across_rounds_with_different_figures() -> None:
    """The trap deduplication has to survive in Phase 3.

    Docket `PRE*B6E01C39001*06Z` appears in both rounds for the same consignment, with a
    different date, quantity and account sale. It is two genuine sales, not one recorded twice,
    so docket number alone cannot be an identity.
    """
    first = _consignment(read(DAILY_ROUND_1), "118312006Z").dockets[0]
    second = _consignment(read(DAILY_ROUND_2), "118312006Z").dockets[0]
    assert first.docket_number == second.docket_number == "PRE*B6E01C39001*06Z"
    assert (first.date_sold, first.quantity) != (second.date_sold, second.quantity)
    assert first.payment_reference != second.payment_reference


# --- Consignment Reports -------------------------------------------------------------------------


def test_the_consignment_report_carries_no_account_sale_at_all() -> None:
    """Section 4: this kind cannot tell one payment run from the next.

    Every docket must come out with `None`, which has to stay distinguishable from a Daily Sales
    docket that names its account sale.
    """
    result = read(CONSIGNMENTS)
    dockets = [d for block in result.consignments for d in block.dockets]
    assert dockets
    assert all(d.payment_reference is None for d in dockets)
    assert all(d.date_paid is None for d in dockets)


def test_the_consignment_report_recovers_the_market_daily_sales_omits() -> None:
    grapes = _consignment(read(CONSIGNMENTS), "118246503Z")
    assert grapes.market == "JOBURG MKT - TFRESH"


def test_a_blank_scope_filter_is_not_read_as_all() -> None:
    """`Market:` with nothing after it states no scope. ALL states a full one."""
    scope = read(CONSIGNMENTS).scope
    assert scope.is_unstated is True
    assert scope.describe() == "Scope not stated"


def test_qty_sent_and_qty_available_are_both_kept_when_they_differ() -> None:
    # Delivery 1181705Z: sent 71, available 70. Not in the brief. Which figure the delivery
    # should be judged on is the operator's call, so both are kept and the difference reported.
    nectarines = _consignment(read(CONSIGNMENTS), "118170502Z")
    assert nectarines.qty_sent == Decimal("71")
    assert nectarines.qty_available == Decimal("70")
    assert "only 70 were available" in messages(read(CONSIGNMENTS))


# --- Account sales statements ---------------------------------------------------------------------


def test_a_single_product_statement() -> None:
    statement = read(STATEMENT_ONE_PRODUCT).statements[0]
    assert statement.account_sale_number == "382405"
    assert statement.gross_amount == Decimal("400.00")
    assert statement.nett_amount == Decimal("340.00")
    assert statement.previous_account_sale_number == "382399"
    assert [d.name for d in statement.deductions] == ["MARKET FEES"]


def test_the_fruit_named_deduction_stays_a_named_line() -> None:
    """Section 6: a deduction named for a fruit lands only on that fruit's rows.

    Collapsing the table into one total would put part of the plum levy on the nectarines.
    """
    statement = read(STATEMENT_TWO_PRODUCTS).statements[0]
    names = [d.name for d in statement.deductions]
    assert names == ["MARKET FEES", "PLUMS LEVY"]
    assert dict(zip(names, [d.total for d in statement.deductions], strict=True)) == {
        "MARKET FEES": Decimal("230.00"),
        "PLUMS LEVY": Decimal("46.00"),
    }


def test_the_printed_deductions_reconcile_to_the_printed_nett() -> None:
    statement = read(STATEMENT_TWO_PRODUCTS).statements[0]
    deducted = sum(d.total for d in statement.deductions if d.total is not None)
    assert statement.gross_amount == Decimal("4000.00")
    assert statement.gross_amount - deducted == statement.nett_amount == Decimal("3724.00")


def test_a_statement_covering_two_products_keeps_them_apart() -> None:
    statement = read(STATEMENT_TWO_PRODUCTS).statements[0]
    assert [p.product_name for p in statement.products] == [
        "PLAN 2A MA53 PLUM ANGELINO",
        "NEOT 1L MA50 36 T2 NECTARINE OTHER",
    ]
    assert [p.total_value for p in statement.products] == [Decimal("3000.00"), Decimal("1000.00")]


def test_the_agents_delivery_note_number_is_kept_apart_from_zacos() -> None:
    """`DELIVERY NOTE NO : 203003` is the agent's number, in the same 203xxx series as the
    payment reports' FMS IDs. Zaco's own delivery notes are 14xxx. It is read so the operator
    can see what the page said, under a name that cannot be mistaken for column A."""
    statement = read(STATEMENT_ONE_PRODUCT).statements[0]
    assert statement.agent_delivery_note_number == "203003"
    assert not hasattr(statement, "delivery_note_number")


def test_the_statement_product_vocabulary_differs_from_the_sales_side() -> None:
    """`CHOT 1L HT25 CHERRY OTHER` here; `CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)` on the
    sales side. Same fruit, two namespaces -- and `lookup/product-codes.json` is keyed on this
    one, not the other. Phase 2 has to reconcile them."""
    statement = read(STATEMENT_ONE_PRODUCT).statements[0]
    assert statement.products[0].product_name == "CHOT 1L HT25 CHERRY OTHER"
    sales_side = _consignment(read(DAILY_ROUND_1), "118069901Z")
    assert sales_side.product_name == "CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)"


# --- Payment Details -------------------------------------------------------------------------------


def test_both_shapes_of_payment_details_read_the_same_way() -> None:
    csv_result, txt_result = read(PAYMENTS_CSV), read(PAYMENTS_TXT)
    assert len(csv_result.payments) == 6
    assert len(txt_result.payments) == 7
    for record in csv_result.payments + txt_result.payments:
        assert record.account_sale_number


def test_the_nett_and_gross_come_off_a_line_mixing_two_thousands_separators() -> None:
    record = _payment(read(PAYMENTS_TXT), "JOH*SUB*5644210/1")
    assert record.nett_payment == Decimal("1275.00")
    assert record.gross_payment == Decimal("1500.00")


def test_a_payment_with_no_commodity_breakdown_is_kept_and_flagged() -> None:
    """Section 8: it can never reconcile, and must be reported rather than letting its money
    vanish. AccSale 382999 -- R260 gross, R207.30 nett, and nothing else on the page."""
    record = _payment(read(PAYMENTS_TXT), "PRE*BT*382999")
    assert record.has_commodity_breakdown is False
    assert record.gross_payment == Decimal("260.00")
    assert record.nett_payment == Decimal("207.30")
    assert "can never be reconciled" in messages(read(PAYMENTS_TXT), Severity.WARNING)


def test_one_payment_covering_three_commodities() -> None:
    record = _payment(read(PAYMENTS_TXT), "PRE*BT*382880")
    assert len(record.commodities) == 3
    assert sum(c.sales_total for c in record.commodities if c.sales_total) == Decimal("300.00")


def test_a_narrowed_export_says_so() -> None:
    """Section 4: the person who ran it usually believes they took the lot."""
    result = read(PAYMENTS_NARROWED)
    assert result.scope.is_narrowed is True
    assert result.scope.market == "TSHWANE MARKET"
    assert result.scope.agent == "Farmers Trust (Pre)"
    assert "not for everything" in messages(result, Severity.WARNING)


def test_a_full_export_does_not_warn_about_scope() -> None:
    result = read(PAYMENTS_CSV)
    assert result.scope.is_narrowed is False
    assert "not for everything" not in messages(result)


def test_the_narrowed_export_overlaps_the_full_one_on_account_sale_not_fms_id() -> None:
    """Identity has to be the account sale number: the FMS IDs collide across different records.

    `203451` is AccSale 382405 in the first round's CSV and AccSale 382860 in the narrowed
    re-export. Deduplicating on FMS ID would merge two unrelated payments.
    """
    narrowed = {p.account_sale_number for p in read(PAYMENTS_NARROWED).payments}
    full = {p.account_sale_number for p in read(PAYMENTS_TXT).payments}
    assert narrowed <= full

    first_round = {p.fms_id: p.account_sale_number for p in read(PAYMENTS_CSV).payments}
    re_export = {p.fms_id: p.account_sale_number for p in read(PAYMENTS_NARROWED).payments}
    shared = set(first_round) & set(re_export)
    assert shared
    assert any(first_round[k] != re_export[k] for k in shared)


# --- Nett Payment Adjustments -----------------------------------------------------------------------


def test_the_jammed_account_sale_and_date_are_separated() -> None:
    result = read(ADJUSTMENTS)
    numbers = [a.account_sale_number for a in result.adjustments]
    assert "JOH*SUB*5640001/1" in numbers
    assert "JOH*SUB*5640001/2" in numbers


def test_the_two_april_payment_runs_stay_separate() -> None:
    result = read(ADJUSTMENTS)
    by_number = {a.account_sale_number: a for a in result.adjustments}
    assert by_number["JOH*SUB*5640001/1"].nett_payment == Decimal("5100.00")
    assert by_number["JOH*SUB*5640001/2"].nett_payment == Decimal("3230.00")


def test_a_total_row_in_the_middle_of_a_section_does_not_end_it() -> None:
    """Treating any `Total` as a terminator would silently drop the R3,230 line after it."""
    result = read(ADJUSTMENTS)
    assert len(result.adjustments) == 4
    assert "Total row appears mid-list" in messages(result)


def test_one_payment_against_two_supplier_references() -> None:
    """`20026*14705 & 14706`. The proof that a delivery note cannot be derived from a payment:
    the relationship is not one to one, which is why section 7 says the DN must be captured."""
    result = read(ADJUSTMENTS)
    both = next(a for a in result.adjustments if len(a.supplier_refs) > 1)
    assert both.supplier_refs == ["20026*14705", "20026*14706"]


def test_this_kind_carries_no_product_or_quantity() -> None:
    result = read(ADJUSTMENTS)
    assert result.consignments == []
    assert result.docket_count == 0


# --- helpers ------------------------------------------------------------------------------------------


def _consignment(result: ParseResult, consignment_id: str):  # type: ignore[no-untyped-def]
    return next(c for c in result.consignments if c.consignment_id == consignment_id)


def _payment(result: ParseResult, account_sale: str):  # type: ignore[no-untyped-def]
    return next(p for p in result.payments if p.account_sale_number == account_sale)
