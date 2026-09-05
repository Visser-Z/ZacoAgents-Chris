"""Section 9, against the real record.

Section 9 leaves the signals, the weighting and the banding to us and asks that the result be
"computed and reproducible: the same history in gives the same answer out, and every score traces
to the figures shown beside it". These pin the choices that were made and the figures that would
otherwise be quietly wrong.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from zaco.domain.build import build_round
from zaco.domain.model import Cartons, StagedRound
from zaco.ingest.classifier import read_document
from zaco.reporting.reports import (
    ALL_TIME,
    Band,
    Period,
    ProductLine,
    build,
    take_on,
)
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
    return one


def test_the_takings_count_a_sale_no_payment_run_has_named_yet(record: StagedRound) -> None:
    """R800 of grapes sold on 2026-06-02 with no account sale, so it forms no workbook row.

    Section 9 asks what *sold*. Counting rows instead would leave the takings R800 short of the
    record while looking complete.
    """
    report = build(record, ALL_TIME)

    assert report.headline.takings == d("23010.00")
    assert report.headline.not_yet_paid == d("800.00")
    assert any("not yet in any payment run" in c for c in report.caveats)


def test_the_return_rate_is_over_what_sold_and_says_so(record: StagedRound) -> None:
    """6 back out of 366 sold is 1.64%. Over the net it would read 1.67% -- a different claim."""
    head = build(record, ALL_TIME).headline

    assert head.cartons_sold == d("366")
    assert head.cartons_returned == d("6")
    assert head.cartons_net == d("360")
    assert head.return_rate is not None
    assert head.return_rate == d("6") / d("366")
    assert "over cartons sold" in head.return_rate_basis


def test_what_was_sent_is_not_doubled_by_a_consignment_selling_twice(
    record: StagedRound,
) -> None:
    """The oranges sell in both rounds. 200 sent, once -- not 400 (section 3)."""
    line = next(x for x in build(record, ALL_TIME).products if "ORANGES" in x.product)

    assert line.cartons_sent == d("200")
    assert line.cartons.net == d("80")
    assert line.sell_through == d("80") / d("200")


def test_time_on_market_is_the_consignment_s_and_survives_the_round_boundary(
    record: StagedRound,
) -> None:
    line = next(x for x in build(record, ALL_TIME).products if "ORANGES" in x.product)

    assert line.days_on_market == 6


def test_the_bands_follow_cumulative_value_rather_than_a_fixed_count(
    record: StagedRound,
) -> None:
    """A closes at 80% of value, B at 95%. Five lines reach 79.7% here; the sixth takes it past."""
    lines = build(record, ALL_TIME).products

    assert [x.band for x in lines[:5]] == [Band.A] * 5
    assert lines[5].band is Band.B
    assert lines[6].band is Band.C
    # Within a rounding tail, not to the cent. A share of value is a display proportion; the
    # exactness section 8 demands is of money being apportioned, which this is not.
    assert abs(sum((x.share_of_value for x in lines), Decimal(0)) - 1) < Decimal("0.0000001")


def test_a_record_too_small_to_have_a_long_tail_is_not_banded(record: StagedRound) -> None:
    """Three lines cannot have a vital few. Banding them dresses an arbitrary cut as a finding."""
    one_day = Period("A single day", date(2026, 6, 1), date(2026, 6, 1))

    report = build(record, one_day)

    assert 0 < len(report.products) < 5
    assert all(x.band is Band.UNBANDED for x in report.products)
    assert any("too few to band" in c for c in report.caveats)


def test_the_same_history_gives_the_same_answer(record: StagedRound) -> None:
    """Section 9 requires it, and a ranking with an arbitrary tie-break would not."""
    first = build(record, ALL_TIME)
    second = build(record, ALL_TIME)

    assert [x.product for x in first.products] == [x.product for x in second.products]
    assert [x.product for x in first.take_on] == [x.product for x in second.take_on]
    assert first.headline == second.headline


def test_what_to_take_on_says_it_is_ranking_on_a_proxy(record: StagedRound) -> None:
    """Until terms exist the ranking is on the market's money, not Zaco's, and must say so."""
    report = build(record, ALL_TIME)

    assert "proxy" in report.take_on_basis
    assert any("proxy for what Zaco would earn" in c for c in report.caveats)
    assert report.take_on[0].per_carton_sent == d("3000") / d("25")


def test_recorded_earnings_change_the_basis_and_the_order(record: StagedRound) -> None:
    """Once terms exist the same ranking runs on what Zaco actually earned."""
    lines = build(record, ALL_TIME).products
    # Earn most on the line that ranks worst on gross, so the order has to move.
    worst = lines[-1].product
    report = build(record, ALL_TIME, earned={worst: d("100000")})

    assert "What Zaco earned" in report.take_on_basis
    assert report.take_on[0].product == worst
    assert not any("proxy for what Zaco would earn" in c for c in report.caveats)


def test_a_line_that_cannot_be_ranked_is_shown_last_rather_than_dropped() -> None:
    """A line missing from a ranking reads as one that did badly."""
    known = ProductLine(
        product="PEARS",
        short_code=None,
        cartons=Cartons(sold=d("10"), returned=d("0")),
        value=d("100"),
        band=Band.A,
        share_of_value=d("0.5"),
        cartons_sent=d("10"),
        days_on_market=1,
        consignments=1,
    )
    unknown = ProductLine(
        product="PLUMS",
        short_code=None,
        cartons=Cartons(sold=d("10"), returned=d("0")),
        value=d("900"),
        band=Band.A,
        share_of_value=d("0.5"),
        cartons_sent=None,
        days_on_market=1,
        consignments=1,
    )

    ranked, _ = take_on([known, unknown], None)

    assert [x.product for x in ranked] == ["PEARS", "PLUMS"]
    assert ranked[-1].per_carton_sent is None
    assert "cannot be ranked" in ranked[-1].note
