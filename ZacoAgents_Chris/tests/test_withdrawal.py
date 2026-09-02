"""Taking a document back out of a round.

The classifier refuses what it cannot read, which is a narrower guard than it looks. A file that
genuinely *is* one of the five kinds -- another producer's payment export, last quarter's run --
is read without complaint and lands in the round. Being readable is not the same as belonging
here, so there has to be a way out.

A document is withdrawn, never deleted: its figures leave the round, the bytes stay, and the
reason and the person stay with them. A round that once held six documents and now holds five
must not look like one that always held five.
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
PERSONAL = Path(__file__).resolve().parent.parent / "PersonalTest"

SALES = "DailySalesDetail_20260525-20260531.csv"
PAYMENTS = "PaymentDetails_20260529-20260602.csv"


def _files(*names: str) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (n, (DATA / n).read_bytes(), "text/csv")) for n in names]


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "operator@example.com", [Permission.INGEST, Permission.RESOLVE])
    client.post("/api/auth/login", json={"email": "operator@example.com", "password": PASSWORD})
    return client


@pytest.fixture
def round_(operator: TestClient) -> Any:
    response = operator.post("/api/rounds", files=_files(SALES, PAYMENTS))
    assert response.status_code == 201, response.text
    return response.json()


def _document(body: Any, filename: str) -> Any:
    return next(d for d in body["documents"] if d["filename"] == filename)


def _withdraw(client: TestClient, body: Any, filename: str, reason: str = "not ours") -> Any:
    response = client.post(
        f"/api/rounds/{body['summary']['id']}/documents/{_document(body, filename)['id']}/withdraw",
        json={"reason": reason},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- the figures ---------------------------------------------------------------------------------


def test_the_documents_are_listed_with_what_each_was_read_as(round_: Any) -> None:
    """An operator cannot remove the wrong file if the screen does not say which is which."""
    assert {d["filename"] for d in round_["documents"]} == {SALES, PAYMENTS}
    assert all(d["state"] == "counted" for d in round_["documents"])
    assert all(d["byte_count"] > 0 for d in round_["documents"])


def test_withdrawing_a_document_takes_its_figures_out_of_the_round(
    operator: TestClient, round_: Any
) -> None:
    before = round_["totals"]
    after = _withdraw(operator, round_, SALES)["totals"]

    assert int(after["rows"]) < int(before["rows"])
    assert after["value"] != before["value"]
    assert _document(_reload(operator, round_), SALES)["state"] == "withdrawn"


def _reload(client: TestClient, body: Any) -> Any:
    return client.get(f"/api/rounds/{body['summary']['id']}").json()


def test_the_file_is_kept_and_the_removal_is_said_out_loud(
    operator: TestClient, round_: Any
) -> None:
    """A silent removal is indistinguishable from a file that went missing."""
    after = _withdraw(operator, round_, SALES, "another producer's export, uploaded by mistake")

    document = _document(after, SALES)
    assert document["byte_count"] > 0, "the bytes were discarded"
    assert document["withdrawn_by"] == "operator@example.com"
    assert "another producer" in document["withdrawn_reason"]
    assert any(SALES in alert["subject"] for alert in after["alerts"])


def test_the_removal_is_kept_in_the_round_history(operator: TestClient, round_: Any) -> None:
    after = _withdraw(operator, round_, SALES, "wrong producer")
    event = next(e for e in after["events"] if e["action"] == "document_withdrawn")
    assert event["subject"] == SALES
    assert event["reason"] == "wrong producer"
    assert event["by"] == "operator@example.com"


def test_removing_a_document_needs_a_reason(operator: TestClient, round_: Any) -> None:
    response = operator.post(
        f"/api/rounds/{round_['summary']['id']}/documents/"
        f"{_document(round_, SALES)['id']}/withdraw",
        json={"reason": "   "},
    )
    assert response.status_code == 422
    assert "why" in response.json()["detail"].lower()


def test_putting_a_document_back_returns_the_figures_exactly(
    operator: TestClient, round_: Any
) -> None:
    before = round_["totals"]
    withdrawn = _withdraw(operator, round_, SALES)
    assert withdrawn["totals"] != before

    document_id = _document(withdrawn, SALES)["id"]
    restored = operator.post(
        f"/api/rounds/{round_['summary']['id']}/documents/{document_id}/restore", json={}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["totals"] == before


def test_a_document_cannot_be_removed_twice(operator: TestClient, round_: Any) -> None:
    withdrawn = _withdraw(operator, round_, SALES)
    again = operator.post(
        f"/api/rounds/{round_['summary']['id']}/documents/{_document(withdrawn, SALES)['id']}"
        "/withdraw",
        json={"reason": "again"},
    )
    assert again.status_code == 409


# --- the same bytes coming back --------------------------------------------------------------------


def test_withdrawn_bytes_uploaded_again_count_rather_than_being_called_a_duplicate(
    operator: TestClient, round_: Any
) -> None:
    """Otherwise removing a file poisons it: the very copy that was meant to be there comes back
    marked a duplicate of the one that was taken out, and contributes nothing either."""
    _withdraw(operator, round_, SALES)

    second = operator.post("/api/rounds", files=_files(SALES))
    assert second.status_code == 201, second.text
    body = second.json()

    assert _document(body, SALES)["state"] == "counted"
    assert body["alerts"] == []
    assert int(body["totals"]["rows"]) > 0


def test_the_documents_of_a_round_put_aside_do_not_block_a_fresh_upload(
    operator: TestClient, round_: Any
) -> None:
    aside = operator.post(
        f"/api/rounds/{round_['summary']['id']}/abandon",
        json={"reason": "uploaded against the wrong producer"},
    )
    assert aside.status_code == 200, aside.text
    assert aside.json()["summary"]["status"] == "abandoned"

    again = operator.post("/api/rounds", files=_files(SALES, PAYMENTS))
    assert again.status_code == 201
    assert again.json()["alerts"] == []
    assert int(again.json()["totals"]["rows"]) == int(round_["totals"]["rows"])


def test_putting_a_round_aside_needs_a_reason(operator: TestClient, round_: Any) -> None:
    response = operator.post(f"/api/rounds/{round_['summary']['id']}/abandon", json={"reason": ""})
    assert response.status_code == 422


# --- after the round is closed ---------------------------------------------------------------------


def _settle(client: TestClient, body: Any) -> Any:
    """Answer every question in a round and close it."""
    round_id = body["summary"]["id"]
    while True:
        current = client.get(f"/api/rounds/{round_id}").json()
        if not current["queue"]:
            break
        item = current["queue"][0]
        if item["kind"] == "product_code":
            assert (
                client.post(
                    "/api/products/code",
                    json={"product_key": item["key"], "short_code": "Code " + item["key"][:10]},
                ).status_code
                == 200
            )
        elif item["kind"] == "product_link":
            left, right = item["key"].split("||")
            assert (
                client.post(
                    "/api/products/link",
                    json={"left": left, "right": right, "accepted": False, "reason": "not proven"},
                ).status_code
                == 200
            )
        else:
            assert (
                client.post(
                    f"/api/rounds/{round_id}/delivery-notes",
                    params={"delivery_id": item["key"]},
                    json={"dn": item["proposal"], "provenance": "operator", "reason": "as offered"},
                ).status_code
                == 200
            )
    closed = client.post(f"/api/rounds/{round_id}/resolve")
    assert closed.status_code == 200, closed.text
    return closed.json()


def test_a_closed_round_refuses_a_removal_until_it_is_reopened(
    operator: TestClient, round_: Any
) -> None:
    closed = _settle(operator, round_)
    round_id = closed["summary"]["id"]

    refused = operator.post(
        f"/api/rounds/{round_id}/documents/{_document(closed, SALES)['id']}/withdraw",
        json={"reason": "not ours"},
    )
    assert refused.status_code == 409
    assert "resolved" in refused.json()["detail"]

    reopened = operator.post(
        f"/api/rounds/{round_id}/reopen", json={"reason": "the sales file is another producer's"}
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["summary"]["status"] == "staged"

    allowed = operator.post(
        f"/api/rounds/{round_id}/documents/{_document(closed, SALES)['id']}/withdraw",
        json={"reason": "another producer's export"},
    )
    assert allowed.status_code == 200, allowed.text


def test_reopening_needs_a_reason_and_keeps_it(operator: TestClient, round_: Any) -> None:
    closed = _settle(operator, round_)
    round_id = closed["summary"]["id"]

    assert operator.post(f"/api/rounds/{round_id}/reopen", json={"reason": ""}).status_code == 422

    reopened = operator.post(f"/api/rounds/{round_id}/reopen", json={"reason": "wrong file"}).json()
    event = next(e for e in reopened["events"] if e["action"] == "round_reopened")
    assert event["reason"] == "wrong file"
    assert event["by"] == "operator@example.com"


def test_reopening_says_which_later_rounds_are_derived_without_it(
    operator: TestClient, round_: Any
) -> None:
    """`history()` walks resolved rounds only, so a reopened round drops out of the history the
    rounds after it are built from. Correct, and surprising, so it is said rather than left."""
    first = _settle(operator, round_)
    second = operator.post(
        "/api/rounds", files=_files("DailySalesDetail_20260601-20260608.csv")
    ).json()
    _settle(operator, second)

    reopened = operator.post(
        f"/api/rounds/{first['summary']['id']}/reopen", json={"reason": "wrong file"}
    ).json()
    warnings = [a["message"] for a in reopened["alerts"] if "derived without it" in a["message"]]
    assert warnings, "reopening said nothing about the round built on top of it"
    assert f"#{second['summary']['id']}" in warnings[0]


def test_a_round_put_aside_stops_carrying_stock_into_the_next_one(
    operator: TestClient, round_: Any
) -> None:
    """Everything downstream is re-derived from the documents, so correcting an old round
    corrects the rounds after it without anything being rewritten."""
    first = _settle(operator, round_)
    second = operator.post(
        "/api/rounds", files=_files("DailySalesDetail_20260601-20260608.csv")
    ).json()
    carried = [r for r in second["rows"] if (r["stock"] or {}).get("is_carried_forward")]
    assert carried, "the fixture no longer carries stock across the boundary"

    operator.post(f"/api/rounds/{first['summary']['id']}/reopen", json={"reason": "wrong producer"})
    operator.post(f"/api/rounds/{first['summary']['id']}/abandon", json={"reason": "all wrong"})

    again = operator.get(f"/api/rounds/{second['summary']['id']}").json()
    assert not [r for r in again["rows"] if (r["stock"] or {}).get("is_carried_forward")]


# --- the number a removal would otherwise burn -----------------------------------------------------


def test_a_delivery_note_stranded_by_a_removal_is_reported_and_can_be_released(
    operator: TestClient,
) -> None:
    """An approved note is keyed on the delivery, not the round, and every number ever approved is
    avoided when a fresh one is minted. Left alone, a note stranded by a removal holds a number out
    of the 14xxx series for a delivery that no longer exists anywhere."""
    body = operator.post("/api/rounds", files=_files(SALES)).json()
    round_id = body["summary"]["id"]

    item = next(i for i in body["queue"] if i["kind"] == "delivery_note")
    approved = operator.post(
        f"/api/rounds/{round_id}/delivery-notes",
        params={"delivery_id": item["key"]},
        json={"dn": item["proposal"], "provenance": "operator", "reason": "as offered"},
    )
    assert approved.status_code == 200, approved.text
    number = item["proposal"]

    after = _withdraw(operator, body, SALES, "another producer's export")
    stranded = after["orphaned_delivery_notes"]
    assert [n["delivery_id"] for n in stranded] == [item["key"]]
    assert any(number in a["message"] for a in after["alerts"])

    assert (
        operator.post(
            f"/api/rounds/{round_id}/delivery-notes/{item['key']}/release", json={"reason": ""}
        ).status_code
        == 422
    )

    released = operator.post(
        f"/api/rounds/{round_id}/delivery-notes/{item['key']}/release",
        json={"reason": "the delivery came from a file that was removed"},
    )
    assert released.status_code == 200, released.text
    assert released.json()["orphaned_delivery_notes"] == []

    event = next(e for e in released.json()["events"] if e["action"] == "delivery_note_released")
    assert number in event["subject"]

    # And the number is genuinely back: a fresh round proposes it again rather than skipping past.
    fresh = operator.post("/api/rounds", files=_files(SALES)).json()
    proposals = [i["proposal"] for i in fresh["queue"] if i["kind"] == "delivery_note"]
    assert number in proposals


def test_nothing_is_reported_as_stranded_when_no_document_was_removed(round_: Any) -> None:
    """A warning that shows up on every round is a warning nobody reads by the second week."""
    assert round_["orphaned_delivery_notes"] == []


def test_a_note_is_only_released_once_its_delivery_has_gone(
    operator: TestClient, round_: Any
) -> None:
    item = next(i for i in round_["queue"] if i["kind"] == "delivery_note")
    operator.post(
        f"/api/rounds/{round_['summary']['id']}/delivery-notes",
        params={"delivery_id": item["key"]},
        json={"dn": item["proposal"], "provenance": "operator", "reason": "as offered"},
    )
    refused = operator.post(
        f"/api/rounds/{round_['summary']['id']}/delivery-notes/{item['key']}/release",
        json={"reason": "changed my mind"},
    )
    assert refused.status_code == 404


# --- who may do it -------------------------------------------------------------------------------


def test_uploading_a_document_does_not_carry_the_right_to_remove_one(
    client: TestClient, db: Session, round_: Any
) -> None:
    """Removal moves the round's figures the way answering a question does, so it takes the same
    permission -- not the one that merely puts documents in."""
    _make_user(db, "uploader@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "uploader@example.com", "password": PASSWORD})

    round_id = round_["summary"]["id"]
    document_id = _document(round_, SALES)["id"]
    assert (
        client.post(
            f"/api/rounds/{round_id}/documents/{document_id}/withdraw", json={"reason": "no"}
        ).status_code
        == 403
    )
    assert client.post(f"/api/rounds/{round_id}/abandon", json={"reason": "no"}).status_code == 403
    assert client.post(f"/api/rounds/{round_id}/reopen", json={"reason": "no"}).status_code == 403
