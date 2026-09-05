"""Section 9 over HTTP.

`tests/test_reports.py` pins the arithmetic and the choices. This pins the contract: that money
crosses as a string, that a period the report does not know is refused rather than quietly
treated as all time, and that the statements which qualify a figure travel with it.
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


@pytest.fixture
def viewer(client: TestClient, db: Session) -> TestClient:
    _make_user(
        db,
        "viewer@example.com",
        [Permission.INGEST, Permission.RESOLVE, Permission.VIEW_REPORTS],
    )
    client.post("/api/auth/login", json={"email": "viewer@example.com", "password": PASSWORD})
    return client


def test_an_empty_record_reports_nothing_rather_than_failing(viewer: TestClient) -> None:
    body = viewer.get("/api/reports").json()

    assert body["headline"]["takings"] == "R0.00"
    assert body["products"] == []


def test_the_figures_cross_the_wire_as_strings(viewer: TestClient) -> None:
    """No client gets the chance to turn a Decimal into a float on the way to a screen."""
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/reports").json()

    assert isinstance(body["headline"]["takings"], str)
    assert body["headline"]["takings"].startswith("R")
    assert all(isinstance(p["value"], str) for p in body["products"])


def test_the_return_rate_arrives_with_what_it_is_a_share_of(viewer: TestClient) -> None:
    """Section 9: "be careful what the rate is a share of". So the basis is not optional."""
    _settle(viewer, SALES, PAYMENTS)

    head = viewer.get("/api/reports").json()["headline"]

    assert head["return_rate"] is not None
    assert "over cartons sold" in head["return_rate_basis"]


def test_a_period_the_report_does_not_know_is_refused(viewer: TestClient) -> None:
    """A report labelled with a window it did not apply is worse than no report."""
    refused = viewer.get("/api/reports", params={"period": "quarter", "on": "2026-06-01"})

    assert refused.status_code == 422
    assert "all, month or week" in refused.json()["detail"]


def test_a_week_covers_only_that_week(viewer: TestClient) -> None:
    _settle(viewer, SALES, PAYMENTS)

    everything = viewer.get("/api/reports").json()
    week = viewer.get("/api/reports", params={"period": "week", "on": "2026-05-25"}).json()

    assert week["is_all_time"] is False
    assert week["period"].startswith("Week of")
    assert week["headline"]["docket_count"] <= everything["headline"]["docket_count"]


def test_the_ranking_says_which_basis_it_used_and_what_it_covers(viewer: TestClient) -> None:
    """Until terms exist it ranks on the market's money, not Zaco's, and has to say so."""
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/reports").json()

    assert "proxy" in body["take_on_basis"]
    assert body["commission_coverage"]
    assert any("proxy for what Zaco would earn" in c for c in body["caveats"])


def test_the_bands_arrive_with_what_they_mean(viewer: TestClient) -> None:
    """The letters alone say nothing to somebody who has not read the code."""
    _settle(viewer, SALES, PAYMENTS)

    bands = viewer.get("/api/reports").json()["bands"]

    assert "vital few" in bands["A"]
    assert "long tail" in bands["C"]


def test_reading_reports_is_its_own_permission(client: TestClient, db: Session) -> None:
    _make_user(db, "clerk@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "clerk@example.com", "password": PASSWORD})

    assert client.get("/api/reports").status_code == 403
