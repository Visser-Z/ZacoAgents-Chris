"""Turning domain values into the strings the API sends.

Money and quantities cross the wire as **strings**, not numbers. A `Decimal` serialised as a
JSON number becomes a float in every client that parses it, and section 8 requires agreement to
the cent -- so the formatting decision is made once, here, and the client is never handed a type
that can lose a cent on the way in.
"""

from __future__ import annotations

from decimal import Decimal

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
