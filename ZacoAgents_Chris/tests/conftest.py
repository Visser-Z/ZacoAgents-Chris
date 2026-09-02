"""Test fixtures.

Tests that need a database are marked `db` and skip when Postgres is unreachable, so the
suite still runs on a machine that has not started the compose stack. The schema is built by
running the real migrations rather than `create_all`, so a migration that has drifted from the
models fails here rather than on a deploy.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "seeded-admin-password"

REPO_ROOT = Path(__file__).resolve().parent.parent


def _configure_environment(tmp_root: Path) -> None:
    # A database of its own. These tests TRUNCATE between cases, and pointing them at the
    # development database would mean running the suite destroyed a staged round.
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+psycopg://zaco:zaco@127.0.0.1:5432/zaco_test"
    )
    os.environ["SECRET_KEY"] = "tests-only-not-a-secret"
    os.environ["ADMIN_EMAIL"] = ADMIN_EMAIL
    os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
    os.environ["WORKBOOK_DIR"] = str(tmp_root / "workbook")
    os.environ["BACKUP_DIR"] = str(tmp_root / "backups")
    os.environ.setdefault("ALLOWED_EMAIL_DOMAINS", "")

    from zaco.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session")
def settings_env(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("zaco-data")
    _configure_environment(root)
    return root


@pytest.fixture(scope="session")
def database_url(settings_env: Path) -> str:
    """Skip the whole database-backed suite if Postgres is not there, with a clear reason."""
    from zaco.config import get_settings

    url = get_settings().database_url
    try:
        # Short timeout on purpose: without it a missing database makes the whole suite
        # hang for a minute instead of skipping with a reason.
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 - the reason is what matters to the reader.
        pytest.skip(f"No database at {url} ({type(exc).__name__}). Run `docker compose up db`.")
    return url


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    from alembic import command
    from alembic.config import Config

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")
    return database_url


@pytest.fixture
def clean_db(migrated: str) -> Iterator[None]:
    from zaco.db.base import get_engine

    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE invitations, users RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db(clean_db: None) -> Iterator[Session]:
    from zaco.db.base import get_session_factory

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client(clean_db: None) -> Iterator[TestClient]:
    """A client whose startup has seeded the first admin, as a real boot would."""
    from zaco.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client
