"""Writing resolved rows into the operator's live book (section 5).

Three rules shape everything here.

**Nothing is located by position.** The brief describes 21 columns, A to U. The operator's real
book has 23: `Buyer note` at C and `Packhouse` at V push every letter after B along, so `Baby
Stock` is `=I{r}-K{r}` in the live file and not the `=H{r}-J{r}` the brief prints. Formulas are
therefore built from letters `locate()` resolved, never from letters written down here.

**A computed value is never written into a formula column.** Eight columns belong to the
operator. The system writes the formula for the new row number and lets Excel do the arithmetic,
so an operator who corrects one input sees everything downstream follow.

**Rows are appended, never rebuilt.** The `NOTES` column -- the operator's own margin -- is not
read, not derived and not written.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from zaco.domain.model import display_account_sale
from zaco.workbook import snapshot
from zaco.workbook.locate import SheetLayout, WorkbookShapeError, locate

#: The eight columns that belong to the operator, written as formulas for the new row number.
#: The placeholders are *field names*; the letters are filled in from the book being written.
FORMULAS: dict[str, str] = {
    "frui_price_per_crt": '=IFERROR({nett_price_per_crt}{r}*70%,"-")',
    "baby_stock": "={opening_stock}{r}-{cartons_sold}{r}",
    "gross_total": "=SUM({cartons_sold}{r}*{price}{r})",
    "nett_price_per_crt": '=IFERROR({nett_total}{r}/{cartons_sold}{r},"-")',
    "z_rand_per_crt": '=IFERROR({nett_price_per_crt}{r}-{frui_price_per_crt}{r},"-")',
    "z_total": "={nett_total}{r}-{frui_curr_sales_value}{r}",
    "markup_percent": '=IFERROR({z_rand_per_crt}{r}/{nett_price_per_crt}{r},"-")',
    "frui_curr_sales_value": "={frui_price_per_crt}{r}*{cartons_sold}{r}",
}

#: The operator's own margin. Read back and written back unchanged means: left alone entirely.
NEVER_WRITTEN = frozenset({"notes"})

#: What the price column is rounded to before it is written.
#:
#: Not a stylistic choice. `openpyxl` converts a `Decimal` to a float on the way into the file,
#: so `400 / 3` -- an exact 28-digit Decimal in this system -- is stored as
#: `133.33333333333331` and the tail is gone whatever we do. Excel keeps 15 significant digits
#: of its own, so there is no precision here to protect: rounding to the five decimals this
#: column already displays writes a number that survives the round trip exactly, instead of one
#: that changes quietly between the system and the file.
#:
#: Money itself is untouched by this. Every other currency column is two decimals and exact.
PRICE_PLACES = Decimal("0.00001")

#: Below half a cent the money columns round identically, so the difference is not worth saying.
WORTH_SAYING = Decimal("0.005")

INCOMPLETE = "Incomplete"


class AppendRefusedError(Exception):
    """The append was not attempted, and the file was not opened."""


@dataclass
class PlannedRow:
    """One row as it will be written, before any of it touches the file."""

    delivery_id: str | None
    consignment_id: str | None
    product: str
    account_sale: str
    values: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    """Why a cell is blank, where blank was a decision rather than an absence."""


@dataclass
class AppendPlan:
    rows: list[PlannedRow] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    """Reasons the whole append cannot proceed. Non-empty means nothing is written."""

    @property
    def is_writable(self) -> bool:
        return bool(self.rows) and not self.refusals


@dataclass
class AppendResult:
    first_row: int
    last_row: int
    saved_as: snapshot.Snapshot
    sheet_name: str
    letters: dict[str, str]


def _number_or_text(value: str | None) -> object | None:
    """D7: the bare number where one exists, the full reference where it does not.

    `382405` goes in as a number so it sorts and filters beside the operator's existing rows;
    `5644200/1` goes in as text, because dropping the suffix would merge two separate April
    payment runs worth R5,100 and R3,230 into one.
    """
    if value is None:
        return None
    return int(value) if value.isdigit() else value


def plan(resolved: Any) -> AppendPlan:
    """Work out every cell, and every reason not to write one, without opening the workbook."""
    from zaco.db.models import RoundStatus

    built = AppendPlan()
    if resolved.round.status not in (RoundStatus.RESOLVED.value, RoundStatus.APPENDED.value):
        built.refusals.append(
            f"Round {resolved.round.id} is {resolved.round.status}. Only a round whose queue has "
            "been closed can be appended."
        )
    if resolved.round.appended_at is not None:
        built.refusals.append(
            f"Round {resolved.round.id} was already appended on "
            f"{resolved.round.appended_at:%d %b %Y at %H:%M}. Rows are appended, never rebuilt, "
            "so appending it again would write every row a second time."
        )
    if not resolved.is_clear:
        built.refusals.append(resolved.blocking_reason or "The queue is still open.")

    staged = resolved.staged
    # A delivery sends its cartons once. Writing `Qty Received` on both rows of a consignment
    # that sold under two account sales would double it in every column that sums.
    counted: set[str] = set()
    rows_per_sale: dict[str, int] = {}
    for row in staged.rows:
        rows_per_sale[row.account_sale] = rows_per_sale.get(row.account_sale, 0) + 1

    for row in staged.rows:
        note = resolved.approved.get(row.delivery_id or "")
        blocked = []
        if note is None:
            blocked.append(f"{row.delivery_id or '(no delivery)'} has no approved delivery note")
        if row.product.short_code is None:
            blocked.append(f"{row.product.display_name} has no short code")
        built.refusals.extend(blocked)
        if blocked or note is None:
            continue

        position = resolved.ledger.for_row(row)
        sale = staged.account_sales.get(row.account_sale)
        planned = PlannedRow(
            delivery_id=row.delivery_id,
            consignment_id=row.consignment_id,
            product=row.product.display_name,
            account_sale=row.account_sale,
        )

        planned.values["dn"] = _number_or_text(note.dn) if note.dn else None
        if not note.dn:
            planned.notes.append(
                f"No delivery note, recorded: {note.operator_reason or note.reasoning}"
            )
        planned.values["market_agent"] = row.agent
        planned.values["completed"] = INCOMPLETE
        planned.values["date"] = (
            resolved.grouping_dates.get(note.dn) if note.dn else None
        ) or row.earliest_date
        # Through `display_account_sale` even when no payment run accounts for the row: the
        # column is the operator's STM No either way, and `PRE*BT*390100` sitting between two
        # bare numbers is the sort of thing that stops a filter working.
        planned.values["stm_no"] = _number_or_text(display_account_sale(row.account_sale))
        planned.values["description"] = row.product.short_code

        # What was sent belongs to the consignment, not to the row. A consignment that sold under
        # two account sales makes two rows, and writing its cartons on both would double them in
        # every column that sums; a delivery holding two products makes two consignments, and
        # writing the delivery's total on each would double them again the other way.
        consignment_id = row.consignment_id or ""
        consignment = next(
            (c for c in staged.consignments if c.consignment_id == consignment_id), None
        )
        if consignment_id and consignment_id not in counted:
            counted.add(consignment_id)
            sent = consignment.qty_sent if consignment is not None else None
            planned.values["qty_received"] = sent
            if sent is None:
                # Absent is not zero (section 6). The consignment report carries what was sent
                # and the daily sales file does not, so a round without one simply does not know.
                planned.notes.append(
                    "Qty Received is blank: no document in this round says what this consignment "
                    "was sent. That is absent, not nought."
                )
        else:
            planned.values["qty_received"] = None
            planned.notes.append(
                "Qty Received is on the first row of this consignment only; what was sent is sent "
                "once, however many account sales it sells under."
            )

        planned.values["opening_stock"] = position.opening if position else None
        planned.values["cartons_sold"] = row.cartons.net
        planned.values["price"] = _priced(row, planned)

        # Nett is the payment side's figure for the whole account sale. Splitting one across
        # several rows is section 8's job and has to sum to the payment exactly, so it is left
        # for Phase 5 rather than guessed at here.
        if sale is not None and sale.nett is not None and rows_per_sale[row.account_sale] == 1:
            planned.values["nett_total"] = sale.nett
        else:
            planned.values["nett_total"] = None
            if sale is not None and sale.nett is not None:
                planned.notes.append(
                    f"Nett Total left blank: {sale.display_number} pays R{sale.nett:,.2f} across "
                    f"{rows_per_sale[row.account_sale]} rows, and apportioning it is section 8."
                )
            else:
                planned.notes.append("Nett Total left blank: no payment run accounts for this row.")

        paid = sale.date_paid if sale else None
        planned.values["status"] = f"{paid:%d.%m}" if paid else None

        built.rows.append(planned)

    if not built.rows and not built.refusals:
        built.refusals.append("This round produced no rows, so there is nothing to append.")
    return built


def _priced(row: Any, planned: PlannedRow) -> Decimal | None:
    """The price, rounded to what the column carries, saying so when the money no longer lands.

    Section 5 asks for a price such that `Cartons Sold * Price` recovers the money. Where the
    value does not divide by the cartons -- R400 across 3 -- no price at any precision does that,
    and the row that says so is worth more than a figure that looks exact and is not.
    """
    price = row.price
    if price is None:
        return None
    rounded: Decimal = price.quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)
    shortfall: Decimal = row.value - (rounded * row.cartons.net)
    if abs(shortfall) >= WORTH_SAYING:
        planned.notes.append(
            f"Cartons Sold x Price recovers R{rounded * row.cartons.net:,.2f} against the "
            f"R{row.value:,.2f} the dockets show, R{abs(shortfall):,.2f} out: "
            f"R{row.value:,.2f} does not divide by {row.cartons.net:g} cartons at any price."
        )
    return rounded


def _last_written_row(sheet: Any, layout: SheetLayout) -> int:
    """The last row with anything in it, ignoring the blank tail Excel leaves behind."""
    last = layout.header_row
    for row_number in range(sheet.max_row, layout.header_row, -1):
        if any(sheet.cell(row_number, c).value is not None for c in range(1, sheet.max_column + 1)):
            last = row_number
            break
    return last


def _formula(field_name: str, layout: SheetLayout, row_number: int) -> str | None:
    """Build one formula from the letters this book actually uses.

    Returns `None` when a column the formula points at is missing, because a formula referring to
    a column that is not there is worse than an empty cell: it opens as `#REF!` and looks like
    corruption in a file the business settles money against.
    """
    letters = {name: letter for name in layout.columns if (letter := layout.letter(name))}
    try:
        return FORMULAS[field_name].format(r=row_number, **letters)
    except KeyError:
        return None


def append(path: Path, built: AppendPlan, label: str = "") -> AppendResult:
    """Snapshot, write, and either keep both or neither (D4).

    The copy is taken first and put back if anything goes wrong, so a half-written book is not a
    state this can leave behind. The caller holds the database transaction open across this call
    and rolls it back on the exception, which is what keeps "appended" and "actually in the file"
    the same answer.
    """
    if not built.is_writable:
        raise AppendRefusedError("; ".join(built.refusals) or "There is nothing to append.")
    if not path.exists():
        raise AppendRefusedError(f"There is no workbook at {path}. Nothing was written.")

    layout = locate(path)
    saved = snapshot.take(path, label=label or "before append")
    temporary = path.with_suffix(".appending.xlsx")
    try:
        workbook = load_workbook(path, data_only=False)
        try:
            sheet = workbook[layout.sheet_name]
            template_row = _last_written_row(sheet, layout)
            start = template_row + 1

            for offset, planned in enumerate(built.rows):
                row_number = start + offset
                for name, index in layout.columns.items():
                    if name in NEVER_WRITTEN:
                        continue
                    cell = sheet.cell(row_number, index)
                    if name in FORMULAS:
                        formula = _formula(name, layout, row_number)
                        if formula is not None:
                            cell.value = formula
                    else:
                        cell.value = _cell_value(planned.values.get(name))
                    if template_row > layout.header_row:
                        # Number formats must match the existing sheet: the price column carries
                        # five decimals and the date column `d-mmm`, and a row that renders
                        # differently from its neighbours reads as an error in the figures.
                        cell.number_format = sheet.cell(template_row, index).number_format

            workbook.save(temporary)
        finally:
            workbook.close()
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        if saved.path.exists():
            os.replace(saved.path, path)
        raise
    snapshot.prune()
    return AppendResult(
        first_row=start,
        last_row=start + len(built.rows) - 1,
        saved_as=saved,
        sheet_name=layout.sheet_name,
        letters={name: layout.letter(name) or "" for name in layout.columns},
    )


def _cell_value(value: object) -> object:
    """openpyxl writes `Decimal` as a number of its own accord, so nothing here becomes a float."""
    if value is None or isinstance(value, (Decimal, int, str, date)):
        return value
    return str(value)


__all__ = [
    "FORMULAS",
    "AppendPlan",
    "AppendRefusedError",
    "AppendResult",
    "PlannedRow",
    "WorkbookShapeError",
    "append",
    "plan",
]
