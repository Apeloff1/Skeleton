"""Engine readiness must reflect the same authority as work admission."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.routes import _state, router
from skeleton.kernel.runtime_supervision import RuntimeServiceLifecycle


@pytest.fixture
def probe():
    app = FastAPI()
    lifecycle = RuntimeServiceLifecycle("skeleton")
    app.state.runtime_lifecycle = lifecycle
    health = SimpleNamespace(readiness=lambda: {"ready": True, "subsystems": 2})
    state = SimpleNamespace(health=health)
    app.dependency_overrides[_state] = lambda: state
    app.include_router(router, prefix="/api/v1")
    return TestClient(app), lifecycle, state


def test_starting_ready_draining(probe):
    client, lifecycle, _ = probe
    path = "/api/v1/health/ready"
    assert client.get(path).status_code == 503
    lifecycle.mark_ready(reason="recovery-complete")
    assert client.get(path).json() == {"ready": True, "subsystems": 2}
    lifecycle.begin_drain(reason="shutdown")
    assert client.get(path).status_code == 503


def test_missing_or_unready_health(probe):
    client, lifecycle, state = probe
    lifecycle.mark_ready(reason="recovery-complete")
    path = "/api/v1/health/ready"
    state.health = None
    assert client.get(path).status_code == 503
    state.health = SimpleNamespace(readiness=lambda: {"ready": False})
    assert client.get(path).status_code == 503


def test_compose_admission():
    from pathlib import Path

    import yaml

    services = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
    )["services"]
    assert "/api/v1/health/ready" in " ".join(services["skeleton"]["healthcheck"]["test"])
    assert services["backend"]["depends_on"]["skeleton"]["condition"] == "service_healthy"
    assert not services["frontend"].get("depends_on")
