"""Recreating each product's share of a statement's single printed Nett (section 6).

An account sales statement prints one Nett for a page that may cover several products. The
workbook needs a figure per row, and section 6 says where it comes from: "Recreate each row's
share from the statement's **own printed deductions table**. Do not derive rates of your own;
split the printed totals."

Two rules, and the second is the one that costs money if it is missed:

- a deduction that applies generally spreads across the rows it covers, in proportion to value
- **a deduction named for a fruit lands only on the rows for that fruit.** "Splitting a plum levy
  proportionally puts part of it on the grapes."

`AccountSales_382900.txt` is the case. Gross 4000 over plums (3000) and nectarines (1000); market
fees 230 general; plums levy 46 named. Plums take 3000 - 172.50 - 46 = 2781.50, nectarines
1000 - 57.50 = 942.50, and those sum to the printed 3724.00 exactly.

Nothing is apportioned silently. Every share carries the deductions that produced it and the
reason each one landed, and where the printed figures do not reconcile, no figure is produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from zaco.ingest.records import AccountSalesStatement, Deduction
from zaco.money.allocate import CannotAllocateError, allocate


class CannotSplitError(Exception):
    """The printed figures do not reconcile, so no share is produced (section 6).

    "If the printed deductions cannot be reconciled to the printed Nett, do not produce a figure.
    Say so instead."
    """


@dataclass(frozen=True)
class AppliedDeduction:
    """One deduction's share of one product, and why it landed there."""

    name: str
    amount: Decimal
    reason: str


@dataclass(frozen=True)
class Share:
    """One product's part of the statement, and the Nett it works out to."""

    product_name: str
    value: Decimal
    nett: Decimal
    deductions: list[AppliedDeduction] = field(default_factory=list)


@dataclass(frozen=True)
class Split:
    """Every product's share, with what was decided along the way.

    `is_apportioned` is false only where the statement covered a single product, because then the
    printed Nett *is* that product's and nothing was worked out. Everywhere else the figure is
    this module's arithmetic, and section 6 requires it to be marked and to stay editable.
    """

    shares: list[Share]
    notes: list[str] = field(default_factory=list)

    @property
    def is_apportioned(self) -> bool:
        return len(self.shares) > 1


#: Words in a deduction name that describe a cost rather than a fruit. Deliberately short: a word
#: only targets a deduction when a product **on this statement** carries it, so this list is a
#: readability aid rather than the thing keeping a plum levy off the grapes.
_COST_WORDS = frozenset(
    {
        "levy",
        "levies",
        "fee",
        "fees",
        "market",
        "commission",
        "handling",
        "transport",
        "delivery",
        "admin",
        "administration",
        "insurance",
        "cost",
        "costs",
        "charge",
        "charges",
        "vat",
        "input",
        "output",
        "total",
        "agent",
        "deduction",
        "deductions",
    }
)


def _words(text: str) -> set[str]:
    """The meaningful words of a name, stemmed just enough to match `PLUMS` to `PLUM`.

    Only a trailing `s` comes off. Anything cleverer starts matching things that are not the same
    fruit, and a wrong match here moves money onto the wrong rows.
    """
    found = set()
    for word in re.findall(r"[A-Za-z]+", text.lower()):
        if len(word) < 3 or word in _COST_WORDS:
            continue
        found.add(word[:-1] if word.endswith("s") and len(word) > 3 else word)
    return found


def _targets(deduction: Deduction, products: list[tuple[str, Decimal]]) -> list[int]:
    """Which products a deduction lands on: the ones it names, or all of them.

    A deduction counts as naming a fruit only when a product **on this statement** carries one of
    its words. That is evidence rather than resemblance -- the same standard the product merge is
    held to -- so an unfamiliar cost name spreads generally instead of stopping the round.
    """
    named = _words(deduction.name)
    matched = [i for i, (name, _) in enumerate(products) if named & _words(name)]
    return matched or list(range(len(products)))


def split_statement(statement: AccountSalesStatement) -> Split:
    """Each product's share of the statement's printed Nett, or a refusal to state one."""
    products = [
        (product.product_name or f"(unnamed product {i + 1})", product.total_value)
        for i, product in enumerate(statement.products)
    ]
    if not products:
        raise CannotSplitError(
            "This statement prints no product blocks, so its Nett cannot be attributed to "
            "anything. It has to be reported rather than split."
        )
    if statement.nett_amount is None:
        raise CannotSplitError(
            "This statement prints no Nett amount, so there is nothing to split."
        )

    notes: list[str] = []
    gross = sum((value for _, value in products), Decimal(0))
    if statement.gross_amount is not None and statement.gross_amount != gross:
        raise CannotSplitError(
            f"The product blocks add up to R{gross:,.2f} but the statement prints a gross of "
            f"R{statement.gross_amount:,.2f}. Until that is explained, no share can be stood "
            f"behind."
        )

    charged = sum((d.total for d in statement.deductions if d.total is not None), Decimal(0))
    if gross - charged != statement.nett_amount:
        raise CannotSplitError(
            f"The printed deductions do not reconcile to the printed Nett: R{gross:,.2f} less "
            f"R{charged:,.2f} is R{gross - charged:,.2f}, and the statement prints "
            f"R{statement.nett_amount:,.2f}. No figure is produced."
        )

    applied: list[list[AppliedDeduction]] = [[] for _ in products]
    for deduction in statement.deductions:
        if deduction.total is None:
            notes.append(f"{deduction.name} prints no total and was left out of the split.")
            continue
        where = _targets(deduction, products)
        general = len(where) == len(products)
        reason = (
            "spread across every row, in proportion to value"
            if general
            else "on this row only, because the deduction names this fruit"
        )
        try:
            portions = allocate(deduction.total, [products[i][1] for i in where])
        except CannotAllocateError as refusal:
            raise CannotSplitError(
                f"{deduction.name} (R{deduction.total:,.2f}) cannot be split: {refusal}"
            ) from refusal
        for index, amount in zip(where, portions, strict=True):
            applied[index].append(AppliedDeduction(deduction.name, amount, reason))
        if not general:
            named = ", ".join(products[i][0] for i in where)
            notes.append(f"{deduction.name} landed only on {named}, because it names that fruit.")

    shares = [
        Share(
            product_name=name,
            value=value,
            nett=value - sum((d.amount for d in applied[index]), Decimal(0)),
            deductions=applied[index],
        )
        for index, (name, value) in enumerate(products)
    ]

    total = sum((share.nett for share in shares), Decimal(0))
    if total != statement.nett_amount:
        raise CannotSplitError(
            f"The shares add up to R{total:,.2f} and the statement prints "
            f"R{statement.nett_amount:,.2f}. They must agree to the cent, so no figure is produced."
        )
    return Split(shares=shares, notes=notes)
