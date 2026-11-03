"""Fail-closed Compose bootstrap contract for the first-run diagnostic UI.

The frontend does not grant AI, API, or database readiness. It must be able
to render status and setup independently from protected backend health.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from skeleton.app.assembly import find_repo_root


def _services() -> dict:
    root = find_repo_root(Path(__file__))
    return yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))["services"]


def test_frontend_setup_is_not_blocked_by_unhealthy_api_or_guarded_engine():
    services = _services()
    # A service_started dependency on backend is NOT enough: backend waits
    # for a healthy engine, which itself waits for a healthy database.
    # No direct or transitive Compose startup dependency may block setup UI.
    assert not services["frontend"].get("depends_on")
    assert not services["frontend"].get("network_mode", "").startswith("service:")


def test_relaxing_frontend_startup_does_not_relax_api_and_storage_health_fences():
    services = _services()
    assert services["backend"]["depends_on"]["mongo"]["condition"] == "service_healthy"
    assert services["backend"]["depends_on"]["skeleton"]["condition"] == "service_healthy"
    assert services["skeleton"]["depends_on"]["mongo"]["condition"] == "service_healthy"
    assert services["skeleton"]["environment"]
    assert any(
        str(value).startswith("AI_PROVIDER=")
        for value in services["skeleton"]["environment"]
    )
