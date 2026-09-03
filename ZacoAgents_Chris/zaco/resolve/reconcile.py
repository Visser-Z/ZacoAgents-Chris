"""Holding what sold under an account sale against what was paid for it (section 8).

"Report, per account sale, what the sales side says was sold under it against what the payment
side says was paid for it, and whether those agree. Agreement is to the cent, within R0.01."

**The join is already exact and nothing softer is used.** Section 8 requires the account sale a
docket names to be preferred over any looser match. That is how the round is built: a docket's
payment reference *is* the account sale its row belongs to (`domain/model.py`, `Row.key`), so
this module compares two figures that are already on the same key. There is no fuzzy fallback to
get wrong, and adding one later would break the preference the brief asks for.

Five states have to be distinguishable, and the two disagreements are kept apart because they mean
opposite things. Sold more than was paid for is money Zaco is owed or a sale the agent has not
closed off yet. Paid more than sold is a payment run this system cannot account for, and it is the
one that should worry an operator, because the money is already in the bank against sales nobody
can point at.

AccSale 382999 is the case the brief names: a gross and a nett and no commodity lines at all. It
can never reconcile, and it is reported with that said rather than allowed to vanish.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from zaco.domain.model import AccountSale, Row, StagedRound

ZERO = Decimal("0")

#: "Agreement is to the cent, within R0.01." A tolerance, not a rounding: the two sides are
#: independently printed documents, and a cent between them is a printing artefact rather than a
#: disagreement worth putting to an operator.
TOLERANCE = Decimal("0.01")


class State(StrEnum):
    """The five states section 8 requires to be told apart."""

    RECONCILED = "reconciled"
    SOLD_NOT_PAID = "sold_not_paid"
    PAID_NOT_SOLD = "paid_not_sold"
    SOLD_EXCEEDS_PAID = "sold_exceeds_paid"
    PAID_EXCEEDS_SOLD = "paid_exceeds_sold"


LABELS: dict[State, str] = {
    State.RECONCILED: "Reconciled",
    State.SOLD_NOT_PAID: "Sold, not yet in any payment run",
    State.PAID_NOT_SOLD: "Paid, with no sales behind it",
    State.SOLD_EXCEEDS_PAID: "Sold more than was paid for",
    State.PAID_EXCEEDS_SOLD: "Paid more than was sold",
}


@dataclass(frozen=True)
class Reconciliation:
    """One account sale, both sides of it, and whether they agree."""

    account_sale: str
    display_number: str
    state: State
    sold: Decimal | None
    """What the sales side says was sold under it, from the dockets that name it."""

    paid: Decimal | None
    """What the payment side says was sold under it, from its own stated figure."""

    difference: Decimal | None
    nett: Decimal | None
    row_count: int
    market: str | None
    agent: str | None
    can_never_reconcile: bool
    note: str

    @property
    def label(self) -> str:
        return LABELS[self.state]

    @property
    def agrees(self) -> bool:
        return self.state is State.RECONCILED


def _payment_side(sale: AccountSale) -> Decimal | None:
    """What the payment side says was sold, preferring its own stated sales total.

    `sales_value` is the figure the payment report prints for what sold under the run. Where it
    prints none, the gross stands in -- it is the same quantity seen from the other end, before
    the agent's deductions. The nett is never used here: it is what reached Zaco, not what the
    fruit rang up, and comparing it against a sales total would show a disagreement on every
    single account sale.
    """
    if sale.sales_value is not None:
        return sale.sales_value
    return sale.gross


def reconcile(round_: StagedRound) -> list[Reconciliation]:
    """Every account sale either side mentions, with the two sides held against each other."""
    rows_by_sale: dict[str, list[Row]] = {}
    for row in round_.rows:
        rows_by_sale.setdefault(row.account_sale, []).append(row)

    numbers = sorted(set(rows_by_sale) | set(round_.account_sales))
    return [
        _one(number, rows_by_sale.get(number, []), round_.account_sales.get(number))
        for number in numbers
    ]


def _one(number: str, rows: list[Row], sale: AccountSale | None) -> Reconciliation:
    sold = sum((row.value for row in rows), ZERO) if rows else None
    paid = _payment_side(sale) if sale else None
    never = bool(sale and not sale.has_commodity_breakdown)

    state, note = _judge(rows, sale, sold, paid, never)
    return Reconciliation(
        account_sale=number,
        display_number=sale.display_number if sale else number,
        state=state,
        sold=sold,
        paid=paid,
        difference=None if sold is None or paid is None else sold - paid,
        nett=sale.nett if sale else None,
        row_count=len(rows),
        market=sale.market if sale else next((r.market for r in rows if r.market), None),
        agent=sale.agent if sale else next((r.agent for r in rows if r.agent), None),
        can_never_reconcile=never,
        note=note,
    )


def _judge(
    rows: list[Row],
    sale: AccountSale | None,
    sold: Decimal | None,
    paid: Decimal | None,
    never: bool,
) -> tuple[State, str]:
    """Which state, and why in words an operator would act on."""
    if sale is None:
        return (
            State.SOLD_NOT_PAID,
            f"{len(rows)} row(s) name this account sale and no payment document in the record "
            f"accounts for it. It stays here until a payment report names it.",
        )
    if not rows:
        if never:
            return (
                State.PAID_NOT_SOLD,
                "This payment run carries a gross and a nett and no commodity lines at all, so "
                "there is nothing to reconcile it against and there never will be. Its money is "
                "real and is reported here rather than left out of the totals.",
            )
        return (
            State.PAID_NOT_SOLD,
            "A payment document accounts for this account sale and no sale in the record names "
            "it. Either the sales export for it has not been loaded, or the payment belongs to "
            "produce this system has not seen.",
        )
    if paid is None:
        return (
            State.SOLD_NOT_PAID,
            "The payment side names this account sale but prints no figure for what sold under "
            "it, so the two cannot be held against each other.",
        )

    assert sold is not None
    difference = sold - paid
    if abs(difference) <= TOLERANCE:
        return (State.RECONCILED, f"Both sides agree at R{sold:,.2f}.")
    if difference > ZERO:
        return (
            State.SOLD_EXCEEDS_PAID,
            f"The sales side accounts for R{sold:,.2f} and the payment side for R{paid:,.2f}, "
            f"R{difference:,.2f} more sold than paid for. Either part of it is settled in a "
            f"later run, or the payment is short.",
        )
    return (
        State.PAID_EXCEEDS_SOLD,
        f"The payment side accounts for R{paid:,.2f} and the sales side for only R{sold:,.2f}, "
        f"R{-difference:,.2f} paid that no sale in the record explains. The money is already in.",
    )


def by_state(found: list[Reconciliation]) -> dict[State, list[Reconciliation]]:
    """Grouped for the board, in the order section 8 lists them, empty groups included.

    Empty groups are kept so a state with nothing in it reads as "none of these" rather than
    disappearing -- an operator should be able to see that nothing is unaccounted for.
    """
    return {state: [r for r in found if r.state is state] for state in State}
