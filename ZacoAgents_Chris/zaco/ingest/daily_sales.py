"""Daily Sales Detail: every docket, and the account sale each one was paid under.

This is the richest of the five. It is the only sales-side report that names the account sale a
docket was paid under, which section 8 requires be used in preference to matching on anything
softer.

The two supplied exports of it differ in ways nothing in the brief mentions:

* the first wraps every line in a further pair of quotes, so a correct CSV reader sees one field
  per row; the second does not, and carries a byte order mark instead
* the first labels the Subtropico block `Destination` where the market name should be, so the
  market has to come from somewhere else or stay empty -- it is never guessed
* the second contains `PRE*BT*0` with a date paid of `0000-00-00`, which is not an account sale
  and must not become one
"""

from __future__ import annotations

from decimal import Decimal

from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import ConsignmentBlock, Docket, DocumentKind, DocumentScope, ParseResult
from zaco.ingest.values import (
    cell,
    clean,
    is_blank_row,
    looks_like_date,
    parse_date,
    parse_money,
    parse_quantity,
    read_csv_rows,
    squeeze,
)

KIND = DocumentKind.DAILY_SALES_DETAIL

HEADER_FIELDS = (
    "delivery date",
    "date sold",
    "date paid",
    "docket number",
    "payment reference",
    "qty sold",
)

#: What the export prints instead of a market name for one of the two agents.
MARKET_PLACEHOLDERS = {"destination", "market", ""}

#: A payment reference that names no account sale. Section 3: a row is delivery x product x
#: account sale, so a docket carrying this cannot form one yet.
NULL_PAYMENT_REFERENCES = {"", "0"}


def sniff(text: str) -> float:
    """Confidence that this is a Daily Sales Detail export.

    Deliberately keyed on the CSV header rather than on the words "Daily Sales Detail", because
    `ConsignmentReports_20260525-20260531.txt` prints exactly those words on its `Report:` line
    while being a different document with less information in it.
    """
    rows = read_csv_rows(text[:4000])
    for row in rows[:5]:
        lowered = [clean(c).lower() for c in row]
        if all(f in lowered for f in HEADER_FIELDS):
            return 1.0
    if "Consignment ID :," in text and "Date Paid" in text:
        return 0.6
    return 0.0


def parse(text: str, log: ProblemLog) -> ParseResult:
    rows = read_csv_rows(text)
    result = ParseResult(kind=KIND, scope=DocumentScope())

    market: str | None = None
    agent: str | None = None
    current: ConsignmentBlock | None = None
    seen_header = False

    for number, row in enumerate(rows, start=1):
        raw = ",".join(row)
        if is_blank_row(row):
            continue

        first = cell(row, 0)
        lowered_row = [clean(c).lower() for c in row]

        if not seen_header and all(f in lowered_row for f in HEADER_FIELDS):
            seen_header = True
            continue

        if first.lower().startswith("delivery id"):
            current = _start_consignment(row, number, market, agent, log)
            result.consignments.append(current)
            continue

        if first.lower().startswith("consignment id"):
            if current is None:
                log.warn("Consignment ID before any Delivery ID; ignored.", number, raw)
                continue
            current.consignment_id = cell(row, 1) or None
            continue

        if first.lower().startswith("product"):
            if current is None:
                log.warn("Product before any Delivery ID; ignored.", number, raw)
                continue
            current.product_name = squeeze(cell(row, 1)) or None
            continue

        if cell(row, 1).lower() in {"daily total", "grand total"}:
            continue

        if looks_like_date(first):
            if current is None:
                log.warn("Sale line before any Delivery ID; ignored.", number, raw)
                continue
            current.dockets.append(_read_docket(row, number, log))
            continue

        if _is_subtotal(row):
            if current is not None:
                current.stated_total_quantity = parse_quantity(cell(row, 5))
                current.stated_total_value = parse_money(cell(row, 8))
            continue

        if _is_market_agent(row):
            market, agent = _read_market_agent(row, number, log)
            continue

        log.warn("Line not recognised; nothing was taken from it.", number, raw)

    _check_stated_totals(result, log)
    return result


def _start_consignment(
    row: list[str], number: int, market: str | None, agent: str | None, log: ProblemLog
) -> ConsignmentBlock:
    labelled = _labelled_pairs(row)
    block = ConsignmentBlock(
        consignment_id=None,
        delivery_id=labelled.get("delivery id") or None,
        product_name=None,
        supplier_ref=labelled.get("supplier ref") or None,
        qty_sent=parse_quantity(labelled.get("qty sent")),
        qty_amended_to=parse_quantity(labelled.get("qty amended to")),
        market=market,
        agent=agent,
        line_number=number,
    )
    if block.delivery_id is None:
        log.warn("Delivery line carries no Delivery ID.", number, ",".join(row))
    if not block.supplier_ref:
        # Delivery 1181705Z. The payment side gives it as `20026*00000`; both are the absence of
        # a reference, not a reference of zero.
        log.note(
            f"Delivery {block.delivery_id or '?'} has no Supplier Ref. "
            "Its delivery note number cannot be recovered from this document.",
            number,
        )
    return block


def _labelled_pairs(row: list[str]) -> dict[str, str]:
    """Read a `Label : ,value,Label : ,value` row without depending on column positions."""
    pairs: dict[str, str] = {}
    for index in range(0, len(row) - 1, 2):
        label = clean(row[index]).rstrip(":").strip().lower()
        if label:
            pairs[label] = clean(row[index + 1])
    return pairs


def _read_docket(row: list[str], number: int, log: ProblemLog) -> Docket:
    reference = cell(row, 4)
    account_sale = reference.rsplit("*", 1)[-1] if reference else ""
    if account_sale in NULL_PAYMENT_REFERENCES:
        log.note(
            f"Docket {cell(row, 3) or '?'} carries payment reference "
            f"{reference or '(blank)'}, which names no account sale. It has sold but is not yet "
            "in any payment run.",
            number,
        )
        reference = ""

    date_paid_raw = cell(row, 2)
    date_paid = parse_date(date_paid_raw)
    if date_paid_raw and date_paid is None:
        log.note(
            f"Docket {cell(row, 3) or '?'} has date paid {date_paid_raw!r}, which is not a date. "
            "Read as not yet paid rather than as a date.",
            number,
        )

    quantity = parse_quantity(cell(row, 5))
    value = parse_money(cell(row, 8))
    if quantity is None:
        log.warn("Sale line has no readable quantity.", number, ",".join(row))
    if value is None:
        log.warn("Sale line has no readable sales value.", number, ",".join(row))

    return Docket(
        docket_number=cell(row, 3),
        date_sold=parse_date(cell(row, 1)),
        quantity=quantity,
        price=parse_money(cell(row, 7)),
        value=value,
        date_delivered=parse_date(cell(row, 0)),
        date_paid=date_paid,
        payment_reference=reference or None,
        market_average=parse_money(cell(row, 6)),
        line_number=number,
    )


def _is_subtotal(row: list[str]) -> bool:
    """`" , , , , ,2,,,400.00"` -- a consignment's own printed total."""
    return not cell(row, 0) and bool(cell(row, 5)) and bool(cell(row, 8))


def _is_market_agent(row: list[str]) -> bool:
    filled = [c for c in (clean(x) for x in row) if c]
    return len(filled) == 2 and not any(c.endswith(":") for c in filled)


def _read_market_agent(
    row: list[str], number: int, log: ProblemLog
) -> tuple[str | None, str | None]:
    left, right = squeeze(cell(row, 0)), squeeze(cell(row, 1))
    if left.lower() in MARKET_PLACEHOLDERS:
        log.warn(
            f"This export prints {left!r} where the market name belongs, so the market for "
            f"{right or 'this agent'} is not stated here. It is left empty rather than assumed.",
            number,
            ",".join(row),
        )
        return None, right or None
    return left or None, right or None


def _check_stated_totals(result: ParseResult, log: ProblemLog) -> None:
    """Compare each consignment's printed total against what its lines add up to.

    A mismatch means the reader misread the page, and saying so is the difference between a
    reader that fails loudly and one that fails quietly.
    """
    for block in result.consignments:
        label = block.consignment_id or block.delivery_id or "?"
        if (
            block.stated_total_quantity is not None
            and block.total_quantity != block.stated_total_quantity
        ):
            log.warn(
                f"Consignment {label}: the lines total {block.total_quantity} cartons but "
                f"the export prints {block.stated_total_quantity}.",
                block.line_number,
            )
        if block.stated_total_value is not None:
            difference = block.total_value - block.stated_total_value
            if abs(difference) > Decimal("0.01"):
                log.warn(
                    f"Consignment {label}: the lines total R{block.total_value} but the export "
                    f"prints R{block.stated_total_value}.",
                    block.line_number,
                )
