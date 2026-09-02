"""Opening stock: the running balance down a consignment, and across a round boundary."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from zaco.domain.model import Cartons, Consignment, DocketFact, Evidence, Row
from zaco.domain.products import ProductIdentity
from zaco.resolve.stock import build_ledger


def _product(name: str = "NECTARINES") -> ProductIdentity:
    return ProductIdentity(key=name)


def _row(
    consignment_id: str | None,
    account_sale: str,
    sold: int,
    when: date,
    product: ProductIdentity,
) -> Row:
    return Row(
        delivery_id="D1",
        consignment_id=consignment_id,
        product=product,
        account_sale=account_sale,
        market=None,
        agent=None,
        # Docket-level evidence, so a return is a figure this row can report at all.
        evidence={Evidence.SALES},
        dockets=[
            DocketFact(
                docket_number=f"{account_sale}-1",
                date_sold=when,
                quantity=Decimal(sold),
                price=None,
                value=Decimal(sold) * Decimal(50),
                account_sale=account_sale,
            )
        ],
    )


def _consignment(
    consignment_id: str | None, sent: int | None, product: ProductIdentity
) -> Consignment:
    return Consignment(
        consignment_id=consignment_id,
        delivery_id="D1",
        product=product,
        qty_sent=None if sent is None else Decimal(sent),
    )


def test_the_second_account_sale_opens_where_the_first_one_closed() -> None:
    """71 nectarines, sold 40 then 25. The second row opens at 31, not at 71."""
    product = _product()
    rows = [
        _row("118170502Z", "382410", 40, date(2026, 5, 26), product),
        _row("118170502Z", "382861", 25, date(2026, 5, 30), product),
    ]
    ledger = build_ledger(rows, [_consignment("118170502Z", 71, product)])

    first = ledger.for_row(rows[0])
    second = ledger.for_row(rows[1])
    assert first is not None and second is not None
    assert (first.opening, first.sold, first.closing) == (Decimal(71), Decimal(40), Decimal(31))
    assert (second.opening, second.sold, second.closing) == (Decimal(31), Decimal(25), Decimal(6))
    assert ledger.closing["118170502Z"] == Decimal(6)


def test_the_quantity_sent_is_not_the_opening_stock_of_every_row() -> None:
    """The failure this guards against: 71 opening twice, and the book still balancing."""
    product = _product()
    rows = [
        _row("118170502Z", "382410", 40, date(2026, 5, 26), product),
        _row("118170502Z", "382861", 25, date(2026, 5, 30), product),
    ]
    ledger = build_ledger(rows, [_consignment("118170502Z", 71, product)])
    openings = [p.opening for p in ledger.positions.values()]
    assert openings.count(Decimal(71)) == 1


def test_a_balance_carries_into_the_next_round() -> None:
    product = _product()
    rows = [_row("118069901Z", "382860", 1, date(2026, 6, 2), product)]
    ledger = build_ledger(
        rows, [_consignment("118069901Z", 14, product)], carried_in={"118069901Z": Decimal(12)}
    )
    position = ledger.for_row(rows[0])
    assert position is not None
    assert position.opening == Decimal(12)
    assert position.is_carried_forward is True
    assert position.closing == Decimal(11)


def test_only_the_first_row_of_a_round_is_marked_as_carried_in() -> None:
    product = _product()
    rows = [
        _row("C1", "A", 3, date(2026, 6, 1), product),
        _row("C1", "B", 2, date(2026, 6, 5), product),
    ]
    ledger = build_ledger(rows, [_consignment("C1", 20, product)], carried_in={"C1": Decimal(10)})
    marks = [p.is_carried_forward for p in ledger.positions.values()]
    assert marks.count(True) == 1


def test_a_consignment_that_cannot_be_identified_carries_nothing() -> None:
    """Section 6: left alone rather than pooled with one that merely looks similar."""
    product = _product()
    rows = [_row(None, "382860", 5, date(2026, 6, 2), product)]
    ledger = build_ledger(rows, [_consignment(None, 14, product)], carried_in={"": Decimal(99)})
    position = ledger.for_row(rows[0])
    assert position is not None
    assert position.is_carried_forward is False
    assert ledger.closing == {}
    assert any("cannot be identified" in n for n in ledger.notes)


def test_an_unknown_quantity_sent_leaves_the_opening_empty_rather_than_zero() -> None:
    product = _product()
    rows = [_row("C9", "382860", 5, date(2026, 6, 2), product)]
    ledger = build_ledger(rows, [_consignment("C9", None, product)])
    position = ledger.for_row(rows[0])
    assert position is not None
    assert position.opening is None
    assert position.closing is None
    assert any("not known" in n for n in ledger.notes)


def test_selling_more_than_was_sent_is_reported_and_not_corrected() -> None:
    product = _product()
    rows = [_row("C2", "A", 30, date(2026, 6, 1), product)]
    ledger = build_ledger(rows, [_consignment("C2", 20, product)])
    assert ledger.closing["C2"] == Decimal(-10)
    assert any("more than were sent" in n for n in ledger.notes)


def test_returns_reduce_what_sold_so_the_balance_is_over_the_net() -> None:
    product = _product()
    row = _row("C3", "A", 10, date(2026, 6, 1), product)
    row.dockets.append(
        DocketFact(
            docket_number="return",
            date_sold=date(2026, 6, 2),
            quantity=Decimal(-4),
            price=None,
            value=Decimal(-200),
            account_sale="A",
        )
    )
    assert row.cartons == Cartons(sold=Decimal(10), returned=Decimal(4))
    ledger = build_ledger([row], [_consignment("C3", 20, product)])
    position = ledger.for_row(row)
    assert position is not None
    assert position.sold == Decimal(6)
    assert position.closing == Decimal(14)
