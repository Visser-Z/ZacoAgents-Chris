"""Shares that add back up to the payment, exactly (section 8).

"The shares must add up to the payment exactly. Rounding each share to the cent will not do that
on its own." These pin that, and the cases where no figure should be produced at all.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from zaco.money.allocate import CannotAllocateError, allocate


def d(text: str) -> Decimal:
    return Decimal(text)


def test_the_case_rounding_gets_wrong() -> None:
    """R100 across three equal rows is 33.33 each and a cent short. It must not be."""
    shares = allocate(d("100.00"), [d("1"), d("1"), d("1")])

    assert sum(shares) == d("100.00")
    assert shares == [d("33.34"), d("33.33"), d("33.33")]


def test_shares_follow_the_weights() -> None:
    shares = allocate(d("3724.00"), [d("3000"), d("1000")])

    assert sum(shares) == d("3724.00")
    assert shares == [d("2793.00"), d("931.00")]


@pytest.mark.parametrize(
    "total, weights",
    [
        ("0.01", ["1", "1", "1"]),
        ("0.02", ["1", "1", "1"]),
        ("1000.00", ["1", "2", "3", "5", "7", "11", "13"]),
        ("8025.00", ["900", "1925", "1200", "2100", "1900"]),
        ("0.03", ["0.001", "999999", "1"]),
        ("12345.67", ["1", "1", "1", "1", "1", "1", "1"]),
    ],
)
def test_the_shares_always_sum_to_the_payment(total: str, weights: list[str]) -> None:
    shares = allocate(d(total), [d(w) for w in weights])

    assert sum(shares) == d(total)
    assert all(share.as_tuple().exponent == -2 for share in shares)


def test_a_single_row_takes_the_whole_payment() -> None:
    assert allocate(d("2040.00"), [d("17")]) == [d("2040.00")]


def test_a_credit_is_split_the_same_way() -> None:
    """A payment run can be a credit. The sign must not disturb the remainder handling."""
    shares = allocate(d("-100.00"), [d("1"), d("1"), d("1")])

    assert sum(shares) == d("-100.00")
    assert shares == [d("-33.34"), d("-33.33"), d("-33.33")]


def test_the_same_input_always_gives_the_same_answer() -> None:
    """Section 9: the same history in gives the same answer out."""
    weights = [d("1"), d("1"), d("1"), d("1"), d("1"), d("1"), d("1")]

    assert allocate(d("100.00"), weights) == allocate(d("100.00"), weights)


def test_rows_worth_nothing_produce_no_figure() -> None:
    with pytest.raises(CannotAllocateError, match="no proportion"):
        allocate(d("500.00"), [d("0"), d("0")])


def test_a_negative_weight_produces_no_figure() -> None:
    """A row whose returns exceed its sales needs a person, not an apportionment."""
    with pytest.raises(CannotAllocateError, match="negative"):
        allocate(d("500.00"), [d("100"), d("-20")])


def test_no_rows_produces_no_figure() -> None:
    with pytest.raises(CannotAllocateError, match="no rows"):
        allocate(d("500.00"), [])
