"""Every sale off the floor, dated.

This endpoint exists so a client can bucket sales by day or week without section 9 recomputing
the record once per point. What could be wrong here without looking wrong is the counting: a
docket seen in two rounds appearing twice, or an undated one quietly dropped, would both produce
a chart that looks entirely reasonable and disagrees with the reports beside it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from tests.test_workbook_api import _settle
from zaco.auth.permissions import Permission

pytestmark = pytest.mark.db

SALES = "DailySalesDetail_20260525-20260531.csv"
PAYMENTS = "PaymentDetails_20260529-20260602.csv"
CONSIGNMENTS = "ConsignmentReports_20260525-20260531.txt"


def viewer_dockets(client: TestClient) -> list[dict[str, object]]:
    body = client.get("/api/dockets").json()
    return list(body["dockets"])


@pytest.fixture
def viewer(client: TestClient, db: Session) -> TestClient:
    _make_user(
        db,
        "dockets@example.com",
        [Permission.INGEST, Permission.RESOLVE, Permission.VIEW_REPORTS],
    )
    client.post("/api/auth/login", json={"email": "dockets@example.com", "password": PASSWORD})
    return client


def test_an_empty_record_reports_nothing_rather_than_failing(viewer: TestClient) -> None:
    body = viewer.get("/api/dockets").json()

    assert body["dockets"] == []
    assert body["first_sale"] is None
    assert body["undated"] == 0


def test_the_figures_are_numbers_because_a_chart_cannot_draw_a_string(viewer: TestClient) -> None:
    """The one documented exception to the money-as-strings rule -- see `render.plot`."""
    _settle(viewer, SALES, PAYMENTS)

    dockets = viewer.get("/api/dockets").json()["dockets"]

    assert dockets
    valued = [d for d in dockets if d["value"] is not None]
    assert valued
    assert all(isinstance(d["value"], (int, float)) for d in valued)
    assert all(isinstance(d["date_sold"], str) for d in dockets if d["date_sold"])


def test_a_sale_told_twice_by_two_documents_is_one_docket(client: TestClient, db: Session) -> None:
    """The consignment report restates every sale the daily sales file already carried.

    Adding it must change nothing: 8 dockets either way. Counted twice, a takings chart would run
    ahead of the reports beside it and look entirely normal doing it. Asserting the count is
    unchanged pins that, where asserting the identities are unique would still pass if the
    duplicates differed in some field nobody thought to compare.
    """
    _make_user(
        db, "one@example.com", [Permission.INGEST, Permission.RESOLVE, Permission.VIEW_REPORTS]
    )
    client.post("/api/auth/login", json={"email": "one@example.com", "password": PASSWORD})
    _settle(client, SALES, PAYMENTS)
    alone = viewer_dockets(client)

    _make_user(
        db, "two@example.com", [Permission.INGEST, Permission.RESOLVE, Permission.VIEW_REPORTS]
    )
    client.post("/api/auth/login", json={"email": "two@example.com", "password": PASSWORD})
    _settle(client, SALES, CONSIGNMENTS, PAYMENTS)
    together = viewer_dockets(client)

    assert alone
    assert len(together) == len(alone)


def test_the_dockets_are_ordered_by_sale_date_with_the_undated_last(viewer: TestClient) -> None:
    """A client plotting them in receipt order draws a line that wanders backwards."""
    _settle(viewer, SALES, PAYMENTS)

    dockets = viewer.get("/api/dockets").json()["dockets"]
    dated = [d["date_sold"] for d in dockets if d["date_sold"]]
    seen_undated = [i for i, d in enumerate(dockets) if d["date_sold"] is None]

    assert dated == sorted(dated)
    assert all(i >= len(dated) for i in seen_undated)


def test_an_undated_docket_is_counted_and_not_dropped(viewer: TestClient) -> None:
    """It cannot go on a time axis, and leaving it out would shrink the total silently."""
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/dockets").json()

    assert body["undated"] == sum(1 for d in body["dockets"] if d["date_sold"] is None)


def test_the_span_reported_is_the_span_of_the_dockets(viewer: TestClient) -> None:
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/dockets").json()
    dated = sorted(d["date_sold"] for d in body["dockets"] if d["date_sold"])

    assert body["first_sale"] == dated[0]
    assert body["last_sale"] == dated[-1]
    assert body["rounds_covered"] >= 1


def test_reading_dockets_is_the_reports_permission(client: TestClient, db: Session) -> None:
    _make_user(db, "docket-clerk@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "docket-clerk@example.com", "password": PASSWORD})

    assert client.get("/api/dockets").status_code == 403
