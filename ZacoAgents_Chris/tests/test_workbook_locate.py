"""Finding the data sheet and its columns by header text, against the operator's real book.

The brief describes 21 columns, A to U. The real file has 23, with `Buyer note` inserted at C
and `Packhouse` at V, and the data on the *third* sheet. Every column letter in the brief is
therefore wrong, and a system that indexes by letter writes a book that opens without complaint
and has the price under the description.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from zaco.resolve import book as book_reader
from zaco.workbook.locate import WorkbookShapeError, locate, read_rows

#: The operator's book as it stood before this system touched it. Deliberately not
#: `workbook/account-sales-book.xlsx`: that file is a deliverable committed with both rounds
#: processed into it, so it grows. A fixture that moves is not a fixture.
LIVE = Path(__file__).resolve().parent / "fixtures" / "account-sales-book.pristine.xlsx"


def test_the_data_sheet_is_found_even_though_it_is_third() -> None:
    layout = locate(LIVE)
    assert layout.sheet_name == "Sheet1"
    assert layout.header_row == 1


def test_the_columns_are_where_the_file_says_and_not_where_the_brief_says() -> None:
    """`Baby Stock` is `=I-K` in the live book, not the `=H-J` the brief describes."""
    layout = locate(LIVE)
    assert layout.letter("dn") == "A"
    assert layout.letter("opening_stock") == "I"
    assert layout.letter("cartons_sold") == "K"
    assert layout.letter("baby_stock") == "L"
    assert layout.letter("notes") == "W"


def test_the_two_columns_the_brief_never_mentions_are_seen_and_left_alone() -> None:
    layout = locate(LIVE)
    assert set(layout.unknown_headers) == {"Buyer note", "Packhouse"}


def test_reordered_columns_are_handled_because_nothing_counts_positions() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(
        ["Description", "DN", "Cartons Sold", "STM No", "Qty Received", "Date", "Surprise"]
    )
    sheet.append(["Imp Cherries 5kg", 14690, 18, 381900, 20, "2026-05-18", "?"])
    path = Path(__file__).resolve().parent / "_reordered.xlsx"
    workbook.save(path)
    try:
        layout = locate(path)
        assert layout.letter("dn") == "B"
        assert layout.letter("description") == "A"
        rows = read_rows(path, layout)
        assert rows[0].dn == "14690"
        assert rows[0].description == "Imp Cherries 5kg"
    finally:
        path.unlink()


def test_a_workbook_with_no_header_row_is_refused_with_an_explanation() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["some", "prose", "about", "fruit"])
    path = Path(__file__).resolve().parent / "_headerless.xlsx"
    workbook.save(path)
    try:
        with pytest.raises(WorkbookShapeError) as refusal:
            locate(path)
        assert "recognisable header row" in str(refusal.value)
        assert "Nothing was written" in str(refusal.value)
    finally:
        path.unlink()


def test_a_number_in_column_a_is_read_as_text_without_a_trailing_point_zero() -> None:
    """`14690.0` matches no delivery note. Column A is a number in the live book."""
    assert [row.dn for row in read_rows(LIVE)] == ["14690", "14691", "14692"]


# --- what Phase 3 takes from the book ------------------------------------------------------------


def test_the_join_uses_the_account_sale_and_never_the_not_paid_marker() -> None:
    """Row 3 carries STM No `0`, the operator's own "not paid yet" marker (D7).

    Joined on, every unpaid row in the book would link to one delivery note.
    """
    knowledge = book_reader.read(LIVE)
    assert knowledge.links == {"381900": "14690", "381950": "14692"}
    assert "0" not in knowledge.links


def test_the_series_comes_from_every_delivery_note_in_the_book() -> None:
    knowledge = book_reader.read(LIVE)
    assert knowledge.delivery_notes == ["14690", "14691", "14692"]


def test_the_descriptions_are_offered_as_the_codes_the_operator_actually_types() -> None:
    knowledge = book_reader.read(LIVE)
    assert knowledge.short_codes == ["Imp Cherries 5kg", "IMP Nect", "Imp Pink Grapes"]


def test_a_missing_book_is_reported_rather_than_being_an_error() -> None:
    knowledge = book_reader.read(Path("nowhere/account-sales-book.xlsx"))
    assert knowledge.is_readable is False
    assert knowledge.links == {}
    assert "cannot be reused" in (knowledge.problem or "")


# --- reading the whole row, for drawing the book ------------------------------------------------


def test_the_rows_come_back_narrow_unless_the_whole_row_is_asked_for() -> None:
    """The DN join wants three fields. It should not pay for a second pass over the file."""
    rows = read_rows(LIVE)

    assert rows
    assert all(row.cells == {} and row.formulas == {} for row in rows)


def test_asking_for_the_whole_row_gives_every_column_keyed_by_its_letter() -> None:
    rows = read_rows(LIVE, with_cells=True)
    first = rows[0]

    assert first.cells["A"] == "14690"
    assert first.cells["B"] == "Farmers Trust"
    assert first.cells["F"] == "381900"
    assert first.cells["G"] == "Imp Cherries 5kg"


def test_the_operators_own_columns_come_back_too() -> None:
    """`NOTES` at W is never written and is exactly what the operator opens the book to read."""
    rows = read_rows(LIVE, with_cells=True)

    assert any(row.cells.get("W") for row in rows)


def test_a_formula_cell_carries_its_formula_and_shows_it() -> None:
    """openpyxl does not calculate, so an uncached formula must not read as an empty cell."""
    rows = read_rows(LIVE, with_cells=True)
    first = rows[0]

    assert first.formulas["L"] == f"=I{first.row_number}-K{first.row_number}"
    assert first.cells["L"] == first.formulas["L"]


def test_a_cell_that_is_genuinely_empty_stays_out_of_the_row() -> None:
    layout = locate(LIVE)
    rows = read_rows(LIVE, layout, with_cells=True)

    every = {letter for row in rows for letter in row.cells}
    assert "A" in every
    assert all(value != "" for row in rows for value in row.cells.values())


def test_the_narrow_fields_are_unchanged_by_asking_for_the_whole_row() -> None:
    """`resolve/book.py` reads these, so widening the row must not move them."""
    narrow = read_rows(LIVE)
    wide = read_rows(LIVE, with_cells=True)

    assert [(r.row_number, r.dn, r.stm_no, r.description) for r in narrow] == [
        (r.row_number, r.dn, r.stm_no, r.description) for r in wide
    ]
