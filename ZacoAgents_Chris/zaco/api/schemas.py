"""Request and response shapes for `/api/*`.

These are the contract a React or Flutter frontend would build against later (D1), so they are
kept explicit rather than serialising ORM objects directly.
"""

from __future__ import annotations

from datetime import datetime

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
