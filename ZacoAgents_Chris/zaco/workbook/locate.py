"""Finding the data sheet and its columns by header text, never by position.

The brief describes 21 columns, A to U. The operator's actual book has **23**: `Buyer note` is
inserted at C and `Packhouse` at V, so every column letter in the brief is wrong for the real
file. The data is also on `Sheet1`, the *third* sheet, after `Cover` and `Rates`.

A system that indexes by letter appends a book that opens without complaint and has the price
under the description and the notes under the status. So nothing here counts columns: the
header row is read, and every column is found by the words in it. A workbook whose columns
have been reordered, or which has grown another one, keeps working. One with no recognisable
header row is refused with an explanation rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

#: Every column the system reads or writes, and the header text that identifies it. Matching is
#: case- and space-insensitive, because a header retyped by hand rarely comes back identical.
COLUMNS: dict[str, str] = {
    "dn": "DN",
    "market_agent": "Market Agent",
    "completed": "Completed",
    "date": "Date",
    "stm_no": "STM No",
    "description": "Description",
    "qty_received": "Qty Received",
    "opening_stock": "Opening Stock",
    "frui_price_per_crt": "Frui Price/crt",
    "cartons_sold": "Cartons Sold",
    "baby_stock": "Baby Stock",
    "price": "Price",
    "gross_total": "Gross Total",
    "nett_total": "Nett Total",
    "nett_price_per_crt": "Nett Price/crt",
    "z_rand_per_crt": "Z R/crt",
    "z_total": "Z Total",
    "markup_percent": "% Markup",
    "frui_curr_sales_value": "Frui Curr Sales Value",
    "status": "Status",
    "notes": "NOTES",
}

#: Without these there is no data sheet worth appending to, and a guess would be worse than a
#: refusal. Everything else in COLUMNS may legitimately be missing from an older book.
REQUIRED = ("dn", "date", "stm_no", "description", "qty_received", "cartons_sold")

MAX_HEADER_SEARCH_ROWS = 10


class WorkbookShapeError(Exception):
    """The file has no sheet that looks like the account sales book (section 5)."""


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


@dataclass(frozen=True)
class SheetLayout:
    """Where everything is in one particular book."""

    sheet_name: str
    header_row: int
    first_data_row: int
    last_data_row: int
    columns: dict[str, int]
    """Field name to 1-based column index, for the columns this book actually has."""

    unknown_headers: dict[str, int]
    """Columns the book has that the system does not write. `Buyer note` and `Packhouse` land
    here, and they are the reason nothing may be written by position."""

    headers: dict[str, str] = dc_field(default_factory=dict)
    """Field name to the header text **as this book writes it**.

    Kept rather than re-derived from `COLUMNS`, because the point of showing an operator where
    the columns went is to show them their own words. A book that says `STM NO` should say
    `STM NO` back, not the `STM No` this module happens to match against.
    """

    def index(self, field: str) -> int | None:
        return self.columns.get(field)

    def letter(self, field: str) -> str | None:
        column = self.columns.get(field)
        return None if column is None else get_column_letter(column)

    @property
    def row_count(self) -> int:
        return max(0, self.last_data_row - self.first_data_row + 1)


def _score_row(cells: list[Any]) -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    wanted = {_normalise(text): field for field, text in COLUMNS.items()}
    found: dict[str, int] = {}
    unknown: dict[str, int] = {}
    headers: dict[str, str] = {}
    for offset, value in enumerate(cells, start=1):
        text = _normalise(value)
        if not text:
            continue
        field = wanted.get(text)
        if field is not None and field not in found:
            found[field] = offset
            headers[field] = str(value).strip()
        elif field is None:
            unknown[str(value).strip()] = offset
    return found, unknown, headers


def locate(path: Path) -> SheetLayout:
    """Find the data sheet in a workbook, or refuse and say why.

    Every sheet is examined, not just the first, and the best-matching header row wins. That is
    what makes `Cover` and `Rates` sitting in front of the data a non-event rather than a bug.
    """
    workbook = load_workbook(path, data_only=False, read_only=True)
    try:
        best: SheetLayout | None = None
        best_score = 0
        for sheet in workbook.worksheets:
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=1, max_row=MAX_HEADER_SEARCH_ROWS, values_only=True),
                start=1,
            ):
                found, unknown, headers = _score_row(list(row))
                score = len(found)
                if score > best_score and all(field in found for field in REQUIRED):
                    best_score = score
                    best = SheetLayout(
                        sheet_name=sheet.title,
                        header_row=row_number,
                        first_data_row=row_number + 1,
                        last_data_row=max(sheet.max_row, row_number),
                        columns=found,
                        unknown_headers=unknown,
                        headers=headers,
                    )
        if best is None:
            raise WorkbookShapeError(
                f"{path.name} has no sheet with a recognisable header row. The system looks for "
                f"a row naming at least {', '.join(COLUMNS[f] for f in REQUIRED)}, in any order "
                "and on any sheet. Nothing was written."
            )
        return best
    finally:
        workbook.close()


@dataclass(frozen=True)
class BookRow:
    """One existing row of the operator's book, read leniently."""

    row_number: int
    dn: str | None
    stm_no: str | None
    description: str | None
    date: object | None


def _text(value: object) -> str | None:
    """Read a cell as text without caring what type it was stored as.

    Column A is a number in the live book and column E is sometimes a number and sometimes a
    reference like `5644200/1`, so anything that insists on a type here starts throwing on a
    real file. A float that is a whole number loses its `.0`, because `14690.0` matches nothing.
    """
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def read_rows(path: Path, layout: SheetLayout | None = None) -> list[BookRow]:
    """The existing rows, for the DN join and the series. Formulas are not evaluated."""
    layout = layout or locate(path)
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook[layout.sheet_name]
        rows: list[BookRow] = []
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=layout.first_data_row, values_only=True),
            start=layout.first_data_row,
        ):
            cells = list(row)

            def cell(field: str, cells: list[Any] = cells) -> object | None:
                index = layout.index(field) if layout else None
                return cells[index - 1] if index is not None and index <= len(cells) else None

            if all(value is None for value in cells):
                continue
            rows.append(
                BookRow(
                    row_number=row_number,
                    dn=_text(cell("dn")),
                    stm_no=_text(cell("stm_no")),
                    description=_text(cell("description")),
                    date=cell("date"),
                )
            )
        return rows
    finally:
        workbook.close()
