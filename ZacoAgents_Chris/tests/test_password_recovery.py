"""Getting back into an account, and the three ways in that must stay different.

What could be wrong here without looking wrong is the whole file. A reset flow that works when you
try it is not evidence: the failures are a link that still works after it was spent, a request
endpoint that quietly says which addresses have accounts, a deactivated person walking back in
through a link issued before they were turned off, and a recovery command that answers to anything
other than possession of the server.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_accounts_api import PASSWORD, _make_user
from zaco.auth.permissions import Permission
from zaco.auth.service import RESET_PATH, get_user_by_email
from zaco.main import spa_dir

pytestmark = pytest.mark.db

NEW = "a-brand-new-password"


def _admin(client: TestClient, db: Session) -> TestClient:
    _make_user(db, "boss@example.com", [Permission.ADMIN])
    client.post("/api/auth/login", json={"email": "boss@example.com", "password": PASSWORD})
    return client


def _issue_for(client: TestClient, user_id: int) -> str:
    response = client.post(
        f"/api/admin/users/{user_id}/password-reset", json={"reason": "phoned in"}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["reset_url"])


def _token_of(url: str) -> str:
    return url.rsplit("/", 1)[-1]


# --- changing your own -------------------------------------------------------------------------


def test_changing_your_own_password_needs_the_current_one(client: TestClient, db: Session) -> None:
    """The session proves who you are; it does not prove you are not somebody at their desk."""
    user = _make_user(db, "clerk@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "clerk@example.com", "password": PASSWORD})

    wrong = client.post(
        "/api/auth/password",
        json={"current_password": "not-the-password", "new_password": NEW},
    )

    assert wrong.status_code == 400
    assert (
        client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD}).status_code
        == 200
    )


def test_a_changed_password_is_the_one_that_works(client: TestClient, db: Session) -> None:
    _make_user(db, "clerk@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "clerk@example.com", "password": PASSWORD})

    changed = client.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW}
    )

    assert changed.status_code == 200
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login", json={"email": "clerk@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "clerk@example.com", "password": NEW}
        ).status_code
        == 200
    )


def test_a_short_password_is_refused_everywhere_it_can_be_set(
    client: TestClient, db: Session
) -> None:
    """A reset that accepted a weaker password than an invitation did would be the way in."""
    user = _make_user(db, "clerk@example.com", [Permission.INGEST])
    client.post("/api/auth/login", json={"email": "clerk@example.com", "password": PASSWORD})
    assert (
        client.post(
            "/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
        ).status_code
        == 400
    )

    admin = _admin(client, db)
    token = _token_of(_issue_for(admin, user.id))
    admin.post("/api/auth/logout")

    assert (
        client.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code
        == 400
    )


# --- saying you cannot get in ------------------------------------------------------------------


def test_forgetting_says_the_same_thing_whether_or_not_the_account_exists(
    client: TestClient, db: Session
) -> None:
    """Otherwise the login page is a way to find out who works here, one address at a time."""
    _make_user(db, "real@example.com", [Permission.INGEST])

    known = client.post("/api/auth/forgot", json={"email": "real@example.com"})
    unknown = client.post("/api/auth/forgot", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_a_request_reaches_an_administrator_and_carries_no_token(
    client: TestClient, db: Session
) -> None:
    _make_user(db, "real@example.com", [Permission.INGEST])
    client.post("/api/auth/forgot", json={"email": "real@example.com"})

    admin = _admin(client, db)
    waiting = admin.get("/api/admin/password-requests").json()

    assert [row["email"] for row in waiting] == ["real@example.com"]
    assert "token" not in waiting[0]
    assert "reset_url" not in waiting[0]


def test_asking_twice_is_one_person_waiting(client: TestClient, db: Session) -> None:
    """A list of the same request eight times is a list nobody reads."""
    _make_user(db, "real@example.com", [Permission.INGEST])
    for _ in range(3):
        client.post("/api/auth/forgot", json={"email": "real@example.com"})

    admin = _admin(client, db)

    assert len(admin.get("/api/admin/password-requests").json()) == 1


def test_issuing_a_link_answers_the_request(client: TestClient, db: Session) -> None:
    """A list of people waiting has to be a list of people still waiting."""
    user = _make_user(db, "real@example.com", [Permission.INGEST])
    client.post("/api/auth/forgot", json={"email": "real@example.com"})
    admin = _admin(client, db)
    _issue_for(admin, user.id)

    assert admin.get("/api/admin/password-requests").json() == []


# --- spending a link ---------------------------------------------------------------------------


def test_a_link_sets_the_password_and_signs_the_person_in(client: TestClient, db: Session) -> None:
    user = _make_user(db, "lost@example.com", [Permission.INGEST])
    admin = _admin(client, db)
    url = _issue_for(admin, user.id)
    admin.post("/api/auth/logout")

    used = client.post("/api/auth/reset", json={"token": _token_of(url), "password": NEW})

    assert used.status_code == 200
    assert used.json()["email"] == "lost@example.com"
    assert client.get("/api/auth/me").json()["email"] == "lost@example.com"


def test_a_link_works_once(client: TestClient, db: Session) -> None:
    """A link is carried by hand, so it lives in a chat window afterwards."""
    user = _make_user(db, "lost@example.com", [Permission.INGEST])
    admin = _admin(client, db)
    token = _token_of(_issue_for(admin, user.id))
    admin.post("/api/auth/logout")
    assert client.post("/api/auth/reset", json={"token": token, "password": NEW}).status_code == 200

    again = client.post("/api/auth/reset", json={"token": token, "password": "another-password-x"})

    assert again.status_code == 400
    assert (
        client.post("/api/auth/login", json={"email": user.email, "password": NEW}).status_code
        == 200
    )


def test_a_made_up_token_is_refused(client: TestClient, db: Session) -> None:
    assert (
        client.post("/api/auth/reset", json={"token": "not-a-token", "password": NEW}).status_code
        == 400
    )


def test_a_turned_off_account_cannot_be_let_back_in_by_a_link(
    client: TestClient, db: Session
) -> None:
    """Turning somebody off is meant to stop them working. A link that walked past it would
    undo that silently, and the account would be back without anybody deciding so."""
    user = _make_user(db, "gone@example.com", [Permission.INGEST])
    admin = _admin(client, db)
    token = _token_of(_issue_for(admin, user.id))
    assert (
        admin.put(f"/api/admin/users/{user.id}/active", json={"is_active": False}).status_code
        == 200
    )
    admin.post("/api/auth/logout")

    refused = client.post("/api/auth/reset", json={"token": token, "password": NEW})

    assert refused.status_code == 400
    assert "not active" in refused.json()["detail"]


def test_only_an_administrator_can_issue_one(client: TestClient, db: Session) -> None:
    victim = _make_user(db, "victim@example.com", [Permission.INGEST])
    _make_user(db, "clerk@example.com", [Permission.INGEST, Permission.RESOLVE])
    client.post("/api/auth/login", json={"email": "clerk@example.com", "password": PASSWORD})

    assert client.post(f"/api/admin/users/{victim.id}/password-reset").status_code == 403
    assert client.get("/api/admin/password-requests").status_code == 403


# --- the way in when every administrator is locked out -----------------------------------------


def test_the_recovery_command_opens_an_account_and_names_itself(
    client: TestClient, db: Session
) -> None:
    """The case every other route dead-ends in: nobody left with the standing to help.

    What it asks for instead is possession of the server, which is why it is a command and not an
    endpoint. Run here the way it is run there -- through `main`, on the same database.
    """
    from zaco import recover

    user = _make_user(db, "onlyadmin@example.com", [Permission.ADMIN])
    db.commit()

    code = recover.main([user.email, "--base-url", "http://localhost:8000"])
    assert code == 0

    admin = _admin(client, db)
    trail = admin.get("/api/admin/events").json()
    issued = [row for row in trail if row["action"] == "password reset issued"]
    assert issued
    assert issued[0]["by"] == recover.VIA
    assert issued[0]["email"] == "onlyadmin@example.com"


def test_the_recovery_command_refuses_an_address_with_no_account(db: Session) -> None:
    from zaco import recover

    assert recover.main(["nobody@example.com"]) == 1


def test_the_recovery_command_is_not_reachable_over_http(client: TestClient, db: Session) -> None:
    """Its whole safety argument is that it needs the server rather than an account. An endpoint
    that did the same thing would hand that away."""
    admin = _admin(client, db)

    for path in ("/api/recover", "/api/admin/recover", "/api/auth/recover"):
        assert admin.post(path, json={"email": "boss@example.com"}).status_code == 404


def test_a_recovery_link_points_at_a_page_that_exists(client: TestClient, db: Session) -> None:
    """A printed link that 404s is a recovery path that does not recover anything.

    Pinned by fetching it, not by comparing it to `RESET_PATH` -- that would pass just as happily
    if the app stopped serving the page, which is the failure this is here to catch. Skipped
    rather than passed where the frontend has not been built, because a check that reads as a
    pass without having run is the same failure somewhere else.
    """
    if not (spa_dir() / "index.html").exists():
        pytest.skip("No built frontend; run `npm run build` in frontend/.")

    user = _make_user(db, "lost@example.com", [Permission.INGEST])
    admin = _admin(client, db)
    url = _issue_for(admin, user.id)

    assert RESET_PATH in url
    page = client.get(f"{RESET_PATH}/{_token_of(url)}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")


# --- the rest of an account --------------------------------------------------------------------


def test_a_name_can_be_corrected_and_the_change_is_written_down(
    client: TestClient, db: Session
) -> None:
    user = _make_user(db, "typo@example.com", [Permission.INGEST])
    admin = _admin(client, db)

    changed = admin.put(f"/api/admin/users/{user.id}/profile", json={"display_name": "Ann Smith"})

    assert changed.status_code == 200
    assert changed.json()["display_name"] == "Ann Smith"
    trail = admin.get("/api/admin/events").json()
    assert any(row["action"] == "name changed" for row in trail)


def test_changing_an_email_without_a_reason_is_refused(client: TestClient, db: Session) -> None:
    """It is the name on every decision the account has already made."""
    user = _make_user(db, "old@example.com", [Permission.INGEST])
    admin = _admin(client, db)

    refused = admin.put(
        f"/api/admin/users/{user.id}/email", json={"email": "new@example.com", "reason": "   "}
    )

    assert refused.status_code == 400
    assert get_user_by_email(db, "old@example.com") is not None


def test_a_changed_email_is_the_one_that_signs_in_and_the_trail_says_why(
    client: TestClient, db: Session
) -> None:
    user = _make_user(db, "old@example.com", [Permission.INGEST])
    admin = _admin(client, db)

    admin.put(
        f"/api/admin/users/{user.id}/email",
        json={"email": "new@example.com", "reason": "she married"},
    )
    trail = admin.get("/api/admin/events").json()
    admin.post("/api/auth/logout")

    assert (
        client.post(
            "/api/auth/login", json={"email": "new@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    change = next(row for row in trail if row["action"] == "email changed")
    assert change["detail"] == "old@example.com -> new@example.com"
    assert change["reason"] == "she married"


def test_an_email_already_in_use_is_refused(client: TestClient, db: Session) -> None:
    _make_user(db, "taken@example.com", [Permission.INGEST])
    user = _make_user(db, "mine@example.com", [Permission.INGEST])
    admin = _admin(client, db)

    refused = admin.put(
        f"/api/admin/users/{user.id}/email",
        json={"email": "taken@example.com", "reason": "a mistake"},
    )

    assert refused.status_code == 409


def test_an_invitation_that_ran_out_can_be_given_a_fresh_one(
    client: TestClient, db: Session
) -> None:
    """The same row, not a second one. Two open invitations to one address means two accounts
    could be made from them, and the second is refused halfway through typing a password."""
    admin = _admin(client, db)
    first = admin.post(
        "/api/admin/invitations", json={"email": "new@example.com", "permissions": ["ingest"]}
    ).json()

    again = admin.post(f"/api/admin/invitations/{first['id']}/reissue")

    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert again.json()["accept_url"] != first["accept_url"]
    assert len(admin.get("/api/admin/invitations").json()) == 1


def test_an_accepted_invitation_is_not_reissued(client: TestClient, db: Session) -> None:
    """The account exists; the thing being asked for is a password reset."""
    admin = _admin(client, db)
    invitation = admin.post(
        "/api/admin/invitations", json={"email": "new@example.com", "permissions": []}
    ).json()
    token = invitation["accept_url"].rsplit("/", 1)[-1]
    admin.post("/api/auth/accept", json={"token": token, "password": "a-good-password-x"})
    admin.post("/api/auth/login", json={"email": "boss@example.com", "password": PASSWORD})

    refused = admin.post(f"/api/admin/invitations/{invitation['id']}/reissue")

    assert refused.status_code == 409
