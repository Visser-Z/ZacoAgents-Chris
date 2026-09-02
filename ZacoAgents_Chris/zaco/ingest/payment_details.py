"""Payment Details: one record per account sale, and where the Nett actually comes from.

Two shapes of the same report are supplied -- a CSV and a laid-out text export -- and they have
to read identically, because one of them is a *narrowed re-export overlapping the other*:
`PaymentDetails_20260603-20260608_FarmersTrust.csv` covers the same dates as
`PaymentDetails_20260603-20260608.txt` for one market only. Section 4 forbids recording the same
thing twice, and identity has to be the account sale number: the FMS IDs in those two files
collide across *different* records.

Two things found here that the brief does not mention:

* the text export's last record, AccSale 382999, carries a gross and a nett and no commodity
  lines at all. Section 8 says such a record can never reconcile and must be reported rather
  than letting its money vanish, so it is parsed and kept, flagged.
* the same line mixes thousands separators: `R 1,275.00 ... R 1 500.00` with a no-break space.
"""

from __future__ import annotations

import re

from zaco.ingest.problems import ProblemLog
from zaco.ingest.records import (
    CommodityLine,
    DocumentKind,
    DocumentScope,
    ParseResult,
    PaymentRecord,
)
from zaco.ingest.scope import read_scope_header, read_scope_row
from zaco.ingest.values import (
    cell,
    clean,
    find_money,
    is_blank_row,
    looks_like_date,
    parse_date,
    parse_money,
    parse_quantity,
    read_csv_rows,
    squeeze,
)

KIND = DocumentKind.PAYMENT_DETAILS

_CSV_HEADER = ("fms id", "acc sales number", "nett payment", "gross payments")
_COMMODITY_HEADER = ("line no", "commodity", "delivered", "sold")

_TEXT_RECORD = re.compile(
    r"^(?P<fms>\d+)\s+(?P<ref>\S+)\s+(?P<accsale>\S+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<rest>.*)$"
)
_TEXT_COMMODITY = re.compile(r"^(?P<fms>\d+)\s+(?P<rest>[\d\s].*)$")
_REPORT_TITLE = re.compile(r"Report:\s*Payment\s+Details", re.IGNORECASE)


def sniff(text: str) -> float:
    if _REPORT_TITLE.search(text):
        return 1.0
    for row in read_csv_rows(text[:2000])[:3]:
        lowered = [clean(c).lower() for c in row]
        if all(field in lowered for field in _CSV_HEADER):
            return 1.0
    return 0.0


def parse(text: str, log: ProblemLog) -> ParseResult:
    if _REPORT_TITLE.search(text):
        return _parse_text(text, log)
    return _parse_csv(text, log)


# --- The CSV shape ----------------------------------------------------------------------------


def _parse_csv(text: str, log: ProblemLog) -> ParseResult:
    rows = read_csv_rows(text)
    result = ParseResult(kind=KIND, scope=DocumentScope())

    market: str | None = None
    agent: str | None = None
    current: PaymentRecord | None = None

    for number, row in enumerate(rows, start=1):
        if is_blank_row(row):
            continue
        raw = ",".join(row)
        lowered = [clean(c).lower() for c in row]

        if all(field in lowered for field in _CSV_HEADER):
            continue

        if "market" in lowered and "agent" in lowered:
            result.scope = read_scope_row(row, log, number)
            continue

        if all(field in lowered for field in _COMMODITY_HEADER):
            continue

        if cell(row, 1).lower() in {"grand total", "total"}:
            continue

        if _is_csv_total_sales(row):
            if current is not None:
                current.stated_total_sales = parse_money(_last_filled(row))
            continue

        if _is_csv_commodity(row):
            if current is None:
                log.warn("Commodity line before any payment record; ignored.", number, raw)
                continue
            current.commodities.append(
                CommodityLine(
                    commodity=squeeze(cell(row, 5)) or None,
                    delivered=parse_quantity(cell(row, 6)),
                    sold=parse_quantity(cell(row, 7)),
                    sales_total=parse_money(cell(row, 8)),
                    line_number_label=cell(row, 3) or None,
                    supplier_ref=cell(row, 4) or None,
                    line_number=number,
                )
            )
            continue

        if _is_csv_record(row):
            current = _read_csv_record(row, number, market, agent, log)
            result.payments.append(current)
            continue

        if _is_market_agent_row(row):
            market, agent = squeeze(cell(row, 0)) or None, squeeze(cell(row, 1)) or None
            continue

        log.warn("Line not recognised; nothing was taken from it.", number, raw)

    _check_payments(result, log)
    return result


def _is_csv_record(row: list[str]) -> bool:
    return bool(cell(row, 0)) and looks_like_date(cell(row, 3))


def _is_csv_commodity(row: list[str]) -> bool:
    return not cell(row, 0) and bool(cell(row, 5)) and bool(cell(row, 3))


def _is_csv_total_sales(row: list[str]) -> bool:
    return any(clean(c).lower().startswith("total sales") for c in row)


def _is_market_agent_row(row: list[str]) -> bool:
    filled = [c for c in (clean(x) for x in row) if c]
    return len(filled) == 2 and not looks_like_date(filled[0])


def _last_filled(row: list[str]) -> str:
    return next((clean(c) for c in reversed(row) if clean(c)), "")


def _read_csv_record(
    row: list[str], number: int, market: str | None, agent: str | None, log: ProblemLog
) -> PaymentRecord:
    record = PaymentRecord(
        account_sale_number=cell(row, 2) or None,
        fms_id=cell(row, 0) or None,
        supplier_ref=cell(row, 1) or None,
        date_paid=parse_date(cell(row, 3)),
        nett_payment=parse_money(cell(row, 4)),
        total_deductions=parse_money(cell(row, 5)),
        deduction_vat=parse_money(cell(row, 6)),
        gross_payment=parse_money(cell(row, 7)),
        payment_reference=cell(row, 8) or None,
        market=market,
        agent=agent,
        line_number=number,
    )
    if record.account_sale_number is None:
        log.warn("Payment record carries no account sale number.", number, ",".join(row))
    return record


# --- The laid-out text shape -------------------------------------------------------------------


def _parse_text(text: str, log: ProblemLog) -> ParseResult:
    lines = text.split("\n")
    result = ParseResult(kind=KIND, scope=read_scope_header(lines, log))

    market: str | None = None
    agent: str | None = None
    current: PaymentRecord | None = None
    pending_commodity: str | None = None

    for number, raw in enumerate(lines, start=1):
        line = clean(raw)
        if not line or _is_text_column_header(line):
            continue

        record = _TEXT_RECORD.match(line)
        if record:
            current = _read_text_record(record, number, market, agent, log, raw)
            result.payments.append(current)
            pending_commodity = None
            continue

        commodity = _TEXT_COMMODITY.match(line)
        if commodity and current is not None and pending_commodity is not None:
            figures = find_money(commodity.group("rest"))
            if len(figures) >= 3:
                current.commodities.append(
                    CommodityLine(
                        commodity=pending_commodity,
                        delivered=figures[0],
                        sold=figures[1],
                        sales_total=figures[-1],
                        line_number=number,
                    )
                )
            else:
                log.warn("Commodity line is missing figures.", number, raw)
            pending_commodity = None
            continue

        if _looks_like_market_agent(line):
            market, agent = _read_market_agent(line)
            continue

        if _is_money_only(line):
            if current is not None:
                current.stated_total_sales = find_money(line)[-1]
            continue

        if current is not None:
            # A commodity name on its own line, with its figures on the next. Deliberately not
            # gated on the line being free of digits: pack sizes are part of the product name --
            # `... STANDARD CARTON 15kg` -- and testing for digits drops the commodity entirely.
            pending_commodity = squeeze(line)
            continue

        log.warn("Line not recognised; nothing was taken from it.", number, raw)

    _check_payments(result, log)
    return result


def _read_text_record(
    match: re.Match[str],
    number: int,
    market: str | None,
    agent: str | None,
    log: ProblemLog,
    raw: str,
) -> PaymentRecord:
    figures = find_money(match.group("rest"))
    if len(figures) < 4:
        log.warn("Payment record is missing one of nett, deductions, VAT or gross.", number, raw)
    reference = match.group("rest").split()[-1] if match.group("rest").split() else ""
    return PaymentRecord(
        account_sale_number=match.group("accsale"),
        fms_id=match.group("fms"),
        supplier_ref=match.group("ref"),
        date_paid=parse_date(match.group("date")),
        nett_payment=figures[0] if len(figures) > 0 else None,
        total_deductions=figures[1] if len(figures) > 1 else None,
        deduction_vat=figures[2] if len(figures) > 2 else None,
        gross_payment=figures[3] if len(figures) > 3 else None,
        payment_reference=reference if reference and not reference[0].isdigit() else None,
        market=market,
        agent=agent,
        line_number=number,
    )


def _is_text_column_header(line: str) -> bool:
    # Squeezed, because the column headings are aligned with runs of spaces:
    # `Nett    Total   Deduction Gross Pay.` is one heading, not four values.
    lowered = squeeze(line).lower()
    return any(
        marker in lowered
        for marker in (
            "fms id",
            "nett total deduction",
            "payments deductions",
            "line no",
            "report:",
            "report ",
            "market:",
            "agent:",
            "date range:",
            "zaco agents",
        )
    )


def _is_money_only(line: str) -> bool:
    """A block total such as `R 1,500.00` sitting alone on its own line."""
    return bool(_MONEY_ONLY.fullmatch(line))


_MONEY_ONLY = re.compile(r"R?\s*[\d ,.]+", re.UNICODE)


def _looks_like_market_agent(line: str) -> bool:
    if ":" in line or find_money(line):
        return False
    return len(re.split(r"\s{3,}", line.strip())) == 2


def _read_market_agent(line: str) -> tuple[str | None, str | None]:
    left, right = (p.strip() for p in re.split(r"\s{3,}", line.strip(), maxsplit=1))
    return squeeze(left) or None, squeeze(right) or None


def _check_payments(result: ParseResult, log: ProblemLog) -> None:
    for record in result.payments:
        label = record.account_sale_number or record.fms_id or "?"
        if not record.has_commodity_breakdown:
            # AccSale 382999 in the supplied data. Section 8 requires this be reported rather
            # than quietly dropped, because its money is real even though it cannot reconcile.
            log.warn(
                f"Account sale {label} carries a gross of R{record.gross_payment} and a nett of "
                f"R{record.nett_payment} but no commodity lines at all. It can never be "
                "reconciled against the sales side.",
                record.line_number,
            )
            continue

        total = sum(
            (c.sales_total for c in record.commodities if c.sales_total is not None),
            start=type(record.commodities[0].sales_total or 0)(0),
        )
        if record.stated_total_sales is not None and total != record.stated_total_sales:
            log.warn(
                f"Account sale {label}: its commodity lines total R{total} but the report prints "
                f"R{record.stated_total_sales}.",
                record.line_number,
            )
