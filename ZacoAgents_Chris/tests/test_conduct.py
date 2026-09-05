"""Section 10, against the real record.

Section 10 leaves the thresholds to us and is specific about two failure modes: judging on a
sample too small to have a normal, and letting a not-answerable conclusion sit somewhere other
than with the figures. These pin the choices that make the difference between a figure and an
accusation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from zaco.conduct.conduct import (
    ENOUGH_TO_JUDGE,
    MATERIALLY_ABOVE,
    NOT_ANSWERABLE,
    Kept,
    build,
    median,
)
from zaco.domain.build import build_round
from zaco.domain.model import StagedRound
from zaco.ingest.classifier import read_document
from zaco.resolve.service import _absorb

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


def d(text: str) -> Decimal:
    return Decimal(text)


@pytest.fixture(scope="module")
def record() -> StagedRound:
    """Both supplied rounds, accumulated the way the service accumulates them."""

    def load(names: list[str]) -> list[tuple[str, object]]:
        return [(n, read_document((DATA / n).read_bytes())) for n in names]

    one, registry = build_round(load(ROUND_1))
    two, _ = build_round(
        load(ROUND_2), registry, set(one.docket_identities), dict(one.account_sales)
    )
    one.rows.extend(two.rows)
    for key, delivery in two.deliveries.items():
        if key in one.deliveries:
            _absorb(one.deliveries[key], delivery)
        else:
            one.deliveries[key] = delivery
    for key, sale in two.account_sales.items():
        one.account_sales.setdefault(key, sale)
    return one


def test_the_normal_is_a_median_so_the_outlier_does_not_move_it(record: StagedRound) -> None:
    """The mean share kept here is 17.4%, dragged up by the 60% that is the thing to catch.

    Against the mean, 60% is 3.44x normal; against the median it is 4x. A mean is partly made of
    the outlier it is being used to detect, which is the whole argument for the median.
    """
    found = build(record)
    shares = [s.deduction_share for s in record.account_sales.values() if s.deduction_share]
    mean = sum(shares, Decimal(0)) / len(shares)

    assert found.normal_share_kept == d("0.15")
    assert mean > d("0.17")
    assert d("0.60") / mean < d("0.60") / found.normal_share_kept


def test_the_one_account_sale_that_kept_too_much_is_flagged_with_its_figures(
    record: StagedRound,
) -> None:
    """382875: R1,350 gross, R540 nett. Normal would have kept R202.50, so R607.50 is the

    question. Section 10 requires the figures that raised a flag to travel with it.
    """
    flagged = build(record).flagged_kept

    assert [k.account_sale for k in flagged] == ["382875"]
    only = flagged[0]
    assert only.gross == d("1350.00")
    assert only.kept == d("810.00")
    assert only.share == d("0.60")
    assert only.normal_kept == d("202.50")
    assert only.excess == d("607.50")


def test_a_small_sale_a_little_above_normal_is_shown_but_not_flagged(
    record: StagedRound,
) -> None:
    """382880 keeps 16.67% against a normal of 15% -- R5 more, on a R300 sale.

    Flagging that would bury the R607.50 in noise, and a fixed handling charge explains it. It is
    still listed, because how ordinary the ordinary ones are is what makes the comparison mean
    anything.
    """
    kept = {k.account_sale: k for k in build(record).kept}

    assert kept["382880"].excess == d("5.00")
    assert kept["382880"].is_flagged is False
    assert kept["382880"].share > build(record).normal_share_kept


def test_a_consignment_still_selling_is_not_counted_as_produce_that_failed_to_move(
    record: StagedRound,
) -> None:
    """The oranges last sold on 2026-06-05, the last day the record knows about, with 120 of 200

    still unsold. Those 120 are four fifths of everything Subtropico has not shifted; counting
    them would report an agent whose fruit is still on the floor as one who cannot sell it.
    """
    subtropico = next(n for n in build(record).never_sold if n.agent == "Subtropico (Jhb)")

    assert subtropico.still_selling == 1
    assert subtropico.still_selling_cartons == d("120")
    assert subtropico.cartons_sent == d("125")


def test_an_agent_left_with_too_few_consignments_to_have_a_normal_is_not_judged(
    record: StagedRound,
) -> None:
    """Section 10: "Do not judge either on a sample too small to have a normal."

    Setting the open consignment aside leaves Subtropico two, under `ENOUGH_TO_JUDGE`. The
    reason is stated, because saying nothing at all would read as a pass.
    """
    subtropico = next(n for n in build(record).never_sold if n.agent == "Subtropico (Jhb)")

    assert subtropico.consignments < ENOUGH_TO_JUDGE
    assert subtropico.is_judged is False
    assert subtropico.is_flagged is False
    assert subtropico.why_not_judged is not None
    assert "too few to have a normal" in subtropico.why_not_judged


def test_an_account_sale_naming_no_agent_still_counts_but_is_named(record: StagedRound) -> None:
    """382900 has no agent. Dropping it would quietly change the normal it helped set."""
    found = build(record)

    assert any(k.account_sale == "382900" and k.agent is None for k in found.kept)
    assert any("name no agent" in c and "382900" in c for c in found.caveats)


def test_the_not_answerable_conclusion_is_part_of_the_result(record: StagedRound) -> None:
    """Section 10 requires it to travel *with* the figures rather than sit in a comment.

    So it is a field on the result, not prose in a template: a page can be redesigned and lose a
    paragraph, and what is left reads as a clean bill of health on the thing it is blind to.
    """
    found = build(record)

    assert found.not_answerable == NOT_ANSWERABLE
    assert "cannot be answered from these reports" in found.not_answerable
    assert found.price_evidence


def test_an_agent_who_is_the_only_agent_cannot_be_measured_against_themselves() -> None:
    """The normal is the business's own, so one agent alone defines the yardstick they are held

    to. That has to be said, or a lone agent keeping 40% every time looks perfectly normal.
    """
    from zaco.domain.model import AccountSale

    lone = StagedRound()
    for i in range(6):
        number = f"90000{i}"
        lone.account_sales[number] = AccountSale(
            number=number,
            agent="Only Agent",
            gross=d("1000.00"),
            nett=d("600.00"),
            date_paid=date(2026, 6, 1),
        )

    found = build(lone)

    assert found.normal_share_kept == d("0.40")
    assert not found.flagged_kept
    assert any("defines the normal it is being measured against" in c for c in found.caveats)


def test_median_of_an_even_number_of_values_is_the_middle_pair() -> None:
    assert median([d("1"), d("2"), d("3"), d("4")]) == d("2.5")
    assert median([d("3"), d("1"), d("2")]) == d("2")
    assert median([]) is None


def test_the_threshold_is_relative_so_a_low_normal_is_held_to_a_tight_band() -> None:
    """A business normally paying 5% and one normally paying 30% cannot share a band in points.

    At `MATERIALLY_ABOVE` = 1.5, the first flags at 7.5% and the second not until 45%.
    """
    tight = Kept(
        account_sale="A",
        agent="X",
        market=None,
        gross=d("1000"),
        nett=d("920"),
        kept=d("80"),
        share=d("0.08"),
        normal_share=d("0.05"),
        date_paid=None,
        has_commodity_breakdown=True,
    )
    loose = Kept(
        account_sale="B",
        agent="X",
        market=None,
        gross=d("1000"),
        nett=d("620"),
        kept=d("380"),
        share=d("0.38"),
        normal_share=d("0.30"),
        date_paid=None,
        has_commodity_breakdown=True,
    )

    assert tight.is_flagged is True
    assert loose.is_flagged is False
    assert tight.times_normal is not None and tight.times_normal >= MATERIALLY_ABOVE
