"""Settings is the whole difference between local and hosted, so its edges are worth pinning."""

from __future__ import annotations

import pytest

from zaco.config import Settings


def test_hosting_provider_postgres_url_is_normalised() -> None:
    # Render and friends hand out `postgres://`, which SQLAlchemy 2 refuses. If this silently
    # stopped working, the app would fail only on the hosted target.
    settings = Settings(database_url="postgres://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"

    settings = Settings(database_url="postgresql://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_an_explicit_driver_is_left_alone() -> None:
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert Settings(database_url=url).database_url == url


def test_allowed_domains_accept_a_comma_separated_string() -> None:
    # Environment variables are strings; a list is only ever what a test passes.
    settings = Settings(allowed_email_domains="Zaco.co.za, example.com ,")
    assert settings.allowed_email_domains == ["zaco.co.za", "example.com"]


def test_the_shipped_secret_is_reported_as_insecure() -> None:
    # Explicit rather than relying on the default, so an ambient SECRET_KEY in the environment
    # cannot make this pass or fail for the wrong reason.
    assert Settings(secret_key="dev-only-not-a-secret").is_insecure_secret is True
    assert Settings(secret_key="something-real").is_insecure_secret is False


def test_domains_read_from_the_environment_rather_than_a_constructor_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real path. Environment variables are plain strings, and pydantic-settings will try to
    # JSON-decode a list-typed field unless told not to -- which would mean the app booted fine
    # locally and raised on the first hosted start, where this variable is actually set.
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "zaco.co.za,example.com")
    assert Settings().allowed_email_domains == ["zaco.co.za", "example.com"]


def test_an_empty_domain_variable_means_no_restriction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "")
    assert Settings().allowed_email_domains == []
