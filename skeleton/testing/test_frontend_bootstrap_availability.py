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
    # The canonical assembly planner must agree with the actual Compose graph.
    # Otherwise parity validation and client bootstrap still advertise the
    # backend/engine as frontend startup prerequisites.
    from skeleton.app.assembly import load_manifest
    assert load_manifest().service("frontend").depends_on == ()
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


def test_production_setup_route_cannot_be_spa_fallback_false_positive():
    """The launcher must receive 404, not the root SPA, if /setup was omitted."""
    root = find_repo_root(Path(__file__))
    nginx = (root / "frontend/nginx.conf").read_text(encoding="utf-8")
    route = nginx.split("location = /setup {", 1)
    assert len(route) == 2, "production ingress must own exact /setup"
    location_body = route[1].split("}", 1)[0]
    assert "try_files /setup.html /setup/index.html =404;" in location_body
    assert "/index.html" not in location_body.replace("/setup/index.html", "")
    assert 'Cache-Control "no-store"' in location_body
    assert 'X-Content-Type-Options "nosniff"' in location_body

    dockerfile = (root / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "test -f /app/dist/setup.html || test -f /app/dist/setup/index.html" in dockerfile
    assert (root / "frontend/app/setup.tsx").is_file()
