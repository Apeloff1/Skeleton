from __future__ import annotations

import pytest

from skeleton.api.middleware import GatePolicy


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/health/",
        "/health/live",
        "/metrics",
        "/metrics/prometheus",
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
        "/metrics-private",
        "/api/v1/healthcare",
        "/api/v1/metrics-private",
    ],
)
def test_open_route_lookalikes_remain_sealed(path: str) -> None:
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
    ],
)
def test_governance_domain_lookalikes_are_unwritten(path: str) -> None:
    assert GatePolicy().required_domain(path) is None
