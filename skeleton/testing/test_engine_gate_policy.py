from __future__ import annotations

from skeleton.api.middleware import GatePolicy


def test_engine_execution_routes_are_written_and_sealed() -> None:
    policy = GatePolicy()

    assert policy.is_open_route("/api/v1/engine/executions") is False
    assert policy.required_domain("/api/v1/engine/executions") == "engine"
    assert policy.required_domain("/api/v1/engine/executions/exec-1") == "engine"
    assert policy.required_domain("/api/v1/engine/executions/exec-1/events") == "engine"


def test_engine_prefix_does_not_unseal_lookalike_paths() -> None:
    policy = GatePolicy()

    assert policy.required_domain("/api/v1/engineered") is None
    assert policy.required_domain("/api/v1/engine-admin") is None
