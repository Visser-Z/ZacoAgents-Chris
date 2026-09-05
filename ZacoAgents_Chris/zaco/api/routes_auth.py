"""Sign in, sign out, accept an invitation, and report who the caller is."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from zaco.api.schemas import AcceptIn, LoginIn, Message, UserOut
from zaco.auth.deps import current_user
from zaco.auth.service import (
    SESSION_COOKIE,
    AuthError,
    accept_invitation,
    authenticate,
    issue_session,
)
from zaco.config import get_settings
from zaco.db.base import get_db
from zaco.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _is_secure(request: Request) -> bool:
    """Whether the session cookie should carry `Secure`.

    Decided by how the request actually arrived, not by a proxy for it: plain http locally, https
    when hosted behind a TLS-terminating proxy that sets X-Forwarded-Proto (uvicorn is started
    with --proxy-headers). COOKIE_SECURE overrides where that is wrong.
    """
    settings = get_settings()
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return request.url.scheme == "https"


def _set_session(response: Response, user: User, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(user),
        max_age=get_settings().session_max_age,
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
        path="/",
    )


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        permissions=sorted(user.granted),
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    try:
        user = authenticate(db, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    _set_session(response, user, request)
    if request.headers.get("HX-Request"):
        response.headers["HX-Redirect"] = "/"
    return _to_out(user)


@router.post("/logout", response_model=Message)
def logout(response: Response, request: Request) -> Message:
    """Clear the session, with the same attributes it was set with.

    A browser matches a deletion against `path`, `samesite`, `secure` and `domain`, not against
    the name alone. Deleting on the name and path only happens to work while the cookie is
    `SameSite=lax` over http; it would stop clearing the moment either changed, and a sign-out
    that silently leaves the session standing is the worst way for that to be discovered.
    """
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
    )
    response.headers["HX-Redirect"] = "/login"
    return Message(detail="Signed out.")


@router.post("/accept", response_model=UserOut)
def accept(
    payload: AcceptIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    try:
        user = accept_invitation(db, payload.token, payload.password, payload.display_name)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _set_session(response, user, request)
    if request.headers.get("HX-Request"):
        response.headers["HX-Redirect"] = "/"
    return _to_out(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return _to_out(user)
