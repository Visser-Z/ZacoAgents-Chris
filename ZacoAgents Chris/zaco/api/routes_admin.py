"""Inviting accounts and setting what each one may do (D14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.api.schemas import ActiveIn, InvitationOut, InviteIn, Message, PermissionsIn, UserOut
from zaco.auth.deps import requires
from zaco.auth.permissions import Permission
from zaco.auth.service import AuthError, create_invitation
from zaco.db.base import get_db
from zaco.db.models import Invitation, User

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
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such account.")
    if user.id == actor.id and Permission.ADMIN not in payload.permissions:
        # Leaving nobody able to invite anyone is a lockout, not a permission change.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You cannot remove your own admin permission."
        )
    user.permissions = sorted(p.value for p in payload.permissions)
    db.flush()
    return _user_out(user)


@router.put("/users/{user_id}/active", response_model=UserOut)
def set_active(
    user_id: int,
    payload: ActiveIn,
    db: Session = Depends(get_db),
    actor: User = Depends(admin_only),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such account.")
    if user.id == actor.id and not payload.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself.")
    user.is_active = payload.is_active
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
