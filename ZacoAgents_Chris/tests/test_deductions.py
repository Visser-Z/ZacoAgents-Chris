"""Splitting a statement's one printed Nett across its products (section 6).

The rule that costs money if it is missed: "a deduction named for a fruit lands only on the rows
for that fruit. Splitting a plum levy proportionally puts part of it on the grapes."

The first case is the real `AccountSales_382900.txt`, not an invented one.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from zaco.ingest.classifier import read_document
from zaco.ingest.records import AccountSalesStatement, Deduction, Docket, StatementProduct
from zaco.money.deductions import CannotSplitError, split_statement

DATA = Path(__file__).resolve().parent.parent / "data"


def d(text: str) -> Decimal:
    return Decimal(text)


@pytest.fixture
def statement_382900() -> AccountSalesStatement:
    parsed = read_document(DATA.joinpath("AccountSales_382900.txt").read_bytes())
    return parsed.statements[0]


def test_the_plums_levy_lands_only_on_the_plums(
    statement_382900: AccountSalesStatement,
) -> None:
    """3000 - 172.50 - 46 = 2781.50 and 1000 - 57.50 = 942.50, summing to exactly 3724.00."""
    split = split_statement(statement_382900)

    assert [share.nett for share in split.shares] == [d("2781.50"), d("942.50")]
    assert sum(share.nett for share in split.shares) == d("3724.00")
    assert statement_382900.nett_amount == d("3724.00")


def test_the_general_deduction_is_the_one_that_is_spread(
    statement_382900: AccountSalesStatement,
) -> None:
    plums, nectarines = split_statement(statement_382900).shares

    assert {(x.name, x.amount) for x in plums.deductions} == {
        ("MARKET FEES", d("172.50")),
        ("PLUMS LEVY", d("46.00")),
    }
    assert {(x.name, x.amount) for x in nectarines.deductions} == {("MARKET FEES", d("57.50"))}


def test_every_share_says_why_each_deduction_landed_on_it(
    statement_382900: AccountSalesStatement,
) -> None:
    """Section 6: nothing is apportioned silently."""
    split = split_statement(statement_382900)
    plums = split.shares[0]

    named = next(x for x in plums.deductions if x.name == "PLUMS LEVY")
    general = next(x for x in plums.deductions if x.name == "MARKET FEES")

    assert "names this fruit" in named.reason
    assert "in proportion to value" in general.reason
    assert split.is_apportioned
    assert any("PLUMS LEVY" in note for note in split.notes)


def _made_up(products: list[tuple[str, str]], deductions: list[tuple[str, str]]) -> tuple:
    """A statement in the shape of a real one, for the cases `data/` does not contain."""
    blocks = [
        StatementProduct(
            product_name=name,
            dockets=[
                Docket(
                    docket_number="x",
                    date_sold=None,
                    quantity=None,
                    price=None,
                    value=d(value),
                )
            ],
        )
        for name, value in products
    ]
    charges = [
        Deduction(name=name, amount=None, vat=None, total=d(total)) for name, total in deductions
    ]
    gross = sum((d(v) for _, v in products), Decimal(0))
    nett = gross - sum((d(t) for _, t in deductions), Decimal(0))
    return blocks, charges, gross, nett


def _statement(products: list[tuple[str, str]], deductions: list[tuple[str, str]]):
    blocks, charges, gross, nett = _made_up(products, deductions)
    return AccountSalesStatement(
        account_sale_number="999999",
        products=blocks,
        deductions=charges,
        gross_amount=gross,
        nett_amount=nett,
    )


def test_a_levy_naming_a_fruit_not_on_the_statement_is_spread_and_said_so() -> None:
    """It has to land somewhere. Spreading it is visible in the notes rather than silent."""
    split = split_statement(
        _statement([("GRAPES RED", "600"), ("APPLES GOLDEN", "400")], [("PLUMS LEVY", "100")])
    )

    assert [share.nett for share in split.shares] == [d("540.00"), d("360.00")]


def test_one_product_takes_the_whole_nett_and_is_not_marked_apportioned() -> None:
    split = split_statement(_statement([("PLUM ANGELINO", "3000")], [("MARKET FEES", "230")]))

    assert split.shares[0].nett == d("2770.00")
    assert not split.is_apportioned


def test_deductions_that_do_not_reconcile_produce_no_figure() -> None:
    """Section 6: "do not produce a figure. Say so instead."."""
    broken = _statement([("PLUM", "3000"), ("NECTARINE", "1000")], [("MARKET FEES", "230")])
    broken = replace(broken, nett_amount=d("3000.00"))

    with pytest.raises(CannotSplitError, match="do not reconcile"):
        split_statement(broken)


def test_a_gross_that_disagrees_with_the_blocks_produces_no_figure() -> None:
    wrong = _statement([("PLUM", "3000"), ("NECTARINE", "1000")], [("MARKET FEES", "230")])
    wrong = replace(wrong, gross_amount=d("5000.00"))

    with pytest.raises(CannotSplitError, match="prints a gross"):
        split_statement(wrong)


def test_a_statement_with_no_product_blocks_is_reported_not_split() -> None:
    """The 382999 shape: money and nothing to attribute it to."""
    empty = AccountSalesStatement(
        account_sale_number="382999", gross_amount=d("1000"), nett_amount=d("797")
    )

    with pytest.raises(CannotSplitError, match="no product blocks"):
        split_statement(empty)
