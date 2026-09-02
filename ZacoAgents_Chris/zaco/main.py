"""Application entry point.

Nothing here is specific to any hosting provider. Local and hosted differ only in the values
that `Settings` reads (D3).
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from zaco.api import (
    routes_admin,
    routes_auth,
    routes_health,
    routes_ingest,
    routes_queue,
    routes_rounds,
)
from zaco.auth.service import seed_admin
from zaco.config import get_settings
from zaco.db.base import get_session_factory
from zaco.resolve.service import WORKBOOK_NAME, workbook_path
from zaco.web import routes as web_routes

#: A copy of the starting workbook, shipped in the image. The live book lives on a persistent
#: volume that is empty on a fresh stack, and without a book there is no delivery note series
#: to mint from -- so the queue would ask for every number by hand on the very first round.
SEED_WORKBOOK = Path(__file__).resolve().parent.parent / "seed" / WORKBOOK_NAME

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

    _seed_workbook()

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


def _seed_workbook() -> None:
    """Put a starting book on the volume, once, and never touch it again.

    Only when there is nothing there. The workbook is the operator's live file and the thing the
    business settles money against; overwriting one that already exists would be the single worst
    thing this system could do on a restart.
    """
    target = workbook_path()
    if target.exists() or not SEED_WORKBOOK.exists():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SEED_WORKBOOK, target)
        log.warning("Seeded %s from the shipped starting workbook.", target)
    except OSError as exc:
        log.warning("Could not seed the workbook at %s: %s", target, exc)


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
    app.include_router(routes_ingest.router)
    # routes_rounds first: its literal `/api/rounds/stage` must be matched before the
    # `/api/rounds/{round_id}` pattern that routes_queue registers on the same prefix.
    app.include_router(routes_rounds.router)
    app.include_router(routes_queue.router)
    app.include_router(routes_queue.products)
    app.include_router(web_routes.router)

    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
