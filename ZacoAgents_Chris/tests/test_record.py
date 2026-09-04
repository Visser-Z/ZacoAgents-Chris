"""The whole record, accumulated from the settled rounds (sections 3 and 9).

A consignment sits on the floor until it clears, so it commonly sells in one round and goes on
selling in the next. Two things then have to be true at once and they pull opposite ways: what it
sold must accumulate, and what it was *sent* must not.

Both are pinned here against the real files, because both produce a figure that looks entirely
normal when it is wrong.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from tests.test_workbook_api import _settle
from zaco.auth.permissions import Permission
from zaco.resolve.service import record_so_far

pytestmark = pytest.mark.db

DATA = Path(__file__).resolve().parent.parent / "data"
SALES_MAY = "DailySalesDetail_20260525-20260531.csv"
SALES_JUNE = "DailySalesDetail_20260601-20260608.csv"
PAYMENTS = "PaymentDetails_20260529-20260602.csv"

#: Oranges. One consignment, 200 cartons sent, selling in both supplied rounds.
ORANGES = "118312006Z"


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "operator@example.com", [Permission.INGEST, Permission.RESOLVE])
    client.post("/api/auth/login", json={"email": "operator@example.com", "password": PASSWORD})
    return client


@pytest.fixture
def both_rounds(operator: TestClient, db: Session) -> Session:
    _settle(operator, SALES_MAY, PAYMENTS)
    _settle(operator, SALES_JUNE)
    return db


def _oranges(db: Session):
    combined = record_so_far(db)
    return next(c for c in combined.consignments if c.consignment_id == ORANGES)


def test_a_consignment_selling_in_two_rounds_keeps_both_rounds_of_sales(
    both_rounds: Session,
) -> None:
    """R1,500 in May and R900 in June. Keeping only the first sighting loses the June sale."""
    oranges = _oranges(both_rounds)

    assert oranges.value == Decimal("2400.00")
    assert len(oranges.dockets) == 2


def test_time_on_market_spans_the_rounds_rather_than_stopping_at_the_first(
    both_rounds: Session,
) -> None:
    """Section 9 asks for how long it took to move. Truncated at the round boundary it reads 1."""
    oranges = _oranges(both_rounds)

    assert oranges.last_sold is not None
    assert oranges.days_on_market == 6


def test_what_was_sent_is_not_doubled_by_selling_in_two_rounds(both_rounds: Session) -> None:
    """Section 3: a figure belonging to the delivery is counted once. A round boundary is not a
    second load."""
    combined = record_so_far(both_rounds)
    oranges = [c for c in combined.consignments if c.consignment_id == ORANGES]

    assert len(oranges) == 1
    assert oranges[0].qty_sent == Decimal("200")


def test_the_record_holds_each_consignment_once(both_rounds: Session) -> None:
    combined = record_so_far(both_rounds)
    ids = [c.consignment_id for c in combined.consignments if c.consignment_id]

    assert len(ids) == len(set(ids))
