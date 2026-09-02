"""The value hazards these exports actually contain.

Every case here was taken from a file in `data/`, not invented. A parser that only passes on
tidy input has not been tested.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from zaco.ingest.problems import ProblemLog, Severity
from zaco.ingest.values import (
    NO_BREAK_SPACE,
    find_money,
    parse_date,
    parse_money,
    parse_quantity,
    read_csv_rows,
    read_text,
    split_trailing_date,
    squeeze,
)


class TestMoney:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("340.00", "340.00"),
            ("R 170.00", "170.00"),
            ("R 1,275.00", "1275.00"),
            (f"R 1{NO_BREAK_SPACE}500.00", "1500.00"),  # PaymentDetails txt
            ("R 6 000.00", "6000.00"),  # NettPaymentAdjustments
            ("R -200.00", "-200.00"),  # a return
            ("-200.00", "-200.00"),
            ("0.00", "0.00"),
        ],
    )
    def test_every_separator_and_sign_in_the_data(self, raw: str, expected: str) -> None:
        assert parse_money(raw) == Decimal(expected)

    def test_two_separators_on_one_line(self) -> None:
        # Line 12 of PaymentDetails_20260603-20260608.txt, verbatim in shape: a comma-grouped
        # figure and a no-break-space-grouped one in the same record.
        line = f"R 1,275.00 R 195.65 R 29.35 R 1{NO_BREAK_SPACE}500.00 EFT"
        assert find_money(line) == [
            Decimal("1275.00"),
            Decimal("195.65"),
            Decimal("29.35"),
            Decimal("1500.00"),
        ]

    def test_a_space_grouped_figure_is_one_number_not_two(self) -> None:
        # The failure this guards: `R 6 000.00` reading as 6 and 0.00, which would understate a
        # payment by three orders of magnitude and still look like a plausible figure.
        assert find_money("R 6 000.00 R 782.61") == [Decimal("6000.00"), Decimal("782.61")]

    def test_a_trailing_word_is_not_swallowed(self) -> None:
        assert find_money(f"R 1{NO_BREAK_SPACE}500.00 EFT") == [Decimal("1500.00")]

    def test_unreadable_money_is_none_not_zero(self) -> None:
        # Section 2: a missing fact is never invented. A zero here would read as a real figure.
        assert parse_money("n/a") is None
        assert parse_money("") is None
        assert parse_money(None) is None


class TestDates:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-05-27", date(2026, 5, 27)),  # Daily Sales Detail
            ("29/05/2026", date(2026, 5, 29)),  # account sales statement
            ("2026/05/25", date(2026, 5, 25)),  # report header date range
            ("2026/06/09 09:14:02", date(2026, 6, 9)),  # run date
        ],
    )
    def test_the_three_formats_plus_a_timestamp(self, raw: str, expected: date) -> None:
        assert parse_date(raw) == expected

    def test_the_null_date_is_absent_not_a_date(self) -> None:
        # `0000-00-00` appears in DailySalesDetail_20260601-20260608.csv against a docket that
        # has sold but not yet been paid. Reading it as any date at all invents a payment.
        assert parse_date("0000-00-00") is None

    def test_rubbish_is_absent(self) -> None:
        assert parse_date("not a date") is None
        assert parse_date("") is None


class TestJammedTokens:
    def test_an_account_sale_and_date_run_together(self) -> None:
        # NettPaymentAdjustments_202604.txt, line 9. Splitting on whitespace gives
        # `JOH*SUB*5640001/12026-04-13` as one token, corrupting the reference and losing the
        # date entirely.
        assert split_trailing_date("JOH*SUB*5640001/12026-04-13") == (
            "JOH*SUB*5640001/1",
            date(2026, 4, 13),
        )

    def test_the_suffix_survives(self) -> None:
        # /1 and /2 are two separate April payment runs worth R5,100 and R3,230. A parser that
        # loses the suffix merges R8,330 into one statement number.
        first, _ = split_trailing_date("JOH*SUB*5640001/12026-04-13")
        second, _ = split_trailing_date("JOH*SUB*5640001/22026-04-15")
        assert first != second

    def test_a_token_with_no_trailing_date_is_left_alone(self) -> None:
        assert split_trailing_date("PRE*BT*380101") == ("PRE*BT*380101", None)


class TestEncoding:
    def test_a_byte_order_mark_is_stripped_and_reported(self) -> None:
        log = ProblemLog()
        text = read_text("﻿Delivery Date,Date Sold".encode(), log)
        assert text.startswith("Delivery Date")
        assert any("byte order mark" in p.message for p in log.items)

    def test_windows_line_endings_are_normalised(self) -> None:
        assert read_text(b"a\r\nb\r\n", ProblemLog()) == "a\nb\n"

    def test_a_non_utf8_file_is_read_and_the_fallback_is_reported(self) -> None:
        log = ProblemLog()
        text = read_text("Ndlovu café".encode("cp1252"), log)
        assert "caf" in text
        assert any(p.severity is Severity.WARNING for p in log.items)


class TestCsvQuoting:
    def test_the_extra_layer_of_quoting_is_undone(self) -> None:
        # DailySalesDetail_20260525-20260531.csv wraps every line in a further pair of quotes,
        # so a correct CSV reader sees one field holding the real row.
        rows = read_csv_rows('"Consignment ID :,118069901Z"\n')
        assert rows[0] == ["Consignment ID :", "118069901Z"]

    def test_an_ordinary_row_is_untouched(self) -> None:
        rows = read_csv_rows("Consignment ID :,118069901Z\n")
        assert rows[0] == ["Consignment ID :", "118069901Z"]

    def test_a_genuinely_single_field_row_is_not_split(self) -> None:
        assert read_csv_rows("just one field\n")[0] == ["just one field"]


class TestQuantities:
    def test_a_negative_quantity_is_a_return_not_an_error(self) -> None:
        assert parse_quantity("-1") == Decimal("-1")

    def test_unreadable_quantity_is_none(self) -> None:
        assert parse_quantity("lots") is None


def test_squeeze_collapses_layout_spacing_but_clean_does_not() -> None:
    assert squeeze("TSHWANE MARKET      Farmers Trust") == "TSHWANE MARKET Farmers Trust"
