"""FastAPI dependencies for identifying the caller and checking one permission."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from zaco.auth.permissions import Permission
from zaco.auth.service import SESSION_COOKIE, read_session
from zaco.db.base import get_db
from zaco.db.models import User

#: Declared as a security scheme rather than read off the request, so the session appears in the
#: OpenAPI document. Without it cookie auth is invisible to the schema: a generated client gets
#: methods with no notion of authentication, and `/docs` cannot call a single protected endpoint.
#: `auto_error=False` keeps the existing behaviour -- a missing cookie is `None` here and the
#: refusal is raised by `current_user`, which is what lets a page redirect to sign-in instead.
session_cookie = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    scheme_name="Session cookie",
    description="Signed session cookie set by `POST /api/auth/login`. HttpOnly.",
)


def current_user_optional(
    token: str | None = Security(session_cookie), db: Session = Depends(get_db)
) -> User | None:
    if not token:
        return None
    uid = read_session(token)
    if uid is None:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        return None
    return user


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in first.",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


def requires(permission: Permission) -> Callable[[User], User]:
    """Dependency factory: `Depends(requires(Permission.APPEND))`."""

    def _check(user: User = Depends(current_user)) -> User:
        if not user.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your account does not have the '{permission.value}' permission.",
            )
        return user

    return _check
