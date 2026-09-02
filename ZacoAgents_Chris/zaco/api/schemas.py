"""Request and response shapes for `/api/*`.

These are the contract a React or Flutter frontend would build against later (D1), so they are
kept explicit rather than serialising ORM objects directly.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from zaco.auth.permissions import Permission


class HealthOut(BaseModel):
    status: str
    database: str
    workbook_dir_writable: bool
    warnings: list[str] = Field(default_factory=list)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    permissions: list[Permission]
    is_active: bool
    last_login_at: datetime | None = None


class InviteIn(BaseModel):
    email: EmailStr
    permissions: list[Permission] = Field(default_factory=list)


class InvitationOut(BaseModel):
    id: int
    email: str
    permissions: list[Permission]
    accept_url: str
    expires_at: datetime
    accepted_at: datetime | None = None


class AcceptIn(BaseModel):
    token: str
    password: str
    display_name: str = ""


class PermissionsIn(BaseModel):
    permissions: list[Permission] = Field(default_factory=list)


class ActiveIn(BaseModel):
    is_active: bool


class Message(BaseModel):
    detail: str


# --- Ingest (Phase 1) -------------------------------------------------------------------------


class ProblemOut(BaseModel):
    severity: str
    message: str
    line_number: int | None = None
    line: str | None = None


class ScopeOut(BaseModel):
    description: str
    market: str | None = None
    agent: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    run_at: datetime | None = None
    is_narrowed: bool
    is_unstated: bool


class RecordPreview(BaseModel):
    """One parsed record, flattened for display. The domain model arrives in Phase 2."""

    label: str
    detail: str
    figures: dict[str, str] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


class InspectionOut(BaseModel):
    filename: str
    kind: str
    kind_title: str
    confidence: float
    scores: dict[str, float]
    scope: ScopeOut
    counts: dict[str, int]
    problems: list[ProblemOut]
    preview: list[RecordPreview]


class RefusalOut(BaseModel):
    """Why a document was not read. Section 4 requires an explanation, not a stack trace."""

    filename: str
    detail: str
    scores: dict[str, float]
