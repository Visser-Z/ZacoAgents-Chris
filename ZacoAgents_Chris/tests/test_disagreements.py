"""Two documents describing one record differently (D12).

The supplied data does not contain this case: the narrowed Farmers Trust re-export repeats three
account sales with **identical** figures, so it exercises the auto-skip half of D12 and not the
conflict half. Rather than leave the conflict path untested until it fires on a real round, the
fixture here is the real narrowed export with one number changed -- which is exactly what a
re-run after a correction would look like.
"""

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
FULL = "PaymentDetails_20260603-20260608.txt"
NARROWED = "PaymentDetails_20260603-20260608_FarmersTrust.csv"


def _conflicting() -> bytes:
    """The narrowed export with account sale 382880 paying R260.00 instead of R250.00."""
    text = (DATA / NARROWED).read_text(encoding="utf-8")
    assert "250.00" in text, "fixture drifted from the real file"
    return text.replace("250.00", "260.00", 1).encode("utf-8")


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "operator@example.com", [Permission.INGEST, Permission.RESOLVE])
    client.post("/api/auth/login", json={"email": "operator@example.com", "password": PASSWORD})
    return client


@pytest.fixture
def conflicted(operator: TestClient) -> Any:
    files = [
        ("files", (FULL, (DATA / FULL).read_bytes(), "text/plain")),
        ("files", ("PaymentDetails_corrected.csv", _conflicting(), "text/csv")),
    ]
    response = operator.post("/api/rounds", files=files)
    assert response.status_code == 201, response.text
    return response.json()


def test_the_record_is_suspended_and_the_rest_of_the_file_is_not(conflicted: Any) -> None:
    """Refusing the whole export would throw away every record in it that was fine."""
    assert len(conflicted["suspensions"]) == 1
    assert conflicted["suspensions"][0]["subject_key"] == "PRE*BT*382880"
    assert int(conflicted["totals"]["account_sales"]) > 1


def test_the_suspension_shows_both_figures_and_names_both_documents(conflicted: Any) -> None:
    suspension = conflicted["suspensions"][0]
    assert "250.00" in suspension["differences"]
    assert "260.00" in suspension["differences"]
    assert FULL in suspension["description"]
    assert "PaymentDetails_corrected.csv" in suspension["description"]


def test_neither_figure_is_silently_applied_over_the_other(conflicted: Any) -> None:
    sale = next(a for a in conflicted["account_sales"] if a["display_number"] == "382880")
    assert sale["nett"] == "R250.00"


def test_an_undecided_disagreement_blocks_the_round(operator: TestClient, conflicted: Any) -> None:
    assert conflicted["is_clear"] is False
    response = operator.post(f"/api/rounds/{conflicted['summary']['id']}/resolve")
    assert response.status_code == 409
    assert "disagreement" in response.json()["detail"]


def test_settling_it_requires_a_typed_reason(operator: TestClient, conflicted: Any) -> None:
    """ "Chose the Farmers Trust export" is worth nothing next quarter without the why."""
    round_id = conflicted["summary"]["id"]
    suspension_id = conflicted["suspensions"][0]["id"]
    response = operator.post(
        f"/api/rounds/{round_id}/suspensions/{suspension_id}",
        json={"chosen_source": FULL, "reason": ""},
    )
    assert response.status_code == 422


def test_a_settled_disagreement_keeps_the_reason_and_the_person(
    operator: TestClient, conflicted: Any
) -> None:
    round_id = conflicted["summary"]["id"]
    suspension_id = conflicted["suspensions"][0]["id"]
    response = operator.post(
        f"/api/rounds/{round_id}/suspensions/{suspension_id}",
        json={"chosen_source": FULL, "reason": "the full export, not the corrected re-run"},
    )
    assert response.status_code == 200
    settled = response.json()["suspensions"][0]
    assert settled["is_decided"] is True
    assert settled["chosen_source"] == FULL
    assert settled["decided_by"] == "operator@example.com"
    assert "full export" in settled["reason"]


def test_a_decision_is_not_asked_for_twice(operator: TestClient, conflicted: Any) -> None:
    round_id = conflicted["summary"]["id"]
    suspension_id = conflicted["suspensions"][0]["id"]
    operator.post(
        f"/api/rounds/{round_id}/suspensions/{suspension_id}",
        json={"chosen_source": FULL, "reason": "the full export"},
    )
    again = operator.get(f"/api/rounds/{round_id}").json()
    assert len(again["suspensions"]) == 1
    assert again["suspensions"][0]["is_decided"] is True
