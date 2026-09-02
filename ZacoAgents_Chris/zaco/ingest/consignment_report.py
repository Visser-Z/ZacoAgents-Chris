"""Consignment Reports: the same sales, with less in them.

Section 4 says this kind does not carry the account sale a docket was paid under, so it cannot
tell one payment run from the next. Two consequences the reader has to preserve rather than
paper over:

* every docket comes out with `payment_reference=None`. That is genuinely unknown, not zero, and
  must stay distinguishable from a Daily Sales Detail docket that names its account sale.
* it also carries no date paid, so nothing here can be reconciled to the payment side on its own.

Two things found in this document that the brief does not mention:

* its `Report:` line says `Daily Sales Detail` while the page title says `Consignment Reports`.
  Classifying on the `Report:` line alone would file it as the richer document and then read
  account sales out of it that are not there.
* its `Market:` and `Agent:` lines are *blank* rather than `ALL`. That states no scope at all,
  which is not the same as stating a full one, and is reported as such.
"""

from __future__ import annotations

import re

from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import ConsignmentBlock, Docket, DocumentKind, ParseResult
from zaco.ingest.scope import read_scope_header
from zaco.ingest.values import (
    clean,
    find_money,
    parse_date,
    parse_quantity,
    squeeze,
)

KIND = DocumentKind.CONSIGNMENT_REPORT

_DELIVERY = re.compile(
    r"Delivery\s+ID:\s*(?P<delivery>\S*)\s*"
    r"Supplier\s+Ref:\s*(?P<ref>\S*)\s*"
    r"Qty\s+Sent:\s*(?P<sent>\S*)\s*"
    r"Qty\s+Amended\s+To:\s*(?P<amended>\S*)\s*"
    r"Qty\s+Avail:\s*(?P<avail>\S*)\s*$"
)
_CONSIGNMENT = re.compile(r"Consignment\s+ID:\s*(?P<id>\S*)\s*(?:Comment:\s*(?P<comment>.*))?$")
_PRODUCT = re.compile(r"Product:\s*(?P<name>.+?)\s*$")
_SALE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<docket>\S+)\s+(?P<rest>.*)$")
_COLUMN_HEADER = re.compile(r"Date\s+Sold\s+Docket\s+Number", re.IGNORECASE)


def sniff(text: str) -> float:
    head = text[:2000]
    if "Consignment Reports" in head and "Consignment ID:" in text:
        return 1.0
    # The layout is distinctive even without the title: colon-labelled fields with no commas,
    # and a Qty Avail column that no other kind carries.
    if "Consignment ID:" in text and "Qty Avail:" in text:
        return 0.85
    return 0.0


def parse(text: str, log: ProblemLog) -> ParseResult:
    lines = text.split("\n")
    scope = read_scope_header(lines, log)
    result = ParseResult(kind=KIND, scope=scope)

    market: str | None = None
    agent: str | None = None
    current: ConsignmentBlock | None = None
    in_header = True

    for number, raw in enumerate(lines, start=1):
        line = clean(raw)
        if not line:
            continue

        if in_header:
            if _DELIVERY.search(line) or _looks_like_market_agent(line):
                in_header = False
            else:
                continue

        delivery = _DELIVERY.search(line)
        if delivery:
            current = ConsignmentBlock(
                consignment_id=None,
                delivery_id=delivery.group("delivery") or None,
                product_name=None,
                supplier_ref=delivery.group("ref") or None,
                qty_sent=parse_quantity(delivery.group("sent")),
                qty_amended_to=parse_quantity(delivery.group("amended")),
                qty_available=parse_quantity(delivery.group("avail")),
                market=market,
                agent=agent,
                line_number=number,
            )
            result.consignments.append(current)
            _note_available_discrepancy(current, log, number)
            continue

        consignment = _CONSIGNMENT.match(line)
        if consignment:
            if current is None:
                log.warn("Consignment ID before any Delivery ID; ignored.", number, raw)
                continue
            current.consignment_id = consignment.group("id") or None
            continue

        if _COLUMN_HEADER.search(line):
            continue

        product = _PRODUCT.match(line)
        if product:
            if current is None:
                log.warn("Product before any Delivery ID; ignored.", number, raw)
                continue
            current.product_name = squeeze(product.group("name")) or None
            continue

        sale = _SALE.match(line)
        if sale:
            if current is None:
                log.warn("Sale line before any Delivery ID; ignored.", number, raw)
                continue
            current.dockets.append(_read_docket(sale, number, log, raw))
            continue

        if _is_block_total(line):
            if current is not None:
                _read_block_total(current, line)
            continue

        if _looks_like_market_agent(line):
            market, agent = _read_market_agent(line)
            continue

        log.warn("Line not recognised; nothing was taken from it.", number, raw)

    return result


def _read_docket(match: re.Match[str], number: int, log: ProblemLog, raw: str) -> Docket:
    figures = find_money(match.group("rest"))
    # The columns are Qty Sold, Market Avg, Price, Sales Value. A returns line in the supplied
    # data prints only three of the four, so trailing values are read from the right.
    quantity = figures[0] if figures else None
    price = figures[-2] if len(figures) >= 3 else None
    value = figures[-1] if len(figures) >= 2 else None

    if quantity is None:
        log.warn("Sale line has no readable quantity.", number, raw)
    if value is None:
        log.warn("Sale line has no readable sales value.", number, raw)
    elif quantity is not None and quantity < 0 and value > 0:
        # `2026-05-28 PRE*B6E02C39002*01Z -1 R 0.00 R -200.00` -- the value carries the sign.
        log.note(
            f"Docket {match.group('docket')} returns {abs(quantity)} cartons but its value is "
            f"printed positive as R{value}. Read as a return.",
            number,
        )

    return Docket(
        docket_number=match.group("docket"),
        date_sold=parse_date(match.group("date")),
        quantity=quantity,
        price=price,
        value=value,
        # This kind carries neither, and saying so is the point of it existing separately.
        date_paid=None,
        payment_reference=None,
        market_average=figures[1] if len(figures) >= 4 else None,
        line_number=number,
    )


def _is_block_total(line: str) -> bool:
    """A consignment's own printed total: figures only, no date and no docket number."""
    if not line or line[0].isalpha():
        return False
    return bool(find_money(line)) and not _SALE.match(line)


def _read_block_total(block: ConsignmentBlock, line: str) -> None:
    figures = find_money(line)
    if len(figures) >= 2:
        block.stated_total_quantity = figures[0]
        block.stated_total_value = figures[-1]
    elif figures:
        block.stated_total_value = figures[-1]


def _looks_like_market_agent(line: str) -> bool:
    """`TSHWANE MARKET      Farmers Trust (Pre)` -- two names separated by a run of spaces."""
    if ":" in line or find_money(line):
        return False
    return len(re.split(r"\s{3,}", line.strip())) == 2


def _read_market_agent(line: str) -> tuple[str | None, str | None]:
    left, right = (part.strip() for part in re.split(r"\s{3,}", line.strip(), maxsplit=1))
    return squeeze(left) or None, squeeze(right) or None


def _note_available_discrepancy(block: ConsignmentBlock, log: ProblemLog, number: int) -> None:
    """`Qty Sent: 71` against `Qty Avail: 70` -- a carton that never reached the floor.

    Not mentioned in the brief. It is reported rather than reconciled, because which of the two
    figures the delivery should be judged on is the operator's call, not the reader's.
    """
    if block.qty_sent is None or block.qty_available is None:
        return
    if block.qty_sent != block.qty_available:
        log.note(
            f"Delivery {block.delivery_id or '?'} was sent {block.qty_sent} cartons but only "
            f"{block.qty_available} were available on the floor. Both figures are kept.",
            number,
        )
