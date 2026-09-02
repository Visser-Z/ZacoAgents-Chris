"""Password hashing, session cookies, invitation issue and acceptance."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zaco.auth.permissions import ALL_PERMISSIONS, Permission
from zaco.config import Settings, get_settings
from zaco.db.models import Invitation, User, utcnow

SESSION_COOKIE = "zaco_session"
_hasher = PasswordHasher()


class AuthError(Exception):
    """Raised where the caller should show a message, not a stack trace."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False
    return True


def _serializer(settings: Settings | None = None) -> URLSafeTimedSerializer:
    settings = settings or get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt="zaco-session")


def issue_session(user: User, settings: Settings | None = None) -> str:
    return _serializer(settings).dumps({"uid": user.id})


def read_session(token: str, settings: Settings | None = None) -> int | None:
    settings = settings or get_settings()
    try:
        payload = _serializer(settings).loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    return uid if isinstance(uid, int) else None


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == normalise_email(email))
    return db.execute(stmt).scalar_one_or_none()


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    # Hash regardless of whether the user exists, so a missing account and a wrong password
    # take the same time and cannot be told apart from outside.
    reference = user.password_hash if user else hash_password("no-such-user")
    ok = verify_password(reference, password)
    if user is None or not ok or not user.is_active:
        raise AuthError("Email or password is not right.")
    user.last_login_at = utcnow()
    return user


def domain_allowed(email: str, settings: Settings | None = None) -> bool:
    """The allowed-domain rule gates who may be *invited*. It is never an identity (D14)."""
    settings = settings or get_settings()
    if not settings.allowed_email_domains:
        return True
    _, _, domain = normalise_email(email).partition("@")
    return domain in settings.allowed_email_domains


def create_invitation(
    db: Session,
    email: str,
    permissions: set[Permission],
    invited_by: User,
    valid_for: timedelta = timedelta(days=7),
    settings: Settings | None = None,
) -> Invitation:
    email = normalise_email(email)
    if "@" not in email:
        raise AuthError("That does not look like an email address.")
    if not domain_allowed(email, settings):
        allowed = ", ".join((settings or get_settings()).allowed_email_domains)
        raise AuthError(f"Invitations are limited to: {allowed}.")
    if get_user_by_email(db, email) is not None:
        raise AuthError(f"{email} already has an account.")

    invitation = Invitation(
        email=email,
        token=secrets.token_urlsafe(32),
        permissions=sorted(p.value for p in permissions),
        invited_by_id=invited_by.id,
        expires_at=datetime.now(UTC) + valid_for,
    )
    db.add(invitation)
    db.flush()
    return invitation


def accept_invitation(db: Session, token: str, password: str, display_name: str = "") -> User:
    stmt = select(Invitation).where(Invitation.token == token)
    invitation = db.execute(stmt).scalar_one_or_none()
    if invitation is None or not invitation.is_open:
        raise AuthError("That invitation is not valid any more. Ask an admin for a new one.")
    if len(password) < 12:
        raise AuthError("Use at least 12 characters.")
    if get_user_by_email(db, invitation.email) is not None:
        raise AuthError(f"{invitation.email} already has an account.")

    user = User(
        email=invitation.email,
        display_name=display_name.strip() or invitation.email,
        password_hash=hash_password(password),
        permissions=list(invitation.permissions),
    )
    db.add(user)
    invitation.accepted_at = utcnow()
    db.flush()
    return user


def seed_admin(db: Session, settings: Settings | None = None) -> User | None:
    """Create the first account on an empty database, so someone can invite everyone else.

    Never touches an existing account, and never resets a password.
    """
    settings = settings or get_settings()
    if db.execute(select(func.count()).select_from(User)).scalar_one():
        return None
    admin = User(
        email=normalise_email(settings.admin_email),
        display_name="Administrator",
        password_hash=hash_password(settings.admin_password),
        permissions=sorted(p.value for p in ALL_PERMISSIONS),
    )
    db.add(admin)
    db.flush()
    return admin
