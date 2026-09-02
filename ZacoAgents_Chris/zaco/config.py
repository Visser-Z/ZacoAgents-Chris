"""Every environment-dependent value the application has.

Deliberately small. Switching from `docker compose up` to a hosting provider means filling in
these variables and nothing else -- there is no provider-specific code anywhere in the package.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://zaco:zaco@127.0.0.1:5432/zaco",
        description="SQLAlchemy URL. Render supplies a postgres:// URL; normalised below.",
    )

    workbook_dir: Path = Field(
        default=Path("/data/workbook"),
        description="Where the operator's live workbook lives. A named volume locally, "
        "a mounted disk when hosted.",
    )
    backup_dir: Path = Field(
        default=Path("/data/backups"),
        description="Timestamped snapshots taken inside the append transaction (D4).",
    )
    backup_retention: int = Field(
        default=50, ge=1, description="How many snapshots to keep before pruning the oldest."
    )

    secret_key: str = Field(
        default="dev-only-not-a-secret",
        description="Signs the session cookie. Must be set to a real value when hosted.",
    )
    session_max_age: int = Field(default=60 * 60 * 12, description="Session lifetime, seconds.")
    cookie_secure: bool | None = Field(
        default=None,
        description="Mark the session cookie Secure. None means decide from the request "
        "scheme, which is right in both targets: plain http locally, https when hosted "
        "behind a TLS-terminating proxy that sets X-Forwarded-Proto.",
    )

    admin_email: str = Field(
        default="admin@example.com",
        description="Seeded on first boot so there is someone who can invite everyone else.",
    )
    admin_password: str = Field(
        default="change-me",
        description="Seeded admin's initial password. Change it after the first login.",
    )
    # NoDecode: without it pydantic-settings tries to JSON-decode any list-typed
    # environment variable before validation, so the plain comma-separated string that a
    # .env file or a hosting provider's environment group actually contains raises.
    allowed_email_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="If non-empty, only these domains may be invited (D14). This gates who may "
        "be invited; it is never an identity.",
    )

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        # Hosting providers hand out `postgres://`, which SQLAlchemy 2 no longer recognises.
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("allowed_email_domains", mode="before")
    @classmethod
    def _split_domains(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip().lower() for part in value.split(",") if part.strip()]
        return value

    @property
    def is_insecure_secret(self) -> bool:
        """True when running on the shipped default. Surfaced as a banner, not a crash."""
        return self.secret_key == "dev-only-not-a-secret"


@lru_cache
def get_settings() -> Settings:
    return Settings()
