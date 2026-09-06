"""Serving the React app from the API's own origin, at the root.

Three things here could be wrong without looking wrong. A client route that 404s only shows up
when somebody reloads a page rather than clicking to it. A *missing bundle* answered with the
page reaches the browser as HTML where it asked for JavaScript, reported as
`Unexpected token '<'` -- a message that says nothing about the real fault. And since the app
moved from `/app` to `/`, the mount is the last thing every unmatched request falls through to,
so a mistyped API path would be answered with a page unless something stops it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zaco.main import _is_client_route, _mount_spa, create_app

SPA = Path(__file__).resolve().parent.parent / "zaco" / "web" / "spa"
needs_build = pytest.mark.skipif(
    not (SPA / "index.html").exists(),
    reason="No built frontend; run `npm run build` in frontend/.",
)


def test_what_is_a_page_and_what_is_not_whatever_the_separator() -> None:
    """Starlette builds this path with the host's separator.

    A `startswith("assets/")` test passes on Linux and silently never matches on Windows, so the
    guard would work in the image and not on the machine it was written on.
    """
    assert _is_client_route("reports")
    assert _is_client_route("")
    assert _is_client_route(str(Path("rounds") / "3"))
    # Not a prefix match: a client route may legitimately begin with those letters.
    assert _is_client_route("assets-report")
    assert _is_client_route("apiary")

    assert not _is_client_route("assets/index-abc123.js")
    assert not _is_client_route(str(Path("assets") / "index-abc123.js"))
    assert not _is_client_route(str(Path("assets") / "nested" / "thing.css"))
    assert not _is_client_route("api/health")
    assert not _is_client_route(str(Path("api") / "rounds" / "3"))


@needs_build
def test_a_client_route_is_answered_with_the_page() -> None:
    """The browser asks the server for `/reports` on a reload, and there is no such file."""
    client = TestClient(create_app())

    for path in ("/", "/reports", "/rounds/3/append", "/reset/some-token"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html"), path


@needs_build
def test_a_missing_bundle_stays_missing() -> None:
    """Answering it with the page hands the browser HTML where it asked for JavaScript."""
    client = TestClient(create_app())

    response = client.get("/assets/does-not-exist.js")

    assert response.status_code == 404
    assert not response.headers["content-type"].startswith("text/html")


@needs_build
def test_a_write_to_an_address_that_is_not_there_is_not_found() -> None:
    """404, not 405.

    `StaticFiles` answers GET and HEAD and refuses every other method with 405. Since the mount
    moved to `/` it is what unmatched requests fall through to, so without a guard every POST to a
    misspelled endpoint came back as "that address exists and will not take a POST" -- which is
    untrue, and tells a caller a path is real when it is not. It also made a path-traversal test
    in `test_workbook_api` pass through the mount instead of reaching the handler that refuses it.
    """
    client = TestClient(create_app())

    for method, path in (
        ("POST", "/api/not-a-real-endpoint"),
        ("PUT", "/api/admin/nonsense"),
        ("DELETE", "/queue"),
    ):
        response = client.request(method, path)
        assert response.status_code == 404, f"{method} {path}"


@needs_build
def test_the_api_is_not_shadowed_by_the_app() -> None:
    """Nothing under `/api` may be answered with a page.

    This was free while the app sat under `/app` -- nothing outside that prefix reached the mount
    at all. At `/` the mount catches everything unmatched, so a mistyped endpoint would come back
    as HTTP 200 and a page. A client would report it as a JSON parse error, which points at the
    response body rather than at the URL that was wrong.
    """
    client = TestClient(create_app())

    health = client.get("/api/health")
    missing = client.get("/api/not-a-real-endpoint")

    assert health.status_code == 200
    assert health.headers["content-type"].startswith("application/json")
    assert missing.status_code == 404
    assert not missing.headers["content-type"].startswith("text/html")


def test_the_app_still_starts_with_no_frontend_built(tmp_path: Path) -> None:
    """A checkout that has never run `npm run build` is not a broken one.

    There is no interface at all until it is built, but the API is still serviceable and the
    tests still have to run: cloning the repo would otherwise fail on a build artefact that is
    deliberately not committed.
    """
    app = FastAPI()

    _mount_spa(app, tmp_path)

    assert not [r for r in app.routes if getattr(r, "name", None) == "spa"]


def test_a_built_frontend_is_mounted(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>ok", encoding="utf-8")
    app = FastAPI()

    _mount_spa(app, tmp_path)

    assert [r for r in app.routes if getattr(r, "name", None) == "spa"]
