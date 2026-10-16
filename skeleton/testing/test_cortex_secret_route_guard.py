"""Cortex HTTP secrets must remain unmounted and fail closed."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes


@pytest.mark.parametrize("path", [
    "/api/v1/secrets",
    "/api/v1/secrets/{name}",
    "/api/v1/secrets/{name}/rotate",
    "/api/v1/%73ecrets/{name}",
    "/API/V1/SECRETS/{name}",
    "/api/v1//secrets/{name}",
    "/api/v1///secrets/{name}",
    "/api/v1/%2573ecrets/{name}",
])
def test_unchartered_secret_routes_are_rejected(path: str) -> None:
    app = SimpleNamespace(routes=[SimpleNamespace(path=path)])
    with pytest.raises(RuntimeError, match="cortex secrets"):
        reject_cortex_secret_routes(app)


@pytest.mark.parametrize("path", [
    "/api/v1/health",
    "/api/v1/commands/contracts",
    "/api/v1/swarm/status",
    "/cortex/status",
    "/api/v1/secrets-metadata",
])
def test_unrelated_registered_http_routes_still_work(path: str) -> None:
    reject_cortex_secret_routes(
        SimpleNamespace(routes=[SimpleNamespace(path=path)])
    )


def test_route_inventory_is_required() -> None:
    with pytest.raises(RuntimeError, match="route inventory"):
        reject_cortex_secret_routes(SimpleNamespace())
    with pytest.raises(RuntimeError, match="uninspectable"):
        reject_cortex_secret_routes(
            SimpleNamespace(routes=[SimpleNamespace(path=None)])
        )


def test_real_application_factory_rejects_unchartered_cortex_paths() -> None:
    from skeleton.api.server import create_app

    app = create_app()
    reject_cortex_secret_routes(app)
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any(
        path == "/api/v1/secrets" or path.startswith("/api/v1/secrets/")
        for path in paths
    )
