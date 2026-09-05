"""Serving the React app from the API's own origin.

Two things here could be wrong without looking wrong. A client route that 404s only shows up when
somebody reloads a page rather than clicking to it. And a *missing bundle* answered with the page
reaches the browser as HTML where it asked for JavaScript, which is reported as
`Unexpected token '<'` -- a message that says nothing about the real fault.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zaco.main import _is_asset, _mount_spa, create_app

SPA = Path(__file__).resolve().parent.parent / "zaco" / "web" / "spa"
needs_build = pytest.mark.skipif(
    not (SPA / "index.html").exists(),
    reason="No built frontend; run `npm run build` in frontend/.",
)


def test_a_path_under_assets_is_an_asset_whatever_the_separator() -> None:
    """Starlette builds this path with the host's separator.

    A `startswith("assets/")` test passes on Linux and silently never matches on Windows, so the
    guard would work in the image and not on the machine it was written on.
    """
    assert _is_asset("assets/index-abc123.js")
    assert _is_asset(str(Path("assets") / "index-abc123.js"))
    assert _is_asset(str(Path("assets") / "nested" / "thing.css"))

    assert not _is_asset("reports")
    assert not _is_asset("")
    assert not _is_asset(str(Path("rounds") / "3"))
    # Not a prefix match: a client route may legitimately begin with those letters.
    assert not _is_asset("assets-report")


@needs_build
def test_a_client_route_is_answered_with_the_page() -> None:
    """The browser asks the server for `/app/reports` on a reload, and there is no such file."""
    client = TestClient(create_app())

    for path in ("/app/", "/app/reports", "/app/rounds/3/append"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html"), path


@needs_build
def test_a_missing_bundle_stays_missing() -> None:
    """Answering it with the page hands the browser HTML where it asked for JavaScript."""
    client = TestClient(create_app())

    response = client.get("/app/assets/does-not-exist.js")

    assert response.status_code == 404
    assert not response.headers["content-type"].startswith("text/html")


@needs_build
def test_the_api_is_not_shadowed_by_the_app() -> None:
    """The mount is scoped to `/app`, so nothing under `/api` can be answered with a page."""
    client = TestClient(create_app())

    health = client.get("/api/health")
    missing = client.get("/api/not-a-real-endpoint")

    assert health.status_code == 200
    assert health.headers["content-type"].startswith("application/json")
    assert missing.status_code == 404
    assert not missing.headers["content-type"].startswith("text/html")


def test_the_app_still_starts_with_no_frontend_built(tmp_path: Path) -> None:
    """A checkout that has never run `npm run build` is not a broken one.

    It has no SPA yet and the Jinja interface is still what is served, so the mount is skipped
    rather than raising -- otherwise cloning the repo and running the tests would fail on a
    missing build artefact that is deliberately not committed.
    """
    app = FastAPI()

    _mount_spa(app, tmp_path)

    assert not [r for r in app.routes if getattr(r, "name", None) == "spa"]


def test_a_built_frontend_is_mounted(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>ok", encoding="utf-8")
    app = FastAPI()

    _mount_spa(app, tmp_path)

    assert [r for r in app.routes if getattr(r, "name", None) == "spa"]
