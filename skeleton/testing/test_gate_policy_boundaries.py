from __future__ import annotations

import pytest

from skeleton.api.middleware import GatePolicy


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/health/",
        "/health/live",
        "/ready",
        "/api/v1/health/live",
        "/api/v1/health/ready",
    ],
)
def test_open_routes_allow_only_exact_routes_and_true_children(path: str) -> None:
    assert GatePolicy().is_open_route(path)


@pytest.mark.parametrize(
    "path",
    [
        "/healthcare",
        "/health-check",
        "/readyz",
        "/metrics",
        "/metrics-private",
        "/api/v1/health",
        "/api/v1/healthcare",
        "/api/v1/metrics",
        "/api/v1/metrics-private",
    ],
)
def test_sensitive_or_lookalike_routes_remain_sealed(path: str) -> None:
    assert not GatePolicy().is_open_route(path)


def test_root_open_prefix_is_exact_only() -> None:
    policy = GatePolicy(open_prefixes=("/",))

    assert policy.is_open_route("/")
    assert not policy.is_open_route("/admin")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/forge", "forge"),
        ("/api/v1/forge/jobs", "forge"),
        ("/api/v1/cortex", "cognition"),
        ("/api/v1/cortex/status", "cognition"),
        ("/api/v1/health", "observability"),
        ("/api/v1/metrics", "observability"),
        ("/cortex/status", "cognition"),
        ("/cockpit", "interface"),
        ("/openapi.json", "interface"),
    ],
)
def test_governance_domain_matches_exact_routes_and_children(path: str, expected: str) -> None:
    assert GatePolicy().required_domain(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/forge-admin",
        "/api/v1/cortexual",
        "/api/governance-backdoor",
        "/api/courtroom",
        "/cockpit-admin",
        "/docs-private",
    ],
)
def test_governance_domain_lookalikes_are_unwritten(path: str) -> None:
    assert GatePolicy().required_domain(path) is None


def test_server_default_open_surface_is_probe_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from skeleton.api import server

    monkeypatch.delenv("SKELETON_PUBLIC_DEV_SURFACES", raising=False)
    prefixes = server._gate_open_prefixes()

    assert "/" in prefixes
    assert "/api/v1/health/live" in prefixes
    assert "/api/v1/health/ready" in prefixes
    for sensitive in (
        "/api/v1/health",
        "/api/v1/metrics",
        "/api/v1/genesis",
        "/cortex/status",
        "/cockpit",
        "/docs",
        "/openapi.json",
        "/redoc",
    ):
        assert sensitive not in prefixes


def test_dev_surface_exposure_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from skeleton.api import server

    monkeypatch.setenv("SKELETON_PUBLIC_DEV_SURFACES", "true")
    prefixes = server._gate_open_prefixes()

    for dev_surface in server._DEV_OPEN_PREFIXES:
        assert dev_surface in prefixes
