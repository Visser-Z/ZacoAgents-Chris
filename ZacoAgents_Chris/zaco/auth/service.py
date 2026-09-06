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
from zaco.db.models import AccountEvent, Invitation, PasswordReset, User, utcnow

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


# --- Passwords, and the ways back into an account ---------------------------------------------

MINIMUM_PASSWORD = 12
"""Long enough to be worth the argon2 hash behind it. The same rule everywhere a password is
set, because a reset that accepted a weaker one than an invitation did would be the way in."""

RESET_PATH = "/app/reset"
"""Where a reset link points.

Under `/app` because that is where the React interface lives while the Jinja one still owns `/`.
The one string, so the step that flips the app to `/` changes it here and nowhere else. A
redirect at `/reset/<token>` catches anyone who reaches the old interface with a link.
"""

RESET_VALID_FOR = timedelta(hours=4)
"""Short, because a reset link is carried by hand and used within minutes of being handed over.
An invitation lasts a week because it is sent to somebody who may be away; a reset is issued
because somebody is standing there unable to work."""


def check_password(password: str) -> None:
    if len(password) < MINIMUM_PASSWORD:
        raise AuthError(f"Use at least {MINIMUM_PASSWORD} characters.")


def record(
    db: Session,
    user: User,
    action: str,
    detail: str = "",
    reason: str = "",
    by: User | None = None,
    by_label: str = "",
) -> AccountEvent:
    """Write down what was done to an account."""
    event = AccountEvent(
        user_id=user.id,
        action=action,
        detail=detail,
        reason=reason,
        by_id=by.id if by is not None else None,
        by_label=by_label or (by.email if by is not None else ""),
    )
    db.add(event)
    db.flush()
    return event


def change_password(db: Session, user: User, current: str, new: str) -> None:
    """Change your own password, having proved you know the old one.

    The old password is required even though the session already proves who you are: a session is
    a cookie on a machine, and an unattended machine is the case this check exists for.
    """
    if not verify_password(user.password_hash, current):
        raise AuthError("That is not your current password.")
    check_password(new)
    if verify_password(user.password_hash, new):
        raise AuthError("That is the password you already have.")
    user.password_hash = hash_password(new)
    record(db, user, "password changed", "by the account holder", by=user)
    db.flush()


def request_reset(db: Session, email: str) -> None:
    """Note that somebody says they cannot get in.

    Returns nothing at all, whether or not the address has an account. The caller says the same
    sentence either way: a page that answered differently would be a way to find out who has an
    account here, and every account is a named person.

    A request grants nothing. It is a note for whoever can issue the link.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return
    already = (
        db.execute(
            select(PasswordReset)
            .where(PasswordReset.user_id == user.id)
            .where(PasswordReset.token.is_(None))
            .where(PasswordReset.used_at.is_(None))
        )
        .scalars()
        .first()
    )
    if already is not None:
        # Asking twice is not two problems, and a list of the same request eight times is a list
        # nobody reads.
        return
    db.add(PasswordReset(user_id=user.id, requested_at=utcnow()))
    db.flush()


def issue_reset(
    db: Session,
    user: User,
    *,
    issued_by: User | None,
    via: str,
    reason: str = "",
    valid_for: timedelta = RESET_VALID_FOR,
) -> PasswordReset:
    """Hand out a one-time link that sets a new password.

    Any request outstanding for this account is answered by the same row rather than left
    standing, so the list of people waiting is a list of people still waiting.
    """
    waiting = (
        db.execute(
            select(PasswordReset)
            .where(PasswordReset.user_id == user.id)
            .where(PasswordReset.token.is_(None))
            .where(PasswordReset.used_at.is_(None))
        )
        .scalars()
        .first()
    )

    reset = waiting or PasswordReset(user_id=user.id)
    reset.token = secrets.token_urlsafe(32)
    reset.issued_at = utcnow()
    reset.issued_by_id = issued_by.id if issued_by is not None else None
    reset.issued_via = via
    reset.reason = reason.strip()
    reset.expires_at = datetime.now(UTC) + valid_for
    db.add(reset)
    record(
        db,
        user,
        "password reset issued",
        f"a one-time link, valid until {reset.expires_at:%Y-%m-%d %H:%M} UTC",
        reason=reason.strip(),
        by=issued_by,
        by_label=via,
    )
    db.flush()
    return reset


def use_reset(db: Session, token: str, password: str) -> User:
    """Spend a reset link on a new password.

    A used link is spent whether or not the account was already reachable another way, and an
    inactive account is refused here rather than let in: deactivating somebody is meant to stop
    them working, and a reset link that walked past that would undo it silently.
    """
    reset = db.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    ).scalar_one_or_none()
    if reset is None or not reset.is_open:
        raise AuthError("That link is not valid any more. Ask for a new one.")
    check_password(password)

    user = reset.user
    if not user.is_active:
        raise AuthError("That account is not active. An administrator can turn it back on.")

    user.password_hash = hash_password(password)
    reset.used_at = utcnow()
    record(db, user, "password reset used", f"issued by {reset.issued_via}", by=user)
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
