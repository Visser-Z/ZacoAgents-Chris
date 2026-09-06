"""Sign in, sign out, accept an invitation, and report who the caller is."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from zaco.api.schemas import (
    AcceptIn,
    ChangePasswordIn,
    ForgotIn,
    LoginIn,
    Message,
    ResetIn,
    UserOut,
)
from zaco.auth.deps import current_user
from zaco.auth.service import (
    SESSION_COOKIE,
    AuthError,
    accept_invitation,
    authenticate,
    change_password,
    issue_session,
    request_reset,
    use_reset,
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


# --- Getting back in ---------------------------------------------------------------------------


@router.post("/password", response_model=Message)
def set_own_password(
    payload: ChangePasswordIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Message:
    """Change your own password, having proved you know the current one.

    The session is re-issued afterwards. Not doing so would leave the cookie minted against the
    old password still working, which is the opposite of what somebody changing a password after
    a scare is asking for.
    """
    try:
        change_password(db, user, payload.current_password, payload.new_password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _set_session(response, user, request)
    return Message(detail="Your password has been changed.")


@router.post("/forgot", response_model=Message)
def forgot(payload: ForgotIn, db: Session = Depends(get_db)) -> Message:
    """Say you cannot get in.

    Answers the same way whether or not that address has an account, and takes the same route
    through the code either way. A page that said "no such account" would be a way to find out
    who works here, one address at a time.

    Nothing is sent: there is no mail in this system by design (D3), so this records the request
    and an administrator hands over the link, exactly as an invitation already reaches somebody.
    """
    request_reset(db, payload.email)
    return Message(
        detail=(
            "If that address has an account, an administrator can now see that you are waiting "
            "and can give you a link to set a new password. Ask them for it."
        )
    )


@router.post("/reset", response_model=UserOut)
def reset(
    payload: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    """Spend a reset link on a new password, and sign in with it."""
    try:
        user = use_reset(db, payload.token, payload.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _set_session(response, user, request)
    return _to_out(user)
