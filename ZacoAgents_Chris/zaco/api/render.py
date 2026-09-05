"""Turning domain values into the strings the API sends.

Money and quantities cross the wire as **strings**, not numbers. A `Decimal` serialised as a
JSON number becomes a float in every client that parses it, and section 8 requires agreement to
the cent -- so the formatting decision is made once, here, and the client is never handed a type
that can lose a cent on the way in.

The one exception is `plot()`, which exists because a chart cannot draw a string. It is confined
to a response's `chart` block, the authoritative figure travels beside it as a string, and nothing
is settled against either. Its docstring carries the full argument.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from zaco.api.schemas import CartonsOut, ConsignmentOut
from zaco.domain.model import Cartons, Consignment
from zaco.domain.model import (
    display_account_sale as _display_account_sale,
)


def number(value: Decimal) -> str:
    return f"{value:g}"


def optional_number(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:g}"


def money(value: Decimal) -> str:
    return f"R{value:,.2f}"


def optional_money(value: Decimal | None) -> str | None:
    return None if value is None else f"R{value:,.2f}"


def percent(value: Decimal | None) -> str | None:
    """A ratio as a percentage to two places.

    **Display only** -- never a figure anything is settled against, which is why rounding here is
    safe where rounding a Nett share is not. Rendered on this side rather than in the page so two
    clients cannot disagree about what "1.64%" was a share of.
    """
    if value is None:
        return None
    return f"{(value * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def multiple(value: Decimal | None) -> str | None:
    """How many times over, to two places -- "4.00x". Display only, as `percent` is."""
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}x"


def plot(value: Decimal | None) -> float | None:
    """A figure as a plain number, **for drawing only**.

    Everything else in this module deliberately refuses to do this: money crosses the wire as a
    string precisely so no client can turn a `Decimal` into a float. A chart cannot draw a string,
    so this is the one documented exception, and it is narrow on purpose:

    * it appears only inside a response's `chart` block, never beside the figure it mirrors;
    * the authoritative figure is still sent as a string in the same response, and that is the one
      a screen shows and a person settles against;
    * nothing is computed from these. A bar's length is not a number anybody is owed.

    The precedent is `percent()` above, which has rounded a display ratio since section 9: safe
    there, and safe here, for the same reason -- no one is paid what a chart says. `None` survives
    as `None`, because a bar of nought and no bar at all are different claims (section 6).
    """
    return None if value is None else float(value)


def display_account_sale(number_: str) -> str:
    """D7: the bare number where one exists, the full reference where it does not."""
    return _display_account_sale(number_)


def cartons(value: Cartons) -> CartonsOut:
    return CartonsOut(
        sold=number(value.sold),
        returned=optional_number(value.returned),
        net=number(value.net),
        returns_reportable=value.returns_reportable,
    )


def consignment(value: Consignment) -> ConsignmentOut:
    return ConsignmentOut(
        consignment_id=value.consignment_id,
        product=value.product.display_name,
        short_code=value.product.short_code,
        market=value.market,
        agent=value.agent,
        qty_sent=optional_number(value.qty_sent),
        qty_available=optional_number(value.qty_available),
        cartons=cartons(value.cartons),
        value=money(value.value),
        docket_count=len(value.dockets),
        account_sales=value.account_sales,
        days_on_market=value.days_on_market,
        is_identifiable=value.is_identifiable,
    )
