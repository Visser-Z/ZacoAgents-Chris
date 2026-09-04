"""Suppliers, terms and settlement over HTTP (section 8, D13, D14).

`tests/test_settlement.py` pins the arithmetic. This pins who may do what, and the inputs that
have to be refused -- both of which decide what a farmer is paid.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from zaco.auth.permissions import Permission

pytestmark = pytest.mark.db


def _client(client: TestClient, db: Session, email: str, *permissions: Permission) -> TestClient:
    _make_user(db, email, list(permissions))
    client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return client


@pytest.fixture
def clerk(client: TestClient, db: Session) -> TestClient:
    """Someone who may record terms, and read what they produce."""
    return _client(
        client, db, "clerk@example.com", Permission.RECORD_TERMS, Permission.VIEW_REPORTS
    )


def test_the_registers_start_empty(clerk: TestClient) -> None:
    """D13: seeded with nothing. Suppliers appear in no report."""
    assert clerk.get("/api/suppliers").json() == []
    assert clerk.get("/api/terms").json() == []

    board = clerk.get("/api/settlement").json()
    assert board["total_owed"] == "R0.00"
    assert board["by_supplier"] == []


def test_a_supplier_can_be_recorded_and_read_back(clerk: TestClient) -> None:
    created = clerk.post("/api/suppliers", json={"name": "Sunnyvale Orchards"})

    assert created.status_code == 201
    assert [s["name"] for s in clerk.get("/api/suppliers").json()] == ["Sunnyvale Orchards"]
    assert created.json()["created_by"] == "clerk@example.com"


def test_two_suppliers_cannot_share_a_name(clerk: TestClient) -> None:
    """Every settlement against either of them would be ambiguous."""
    clerk.post("/api/suppliers", json={"name": "Sunnyvale Orchards"})

    again = clerk.post("/api/suppliers", json={"name": "Sunnyvale Orchards"})

    assert again.status_code == 409


def test_a_commission_outside_nought_to_a_hundred_is_refused(clerk: TestClient) -> None:
    """Not a rate anybody agreed -- a typing slip that would pay a supplier a negative amount."""
    supplier = clerk.post("/api/suppliers", json={"name": "Sunnyvale"}).json()

    for percent in (-5, 150):
        refused = clerk.post(
            "/api/terms",
            json={"consignment_id": "C1", "supplier_id": supplier["id"], "percent": percent},
        )
        assert refused.status_code == 422, percent


def test_agreeing_terms_twice_for_one_line_replaces_rather_than_duplicates(
    clerk: TestClient,
) -> None:
    """One delivery line has one set of terms. Two would mean two settlements for one lot."""
    supplier = clerk.post("/api/suppliers", json={"name": "Sunnyvale"}).json()
    body = {"consignment_id": "C1", "supplier_id": supplier["id"], "percent": 10}
    clerk.post("/api/terms", json=body)

    clerk.post("/api/terms", json={**body, "percent": 12.5})

    terms = clerk.get("/api/terms").json()
    assert len(terms) == 1
    assert terms[0]["percent"] == "12.5"


def test_terms_for_an_unknown_supplier_are_refused(clerk: TestClient) -> None:
    refused = clerk.post(
        "/api/terms", json={"consignment_id": "C1", "supplier_id": 999, "percent": 10}
    )

    assert refused.status_code == 404


def test_reading_a_report_does_not_carry_the_right_to_set_what_a_farmer_is_paid(
    client: TestClient, db: Session
) -> None:
    """D14: permissions are granular, and recording terms decides money."""
    viewer = _client(client, db, "viewer@example.com", Permission.VIEW_REPORTS)

    assert viewer.get("/api/settlement").status_code == 200
    assert viewer.post("/api/suppliers", json={"name": "Sunnyvale"}).status_code == 403
    assert (
        viewer.post(
            "/api/terms", json={"consignment_id": "C1", "supplier_id": 1, "percent": 10}
        ).status_code
        == 403
    )


def test_recording_a_payment_needs_a_real_supplier(clerk: TestClient) -> None:
    refused = clerk.post("/api/supplier-payments", json={"supplier_id": 999, "amount": "100.00"})

    assert refused.status_code == 404


def test_the_coverage_is_returned_beside_the_totals(clerk: TestClient) -> None:
    """Section 9: a figure over a fifth of the business is only useful if you know it is."""
    board = clerk.get("/api/settlement").json()

    assert board["coverage"]
