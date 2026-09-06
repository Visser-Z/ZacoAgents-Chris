"""Inviting accounts, setting what each one may do, and getting somebody back into one (D14)."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.api.schemas import (
    AccountEventOut,
    ActiveIn,
    EmailIn,
    InvitationOut,
    InviteIn,
    Message,
    PermissionsIn,
    ProfileIn,
    ReasonIn,
    ResetOut,
    ResetRequestOut,
    UserOut,
)
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.auth.service import (
    RESET_PATH,
    AuthError,
    create_invitation,
    domain_allowed,
    get_user_by_email,
    issue_reset,
    normalise_email,
    record,
)
from zaco.db.base import get_db
from zaco.db.models import AccountEvent, Invitation, PasswordReset, User, utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = requires(Permission.ADMIN)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        permissions=sorted(user.granted),
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


def _invitation_out(invitation: Invitation, request: Request) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        permissions=sorted(Permission(p) for p in invitation.permissions),
        accept_url=str(request.base_url).rstrip("/") + f"/accept/{invitation.token}",
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
    )


def _must_find(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such account.")
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.email)).scalars().all()
    return [_user_out(u) for u in users]


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
def invite(
    payload: InviteIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> InvitationOut:
    try:
        invitation = create_invitation(db, payload.email, set(payload.permissions), actor)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _invitation_out(invitation, request)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(
    request: Request, db: Session = Depends(get_db), _: User = Depends(admin_only)
) -> list[InvitationOut]:
    rows = db.execute(select(Invitation).order_by(Invitation.created_at.desc())).scalars().all()
    return [_invitation_out(i, request) for i in rows]


@router.put("/users/{user_id}/permissions", response_model=UserOut)
def set_permissions(
    user_id: int,
    payload: PermissionsIn,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> UserOut:
    user = _must_find(db, user_id)
    if user.id == actor.id and Permission.ADMIN not in payload.permissions:
        # Leaving nobody able to invite anyone is a lockout, not a permission change.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot remove your own admin permission."
        )
    before = ", ".join(sorted(p.value for p in user.granted)) or "none"
    user.permissions = sorted(p.value for p in payload.permissions)
    after = ", ".join(user.permissions) or "none"
    record(db, user, "permissions set", f"{before} -> {after}", by=actor)
    db.flush()
    return _user_out(user)


@router.put("/users/{user_id}/active", response_model=UserOut)
def set_active(
    user_id: int,
    payload: ActiveIn,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> UserOut:
    user = _must_find(db, user_id)
    if user.id == actor.id and not payload.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself.")
    user.is_active = payload.is_active
    record(db, user, "turned on" if payload.is_active else "turned off", by=actor)
    db.flush()
    return _user_out(user)


@router.delete("/invitations/{invitation_id}", response_model=Message)
def revoke_invitation(
    invitation_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)
) -> Message:
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such invitation.")
    db.delete(invitation)
    return Message(detail="Invitation revoked.")


# --- The rest of an account --------------------------------------------------------------------


@router.put("/users/{user_id}/profile", response_model=UserOut)
def set_profile(
    user_id: int,
    payload: ProfileIn,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> UserOut:
    """The name shown beside every queue answer, DN approval and append.

    Editable because it was previously set once, when the invitation was accepted, and never
    again -- so a name typed wrong that first time was wrong on every decision afterwards.
    """
    user = _must_find(db, user_id)
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An account needs a name to show.")
    if name != user.display_name:
        record(db, user, "name changed", f"{user.display_name} -> {name}", by=actor)
        user.display_name = name
    db.flush()
    return _user_out(user)


@router.put("/users/{user_id}/email", response_model=UserOut)
def set_email(
    user_id: int,
    payload: EmailIn,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> UserOut:
    """Change the address an account signs in with.

    This is the account's identity, and every queue answer, DN approval and append already in the
    record is stamped with it. So it demands a typed reason and is written into the account's own
    trail: without that, a name changing across the history has no explanation attached to it
    anywhere, and D14's whole argument for named accounts is that somebody can be asked.
    """
    user = _must_find(db, user_id)
    email = normalise_email(payload.email)
    reason = payload.reason.strip()

    if not reason:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Changing the address an account signs in with needs a reason. It is the name on "
            "every decision this account has already made.",
        )
    if email == user.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That is already the address.")
    if not domain_allowed(email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That domain is not allowed here.")
    existing = get_user_by_email(db, email)
    if existing is not None and existing.id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{email} already has an account.")

    record(db, user, "email changed", f"{user.email} -> {email}", reason=reason, by=actor)
    user.email = email
    db.flush()
    return _user_out(user)


@router.post("/users/{user_id}/password-reset", response_model=ResetOut)
def reset_password(
    user_id: int,
    request: Request,
    payload: ReasonIn | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> ResetOut:
    """Hand out a one-time link that lets somebody set a new password.

    Returned once, to the administrator who asked for it, and never listed again. There is no mail
    in this system by design (D3), so they carry it to the person -- which is how an invitation
    already reaches somebody.

    An administrator may do this for their own account too. That is not a hole: they are signed in
    with the standing to do it to anybody, so refusing would protect nothing and would only push
    the ordinary case towards the recovery command.
    """
    user = _must_find(db, user_id)
    reset = issue_reset(
        db,
        user,
        issued_by=actor,
        via=f"an administrator ({actor.email})",
        reason=payload.reason.strip() if payload else "",
    )
    assert reset.expires_at is not None
    base = str(request.base_url).rstrip("/")
    return ResetOut(
        user_id=user.id,
        email=user.email,
        reset_url=f"{base}{RESET_PATH}/{reset.token}",
        expires_at=reset.expires_at,
    )


@router.get("/password-requests", response_model=list[ResetRequestOut])
def password_requests(
    db: Session = Depends(get_db), _: User = Depends(admin_only)
) -> list[ResetRequestOut]:
    """Who has said they cannot get in, and has not been given a link yet."""
    rows = (
        db.execute(
            select(PasswordReset)
            .where(PasswordReset.token.is_(None))
            .where(PasswordReset.used_at.is_(None))
            .order_by(PasswordReset.requested_at)
        )
        .scalars()
        .all()
    )
    return [
        ResetRequestOut(
            user_id=row.user_id,
            email=row.user.email,
            display_name=row.user.display_name,
            requested_at=row.requested_at,
        )
        for row in rows
    ]


@router.post("/invitations/{invitation_id}/reissue", response_model=InvitationOut)
def reissue_invitation(
    invitation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> InvitationOut:
    """Give an invitation that has run out a fresh token and a fresh week.

    The same row rather than a second one to the same address: two open invitations to one person
    means two accounts could be made from them, and the second would be refused halfway through
    somebody typing a password.
    """
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such invitation.")
    if invitation.accepted_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That invitation has already been accepted. The account exists, so reset its "
            "password instead.",
        )
    invitation.token = secrets.token_urlsafe(32)
    invitation.expires_at = utcnow() + timedelta(days=7)
    invitation.invited_by_id = actor.id
    db.flush()
    return _invitation_out(invitation, request)


@router.get("/events", response_model=list[AccountEventOut])
def events(db: Session = Depends(get_db), _: User = Depends(admin_only)) -> list[AccountEventOut]:
    """What has been done to accounts, newest first.

    Rounds have carried a trail since Phase 3. Accounts decide the identity behind every entry in
    that trail and carried none of their own until now.
    """
    rows = (
        db.execute(select(AccountEvent).order_by(AccountEvent.at.desc(), AccountEvent.id.desc()))
        .scalars()
        .all()
    )
    return [
        AccountEventOut(
            user_id=row.user_id,
            email=row.user.email,
            action=row.action,
            detail=row.detail,
            reason=row.reason,
            at=row.at,
            by=row.by_label or (row.by.email if row.by else ""),
        )
        for row in rows
    ]
