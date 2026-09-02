"""Account sales statement: one payment run, one Nett, and a printed table of deductions.

This is the only document that shows *how* the agent arrived at the Nett. Section 6 requires
each row's share to be recreated from this statement's own printed deductions rather than from
rates of our own, and requires a deduction named for a fruit to land only on that fruit's rows.
So the deductions table is read as named lines, never collapsed into a single total.

The trap in this document, which the brief does not mention:

    DELIVERY NOTE NO : 203003

That is the *agent's* delivery note number. It sits in the same 203xxx series as the payment
reports' FMS IDs, while Zaco's own delivery notes are 14xxx. It is read and kept so the operator
can see what the page said, and it is never offered as workbook column A.
"""

from __future__ import annotations

import re
from decimal import Decimal

from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import (
    AccountSalesStatement,
    Deduction,
    Docket,
    DocumentKind,
    DocumentScope,
    ParseResult,
    StatementProduct,
)
from zaco.ingest.values import clean, find_money, parse_date, parse_quantity, squeeze

KIND = DocumentKind.ACCOUNT_SALES_STATEMENT

_ACCOUNT_SALE = re.compile(r"ACCOUNT\s+SALES\s+NO\s*:\s*(?P<value>\S+)", re.IGNORECASE)
_PRODUCER = re.compile(
    r"PRODUCER\s*:\s*(?P<code>\S+)\s+(?P<name>.*?)\s+DATE\s*:\s*(?P<date>[\d/]+)", re.IGNORECASE
)
_AGENT_DELIVERY_NOTE = re.compile(r"DELIVERY\s+NOTE\s+NO\s*:\s*(?P<value>\S+)", re.IGNORECASE)
_REFNO = re.compile(r"REFNO\s*:\s*(?P<value>\S+)", re.IGNORECASE)
_DATE_RECEIVED = re.compile(r"DATE\s+RECEIVED\s*:\s*(?P<value>[\d/]+)", re.IGNORECASE)
_PREVIOUS = re.compile(r"PREVIOUS\s+ACCOUNT\s+SALES\s+NO\s*:\s*(?P<value>\S+)", re.IGNORECASE)
_GRN = re.compile(
    r"MARKET\s+GRN\s*:\s*(?P<grn>\S+)\s+QUANTITY\s+RECEIVED\s*:\s*(?P<received>\S+)\s+"
    r"QUANTITY\s+B/F\s*:\s*(?P<bf>\S+)",
    re.IGNORECASE,
)
_PRODUCT = re.compile(
    r"PRODUCT\s*:\s*(?P<name>.*?)(?:\s+SMAN\s*:\s*(?P<salesman>.*))?\s*$", re.IGNORECASE
)
_OUTSTANDING = re.compile(
    r"QUANTITY\s+OUTSTANDING\s*:\s*(?P<qty>\S+)\s*(?:AGENT\s+COMM\s*%\s*:\s*(?P<comm>\S+))?",
    re.IGNORECASE,
)
_SALE = re.compile(r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<rest>.*)$")
_GROSS = re.compile(r"GROSS\s+AMOUNT\s+(?P<value>[\d ,.]+)", re.IGNORECASE)
_NETT = re.compile(r"NETT\s+AMOUNT\s+(?P<value>[\d ,.\-]+)", re.IGNORECASE)
_VAT_OUTPUT = re.compile(r"VAT\s*\(OUTPUT\)\s*COLLECTED\s+(?P<value>[\d ,.\-]+)", re.IGNORECASE)
_TOTAL_SOLD = re.compile(r"\*\*\s*TOTAL\s+SOLD\s*\*\*\s*(?P<value>[\d ,.\-]+)", re.IGNORECASE)
_FINAL_PAYMENT = re.compile(r"\*\*\s*FINAL\s+PAYMENT\s*\*\*", re.IGNORECASE)

_SKIP = re.compile(
    r"^(-+|=+|VAT\s+Reg|P\.?O\.?\s+BOX|PRETORIA|TEL:|AGENT\s+VAT|TAX\s+INVOICE|"
    r"AFREKENINGSTAAT|ACCOUNT\s+SALES\s*$|BELASTINGFAKTUUR|BT\d+|DATE\s+PRICES|"
    r"COSTS|CURRENT\s+SALES|DEDUCTION\s+AMOUNT|Vat\s+Reg\s+No|EGYPT|\d{4}$)",
    re.IGNORECASE,
)


def sniff(text: str) -> float:
    if _ACCOUNT_SALE.search(text) and _NETT.search(text):
        return 1.0
    if _ACCOUNT_SALE.search(text):
        return 0.7
    return 0.0


def parse(text: str, log: ProblemLog) -> ParseResult:
    lines = text.split("\n")
    statement = AccountSalesStatement(account_sale_number=None, line_number=1)
    result = ParseResult(kind=KIND, scope=DocumentScope(), statements=[statement])

    product: StatementProduct | None = None
    in_deductions = False

    for number, raw in enumerate(lines, start=1):
        line = clean(raw)
        if not line:
            continue

        if _read_header_field(statement, line):
            continue

        grn = _GRN.search(line)
        if grn:
            product = StatementProduct(
                product_name=None,
                market_grn=grn.group("grn"),
                quantity_received=parse_quantity(grn.group("received")),
                quantity_brought_forward=parse_quantity(grn.group("bf")),
                line_number=number,
            )
            statement.products.append(product)
            continue

        if line.upper().startswith("PRODUCT"):
            match = _PRODUCT.match(line)
            if match and product is not None:
                product.product_name = squeeze(match.group("name")) or None
                product.salesman = squeeze(match.group("salesman") or "") or None
            elif match:
                log.warn("Product line before any MARKET GRN; ignored.", number, raw)
            continue

        outstanding = _OUTSTANDING.search(line)
        if outstanding:
            if product is not None:
                product.quantity_outstanding = parse_quantity(outstanding.group("qty"))
                product.agent_commission_percent = _decimal(outstanding.group("comm"))
            continue

        if _FINAL_PAYMENT.search(line):
            statement.is_final_payment = True
        total_sold = _TOTAL_SOLD.search(line)
        if total_sold:
            statement.total_sold = _decimal(total_sold.group("value"))
        if _FINAL_PAYMENT.search(line) or total_sold:
            in_deductions = True
            continue

        vat_output = _VAT_OUTPUT.search(line)
        if vat_output:
            statement.vat_output_collected = _decimal(vat_output.group("value"))
            continue

        nett = _NETT.search(line)
        if nett:
            statement.nett_amount = _decimal(nett.group("value"))
            continue

        gross = _GROSS.search(line)
        if gross:
            statement.gross_amount = _decimal(gross.group("value"))
            deduction = _read_deduction(line[: gross.start()], number)
            if deduction is not None:
                statement.deductions.append(deduction)
            continue

        sale = _SALE.match(line)
        if sale:
            if product is None:
                log.warn("Sale line before any MARKET GRN; ignored.", number, raw)
                continue
            product.dockets.append(_read_sale(sale, number, log, raw))
            continue

        if _SKIP.match(line):
            continue

        if in_deductions:
            deduction = _read_deduction(line, number)
            if deduction is not None:
                statement.deductions.append(deduction)
                continue

        if _is_product_total(line):
            if product is not None:
                _read_product_total(product, line)
            continue

        log.warn("Line not recognised; nothing was taken from it.", number, raw)

    _check_statement(statement, log)
    return result


def _read_header_field(statement: AccountSalesStatement, line: str) -> bool:
    matched = False

    account_sale = _ACCOUNT_SALE.search(line)
    if account_sale and statement.account_sale_number is None:
        statement.account_sale_number = account_sale.group("value")
        matched = True

    producer = _PRODUCER.search(line)
    if producer:
        statement.producer_code = producer.group("code")
        statement.producer_name = squeeze(producer.group("name"))
        statement.statement_date = parse_date(producer.group("date"))
        matched = True

    note = _AGENT_DELIVERY_NOTE.search(line)
    if note:
        statement.agent_delivery_note_number = note.group("value")
        matched = True

    refno = _REFNO.search(line)
    if refno:
        statement.reference_number = refno.group("value")
        matched = True

    received = _DATE_RECEIVED.search(line)
    if received:
        statement.date_received = parse_date(received.group("value"))
        matched = True

    previous = _PREVIOUS.search(line)
    if previous:
        statement.previous_account_sale_number = previous.group("value")
        matched = True

    return matched


def _read_sale(match: re.Match[str], number: int, log: ProblemLog, raw: str) -> Docket:
    """`27/05/2026 200.00 - 200.00  200.00    0.00           2      400.00`.

    Columns are a price range, an average price, the market average, the quantity and the value.
    Read from the right, because the price range prints as two figures or as one.
    """
    figures = find_money(match.group("rest"))
    if len(figures) < 2:
        log.warn("Sale line has no readable quantity and value.", number, raw)
        return Docket(
            docket_number="",
            date_sold=parse_date(match.group("date")),
            quantity=None,
            price=None,
            value=None,
            line_number=number,
        )

    value = figures[-1]
    quantity = figures[-2]
    price = figures[-4] if len(figures) >= 4 else None
    return Docket(
        # This document identifies sales by date and price, not by docket number. Inventing one
        # would create a false identity for deduplication to trip over later.
        docket_number="",
        date_sold=parse_date(match.group("date")),
        quantity=quantity,
        price=price,
        value=value,
        market_average=figures[-3] if len(figures) >= 3 else None,
        line_number=number,
    )


def _read_deduction(text: str, number: int) -> Deduction | None:
    """`MARKET FEES         52.17      7.83    60.00` -> name, amount, VAT, total."""
    line = clean(text)
    if not line:
        return None
    figures = find_money(line)
    if len(figures) < 3:
        return None
    name = squeeze(MONEY_PREFIX.sub("", line)) or line
    return Deduction(
        name=name.rstrip(" .-"),
        amount=figures[-3],
        vat=figures[-2],
        total=figures[-1],
        line_number=number,
    )


MONEY_PREFIX = re.compile(r"[\d ,.]+$")


def _is_product_total(line: str) -> bool:
    return not line[0].isalpha() and len(find_money(line)) >= 2


def _read_product_total(product: StatementProduct, line: str) -> None:
    figures = find_money(line)
    product.stated_total_quantity = figures[-2]
    product.stated_total_value = figures[-1]


def _decimal(raw: str | None) -> Decimal | None:
    figures = find_money(raw or "")
    return figures[0] if figures else None


def _check_statement(statement: AccountSalesStatement, log: ProblemLog) -> None:
    """Reconcile the printed deductions against the printed gross and nett.

    Section 6: "If the printed deductions cannot be reconciled to the printed Nett, do not
    produce a figure. Say so instead." Phase 5 does the refusing; the reader's job is to notice.
    """
    if statement.account_sale_number is None:
        log.error("No account sale number found. This does not read as an account sales statement.")

    if statement.gross_amount is None or statement.nett_amount is None:
        log.warn("Statement does not print both a gross and a nett amount.")
        return

    deducted = sum((d.total for d in statement.deductions if d.total is not None), Decimal(0))
    expected = statement.gross_amount - deducted
    if abs(expected - statement.nett_amount) > Decimal("0.01"):
        log.warn(
            f"Printed deductions do not reconcile: gross R{statement.gross_amount} less "
            f"R{deducted} of deductions is R{expected}, but the statement prints a nett of "
            f"R{statement.nett_amount}. No apportioned figure can be produced from this.",
            statement.line_number,
        )

    for product in statement.products:
        if product.stated_total_value is None:
            continue
        if abs(product.total_value - product.stated_total_value) > Decimal("0.01"):
            log.warn(
                f"Product {product.product_name or product.market_grn or '?'}: its sale lines "
                f"total R{product.total_value} but the statement prints "
                f"R{product.stated_total_value}.",
                product.line_number,
            )
