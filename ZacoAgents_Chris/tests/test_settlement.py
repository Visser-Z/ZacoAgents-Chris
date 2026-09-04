"""What a supplier is owed, and the two cases where the answer is nothing (section 8).

The reports stop at the Nett. Everything below it exists only in this system, so these pin the
rules that decide whether a figure may be produced at all:

* a consignment with no recorded commission produces **no settlement**, never one at a default
* **unsold stock creates no liability** -- on consignment the supplier is paid on what sold
"""

from __future__ import annotations

from decimal import Decimal

from zaco.domain.model import Consignment, Delivery, DocketFact, Row, StagedRound
from zaco.domain.products import ProductIdentity
from zaco.resolve.reconcile import Reconciliation, State
from zaco.resolve.settle import Terms, settle


def d(text: str) -> Decimal:
    return Decimal(text)


def _round(sent: str | None = "100", sold: str = "60", value: str = "3000") -> StagedRound:
    """One consignment, one row, one account sale."""
    product = ProductIdentity(key="PLUM")
    row = Row(
        delivery_id="1183001Z",
        consignment_id="C1",
        product=product,
        account_sale="382870",
        market="TSHWANE MARKET",
        agent="Farmers Trust (Pre)",
        dockets=[
            DocketFact(
                docket_number="K1",
                date_sold=None,
                quantity=d(sold),
                price=None,
                value=d(value),
                account_sale="382870",
            )
        ],
    )
    consignment = Consignment(
        consignment_id="C1",
        delivery_id="1183001Z",
        product=product,
        market="TSHWANE MARKET",
        agent="Farmers Trust (Pre)",
        qty_sent=None if sent is None else d(sent),
    )
    consignment.dockets.extend(row.dockets)
    # `StagedRound.consignments` derives from the deliveries, so the consignment has to hang off
    # one -- the same shape the readers build, rather than a list poked in from the side.
    delivery = Delivery(delivery_id="1183001Z", consignments=[consignment])
    return StagedRound(rows=[row], deliveries={"1183001Z": delivery})


def _agreed(number: str = "382870") -> dict[str, Reconciliation]:
    return {
        number: Reconciliation(
            account_sale=number,
            display_number=number,
            state=State.RECONCILED,
            sold=d("3000"),
            paid=d("3000"),
            difference=d("0"),
            nett=d("2261.00"),
            row_count=1,
            market=None,
            agent=None,
            can_never_reconcile=False,
            note="",
        )
    }


def test_a_consignment_with_no_agreed_commission_produces_no_settlement() -> None:
    """Never a default rate. A default in a payable is a fabrication (section 5)."""
    found = settle(_round(), terms={}, reconciliations=_agreed(), nett_by_row={0: d("2261.00")})

    assert found.settled == []
    assert len(found.awaiting_terms) == 1
    assert found.awaiting_terms[0].owed_to_supplier is None
    assert "default rate" in (found.awaiting_terms[0].blocked_by or "")


def test_what_awaits_terms_is_never_folded_into_the_total() -> None:
    found = settle(_round(), terms={}, reconciliations=_agreed(), nett_by_row={0: d("2261.00")})

    assert found.total_owed == d("0")
    assert "1 awaits agreed terms" in found.coverage


def test_zaco_keeps_its_percentage_and_the_remainder_is_the_supplier_s() -> None:
    terms = {"C1": Terms(consignment_id="C1", supplier="Sunnyvale", percent=d("12.5"))}

    found = settle(_round(), terms, _agreed(), {0: d("2261.00")})

    line = found.settled[0]
    assert line.zaco_keeps == d("282.63")
    assert line.owed_to_supplier == d("1978.37")
    # The two must add back to the Nett exactly: the remainder is subtracted, not re-computed.
    assert line.zaco_keeps + line.owed_to_supplier == d("2261.00")


def test_unsold_cartons_are_reported_and_create_no_liability() -> None:
    """On consignment the supplier is paid on what sold. 40 unsold cartons cost Zaco nothing."""
    terms = {"C1": Terms(consignment_id="C1", supplier="Sunnyvale", percent=d("12.5"))}

    found = settle(_round(sent="100", sold="60"), terms, _agreed(), {0: d("2261.00")})

    line = found.settled[0]
    assert line.cartons_sent == d("100")
    assert line.cartons_sold == d("60")
    assert line.cartons_unsold == d("40")
    assert line.owed_to_supplier == d("1978.37")


def test_what_was_sent_being_unknown_leaves_unsold_absent_not_nought() -> None:
    """Section 6: absent is not zero. A round without a consignment report does not know."""
    terms = {"C1": Terms(consignment_id="C1", supplier="Sunnyvale", percent=d("12.5"))}

    found = settle(_round(sent=None), terms, _agreed(), {0: d("2261.00")})

    assert found.settled[0].cartons_unsold is None


def test_a_consignment_whose_payment_does_not_reconcile_is_not_settled() -> None:
    terms = {"C1": Terms(consignment_id="C1", supplier="Sunnyvale", percent=d("12.5"))}
    disagreeing = _agreed()
    disagreeing["382870"] = Reconciliation(
        account_sale="382870",
        display_number="382870",
        state=State.SOLD_EXCEEDS_PAID,
        sold=d("3000"),
        paid=d("2000"),
        difference=d("1000"),
        nett=d("1700"),
        row_count=1,
        market=None,
        agent=None,
        can_never_reconcile=False,
        note="",
    )

    found = settle(_round(), terms, disagreeing, {0: d("2261.00")})

    assert found.settled == []
    assert len(found.awaiting_payment) == 1
    assert found.total_owed == d("0")


def test_the_coverage_is_stated_beside_the_totals() -> None:
    """Section 9: commission over a fifth of the business is useful only if you know it is."""
    terms = {"C1": Terms(consignment_id="C1", supplier="Sunnyvale", percent=d("12.5"))}

    found = settle(_round(), terms, _agreed(), {0: d("2261.00")})

    assert "1 of 1 consignment(s) can be settled" in found.coverage
