"""Splitting an amount across weights so the shares sum to it exactly.

The obvious approach -- work out each share and round it to the cent -- does not add up. Three
rows sharing R100 by equal value get R33.33 each and lose a cent; the operator is then holding a
payment of R100 against rows totalling R99.99, and no amount of staring at the rows says where it
went.

Largest remainder fixes that. Give every row the whole cents its share is worth, count the cents
left over, and hand them out one each to the rows whose fractional part was largest. The result
sums to the total by construction rather than by luck, and every cent is attributable to a row.

Ties are broken by position, so the same inputs always give the same answer. Section 9 requires
reports to be reproducible; an allocator that broke ties arbitrarily would put that out of reach
for anything built on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


class CannotAllocateError(Exception):
    """The split cannot be made, and no figure should be produced (section 11).

    Raised rather than returning something plausible. A caller that cannot allocate has to say so
    to the operator; it must not quietly fall back to equal shares or to zero.
    """


def allocate(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Split `total` across `weights`, in proportion, summing to `total` exactly.

    `total` may be negative -- a payment run can be a credit -- and is allocated by magnitude and
    then negated, so the sign never interferes with the remainder handling.

    Raises `CannotAllocateError` when the weights cannot express a proportion: none given, any of
    them negative, or all of them nought. Each of those is a real situation the caller has to
    report rather than paper over -- an account sale covering rows that sold nothing has a nett
    that belongs somewhere, and this is not the code that gets to decide where.
    """
    if not weights:
        raise CannotAllocateError("There are no rows to split this across.")
    if any(weight < 0 for weight in weights):
        raise CannotAllocateError(
            "One of the rows has a negative value, so the shares cannot be worked out in "
            "proportion. Sales and returns are held apart for exactly this reason; a row whose "
            "returns exceed its sales needs a person to say what it should be paid."
        )
    if sum(weights) == 0:
        raise CannotAllocateError(
            "Every row is worth nought, so there is no proportion to split by. The money is real "
            "and has to land somewhere a person chooses."
        )

    sign = -1 if total < 0 else 1
    cents = int((abs(total) / CENT).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    weighed = sum(weights)

    # Whole cents first, then the remainder, so nothing is created or lost in the rounding.
    exact = [Decimal(cents) * weight / weighed for weight in weights]
    whole = [int(share) for share in exact]
    left_over = cents - sum(whole)

    # The rows with the largest fractional part have the best claim to the cents left over.
    # Position breaks a tie, so the same input always gives the same answer.
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - whole[i]), i))
    for i in order[:left_over]:
        whole[i] += 1

    return [Decimal(share * sign) * CENT for share in whole]
