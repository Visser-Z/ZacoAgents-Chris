"""Application entry point.

Nothing here is specific to any hosting provider. Local and hosted differ only in the values
that `Settings` reads (D3).
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path, PurePath
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from zaco.api import (
    routes_admin,
    routes_auth,
    routes_conduct,
    routes_dockets,
    routes_health,
    routes_ingest,
    routes_queue,
    routes_reports,
    routes_rounds,
    routes_settlement,
    routes_workbook,
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


#: Refusals every protected endpoint can return, and none of them declares.
#: FastAPI documents what a handler *returns*; these are raised, so the schema never learns about
#: them and a generated client types every one as an unknown error. Written once here rather than
#: on forty routes: they come from the shared dependencies, so they are a property of being
#: protected, not of any one endpoint.
AUTH_REFUSALS: dict[int, str] = {
    401: "No session, or one that has expired. Sign in first.",
    403: "Signed in, but the account does not hold the permission this endpoint needs.",
}


def _document_auth_refusals(schema: dict[str, Any]) -> dict[str, Any]:
    """Add 401 and 403 to every operation that declares the session security scheme."""
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            if not isinstance(operation, dict) or not operation.get("security"):
                continue
            responses = operation.setdefault("responses", {})
            for code, description in AUTH_REFUSALS.items():
                responses.setdefault(str(code), {"description": description})
    return schema


#: The build puts hashed bundles under this directory, and nothing else lives there.
ASSETS = "assets"


def _is_asset(path: str) -> bool:
    r"""Whether a missing path was a bundle rather than a client route.

    Compared through `PurePath` rather than by string prefix: Starlette hands this a path built
    with the host's separator, so on Windows it is `assets\index.js` and a `startswith("assets/")`
    test quietly never matches -- working in the Linux image and failing on the developer's
    machine, which is the harder way round to notice.
    """
    parts = PurePath(path).parts
    return bool(parts) and parts[0] == ASSETS


class _SpaFiles(StaticFiles):
    """Static files that fall back to `index.html` instead of 404ing.

    A single-page app owns its own routes: the browser asks the server for `/app/reports`, and
    there is no such file. Without this, a reload anywhere but the root returns a 404 -- the
    classic way a SPA works perfectly until somebody refreshes.

    Only paths under the mount reach here, so `/api` is untouched and a missing *asset* still
    fails as an asset rather than being answered with a page.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as missing:
            if missing.status_code != 404 or _is_asset(path):
                raise
            return await super().get_response("index.html", scope)

    # Note `html=False` where this is mounted. StaticFiles' own html mode falls back to index.html
    # for *everything* it cannot find, including a missing script, so the browser is handed a page
    # where it asked for JavaScript and reports "Unexpected token '<'". Falling back here instead
    # keeps a missing asset a missing asset.


def spa_dir() -> Path:
    """Where `npm run build` puts the app. Vite writes straight here, so there is no copy step."""
    return Path(__file__).parent / "web" / "spa"


def _mount_spa(app: FastAPI, directory: Path | None = None) -> None:
    """Serve the built React app at `/app`, if it has been built.

    Same origin as the API by design: the session is an HttpOnly cookie with SameSite=lax and
    there is no CSRF token in this system, so a separate frontend origin would need
    `SameSite=None; Secure` and a CSRF layer to go with it. Serving both from here needs neither,
    and keeps the promise that the whole thing runs from `docker compose up` with nothing fetched
    from a CDN (D3).

    Mounted at `/app` rather than `/` while the Jinja interface still exists -- both want `/`,
    `/login` and `/queue`. The move to `/` is a one-line change once every page has a twin.
    """
    built = directory if directory is not None else spa_dir()
    if not (built / "index.html").exists():
        # Not an error: a checkout that has never run `npm run build` simply has no SPA yet, and
        # the Jinja interface is still the one being served.
        log.info("No built frontend at %s; serving the Jinja interface only.", built)
        return
    app.mount("/app", _SpaFiles(directory=str(built)), name="spa")


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
    app.include_router(routes_workbook.router)
    app.include_router(routes_workbook.rounds)
    app.include_router(routes_workbook.board)
    app.include_router(routes_settlement.router)
    app.include_router(routes_reports.router)
    app.include_router(routes_conduct.router)
    app.include_router(routes_dockets.router)
    app.include_router(routes_queue.products)
    app.include_router(web_routes.router)

    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    _mount_spa(app)

    generated = app.openapi

    def openapi() -> dict[str, Any]:
        return _document_auth_refusals(generated())

    app.openapi = openapi  # type: ignore[method-assign]
    return app


app = create_app()
