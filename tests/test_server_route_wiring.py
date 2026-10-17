"""create_app() wiring for the OmniFabric router (env toggle, gate order).

Cortex must stay unmounted and the legacy ``gameforge_routes`` module must not
be included by ``create_app()``.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from skeleton.api import server
from skeleton.app.runtime.audit_parse import create_app_included_routers

OMNI_PATHS = {
    "/api/v1/omnifabric/meta",
    "/api/v1/omnifabric/status",
    "/api/v1/omnifabric/verify-chain",
}


def _paths(app) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


@pytest.mark.parametrize("value", [None, "1", "true", "on", " YES "])
def test_omnifabric_enabled_by_default_and_truthy(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SKELETON_OMNIFABRIC_API", raising=False)
    else:
        monkeypatch.setenv("SKELETON_OMNIFABRIC_API", value)
    assert server._omnifabric_api_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", " OFF "])
def test_omnifabric_disabled_values(monkeypatch, value):
    monkeypatch.setenv("SKELETON_OMNIFABRIC_API", value)
    assert server._omnifabric_api_enabled() is False


def test_create_app_mounts_omnifabric_under_api_v1(monkeypatch):
    monkeypatch.delenv("SKELETON_OMNIFABRIC_API", raising=False)
    paths = _paths(server.create_app())
    assert OMNI_PATHS <= paths
    assert not any(p.startswith("/omnifabric") for p in paths)


def test_create_app_skips_omnifabric_when_disabled(monkeypatch):
    monkeypatch.setenv("SKELETON_OMNIFABRIC_API", "0")
    paths = _paths(server.create_app())
    assert not any("/omnifabric" in p for p in paths)


def test_omnifabric_is_gated_not_open(monkeypatch):
    monkeypatch.delenv("SKELETON_OMNIFABRIC_API", raising=False)
    monkeypatch.delenv("SKELETON_PUBLIC_DEV_SURFACES", raising=False)
    open_prefixes = server._gate_open_prefixes()
    assert not any(p.rstrip("/").endswith("omnifabric") for p in open_prefixes)


def test_cortex_and_legacy_gameforge_routes_stay_unmounted():
    modules = {str(row.get("module") or "") for row in create_app_included_routers()}
    assert "skeleton.api.omnifabric_routes" in modules
    assert "skeleton.api.cortex_routes" not in modules
    assert "skeleton.api.gameforge_routes" not in modules
