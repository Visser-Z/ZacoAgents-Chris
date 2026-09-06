"""The suite must not be able to destroy the development database.

This is here because it happened. `clean_db` truncates fourteen tables between cases, and which
database it truncates comes from `DATABASE_URL`. `conftest._configure_environment` points that at
`zaco_test` -- but it ran only when a test asked for a database fixture, and it cleared the
settings cache without clearing the SQLAlchemy engine built from it. So a run whose first test
needed no database (the SPA mount cases build a `TestClient`, which runs the app's lifespan, which
opens a session) built the engine from `zaco/config.py`'s default. That default is the
*development* database. Every `clean_db` after that emptied the operator's own record, and the run
reported nothing but a row of green dots.

Two things stop it now, and this pins the second: the environment is configured for every test
before any of them run, and the fixture that truncates refuses a database that is not named as a
test one. The first makes the mistake unlikely; the second makes the consequence impossible.
"""

from __future__ import annotations

import pytest

from tests.conftest import _must_be_a_test_database


def test_a_test_database_is_allowed() -> None:
    assert _must_be_a_test_database("postgresql+psycopg://zaco:zaco@127.0.0.1:5432/zaco_test")
    assert _must_be_a_test_database("postgresql://u:p@host:5432/anything_test")


@pytest.mark.parametrize(
    "url",
    [
        # The one that actually happened: `zaco/config.py`'s default.
        "postgresql+psycopg://zaco:zaco@127.0.0.1:5432/zaco",
        # A hosted database, which is the same mistake with worse consequences.
        "postgresql://user:secret@some.provider.com:5432/production",
        # Not a prefix or substring match -- `zaco_testing` is not `zaco_test`, and a name that
        # merely contains the word is not a promise about what it holds.
        "postgresql+psycopg://zaco:zaco@127.0.0.1:5432/test_fixtures",
    ],
)
def test_anything_else_is_refused(url: str) -> None:
    with pytest.raises(RuntimeError, match="truncates"):
        _must_be_a_test_database(url)


def test_the_refusal_names_the_database_so_the_reader_can_act() -> None:
    """A guard that fires without saying what it saw sends somebody reading fixtures."""
    with pytest.raises(RuntimeError) as refusal:
        _must_be_a_test_database("postgresql+psycopg://zaco:zaco@127.0.0.1:5432/zaco")

    assert "'zaco'" in str(refusal.value)
    assert "DATABASE_URL" in str(refusal.value)
