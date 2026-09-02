"""Working a round through the queue, over HTTP, with the real documents.

The two rounds are split the way the dates split them: the May exports and account sale 382405
in the first, the June exports and account sale 382900 in the second. That is what makes the
cross-round cases real rather than contrived -- the June Daily Sales Detail genuinely reprints
two of May's dockets, and the statement that proves the cherry link is only in round one.
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

ROUND_ONE = [
    "DailySalesDetail_20260525-20260531.csv",
    "ConsignmentReports_20260525-20260531.txt",
    "PaymentDetails_20260529-20260602.csv",
    "AccountSales_382405.txt",
]
ROUND_TWO = [
    "DailySalesDetail_20260601-20260608.csv",
    "PaymentDetails_20260603-20260608.txt",
    "PaymentDetails_20260603-20260608_FarmersTrust.csv",
    "AccountSales_382900.txt",
    "NettPaymentAdjustments_202604.txt",
]


def _files(names: list[str]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (n, (DATA / n).read_bytes(), "application/octet-stream")) for n in names]


@pytest.fixture
def operator(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "operator@example.com", [Permission.INGEST, Permission.RESOLVE])
    assert (
        client.post(
            "/api/auth/login", json={"email": "operator@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    return client


def _create(client: TestClient, names: list[str]) -> Any:
    response = client.post("/api/rounds", files=_files(names))
    assert response.status_code == 201, response.text
    return response.json()


def _items(body: Any, kind: str) -> list[Any]:
    return [i for i in body["queue"] if i["kind"] == kind]


def _answer_codes(client: TestClient, body: Any) -> None:
    for item in _items(body, "product_code"):
        response = client.post(
            "/api/products/code",
            json={"product_key": item["key"], "short_code": "Code " + item["title"][:12]},
        )
        assert response.status_code == 200, response.text


def _answer_dns(client: TestClient, round_id: int, body: Any) -> Any:
    for item in _items(body, "delivery_note"):
        response = client.post(
            f"/api/rounds/{round_id}/delivery-notes",
            params={"delivery_id": item["key"]},
            json={"dn": item["proposal"], "provenance": "operator", "reason": "as proposed"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
    return body


@pytest.fixture
def round_one(operator: TestClient) -> Any:
    return _create(operator, ROUND_ONE)


@pytest.fixture
def resolved_one(operator: TestClient, round_one: Any) -> Any:
    round_id = round_one["summary"]["id"]
    _answer_codes(operator, round_one)
    body = operator.get(f"/api/rounds/{round_id}").json()
    body = _answer_dns(operator, round_id, body)
    response = operator.post(f"/api/rounds/{round_id}/resolve")
    assert response.status_code == 200, response.text
    return response.json()


# --- the queue exists and blocks ---------------------------------------------------------------


def test_a_new_round_opens_a_queue_of_the_things_no_document_says(round_one: Any) -> None:
    assert _items(round_one, "product_code")
    assert _items(round_one, "delivery_note")
    assert round_one["is_clear"] is False


def test_a_round_cannot_be_closed_while_anything_is_unanswered(
    operator: TestClient, round_one: Any
) -> None:
    response = operator.post(f"/api/rounds/{round_one['summary']['id']}/resolve")
    assert response.status_code == 409
    assert "unanswered" in response.json()["detail"]


def test_the_blocking_reason_says_what_is_outstanding(round_one: Any) -> None:
    reason = round_one["blocking_reason"]
    assert "delivery note" in reason and "product code" in reason


def test_a_row_says_what_is_standing_between_it_and_the_workbook(round_one: Any) -> None:
    blocked = [r for r in round_one["rows"] if not r["is_writable"]]
    assert blocked
    assert "no approved delivery note" in blocked[0]["blocked_by"]


# --- delivery notes ------------------------------------------------------------------------------


def test_the_reference_half_is_proposed_where_it_passes_the_three_tests(round_one: Any) -> None:
    item = next(i for i in _items(round_one, "delivery_note") if i["key"] == "1180699Z")
    assert item["proposal"] == "14720"
    assert item["provenance"] == "reference"
    assert all(t["passed"] for t in item["tests"])


def test_only_the_two_references_that_earn_it_are_flagged(round_one: Any) -> None:
    """A flag on most rows would mean nothing (D10)."""
    flagged = {i["key"] for i in _items(round_one, "delivery_note") if i["counter_evidence"]}
    assert flagged == {"1183001Z", "1183050Z"}


def test_a_delivery_with_no_supplier_reference_is_minted_and_not_flagged(round_one: Any) -> None:
    """Absence is not counter-evidence. 1181705Z has a blank Supplier Ref."""
    item = next(i for i in _items(round_one, "delivery_note") if i["key"] == "1181705Z")
    assert item["provenance"] == "minted"
    assert item["counter_evidence"] is None


def test_the_agents_own_delivery_note_field_is_never_proposed(round_one: Any) -> None:
    """`DELIVERY NOTE NO : 203003` is the agent's number, not Zaco's."""
    proposals = {i["proposal"] for i in _items(round_one, "delivery_note")}
    assert not any(p and p.startswith("203") for p in proposals)


def test_nothing_is_written_until_a_person_approves_it(round_one: Any) -> None:
    assert round_one["delivery_notes"] == []
    assert all(r["dn"] is None for r in round_one["rows"])


def test_approving_a_proposal_keeps_the_proposals_own_provenance(
    operator: TestClient, round_one: Any
) -> None:
    """So the record can say the number came from a reference, not from somebody typing it."""
    round_id = round_one["summary"]["id"]
    response = operator.post(
        f"/api/rounds/{round_id}/delivery-notes",
        params={"delivery_id": "1180699Z"},
        json={"dn": "14720", "provenance": "operator", "reason": ""},
    )
    assert response.status_code == 200
    note = next(n for n in response.json()["delivery_notes"] if n["delivery_id"] == "1180699Z")
    assert note["provenance"] == "reference"
    assert note["approved_by"] == "operator@example.com"


def test_a_blank_delivery_note_is_refused_unless_it_is_a_recorded_answer(
    operator: TestClient, round_one: Any
) -> None:
    round_id = round_one["summary"]["id"]
    response = operator.post(
        f"/api/rounds/{round_id}/delivery-notes",
        params={"delivery_id": "1182465Z"},
        json={"dn": None, "provenance": "operator", "reason": "not sure"},
    )
    assert response.status_code == 422
    assert "recorded one" in response.json()["detail"]


def test_no_delivery_note_for_another_producers_load_is_a_recorded_answer(
    operator: TestClient, round_one: Any
) -> None:
    """D11: `14013*14710` is producer 14013's produce, and the answer is written down."""
    round_id = round_one["summary"]["id"]
    response = operator.post(
        f"/api/rounds/{round_id}/delivery-notes",
        params={"delivery_id": "1182465Z"},
        json={
            "dn": None,
            "provenance": "none_foreign_producer",
            "reason": "carried for producer 14013; Zaco issues no note",
        },
    )
    assert response.status_code == 200
    note = next(n for n in response.json()["delivery_notes"] if n["delivery_id"] == "1182465Z")
    assert note["dn"] is None
    assert "14013" in note["operator_reason"]


def test_recording_no_delivery_note_still_needs_a_reason(
    operator: TestClient, round_one: Any
) -> None:
    response = operator.post(
        f"/api/rounds/{round_one['summary']['id']}/delivery-notes",
        params={"delivery_id": "1182465Z"},
        json={"dn": None, "provenance": "none_foreign_producer", "reason": "  "},
    )
    assert response.status_code == 422
    assert "needs a reason" in response.json()["detail"]


def test_two_minted_numbers_in_one_round_do_not_collide(round_one: Any) -> None:
    minted = [
        i["proposal"] for i in _items(round_one, "delivery_note") if i["provenance"] == "minted"
    ]
    assert len(minted) == len(set(minted))


def test_the_pears_peaches_and_strawberries_are_offered_as_one_load(
    operator: TestClient, resolved_one: Any
) -> None:
    """1183200Z/1183201Z/1183202Z share an agent and a day, and very likely one truck."""
    body = _create(operator, ROUND_TWO)
    item = next(i for i in _items(body, "delivery_note") if i["key"] == "1183200Z")
    assert set(item["companions"]) >= {"1183201Z", "1183202Z"}


def test_one_delivery_note_across_several_deliveries_requires_a_reason(
    operator: TestClient, resolved_one: Any
) -> None:
    body = _create(operator, ROUND_TWO)
    round_id = body["summary"]["id"]
    response = operator.post(
        f"/api/rounds/{round_id}/delivery-notes/bulk",
        json={
            "delivery_ids": ["1183200Z", "1183201Z", "1183202Z"],
            "dn": "14885",
            "reason": "",
        },
    )
    assert response.status_code == 422
    assert "Say why" in response.json()["detail"]

    response = operator.post(
        f"/api/rounds/{round_id}/delivery-notes/bulk",
        json={
            "delivery_ids": ["1183200Z", "1183201Z", "1183202Z"],
            "dn": "14885",
            "reason": "one truck, three consignments, same delivery date and agent",
        },
    )
    assert response.status_code == 200
    notes = {n["delivery_id"]: n for n in response.json()["delivery_notes"]}
    assert {notes[d]["dn"] for d in ("1183200Z", "1183201Z", "1183202Z")} == {"14885"}
    assert "one truck" in notes["1183200Z"]["operator_reason"]


# --- product codes and links ------------------------------------------------------------------


def test_a_captured_code_reaches_the_row_it_was_holding_up(
    operator: TestClient, round_one: Any
) -> None:
    round_id = round_one["summary"]["id"]
    item = next(i for i in _items(round_one, "product_code") if "NECTARINES" in i["title"])
    assert (
        operator.post(
            "/api/products/code", json={"product_key": item["key"], "short_code": "IMP Nect"}
        ).status_code
        == 200
    )

    body = operator.get(f"/api/rounds/{round_id}").json()
    assert not [i for i in _items(body, "product_code") if "NECTARINES" in i["title"]]
    assert any(r["short_code"] == "IMP Nect" for r in body["rows"])


def test_a_blank_short_code_is_refused(operator: TestClient, round_one: Any) -> None:
    item = _items(round_one, "product_code")[0]
    response = operator.post(
        "/api/products/code", json={"product_key": item["key"], "short_code": "   "}
    )
    assert response.status_code == 422


def test_a_code_captured_in_one_round_is_not_asked_for_again_in_the_next(
    operator: TestClient, resolved_one: Any
) -> None:
    """The whole point of remembering: eleven questions once, not eleven questions a week."""
    body = _create(operator, ROUND_TWO)
    titles = {i["title"] for i in _items(body, "product_code")}
    assert not any("NECTARINES OTHER" in t for t in titles)


def test_the_cherry_link_survives_the_round_that_proved_it(
    operator: TestClient, resolved_one: Any
) -> None:
    """Account sale 382405 proves it, and 382405 is only in round one.

    Re-proving the link each round would mean the cherries losing their short code the moment
    the statement that proved it is no longer in front of us.
    """
    body = _create(operator, ROUND_TWO)
    cherries = next(p for p in body["products"] if "CHERRIES OTHER" in p["display_name"])
    assert cherries["short_code"] == "Imp Cherries 5kg"
    assert any("382405" in reason for reason in cherries["merge_reasons"])


def test_a_resemblance_is_offered_with_its_reasoning_and_never_applied(
    operator: TestClient, resolved_one: Any
) -> None:
    body = _create(operator, ROUND_TWO)
    links = _items(body, "product_link")
    assert links
    assert any("not evidence" in i["reasoning"] for i in links)


def test_accepting_a_link_carries_the_short_code_across(
    operator: TestClient, round_one: Any
) -> None:
    """The plums: one name has a code, the other does not, and they are the same fruit."""
    plums = next(i for i in _items(round_one, "product_code") if "PLUM ANGELINO" in i["title"])
    operator.post(
        "/api/products/code", json={"product_key": plums["key"], "short_code": "Imp Plum"}
    )

    body = _create(operator, ROUND_TWO)
    link = next(i for i in _items(body, "product_link") if "PLUM" in i["title"].upper())
    left, right = link["key"].split("||")
    assert (
        operator.post(
            "/api/products/link",
            json={"left": left, "right": right, "accepted": True, "reason": "same fruit"},
        ).status_code
        == 200
    )

    after = operator.get(f"/api/rounds/{body['summary']['id']}").json()
    statement = next(p for p in after["products"] if "PLAN 2A MA53" in " ".join(p["names"]))
    assert statement["short_code"] == "Imp Plum"


def test_a_rejected_link_is_not_offered_again(operator: TestClient, resolved_one: Any) -> None:
    body = _create(operator, ROUND_TWO)
    link = _items(body, "product_link")[0]
    left, right = link["key"].split("||")
    assert (
        operator.post(
            "/api/products/link",
            json={"left": left, "right": right, "accepted": False, "reason": "different lines"},
        ).status_code
        == 200
    )

    after = operator.get(f"/api/rounds/{body['summary']['id']}").json()
    assert link["key"] not in {i["key"] for i in _items(after, "product_link")}


# --- duplicates (D12) -----------------------------------------------------------------------------


def test_an_identical_re_export_is_counted_once_and_said_out_loud(round_one: Any) -> None:
    """A skip nobody can see is indistinguishable from a record that went missing."""
    body = round_one
    assert isinstance(body["alerts"], list)


def test_the_narrowed_re_export_is_skipped_visibly_not_silently(
    operator: TestClient, resolved_one: Any
) -> None:
    """`PaymentDetails_..._FarmersTrust.csv` repeats three account sales with identical figures."""
    body = _create(operator, ROUND_TWO)
    subjects = {a["subject"] for a in body["alerts"]}
    assert {"PRE*BT*382860", "PRE*BT*382880", "PRE*BT*382885"} <= subjects


def test_the_june_export_does_not_recount_mays_dockets(
    operator: TestClient, resolved_one: Any
) -> None:
    """`DailySalesDetail_20260601-20260608.csv` reprints two of May's nectarine dockets verbatim.

    Counted again, the book gains 65 cartons and R3,500 that never happened -- and looks
    entirely normal while doing it.
    """
    body = _create(operator, ROUND_TWO)
    subjects = {a["subject"] for a in body["alerts"]}
    assert {"PRE*B6E01C39001*02Z", "PRE*B6E02C39002*02Z"} <= subjects
    assert not any(r["consignment_id"] == "118170502Z" for r in body["rows"])


def test_a_round_uploaded_twice_produces_no_rows_and_one_alert_per_document(
    operator: TestClient, resolved_one: Any
) -> None:
    _create(operator, ROUND_TWO)
    again = _create(operator, ROUND_TWO)
    assert again["totals"]["rows"] == "0"
    assert len(again["alerts"]) == len(ROUND_TWO)
    assert again["summary"]["duplicate_count"] == len(ROUND_TWO)


# --- stock across the boundary -------------------------------------------------------------------


def test_a_consignment_still_on_the_floor_carries_its_balance_into_the_next_round(
    operator: TestClient, resolved_one: Any
) -> None:
    body = _create(operator, ROUND_TWO)
    carried = {
        r["consignment_id"]: r["stock"]
        for r in body["rows"]
        if r["stock"] and r["stock"]["is_carried_forward"]
    }
    assert "118069901Z" in carried
    assert carried["118069901Z"]["opening"] == "12"


def test_the_quantity_sent_opens_only_the_first_row_of_a_consignment(resolved_one: Any) -> None:
    """71 nectarines become two rows opening at 71 and 31, never 71 twice."""
    rows = [r for r in resolved_one["rows"] if r["consignment_id"] == "118170502Z"]
    assert len(rows) == 2
    assert [r["stock"]["opening"] for r in rows] == ["71", "31"]
    assert [r["stock"]["closing"] for r in rows] == ["31", "6"]


def test_every_row_under_one_delivery_note_is_grouped_on_the_earliest_date(
    resolved_one: Any,
) -> None:
    rows = [r for r in resolved_one["rows"] if r["dn"]]
    by_dn: dict[str, set[str]] = {}
    for row in rows:
        by_dn.setdefault(row["dn"], set()).add(str(row["grouping_date"]))
    assert all(len(dates) == 1 for dates in by_dn.values())
    nectarines = [r for r in rows if r["consignment_id"] == "118170502Z"]
    assert nectarines[0]["grouping_date"] == min(r["earliest_date"] for r in nectarines)


# --- closing the queue ---------------------------------------------------------------------------


def test_a_round_closes_once_everything_is_answered(resolved_one: Any) -> None:
    assert resolved_one["summary"]["status"] == "resolved"
    assert resolved_one["is_clear"] is True
    assert all(r["is_writable"] for r in resolved_one["rows"])


def test_a_closed_round_takes_no_more_answers(operator: TestClient, resolved_one: Any) -> None:
    response = operator.post(
        f"/api/rounds/{resolved_one['summary']['id']}/delivery-notes",
        params={"delivery_id": "1180699Z"},
        json={"dn": "14999", "provenance": "operator", "reason": "changed my mind"},
    )
    assert response.status_code == 409


def test_the_workbook_join_reports_honestly_that_it_recovered_nothing(round_one: Any) -> None:
    """The book holds 381900 and 381950; the data holds 382399-382999."""
    detail = round_one["book"]["detail"]
    assert "2 account sale" in detail
    assert "pays once" in detail


# --- permissions ------------------------------------------------------------------------------------


def test_answering_the_queue_needs_the_resolve_permission(client: TestClient, db: Session) -> None:
    _make_user(db, "reader@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "reader@example.com", "password": PASSWORD})
    body = _create(client, ROUND_ONE)
    response = client.post(
        f"/api/rounds/{body['summary']['id']}/delivery-notes",
        params={"delivery_id": "1180699Z"},
        json={"dn": "14720", "provenance": "operator", "reason": ""},
    )
    assert response.status_code == 403


def test_a_signed_out_caller_cannot_save_a_round(client: TestClient) -> None:
    assert client.post("/api/rounds", files=_files(ROUND_ONE)).status_code == 401


def test_a_minted_number_cannot_reissue_one_an_earlier_round_approved(
    operator: TestClient, resolved_one: Any
) -> None:
    """Two loads under one delivery note would look entirely normal in the book."""
    already = {n["dn"] for n in resolved_one["delivery_notes"] if n["dn"]}
    assert already

    body = _create(operator, ROUND_TWO)
    proposed = {i["proposal"] for i in _items(body, "delivery_note") if i["proposal"]}
    assert not (proposed & already)


def test_the_refusal_names_the_file_that_could_not_be_read(operator: TestClient) -> None:
    """With five files uploaded at once, "one of these is unreadable" is not an answer."""
    files = [*_files(ROUND_ONE), ("files", ("notes.txt", b"prose about fruit", "text/plain"))]
    response = operator.post("/api/rounds", files=files)
    assert response.status_code == 422
    assert response.json()["detail"]["detail"].startswith("notes.txt:")
