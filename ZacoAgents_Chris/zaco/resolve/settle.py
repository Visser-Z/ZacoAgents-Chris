"""What a supplier earned, is owed, and handed over that never sold (section 8).

```
market buyer pays
  -> agent deducts commission, levies and VAT      (payment report)
    -> NETT lands with Zaco                        (payment report)
      -> Zaco keeps its agreed percentage          (recorded by this system)
        -> the remainder is owed to the supplier   (computed here)
```

Everything above the Nett line the reports state. Everything below it exists only in this system,
because the agents see Zaco as the supplier and know nothing about the farmers behind it.

Two rules that are easy to get wrong, and are the reason most of this module is refusals rather
than arithmetic:

- **A consignment with no recorded commission produces no settlement at all**, rather than one at
  a default rate. Section 5 draws the distinction sharply: a default in a spreadsheet cell is a
  visible, editable suggestion, and a default in a payable is a fabrication.
- **Unsold stock creates no liability.** On consignment the supplier is paid on what sold;
  cartons that never moved cost the supplier, not Zaco. This is the opposite of buy-and-resell,
  and getting it backwards would invent a debt on every carton that failed to clear.

Consignments this system cannot speak for are reported in their own sections and are never folded
into a total. A figure that quietly excludes half the business is worse than no figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from zaco.domain.model import Row, StagedRound
from zaco.money.allocate import CENT
from zaco.resolve.reconcile import Reconciliation

ZERO = Decimal("0")


@dataclass(frozen=True)
class Terms:
    """What Zaco keeps of the Nett on one delivery line, as recorded by a person."""

    consignment_id: str
    supplier: str
    percent: Decimal


@dataclass(frozen=True)
class Line:
    """One consignment's settlement, or the reason there is not one."""

    consignment_id: str
    product: str
    delivery_id: str | None
    supplier: str | None
    percent: Decimal | None
    nett: Decimal | None
    """Zaco's share of the money that actually arrived for this consignment."""

    zaco_keeps: Decimal | None = None
    owed_to_supplier: Decimal | None = None
    cartons_sold: Decimal = ZERO
    cartons_sent: Decimal | None = None
    cartons_unsold: Decimal | None = None
    blocked_by: str | None = None

    @property
    def is_settled(self) -> bool:
        return self.owed_to_supplier is not None


@dataclass
class Settlement:
    """Every consignment, split by whether this system can speak for it."""

    settled: list[Line] = field(default_factory=list)
    awaiting_terms: list[Line] = field(default_factory=list)
    awaiting_payment: list[Line] = field(default_factory=list)

    @property
    def total_owed(self) -> Decimal:
        """Only over the lines with both terms and payment. Never a partial total dressed up."""
        return sum((line.owed_to_supplier or ZERO for line in self.settled), ZERO)

    @property
    def total_kept(self) -> Decimal:
        return sum((line.zaco_keeps or ZERO for line in self.settled), ZERO)

    @property
    def coverage(self) -> str:
        """Stated beside every total. Section 9: a figure over a fifth of the business is only
        useful if you know it is a fifth."""
        total = len(self.settled) + len(self.awaiting_terms) + len(self.awaiting_payment)
        if not total:
            return "No consignment in the record yet."
        return (
            f"{len(self.settled)} of {total} consignment(s) can be settled. "
            f"{len(self.awaiting_terms)} awaits agreed terms and "
            f"{len(self.awaiting_payment)} awaits payment; neither is in the totals."
        )


def _rand(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def settle(
    round_: StagedRound,
    terms: dict[str, Terms],
    reconciliations: dict[str, Reconciliation],
    nett_by_row: dict[int, Decimal],
) -> Settlement:
    """Work every consignment through to what its supplier is owed, or say why not.

    `nett_by_row` is what each row was actually paid, from the same split the workbook writes, so
    a supplier is never settled against a figure the book does not hold.
    """
    found = Settlement()
    rows_by_consignment: dict[str, list[tuple[int, Row]]] = {}
    for offset, row in enumerate(round_.rows):
        rows_by_consignment.setdefault(row.consignment_id or "", []).append((offset, row))

    for consignment in round_.consignments:
        key = consignment.consignment_id or ""
        rows = rows_by_consignment.get(key, [])
        agreed = terms.get(key)

        sold = sum((row.cartons.net for _, row in rows), ZERO)
        sent = consignment.qty_sent
        # Cartons that never moved cost the supplier, not Zaco. Reported, never charged for.
        unsold = None if sent is None else sent - sold

        paid = _paid(rows, reconciliations, nett_by_row)
        line = Line(
            consignment_id=key,
            product=consignment.product.display_name,
            delivery_id=next((row.delivery_id for _, row in rows), None),
            supplier=agreed.supplier if agreed else None,
            percent=agreed.percent if agreed else None,
            nett=paid,
            cartons_sold=sold,
            cartons_sent=sent,
            cartons_unsold=unsold,
        )

        if agreed is None:
            found.awaiting_terms.append(
                _blocked(
                    line,
                    "No commission has been agreed for this delivery line, so what the supplier "
                    "is owed cannot be worked out. It is not settled at a default rate, and it "
                    "is not in any total.",
                )
            )
            continue
        if paid is None:
            found.awaiting_payment.append(
                _blocked(
                    line,
                    "No payment run has settled this consignment yet, or the one that names it "
                    "does not reconcile. There is no Nett to take a percentage of.",
                )
            )
            continue

        keeps = _rand(paid * agreed.percent / Decimal(100))
        found.settled.append(
            Line(
                consignment_id=line.consignment_id,
                product=line.product,
                delivery_id=line.delivery_id,
                supplier=line.supplier,
                percent=line.percent,
                nett=paid,
                zaco_keeps=keeps,
                # The remainder, not a second percentage: the two must add to the Nett exactly.
                owed_to_supplier=paid - keeps,
                cartons_sold=sold,
                cartons_sent=sent,
                cartons_unsold=unsold,
            )
        )
    return found


def _blocked(line: Line, reason: str) -> Line:
    return Line(
        consignment_id=line.consignment_id,
        product=line.product,
        delivery_id=line.delivery_id,
        supplier=line.supplier,
        percent=line.percent,
        nett=line.nett,
        cartons_sold=line.cartons_sold,
        cartons_sent=line.cartons_sent,
        cartons_unsold=line.cartons_unsold,
        blocked_by=reason,
    )


def _paid(
    rows: list[tuple[int, Row]],
    reconciliations: dict[str, Reconciliation],
    nett_by_row: dict[int, Decimal],
) -> Decimal | None:
    """What actually reached Zaco for this consignment, or `None` if any of it is unsettled.

    All or nothing per consignment. Settling a supplier on the half of a consignment that has
    been paid for, while the other half is still on the floor, pays out against money that has
    not arrived -- and the report would show it as complete.
    """
    if not rows:
        return None
    total = ZERO
    for offset, row in rows:
        found = reconciliations.get(row.account_sale)
        if found is None or not found.agrees:
            return None
        share = nett_by_row.get(offset)
        if share is None:
            return None
        total += share
    return total
