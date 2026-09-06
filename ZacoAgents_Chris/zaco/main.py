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


#: The two first segments that are never a page. `assets` is where the build puts hashed bundles
#: and nothing else; `api` is the JSON API, which shares the root with the app now that the app is
#: mounted there.
NOT_PAGES = ("assets", "api")


def _is_client_route(path: str) -> bool:
    r"""Whether a missing path should be answered with the page rather than a 404.

    A single-page app owns its own routes, so almost everything unknown *is* a page. The two
    exceptions have the same failure in common: answered with HTML, a missing bundle reaches the
    browser as `Unexpected token '<'` and a mistyped API path reaches a client as a parse error,
    and neither message says anything about the real fault.

    `api` matters only since the app moved to `/`. While it was under `/app` nothing outside that
    prefix reached here at all.

    Compared through `PurePath` rather than by string prefix: Starlette hands this a path built
    with the host's separator, so on Windows it is `assets\index.js` and a `startswith("assets/")`
    test quietly never matches -- working in the Linux image and failing on the developer's
    machine, which is the harder way round to notice.
    """
    parts = PurePath(path).parts
    return not parts or parts[0] not in NOT_PAGES


class _SpaFiles(StaticFiles):
    """Static files that fall back to `index.html` instead of 404ing.

    A single-page app owns its own routes: the browser asks the server for `/reports`, and there
    is no such file. Without this, a reload anywhere but the root returns a 404 -- the classic way
    a SPA works perfectly until somebody refreshes.

    The mount is at `/` and is registered last, so everything unmatched arrives here. What must
    *not* be answered with a page is decided by `_is_client_route`.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as refusal:
            if refusal.status_code == 405:
                # StaticFiles serves GET and HEAD and refuses everything else with 405. Anything
                # that reached here matched no API route, so 405 would say the address exists and
                # only dislikes the verb -- which is both wrong and a hint that it exists. The
                # answer before the app moved to `/` was 404, and 404 is what it still is.
                raise StarletteHTTPException(404) from refusal
            if refusal.status_code != 404 or not _is_client_route(path):
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
    """Serve the built React app at `/`, if it has been built.

    Same origin as the API by design: the session is an HttpOnly cookie with SameSite=lax and
    there is no CSRF token in this system, so a separate frontend origin would need
    `SameSite=None; Secure` and a CSRF layer to go with it. Serving both from here needs neither,
    and keeps the promise that the whole thing runs from `docker compose up` with nothing fetched
    from a CDN (D3).

    Mounted last, so every route registered above it wins: the API, `/docs`, `/openapi.json`.
    A mount at `/` matches everything left over, which is what a single-page app needs and why
    `_is_client_route` has to keep `/api` out of it.
    """
    built = directory if directory is not None else spa_dir()
    if not (built / "index.html").exists():
        # Not an error, but there is no interface at all now, so it is worth saying out loud
        # rather than leaving somebody to discover a bare API by getting a 404 at the root.
        log.warning("No built frontend at %s; the API is up but nothing serves a page.", built)
        return
    app.mount("/", _SpaFiles(directory=str(built)), name="spa")


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

    _mount_spa(app)

    generated = app.openapi

    def openapi() -> dict[str, Any]:
        return _document_auth_refusals(generated())

    app.openapi = openapi  # type: ignore[method-assign]
    return app


app = create_app()
