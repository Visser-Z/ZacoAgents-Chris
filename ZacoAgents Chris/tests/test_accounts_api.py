"""Accounts, invitations and the permission boundaries (D14).

The audit trail these tests protect is what makes the rest of the system worth anything: every
queue answer, DN approval and append is stamped with a person, so a shared or unbounded account
would quietly destroy it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import ADMIN_EMAIL
from zaco.auth.permissions import Permission
from zaco.auth.service import AuthError, create_invitation, hash_password, seed_admin
from zaco.config import Settings
from zaco.db.base import get_session_factory
from zaco.db.models import Invitation, User

pytestmark = pytest.mark.db

PASSWORD = "a-password-of-length"


def _make_user(db: Session, email: str, permissions: list[Permission]) -> User:
    user = User(
        email=email,
        display_name=email,
        password_hash=hash_password(PASSWORD),
        permissions=[p.value for p in permissions],
    )
    db.add(user)
    db.commit()
    return user


def _login(client: TestClient, email: str, password: str = PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def _token_of(response_json: dict[str, object]) -> str:
    return str(response_json["accept_url"]).rsplit("/", 1)[-1]


# --- Seeding and signing in ------------------------------------------------------------------


def test_the_first_boot_seeds_exactly_one_admin(client: TestClient) -> None:
    with get_session_factory()() as session:
        users = session.execute(select(User)).scalars().all()
    assert [u.email for u in users] == [ADMIN_EMAIL]
    assert users[0].granted == set(Permission)


def test_seeding_never_touches_an_existing_account(client: TestClient) -> None:
    with get_session_factory()() as session:
        before = session.execute(select(User.password_hash)).scalar_one()
        assert seed_admin(session) is None
        session.commit()
        after = session.execute(select(User.password_hash)).scalar_one()
    assert before == after


def test_a_wrong_password_is_refused(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert response.status_code == 401


def test_an_unknown_email_answers_exactly_as_a_wrong_password_does(client: TestClient) -> None:
    # Anything else lets an outsider enumerate who has an account.
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    known = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert unknown.status_code == known.status_code == 401
    assert unknown.json()["detail"] == known.json()["detail"]


def test_a_deactivated_account_cannot_sign_in(client: TestClient, db: Session) -> None:
    user = _make_user(db, "gone@example.com", [Permission.VIEW_REPORTS])
    user.is_active = False
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": "gone@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


def test_signing_out_clears_the_session(admin_client: TestClient) -> None:
    assert admin_client.get("/api/auth/me").status_code == 200
    admin_client.post("/api/auth/logout")
    assert admin_client.get("/api/auth/me").status_code == 401


# --- There is no self-registration -----------------------------------------------------------


def test_an_uninvited_email_cannot_create_an_account(client: TestClient) -> None:
    response = client.post(
        "/api/auth/accept",
        json={"token": "invented", "password": PASSWORD, "display_name": "X"},
    )
    assert response.status_code == 400

    signed_in = client.post(
        "/api/auth/login", json={"email": "invented@example.com", "password": PASSWORD}
    )
    assert signed_in.status_code == 401


def test_an_invitation_is_single_use(admin_client: TestClient) -> None:
    created = admin_client.post(
        "/api/admin/invitations",
        json={"email": "new@example.com", "permissions": ["view_reports"]},
    )
    assert created.status_code == 201, created.text
    token = _token_of(created.json())

    first = admin_client.post("/api/auth/accept", json={"token": token, "password": PASSWORD})
    assert first.status_code == 200
    assert first.json()["permissions"] == ["view_reports"]

    second = admin_client.post(
        "/api/auth/accept", json={"token": token, "password": "another-long-password"}
    )
    assert second.status_code == 400


def test_an_invitation_grants_only_what_it_was_issued_with(admin_client: TestClient) -> None:
    created = admin_client.post(
        "/api/admin/invitations",
        json={"email": "reader@example.com", "permissions": ["view_reports"]},
    )
    accepted = admin_client.post(
        "/api/auth/accept",
        json={"token": _token_of(created.json()), "password": PASSWORD},
    )
    assert accepted.json()["permissions"] == ["view_reports"]


def test_a_short_password_is_refused(admin_client: TestClient) -> None:
    created = admin_client.post(
        "/api/admin/invitations", json={"email": "new@example.com", "permissions": []}
    )
    response = admin_client.post(
        "/api/auth/accept", json={"token": _token_of(created.json()), "password": "short"}
    )
    assert response.status_code == 400


def test_an_expired_invitation_is_refused(admin_client: TestClient, db: Session) -> None:
    created = admin_client.post(
        "/api/admin/invitations", json={"email": "late@example.com", "permissions": []}
    )
    token = _token_of(created.json())
    invitation = db.execute(select(Invitation).where(Invitation.token == token)).scalar_one()
    invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    response = admin_client.post("/api/auth/accept", json={"token": token, "password": PASSWORD})
    assert response.status_code == 400


def test_an_invitation_to_an_existing_account_is_refused(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/admin/invitations", json={"email": ADMIN_EMAIL, "permissions": []}
    )
    assert response.status_code == 400


def test_a_revoked_invitation_can_no_longer_be_accepted(admin_client: TestClient) -> None:
    created = admin_client.post(
        "/api/admin/invitations", json={"email": "revoked@example.com", "permissions": []}
    )
    body = created.json()
    assert admin_client.delete(f"/api/admin/invitations/{body['id']}").status_code == 200

    response = admin_client.post(
        "/api/auth/accept", json={"token": _token_of(body), "password": PASSWORD}
    )
    assert response.status_code == 400


# --- Permission boundaries -------------------------------------------------------------------


def test_a_viewer_cannot_reach_the_admin_api(client: TestClient, db: Session) -> None:
    _make_user(db, "viewer@example.com", [Permission.VIEW_REPORTS])
    _login(client, "viewer@example.com")

    assert client.get("/api/admin/users").status_code == 403
    invited = client.post(
        "/api/admin/invitations", json={"email": "x@example.com", "permissions": ["admin"]}
    )
    assert invited.status_code == 403


def test_a_signed_out_caller_reaches_nothing(client: TestClient) -> None:
    assert client.get("/api/admin/users").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_admin_does_not_imply_every_other_permission(client: TestClient, db: Session) -> None:
    # Deliberate: "who appended this" stays a real answer only while administering accounts
    # and doing the operator's job are separate grants.
    user = _make_user(db, "onlyadmin@example.com", [Permission.ADMIN])
    assert user.can(Permission.ADMIN) is True
    assert user.can(Permission.APPEND) is False
    assert user.can(Permission.RESOLVE) is False


def test_an_admin_cannot_remove_their_own_admin_permission(admin_client: TestClient) -> None:
    me = admin_client.get("/api/auth/me").json()
    response = admin_client.put(
        f"/api/admin/users/{me['id']}/permissions", json={"permissions": ["view_reports"]}
    )
    assert response.status_code == 400
    assert "admin" in admin_client.get("/api/auth/me").json()["permissions"]


def test_an_admin_cannot_deactivate_themselves(admin_client: TestClient) -> None:
    me = admin_client.get("/api/auth/me").json()
    response = admin_client.put(f"/api/admin/users/{me['id']}/active", json={"is_active": False})
    assert response.status_code == 400


def test_an_admin_can_change_someone_elses_permissions(
    admin_client: TestClient, db: Session
) -> None:
    user = _make_user(db, "operator@example.com", [Permission.INGEST])
    response = admin_client.put(
        f"/api/admin/users/{user.id}/permissions",
        json={"permissions": ["ingest", "resolve", "append"]},
    )
    assert response.status_code == 200
    assert response.json()["permissions"] == ["append", "ingest", "resolve"]


def test_an_unknown_permission_in_a_request_is_refused(admin_client: TestClient) -> None:
    me = admin_client.get("/api/auth/me").json()
    response = admin_client.put(
        f"/api/admin/users/{me['id']}/permissions",
        json={"permissions": ["admin", "invented_permission"]},
    )
    assert response.status_code == 422


# --- The domain rule gates invitations; it is never an identity -------------------------------


def test_the_domain_rule_refuses_an_invitation_outside_it(db: Session) -> None:
    limited = Settings(allowed_email_domains=["zaco.co.za"])
    admin = _make_user(db, "boss@zaco.co.za", [Permission.ADMIN])

    with pytest.raises(AuthError) as refused:
        create_invitation(db, "someone@gmail.com", set(), admin, settings=limited)
    assert "zaco.co.za" in str(refused.value)

    invitation = create_invitation(
        db, "Someone@Zaco.co.za", {Permission.VIEW_REPORTS}, admin, settings=limited
    )
    # Still an invitation to one address, not to the domain.
    assert invitation.email == "someone@zaco.co.za"
