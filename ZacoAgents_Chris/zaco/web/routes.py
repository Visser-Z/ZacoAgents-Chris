"""The built-in interface: a thin Jinja + HTMX client over `/api/*` (D1).

These routes render pages and read data. Every action -- signing in, inviting, changing
permissions -- is posted by the browser to the JSON API, so nothing the interface can do is
unavailable to a React or Flutter frontend later.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from zaco.auth.deps import current_user_optional
from zaco.auth.permissions import ALL_PERMISSIONS, DESCRIPTIONS, Permission
from zaco.db.base import get_db
from zaco.db.models import Invitation, User
from zaco.ingest.records import TITLES

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["all_permissions"] = ALL_PERMISSIONS
templates.env.globals["permission_descriptions"] = DESCRIPTIONS
templates.env.globals["Perm"] = Permission

router = APIRouter(include_in_schema=False)

# The nav for the whole system. Phases beyond 0 fill these in; until then each is shown
# disabled with the phase that will build it, so the shell is honest about what exists.
NAV = [
    ("/rounds", "Read a document", Permission.INGEST, None),
    ("/staged", "Stage a round", Permission.INGEST, None),
    ("/queue", "Resolution queue", Permission.RESOLVE, None),
    ("/workbook", "Workbook", Permission.APPEND, "Phase 4"),
    ("/reconciliation", "Reconciliation", Permission.VIEW_REPORTS, "Phase 5"),
    ("/settlement", "Settlement", Permission.RECORD_TERMS, "Phase 5"),
    ("/reports", "Reports", Permission.VIEW_REPORTS, "Phase 6"),
    ("/conduct", "Agent conduct", Permission.VIEW_REPORTS, "Phase 7"),
]


def _page(request: Request, name: str, user: User | None, **context: object) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name=name, context={"user": user, "nav": NAV, **context}
    )


@router.get("/login", response_model=None)
def login_page(
    request: Request, user: User | None = Depends(current_user_optional)
) -> HTMLResponse | RedirectResponse:
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return _page(request, "login.html", None)


@router.get("/accept/{token}", response_model=None)
def accept_page(request: Request, token: str) -> HTMLResponse:
    return _page(request, "accept.html", None, token=token)


@router.get("/", response_model=None)
def home(
    request: Request, user: User | None = Depends(current_user_optional)
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page(request, "home.html", user)


@router.get("/admin", response_model=None)
def admin_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.can(Permission.ADMIN):
        return _page(request, "forbidden.html", user, needed=Permission.ADMIN)
    users = db.execute(select(User).order_by(User.email)).scalars().all()
    invitations = (
        db.execute(select(Invitation).order_by(Invitation.created_at.desc())).scalars().all()
    )
    base = str(request.base_url).rstrip("/")
    return _page(request, "admin.html", user, users=users, invitations=invitations, base_url=base)


@router.get("/rounds", response_model=None)
def rounds_page(
    request: Request, user: User | None = Depends(current_user_optional)
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.can(Permission.INGEST):
        return _page(request, "forbidden.html", user, needed=Permission.INGEST)
    return _page(request, "upload.html", user, kinds={k.value: v for k, v in TITLES.items()})


@router.get("/staged", response_model=None)
def staged_page(
    request: Request, user: User | None = Depends(current_user_optional)
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.can(Permission.INGEST):
        return _page(request, "forbidden.html", user, needed=Permission.INGEST)
    return _page(request, "staged.html", user)


@router.get("/queue", response_model=None)
def queue_page(
    request: Request, user: User | None = Depends(current_user_optional)
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.can(Permission.RESOLVE):
        return _page(request, "forbidden.html", user, needed=Permission.RESOLVE)
    return _page(request, "queue.html", user)
