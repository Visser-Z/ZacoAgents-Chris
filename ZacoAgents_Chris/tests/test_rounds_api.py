"""Staging a round through the API: what the operator sees before anything is written."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from zaco.auth.permissions import Permission

pytestmark = pytest.mark.db

DATA = Path(__file__).resolve().parent.parent / "data"

EVERYTHING = [
    "DailySalesDetail_20260525-20260531.csv",
    "ConsignmentReports_20260525-20260531.txt",
    "PaymentDetails_20260529-20260602.csv",
    "AccountSales_382405.txt",
    "AccountSales_382900.txt",
    "DailySalesDetail_20260601-20260608.csv",
    "PaymentDetails_20260603-20260608.txt",
    "PaymentDetails_20260603-20260608_FarmersTrust.csv",
    "NettPaymentAdjustments_202604.txt",
]


def _stage(client: TestClient, names: list[str]) -> Any:
    files = [("files", (n, (DATA / n).read_bytes(), "application/octet-stream")) for n in names]
    return client.post("/api/rounds/stage", files=files)


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "operator@example.com", [Permission.INGEST])
    assert (
        client.post(
            "/api/auth/login", json={"email": "operator@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    return client


@pytest.fixture
def staged(operator: TestClient) -> Any:
    response = _stage(operator, EVERYTHING)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_round_reports_its_grain(staged: Any) -> None:
    assert staged["totals"]["deliveries"] == "11"
    assert staged["totals"]["consignments"] == "11"
    # More rows than consignments, because three consignments span two account sales each.
    assert staged["totals"]["rows"] == "14"


def test_cartons_sent_is_labelled_as_a_delivery_figure(staged: Any) -> None:
    assert staged["totals"]["cartons_sent"] == "549"
    assert "qty_sent" not in staged["rows"][0]


def test_returns_are_reported_beside_the_sale(staged: Any) -> None:
    assert staged["cartons"]["sold"] == "356"
    assert staged["cartons"]["returned"] == "6"
    assert staged["cartons"]["net"] == "350"
    assert staged["cartons"]["returns_reportable"] is True


def test_the_unresolved_products_are_counted_because_no_row_can_be_written_without_them(
    staged: Any,
) -> None:
    assert staged["totals"]["products_unresolved"] == "11"
    assert len(staged["products"]) == 13


def test_the_proven_product_link_is_shown_with_its_evidence(staged: Any) -> None:
    cherries = next(p for p in staged["products"] if p["short_code"] == "Imp Cherries 5kg")
    assert sorted(cherries["vocabularies"]) == ["sales", "statement"]
    assert "382405" in cherries["merge_reasons"][0]


def test_resemblances_are_offered_as_suggestions_not_applied(staged: Any) -> None:
    reasons = " ".join(s["reason"] for s in staged["suggestions"])
    assert "not evidence" in reasons
    assert "ANGELINO" in reasons


def test_a_docket_with_no_account_sale_is_listed_separately(staged: Any) -> None:
    assert len(staged["unpaid_dockets"]) == 1
    assert staged["unpaid_dockets"][0]["docket_number"] == "PRE*B6E01C39001*03Z"


def test_an_account_sale_with_no_breakdown_is_marked(staged: Any) -> None:
    orphan = next(a for a in staged["account_sales"] if a["display_number"] == "382999")
    assert orphan["has_commodity_breakdown"] is False
    assert orphan["row_count"] == 0


def test_the_agents_share_of_the_sale_is_shown_per_account_sale(staged: Any) -> None:
    apples = next(a for a in staged["account_sales"] if a["display_number"] == "382875")
    assert apples["deduction_share"] == "60.0%"


def test_one_unreadable_document_refuses_the_whole_round(operator: TestClient) -> None:
    """Staging the rest would show a picture that looks complete and is not."""
    files = [
        (
            "files",
            (
                "AccountSales_382405.txt",
                (DATA / "AccountSales_382405.txt").read_bytes(),
                "text/plain",
            ),
        ),
        ("files", ("notes.txt", b"prose about fruit", "text/plain")),
    ]
    response = operator.post("/api/rounds/stage", files=files)
    assert response.status_code == 422
    assert "notes.txt" in response.json()["detail"]["detail"]


def test_staging_is_gated_on_the_ingest_permission(client: TestClient, db: Session) -> None:
    _make_user(db, "viewer@example.com", [Permission.VIEW_REPORTS])
    client.post("/api/auth/login", json={"email": "viewer@example.com", "password": PASSWORD})
    assert _stage(client, ["AccountSales_382405.txt"]).status_code == 403


def test_a_signed_out_caller_cannot_stage(client: TestClient) -> None:
    assert _stage(client, ["AccountSales_382405.txt"]).status_code == 401
