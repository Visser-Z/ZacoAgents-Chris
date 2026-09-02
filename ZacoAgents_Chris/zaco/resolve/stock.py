"""Opening stock: what was still on the floor when each row's selling started.

Workbook column I, and the input to `Baby Stock` (`=I-K` in the live book, not the `=H-J` the
brief describes). A consignment does not sell in one go, so a single consignment commonly
becomes several rows, and each row after the first opens with whatever the one before it left.

Two boundaries have to hold:

* **Between rows of one round.** The 71 nectarines sold across two account sales open at 71 and
  then at whatever is left, never at 71 twice.
* **Between rounds.** A consignment still on the floor when a round closes carries its balance
  forward. This is why a consignment that cannot be identified is left alone rather than pooled
  with one that merely looks similar -- carrying a balance onto the wrong consignment invents
  stock that was never there, and every figure downstream still adds up.

Nothing here corrects anything. A consignment that sold more than was sent keeps its negative
balance and is reported, because that happens in the real book and hiding it loses the signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from zaco.domain.model import ZERO, Consignment, Row


@dataclass(frozen=True)
class Position:
    """One row's stock position, with what could not be known kept out of the arithmetic."""

    opening: Decimal | None
    sold: Decimal
    closing: Decimal | None
    is_carried_forward: bool = False
    """True when the opening came from an earlier round rather than from a delivered quantity."""

    note: str | None = None


@dataclass
class StockLedger:
    """Per-row positions for one round, plus what each consignment leaves behind."""

    positions: dict[tuple[str, str, str], Position] = field(default_factory=dict)
    closing: dict[str, Decimal] = field(default_factory=dict)
    """Consignment ID to what is left on the floor. Only identifiable consignments appear."""

    notes: list[str] = field(default_factory=list)

    def for_row(self, row: Row) -> Position | None:
        return self.positions.get(row.key)


def build_ledger(
    rows: list[Row],
    consignments: list[Consignment],
    carried_in: dict[str, Decimal] | None = None,
) -> StockLedger:
    """Walk each consignment's rows in date order, opening where the last one closed.

    `carried_in` is the closing balance of each consignment from the rounds already committed.
    A consignment absent from it is being seen for the first time and opens at what was sent.
    """
    carried = dict(carried_in or {})
    ledger = StockLedger()
    by_id = {c.consignment_id: c for c in consignments if c.consignment_id}

    grouped: dict[str, list[Row]] = {}
    for row in rows:
        grouped.setdefault(row.consignment_id or f"(unidentified) {row.key}", []).append(row)

    for consignment_id, group in grouped.items():
        consignment = by_id.get(consignment_id)
        identifiable = consignment is not None

        if identifiable and consignment_id in carried:
            balance: Decimal | None = carried[consignment_id]
            carried_forward = True
        else:
            balance = consignment.qty_sent if consignment is not None else None
            carried_forward = False
            if not identifiable:
                ledger.notes.append(
                    f"A consignment with no ID sold {sum((r.cartons.net for r in group), ZERO)} "
                    "cartons. Its opening stock is taken from this round alone, because a "
                    "balance cannot be carried onto a consignment that cannot be identified."
                )
            elif balance is None:
                ledger.notes.append(
                    f"Consignment {consignment_id} has no quantity sent in any document, so its "
                    "opening stock is not known. It is left empty rather than set to zero."
                )

        ordered = sorted(group, key=lambda r: (str(r.earliest_date or ""), r.account_sale))
        for index, row in enumerate(ordered):
            sold = row.cartons.net
            closing = None if balance is None else balance - sold
            ledger.positions[row.key] = Position(
                opening=balance,
                sold=sold,
                closing=closing,
                is_carried_forward=carried_forward and index == 0,
                note=(
                    "Opening stock is what the previous account sale left, not the quantity "
                    "sent, which is counted once for the consignment."
                    if index > 0
                    else None
                ),
            )
            balance = closing

        if identifiable and balance is not None:
            ledger.closing[consignment_id] = balance
            if balance < ZERO:
                ledger.notes.append(
                    f"Consignment {consignment_id} has sold {-balance} cartons more than were "
                    "sent. Reported as it stands; nothing has been adjusted."
                )

    return ledger
