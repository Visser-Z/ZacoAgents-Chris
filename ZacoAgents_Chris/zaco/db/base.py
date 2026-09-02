"""Engine, session factory and the declarative base.

Money is `NUMERIC(14, 2)` everywhere and `Decimal` in Python. No currency value is ever a float:
section 8 requires agreement to the cent, and the Nett shares must sum to the payment exactly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Numeric, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from zaco.config import get_settings

# Use for every currency column so the precision decision lives in one place.
Money = Numeric(14, 2, asdecimal=True)


class Base(DeclarativeBase):
    pass


_engine: Any = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Any:
    global _engine
    if _engine is None:
        # A database that is not there must fail rather than hang: an operator waiting on a
        # blank page cannot tell a slow append from a broken one.
        _engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            future=True,
            connect_args={"connect_timeout": 10},
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency. One session per request, rolled back on any escaping exception."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
