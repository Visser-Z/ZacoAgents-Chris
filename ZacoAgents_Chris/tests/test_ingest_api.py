"""The ingest endpoint: what the operator actually sees when they upload a document."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from zaco.auth.permissions import Permission

pytestmark = pytest.mark.db

DATA = Path(__file__).resolve().parent.parent / "data"


def _upload(client: TestClient, name: str, expected: str | None = None) -> object:
    files = {"file": (name, (DATA / name).read_bytes(), "application/octet-stream")}
    data = {"expected": expected} if expected else {}
    return client.post("/api/ingest/inspect", files=files, data=data)


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "operator@example.com", [Permission.INGEST])
    response = client.post(
        "/api/auth/login", json={"email": "operator@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    return client


def test_reading_a_document_reports_what_it_is_and_what_it_yielded(
    operator: TestClient,
) -> None:
    response = _upload(operator, "DailySalesDetail_20260601-20260608.csv")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["kind"] == "daily_sales_detail"
    assert body["kind_title"] == "Daily Sales Detail"
    assert body["counts"]["consignments"] == 9
    assert body["counts"]["dockets"] == 12
    assert len(body["preview"]) == 9


def test_a_narrowed_export_is_reported_as_narrowed(operator: TestClient) -> None:
    body = _upload(operator, "PaymentDetails_20260603-20260608_FarmersTrust.csv").json()
    assert body["scope"]["is_narrowed"] is True
    assert body["scope"]["market"] == "TSHWANE MARKET"
    assert any("not for everything" in p["message"] for p in body["problems"])


def test_an_unstated_scope_is_not_reported_as_a_full_one(operator: TestClient) -> None:
    body = _upload(
        operator, "ConsignmentReports_20260525-20260531.csv".replace(".csv", ".txt")
    ).json()
    assert body["scope"]["is_unstated"] is True
    assert body["scope"]["description"] == "Scope not stated"


def test_a_payment_with_no_breakdown_is_flagged_in_the_preview(operator: TestClient) -> None:
    body = _upload(operator, "PaymentDetails_20260603-20260608.txt").json()
    orphan = next(r for r in body["preview"] if r["label"] == "PRE*BT*382999")
    assert "can never reconcile" in orphan["flags"]


def test_the_agents_delivery_note_is_shown_but_labelled_as_the_agents(
    operator: TestClient,
) -> None:
    body = _upload(operator, "AccountSales_382405.txt").json()
    statement = body["preview"][0]
    assert statement["figures"]["Agent delivery note"] == "203003"
    assert any("not Zaco's DN" in flag for flag in statement["flags"])


def test_declaring_the_wrong_kind_is_refused_with_an_explanation(
    operator: TestClient,
) -> None:
    response = _upload(operator, "AccountSales_382405.txt", expected="payment_details")
    assert response.status_code == 422

    detail = response.json()["detail"]
    assert "Account sales statement" in detail["detail"]
    assert "Payment Details" in detail["detail"]
    assert "Nothing was taken from it" in detail["detail"]
    # The confidences are shown so the operator can see why, not just that.
    assert detail["scores"]["account_sales_statement"] == 1.0


def test_an_unrecognised_file_is_refused_rather_than_parsed(operator: TestClient) -> None:
    files = {"file": ("notes.txt", b"just some prose about fruit\n", "text/plain")}
    response = operator.post("/api/ingest/inspect", files=files)
    assert response.status_code == 422
    assert "does not read as any of the five" in response.json()["detail"]["detail"]


def test_an_unknown_kind_name_is_rejected(operator: TestClient) -> None:
    response = _upload(operator, "AccountSales_382405.txt", expected="invoice")
    assert response.status_code == 400


def test_the_five_supported_kinds_are_listed(operator: TestClient) -> None:
    body = operator.get("/api/ingest/kinds").json()
    assert len(body) == 5
    assert body["daily_sales_detail"] == "Daily Sales Detail"


# --- Permission boundary -------------------------------------------------------------------------


def test_an_account_without_ingest_cannot_upload(client: TestClient, db: Session) -> None:
    _make_user(db, "viewer@example.com", [Permission.VIEW_REPORTS])
    client.post("/api/auth/login", json={"email": "viewer@example.com", "password": PASSWORD})
    assert _upload(client, "AccountSales_382405.txt").status_code == 403


def test_a_signed_out_caller_cannot_upload(client: TestClient) -> None:
    assert _upload(client, "AccountSales_382405.txt").status_code == 401
