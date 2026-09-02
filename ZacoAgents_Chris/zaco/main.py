"""Application entry point.

Nothing here is specific to any hosting provider. Local and hosted differ only in the values
that `Settings` reads (D3).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from zaco.api import routes_admin, routes_auth, routes_health
from zaco.auth.service import seed_admin
from zaco.config import get_settings
from zaco.db.base import get_session_factory
from zaco.web import routes as web_routes

log = logging.getLogger("zaco")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    for directory in (settings.workbook_dir, settings.backup_dir):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Surfaced by /api/health rather than crashing: the operator should see a reason.
            log.warning("Could not create %s: %s", directory, exc)

    session = get_session_factory()()
    try:
        admin = seed_admin(session)
        session.commit()
        if admin is not None:
            log.warning(
                "Seeded the first account: %s. Change its password after signing in.",
                admin.email,
            )
    except Exception as exc:  # noqa: BLE001 - startup must not die on an unmigrated database.
        session.rollback()
        log.warning("Could not seed the first account (%s). Have migrations been run?", exc)
    finally:
        session.close()

    if settings.is_insecure_secret:
        log.warning("SECRET_KEY is the shipped default. Set a real one before hosting.")

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Zaco account sales",
        version="0.1.0",
        summary=(
            "Reads market agent reports, resolves what they do not carry, and appends to the "
            "operator's workbook."
        ),
        lifespan=lifespan,
    )

    # The built-in interface calls these same endpoints, so a React or Flutter frontend needs
    # only CORS and the schema. Origins stay empty until one exists.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_health.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_admin.router)
    app.include_router(web_routes.router)

    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
