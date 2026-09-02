"""Reading the values these exports actually contain.

Every function here returns `None` rather than a substitute when it cannot read something.
Section 2 is explicit that a missing fact is never invented, and a zero standing where a figure
could not be read is exactly the quietly wrong number section 11 warns about.

What the supplied documents actually do, all of it real:

* three date formats, plus `0000-00-00`, which is not a date at all
* thousands separated by a comma, by a no-break space, or by a plain space -- and the first two
  appear on the *same line* of `PaymentDetails_20260603-20260608.txt`
* money prefixed `R`, sometimes spaced away from the digits, sometimes negative
* one CSV carrying a UTF-8 byte order mark, and another whose every line is wrapped in a further
  pair of quotes so that the whole row reads as a single field

The odd space characters are built with `chr()` rather than written as literals on purpose: an
invisible character inside a regular expression is the kind of thing a later reformat deletes
without anyone noticing, and the money parser would then quietly stop reading `R 1 500.00`.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from zaco.ingest.problems import ProblemLog

NO_BREAK_SPACE = chr(0x00A0)
FIGURE_SPACE = chr(0x2007)
NARROW_NO_BREAK_SPACE = chr(0x202F)
THIN_SPACE = chr(0x2009)

#: Normalised to a plain space before anything else looks at a line.
ODD_SPACES = (NO_BREAK_SPACE, FIGURE_SPACE, NARROW_NO_BREAK_SPACE, THIN_SPACE, "\t")

#: Every thousands separator seen in the data, plus the plain space.
THOUSANDS_SEPARATORS = (",", NO_BREAK_SPACE, THIN_SPACE, " ")

# A separated group is always exactly three digits, which is what stops `R 6 000.00` reading as
# two numbers and `R 1 500.00 EFT` from swallowing the payment reference.
_GROUP_SEPARATORS = "".join(re.escape(s) for s in THOUSANDS_SEPARATORS)
MONEY = re.compile(
    rf"""
    (?P<currency>R\s*)?                              # optional R prefix
    (?P<sign>-\s*)?                                  # minus, sometimes spaced off the digits
    (?P<number>
        \d{{1,3}}(?:[{_GROUP_SEPARATORS}]\d{{3}})+   # grouped: 1,275.00 / 1 500.00
        (?:\.\d+)?
      | \d+(?:\.\d+)?                                # plain: 340.00 / 2 / 0.00
    )
    """,
    re.VERBOSE,
)

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TRAILING_ISO_DATE = re.compile(r"(?P<head>.*?)(?P<date>\d{4}-\d{2}-\d{2})\s*$")

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")
_DATETIME_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S")


def read_text(data: bytes, log: ProblemLog) -> str:
    """Decode a document, saying which encoding was used when it was not the obvious one."""
    if data.startswith(b"\xef\xbb\xbf"):
        log.note("File begins with a UTF-8 byte order mark; it was stripped.")
        data = data[3:]
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding != "utf-8":
            log.warn(f"File is not valid UTF-8; read as {encoding}. Check unusual characters.")
        return text.replace("\r\n", "\n").replace("\r", "\n")
    log.error("File could not be decoded as text in any supported encoding.")
    return ""


def clean(value: str | None) -> str:
    """Normalise the odd whitespace these exports use, without collapsing internal spacing."""
    if value is None:
        return ""
    for odd in ODD_SPACES:
        value = value.replace(odd, " ")
    return value.strip()


def squeeze(value: str | None) -> str:
    """As `clean`, but collapsing runs of spaces. For labels and names, never for figures."""
    return re.sub(r"\s{2,}", " ", clean(value))


def parse_money(raw: str | None) -> Decimal | None:
    """Read one money value. Returns None if there is not exactly one to read."""
    text = clean(raw)
    if not text:
        return None
    match = MONEY.fullmatch(text)
    return None if match is None else _to_decimal(match)


def find_money(raw: str | None) -> list[Decimal]:
    """Every money value on a line, in order. The text reports are laid out, not delimited."""
    return [_to_decimal(m) for m in MONEY.finditer(clean(raw))]


def _to_decimal(match: re.Match[str]) -> Decimal:
    digits = match.group("number")
    for separator in THOUSANDS_SEPARATORS:
        digits = digits.replace(separator, "")
    value = Decimal(digits)
    return -value if match.group("sign") else value


def parse_quantity(raw: str | None) -> Decimal | None:
    """Quantities are cartons. A negative one is a return (section 6), not an error."""
    text = clean(raw)
    if not text:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def parse_date(raw: str | None) -> date | None:
    """Read a date in any format these exports use.

    `0000-00-00` is not a date, and it is certainly not today, so it reads as absent. What an
    absent date means is the caller's decision; this refuses to invent one.
    """
    text = clean(raw)
    if not text or set(text) <= {"0", "-", "/"}:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    stamp = parse_datetime(text)
    return stamp.date() if stamp else None


def parse_datetime(raw: str | None) -> datetime | None:
    text = clean(raw)
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def split_trailing_date(token: str) -> tuple[str, date | None]:
    """Separate a value from a date jammed against it with no delimiter.

    `NettPaymentAdjustments_202604.txt` contains `JOH*SUB*5640001/12026-04-13`: an account sale
    reference and its date run together. Splitting on whitespace loses the date and corrupts the
    reference, so the date is peeled off the end explicitly.
    """
    match = _TRAILING_ISO_DATE.fullmatch(clean(token))
    if match is None:
        return clean(token), None
    return match.group("head").strip(), parse_date(match.group("date"))


def looks_like_date(token: str) -> bool:
    return bool(_ISO_DATE.fullmatch(clean(token)))


def read_csv_rows(text: str) -> list[list[str]]:
    """Parse CSV, undoing the extra layer of quoting one of the exports applies.

    `DailySalesDetail_20260525-20260531.csv` wraps every line in a further pair of quotes, so a
    correct CSV reader sees one field per line holding the real, comma-separated row. The same
    export a week later does not do this. Both have to read the same way.
    """
    rows: list[list[str]] = []
    for row in csv.reader(text.splitlines()):
        if len(row) == 1 and "," in row[0]:
            inner = next(csv.reader([row[0]]), None)
            rows.append(inner if inner is not None else row)
        else:
            rows.append(row)
    return rows


def is_blank_row(row: list[str]) -> bool:
    return all(not clean(item) for item in row)


def cell(row: list[str], index: int) -> str:
    """Read a cell leniently: a short row is missing data, not a crash."""
    return clean(row[index]) if 0 <= index < len(row) else ""
