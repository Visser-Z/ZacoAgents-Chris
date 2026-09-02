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

LIVE = Path(__file__).resolve().parent.parent / "workbook" / "account-sales-book.xlsx"


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
