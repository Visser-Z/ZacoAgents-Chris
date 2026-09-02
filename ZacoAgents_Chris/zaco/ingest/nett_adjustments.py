"""Nett Payment Adjustments: one line per account sale, gross and nett only.

Section 4: this kind carries no product and no quantity. Nothing here can be split across
workbook rows on its own, and the reader does not pretend otherwise.

Three things in the supplied file that the brief does not mention, all of which break a naive
whitespace split:

* `JOH*SUB*5640001/12026-04-13` -- the account sale reference and its date run together with no
  delimiter. Splitting on spaces corrupts the reference and loses the date.
* `20026*14705 & 14706` -- one payment against *two* supplier references. This is the proof that
  a delivery note cannot be derived from a payment: the relationship is not one to one.
* a `Total` row appears in the *middle* of the Subtropico section, before its second line, not
  at the end of it. Treating any `Total` as a terminator would silently drop R3,230.
"""

from __future__ import annotations

import re
from decimal import Decimal

from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import DocumentKind, NettAdjustment, ParseResult
from zaco.ingest.scope import read_scope_header
from zaco.ingest.values import clean, find_money, parse_date, split_trailing_date, squeeze

KIND = DocumentKind.NETT_PAYMENT_ADJUSTMENTS

_REPORT_TITLE = re.compile(r"Report:\s*Nett\s+Payment\s+Adjustments", re.IGNORECASE)
_COLUMN_HEADER = re.compile(r"Supplier\s+Ref\s+AccSale\s+Number", re.IGNORECASE)
_TOTAL_ROW = re.compile(r"^Total\b", re.IGNORECASE)
_SUPPLIER_REF = re.compile(r"^\d+\*\S+")


def sniff(text: str) -> float:
    if _REPORT_TITLE.search(text):
        return 1.0
    if _COLUMN_HEADER.search(text) and "Nett Adjustment" in text:
        return 0.8
    return 0.0


def parse(text: str, log: ProblemLog) -> ParseResult:
    lines = text.split("\n")
    result = ParseResult(kind=KIND, scope=read_scope_header(lines, log))

    market: str | None = None
    agent: str | None = None

    for number, raw in enumerate(lines, start=1):
        line = clean(raw)
        if not line or _COLUMN_HEADER.search(line):
            continue

        if _TOTAL_ROW.match(line):
            # Deliberately not a section terminator: in the supplied file one of these sits in
            # the middle of a section, and treating it as an end would drop the line after it.
            log.note("A Total row appears mid-list; it was skipped, not treated as an end.", number)
            continue

        if _SUPPLIER_REF.match(line):
            adjustment = _read_adjustment(line, number, market, agent, log, raw)
            if adjustment is not None:
                result.adjustments.append(adjustment)
            continue

        if _looks_like_section_header(line):
            market, agent = _read_section_header(line)
            continue

        if _is_report_furniture(line):
            continue

        log.warn("Line not recognised; nothing was taken from it.", number, raw)

    return result


def _read_adjustment(
    line: str,
    number: int,
    market: str | None,
    agent: str | None,
    log: ProblemLog,
    raw: str,
) -> NettAdjustment | None:
    """`20026*14705 & 14706 JOH*SUB*5640001/12026-04-13 R 6 000.00 R 782.61 ...`."""
    money_start = _first_money_position(line)
    head, tail = line[:money_start].strip(), line[money_start:]

    tokens = head.split()
    if not tokens:
        log.warn("Adjustment line has no supplier reference.", number, raw)
        return None

    account_sale, date_paid = split_trailing_date(tokens[-1])
    reference_tokens = tokens[:-1]

    # Two shapes, and the same file uses both. Subtropico's lines run the account sale and its
    # date together -- `JOH*SUB*5640001/12026-04-13` -- so splitting the trailing date leaves the
    # reference behind it. The Tshwane lines put a space between them, so the last token is
    # *only* a date and the account sale is the token before it. Without this second case the
    # account sale is read as another supplier reference and the record loses its number
    # entirely, which is how a real payment ends up in the system with nothing to join it on.
    if not account_sale and reference_tokens:
        account_sale = reference_tokens[-1]
        reference_tokens = reference_tokens[:-1]
    elif date_paid is None and reference_tokens:
        maybe_date = parse_date(account_sale)
        if maybe_date is not None:
            date_paid = maybe_date
            account_sale = reference_tokens[-1]
            reference_tokens = reference_tokens[:-1]

    refs = _split_references(reference_tokens)
    if not refs:
        log.warn("Adjustment line has no readable supplier reference.", number, raw)
    if date_paid is None:
        log.warn(f"Account sale {account_sale or '?'} has no readable payment date.", number, raw)

    figures = find_money(tail)
    if len(figures) < 4:
        log.warn(
            f"Account sale {account_sale or '?'} is missing one of gross, deductions, VAT or nett.",
            number,
            raw,
        )

    return NettAdjustment(
        account_sale_number=account_sale or None,
        supplier_refs=refs,
        date_paid=date_paid,
        gross_payment=_at(figures, 0),
        total_deductions=_at(figures, 1),
        deduction_vat=_at(figures, 2),
        nett_payment=_at(figures, 3),
        calculated_nett_adjustment=_at(figures, 4),
        nett_adjustment=_at(figures, 5),
        market=market,
        agent=agent,
        line_number=number,
    )


def _split_references(tokens: list[str]) -> list[str]:
    """`['20026*14705', '&', '14706']` -> `['20026*14705', '20026*14706']`.

    One payment against two references. The second is written bare, so it inherits the producer
    code of the first rather than being left as a fragment.
    """
    refs: list[str] = []
    producer: str | None = None
    for token in tokens:
        if token == "&":
            continue
        if "*" in token:
            producer = token.split("*", 1)[0]
            refs.append(token)
        elif producer is not None:
            refs.append(f"{producer}*{token}")
        else:
            refs.append(token)
    return refs


def _first_money_position(line: str) -> int:
    match = re.search(r"R\s*[\d-]", line)
    return match.start() if match else len(line)


def _at(figures: list[Decimal], index: int) -> Decimal | None:
    return figures[index] if index < len(figures) else None


def _looks_like_section_header(line: str) -> bool:
    """`Subtropico (Jhb)` alone, or `TSHWANE MARKET     Farmers Trust (Pre)`."""
    if ":" in line or find_money(line) or _SUPPLIER_REF.match(line):
        return False
    return bool(line) and line[0].isalpha()


def _read_section_header(line: str) -> tuple[str | None, str | None]:
    parts = [p.strip() for p in re.split(r"\s{3,}", line.strip()) if p.strip()]
    if len(parts) >= 2:
        return squeeze(parts[0]) or None, squeeze(parts[1]) or None
    # `Subtropico (Jhb)` on its own: an agent with no market named beside it. The market is not
    # invented from the agent.
    return None, squeeze(parts[0]) if parts else None


def _is_report_furniture(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in ("report", "run date", "market:", "agent:", "date range", "zaco agents")
    )
