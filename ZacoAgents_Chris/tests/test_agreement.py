"""Holding what the record claims against what the book actually holds.

An append cannot leave the two disagreeing -- it marks the round and writes the file in one
step. A *rollback* can, and deliberately does: it restores the file and leaves the round's
appended mark alone, because the rows may or may not be in the version restored. These pin the
reporting of that gap, which changes nothing and decides nothing.
"""

from __future__ import annotations

from zaco.workbook.agreement import CHECKED, Agreement, RowClaim, compare, contested
from zaco.workbook.locate import BookRow


def _book(*rows: tuple[int, str | None, str | None, str | None]) -> list[BookRow]:
    return [
        BookRow(row_number=n, dn=dn, stm_no=stm, description=desc, date=None)
        for n, dn, stm, desc in rows
    ]


def _claim(n: int, dn: str | None, stm: str, desc: str) -> RowClaim:
    return RowClaim(row_number=n, dn=dn, stm_no=stm, description=desc)


def test_a_book_still_holding_the_rows_agrees() -> None:
    claims = [_claim(5, "14930", "390100", "Eureka lemons 15kg")]
    result = compare(claims, _book((5, "14930", "390100", "Eureka lemons 15kg")))

    assert result.agrees
    assert result.finding is None
    assert result.checked == CHECKED


def test_the_limits_of_the_check_travel_with_every_result() -> None:
    """Section 10: a panel that only reports what it can check reads as a clean bill of health."""
    agreed = compare([_claim(5, "1", "2", "x")], _book((5, "1", "2", "x")))
    disagreed = compare([_claim(5, "1", "2", "x")], _book((5, "9", "2", "x")))

    for result in (agreed, disagreed):
        assert "figures in those rows are not compared" in result.checked


def test_a_rollback_that_removed_every_row_is_reported_as_such() -> None:
    claims = [_claim(5, "14930", "390100", "lemons"), _claim(6, "14930", "390110", "lemons")]

    result = compare(claims, _book((2, "14690", "381900", "apples")))

    assert not result.agrees
    assert result.finding is not None
    assert "rows 5-6" in result.finding
    assert "no rows there at all" in result.finding
    assert "rollback" in result.finding


def test_a_part_of_a_round_missing_names_the_rows() -> None:
    claims = [_claim(5, "1", "390100", "lemons"), _claim(6, "1", "390110", "lemons")]

    result = compare(claims, _book((5, "1", "390100", "lemons")))

    assert not result.agrees
    assert result.finding is not None
    assert "missing 1 of the 2 rows" in result.finding
    assert "6" in result.finding


def test_rows_that_read_as_someone_elses_name_both_causes() -> None:
    """A difference is a rollback *or* a corrected reader, and the two need telling apart."""
    claims = [_claim(5, "14930", "390100", "lemons")]

    result = compare(claims, _book((5, "14999", "390100", "lemons")))

    assert not result.agrees
    assert result.finding is not None
    assert "rolled back" in result.finding
    assert "reader has been corrected" in result.finding


def test_a_blank_cell_and_an_absent_one_are_the_same_thing() -> None:
    """Column A is deliberately empty on a row carried for another producer (D11)."""
    result = compare([_claim(5, None, "390100", "lemons")], _book((5, "", "390100", "lemons")))

    assert result.agrees


def test_a_round_claiming_no_rows_says_so_rather_than_passing_quietly() -> None:
    result = compare([], _book((5, "1", "2", "x")))

    assert result.agrees
    assert "nothing to compare" in result.checked


def test_two_rounds_cannot_both_own_a_row() -> None:
    found = contested({1: (5, 9), 2: (8, 12), 3: (20, 21)})

    assert set(found) == {1, 2}
    assert "#2" in found[1]
    assert "#1" in found[2]
    assert 3 not in found


def test_spans_that_merely_touch_do_not_clash() -> None:
    assert contested({1: (5, 9), 2: (10, 14)}) == {}


def test_an_agreement_carries_the_default_statement_unless_given_one() -> None:
    assert Agreement(agrees=True, finding=None).checked == CHECKED
