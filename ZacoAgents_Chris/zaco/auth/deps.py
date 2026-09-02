"""FastAPI dependencies for identifying the caller and checking one permission."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from zaco.auth.permissions import Permission
from zaco.auth.service import SESSION_COOKIE, read_session
from zaco.db.base import get_db
from zaco.db.models import User


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
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
