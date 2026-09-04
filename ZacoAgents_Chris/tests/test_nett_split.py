"""Splitting an account sale's Nett across the rows it settles (section 8).

"An account sale settles several rows at once, so its Nett is split between them by sales value.
The shares must add up to the payment exactly."

The case is real. Account sale 382880 pays R250.00 over three rows worth R100.00 each -- pears,
peaches and strawberries. Rounding each share gives 83.33 three times, which is R249.99, and the
operator is left holding a payment that does not match its rows.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from zaco.domain.build import build_round
from zaco.domain.model import AccountSale, DocketFact, Row, StagedRound
from zaco.domain.products import ProductIdentity
from zaco.ingest.classifier import read_document
from zaco.workbook.append import row_netts

DATA = Path(__file__).resolve().parent.parent / "data"

ROUND_1 = [
    "DailySalesDetail_20260525-20260531.csv",
    "ConsignmentReports_20260525-20260531.txt",
    "PaymentDetails_20260529-20260602.csv",
    "AccountSales_382405.txt",
    "AccountSales_382900.txt",
    "NettPaymentAdjustments_202604.txt",
]
ROUND_2 = [
    "DailySalesDetail_20260601-20260608.csv",
    "PaymentDetails_20260603-20260608.txt",
    "PaymentDetails_20260603-20260608_FarmersTrust.csv",
]


def _load(names: list[str]) -> list[tuple[str, object]]:
    return [(n, read_document((DATA / n).read_bytes())) for n in names]


@pytest.fixture(scope="module")
def round_two() -> StagedRound:
    """Round 2 as the service builds it: carrying round 1's counted dockets and settled sales."""
    one, registry = build_round(_load(ROUND_1))
    two, _ = build_round(
        _load(ROUND_2), registry, set(one.docket_identities), dict(one.account_sales)
    )
    return two


def test_the_shares_sum_to_the_payment_exactly(round_two: StagedRound) -> None:
    """382880: R250.00 over three equal rows. Rounding each gives R249.99."""
    shares, _ = row_netts(round_two)
    offsets = [i for i, row in enumerate(round_two.rows) if row.account_sale.endswith("382880")]

    assert len(offsets) == 3
    given = [shares[i] for i in offsets]
    assert sorted(given) == [Decimal("83.33"), Decimal("83.33"), Decimal("83.34")]
    assert sum(given) == Decimal("250.00")


def test_a_row_that_is_the_only_one_under_its_sale_takes_the_printed_nett(
    round_two: StagedRound,
) -> None:
    """One row under an account sale has no proportions, so it takes the Nett as printed.

    Not an inconsistency with the rule above: that rule exists to stop untrustworthy proportions
    being used, and there are none here. Withholding the figure would leave a cell empty over a
    disagreement about the gross, which is a different number.
    """
    shares, _ = row_netts(round_two)
    single = [
        (i, row)
        for i, row in enumerate(round_two.rows)
        if sum(1 for other in round_two.rows if other.account_sale == row.account_sale) == 1
    ]

    assert single
    for offset, row in single:
        sale = round_two.account_sales.get(row.account_sale)
        if sale is None or sale.nett is None:
            continue
        assert shares[offset] == sale.nett


def _row(number: str, product: str, value: str) -> Row:
    """One row under an account sale, worth `value`."""
    return Row(
        delivery_id=f"D{product}",
        consignment_id=f"C{product}",
        product=ProductIdentity(key=product),
        account_sale=number,
        market="TSHWANE MARKET",
        agent="Farmers Trust (Pre)",
        dockets=[
            DocketFact(
                docket_number=f"K{product}",
                date_sold=None,
                quantity=Decimal("10"),
                price=None,
                value=Decimal(value),
                account_sale=number,
            )
        ],
    )


def test_a_group_the_two_sides_disagree_on_gets_no_figure_and_a_reason() -> None:
    """Section 8: only fully matched groups are filled.

    A part-paid group would otherwise take a Nett for produce nobody has been paid for yet. No
    such group exists in the supplied data, so this builds one: two rows worth R1,000 between
    them under a payment run that says R1,500 sold.

    This is also the shape of a group whose rows are split across two rounds -- neither round can
    see all of them, so inside each one the two sides disagree and neither writes a figure. That
    protection falls out of this rule rather than needing a guard of its own.
    """
    number = "382777"
    staged = StagedRound(
        rows=[_row(number, "PEARS", "600"), _row(number, "PEACHES", "400")],
        account_sales={
            number: AccountSale(
                number=number,
                nett=Decimal("1275.00"),
                gross=Decimal("1500.00"),
                sales_value=Decimal("1500.00"),
            )
        },
    )

    shares, refusals = row_netts(staged)

    assert shares == {}, "a group the two sides disagree on must receive no Nett at all"
    assert number in refusals
    assert "only a fully matched group is filled" in refusals[number].lower()
    assert "R1,275.00" in refusals[number]


def test_a_group_the_two_sides_agree_on_is_filled() -> None:
    """The same shape, with the payment side agreeing, does get its split."""
    number = "382778"
    staged = StagedRound(
        rows=[_row(number, "PEARS", "600"), _row(number, "PEACHES", "400")],
        account_sales={
            number: AccountSale(
                number=number,
                nett=Decimal("850.00"),
                gross=Decimal("1000.00"),
                sales_value=Decimal("1000.00"),
            )
        },
    )

    shares, refusals = row_netts(staged)

    assert refusals == {}
    assert shares == {0: Decimal("510.00"), 1: Decimal("340.00")}
    assert sum(shares.values()) == Decimal("850.00")
