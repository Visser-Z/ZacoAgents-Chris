"""What the rounds before this one already account for (S1, S5, section 6).

A round that has been written into the operator's book is the most settled thing in the record.
It must go on counting towards every round after it -- for opening stock, for the dockets already
counted, and for the account sales already paid. These pin that it does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from tests.test_workbook_api import _settle
from zaco.auth.permissions import Permission
from zaco.db.models import Round
from zaco.resolve.service import history, rounds_after, workbook_path

pytestmark = pytest.mark.db

DATA = Path(__file__).resolve().parent.parent / "data"
SALES_MAY = "DailySalesDetail_20260525-20260531.csv"
SALES_JUNE = "DailySalesDetail_20260601-20260608.csv"
PAYMENTS = "PaymentDetails_20260529-20260602.csv"


@pytest.fixture(autouse=True)
def book_is_put_back() -> object:
    path = workbook_path()
    before = path.read_bytes()
    yield path
    path.write_bytes(before)


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(
        db,
        "operator@example.com",
        [
            Permission.INGEST,
            Permission.RESOLVE,
            Permission.APPEND,
        ],
    )
    client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": PASSWORD},
    )
    return client


def test_an_appended_round_still_counts_towards_the_rounds_after_it(
    operator: TestClient, db: Session
) -> None:
    """Appending must not drop a round out of the history the next one is derived from."""
    first = _settle(operator, SALES_MAY, PAYMENTS)
    operator.post(f"/api/rounds/{first}/append")

    later = Round(label="next", status="staged")
    db.add(later)
    db.flush()

    past = history(db, later)

    assert past.counted, "an appended round's dockets are no longer counted"
    assert past.settled, "an appended round's account sales are no longer settled"
    assert past.balances, "an appended round's closing stock is no longer carried forward"


def test_the_overlap_is_still_caught_after_the_first_round_is_appended(
    operator: TestClient,
) -> None:
    """S5: the June export reprints May's nectarine dockets, verbatim.

    Counted twice the book gains 65 cartons and R3,500 that never happened, and looks entirely
    normal doing it. Appending May must not un-catch that -- which it did, because an appended
    round used to drop out of the history the next round is derived from.
    """
    first = _settle(operator, SALES_MAY, PAYMENTS)
    operator.post(f"/api/rounds/{first}/append")

    saved = operator.post(
        "/api/rounds",
        files=[("files", (SALES_JUNE, (DATA / SALES_JUNE).read_bytes(), "text/csv"))],
    )
    assert saved.status_code == 201, saved.text
    body = operator.get(f"/api/rounds/{saved.json()['summary']['id']}").json()

    skipped = [a for a in body["alerts"] if "already" in a["message"].lower()]
    assert skipped, (
        "the June export reprints May's dockets and nothing said so, so they were counted again"
    )


def test_a_later_appended_round_is_named_when_an_earlier_one_is_reopened(
    operator: TestClient, db: Session
) -> None:
    """The warning has to name every round that re-derives without this one, book included."""
    first = _settle(operator, SALES_MAY, PAYMENTS)
    second = _settle(operator, SALES_JUNE, PAYMENTS)
    operator.post(f"/api/rounds/{second}/append")

    affected = rounds_after(db, db.get(Round, first))

    assert second in [r.id for r in affected]
