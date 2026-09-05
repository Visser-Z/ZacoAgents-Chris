"""Section 10 over HTTP.

`tests/test_conduct.py` pins the arithmetic and the choices. This pins the contract: that the
not-answerable conclusion cannot be fetched away from the figures, and that money crosses as a
string like everywhere else.
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
        "conduct@example.com",
        [Permission.INGEST, Permission.RESOLVE, Permission.VIEW_REPORTS],
    )
    client.post("/api/auth/login", json={"email": "conduct@example.com", "password": PASSWORD})
    return client


def test_an_empty_record_still_states_what_cannot_be_checked(viewer: TestClient) -> None:
    """The blind spot does not depend on there being anything to look at.

    A panel with nothing in it is exactly where a missing caveat reads as a clean bill of health.
    """
    body = viewer.get("/api/conduct").json()

    assert body["not_answerable"]
    assert body["kept"] == []
    assert body["normal_share_kept"] is None


def test_the_not_answerable_conclusion_arrives_with_the_figures(viewer: TestClient) -> None:
    """One response, so a client cannot fetch the reassuring half on its own."""
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/conduct").json()

    assert body["kept"]
    assert "cannot be answered from these reports" in body["not_answerable"]
    assert body["price_evidence"]


def test_the_figures_cross_the_wire_as_strings(viewer: TestClient) -> None:
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/conduct").json()

    assert all(isinstance(k["gross"], str) and k["gross"].startswith("R") for k in body["kept"])
    assert all(isinstance(k["share"], str) and k["share"].endswith("%") for k in body["kept"])


def test_every_account_sale_is_listed_not_only_the_flagged_ones(viewer: TestClient) -> None:
    """The threshold governs emphasis, never visibility: how ordinary the ordinary ones are is
    what makes the comparison mean anything."""
    _settle(viewer, SALES, PAYMENTS)

    body = viewer.get("/api/conduct").json()

    assert len(body["kept"]) > len([k for k in body["kept"] if k["is_flagged"]])


def test_a_flag_carries_the_figures_that_raised_it(viewer: TestClient) -> None:
    """Section 10: "Anything flagged carries the figures that raised it"."""
    _settle(viewer, SALES, PAYMENTS)

    flagged = [k for k in viewer.get("/api/conduct").json()["kept"] if k["is_flagged"]]

    for line in flagged:
        assert line["gross"] and line["nett"] and line["kept"]
        assert line["normal_kept"] is not None
        assert line["excess"] is not None


def test_reading_conduct_is_the_reports_permission(client: TestClient, db: Session) -> None:
    _make_user(db, "conduct-clerk@example.com", [Permission.INGEST])
    client.post(
        "/api/auth/login", json={"email": "conduct-clerk@example.com", "password": PASSWORD}
    )

    assert client.get("/api/conduct").status_code == 403
