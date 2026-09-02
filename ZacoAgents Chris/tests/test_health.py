"""Health reports what it actually checked, so a green tick never stands in for an unmade check."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


def test_health_is_reachable_without_signing_in(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["database"] == "up"
    assert body["workbook_dir_writable"] is True
    assert body["status"] == "ok"


def test_health_does_not_warn_when_a_real_secret_is_configured(client: TestClient) -> None:
    # Tests run with a real secret, so this asserts the absence of a false alarm. The warning
    # itself is covered by test_config.
    warnings = client.get("/api/health").json()["warnings"]
    assert not any("SECRET_KEY" in warning for warning in warnings)
