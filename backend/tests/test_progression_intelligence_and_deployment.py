import pytest

from core.deployment_planner import compile_deployment_plan, verify_deployment_plan
from core.progression import Medal, ProgressionState
from core.progression_intelligence import inspect_progression, verify_progression_projection


def test_progression_migration_discards_malformed_values_instead_of_crashing():
    state = ProgressionState.migrate({
        "best": {"good": 12.5, "bad": "nan", "negative": -2, "garbage": object()},
        "medals": {"good": 3, "bad": 99, "text": "x"},
        "ghosts": {"good": [{"x": 1}, "bad-sample"], "bad": "not-a-list"},
        "total_distance": "not-a-number",
        "unlocked": ["stage-2", ""],
    })
    assert state.best == {"good": 12.5}
    assert state.medals == {"good": Medal.GOLD}
    assert state.ghosts == {"good": [{"x": 1}]}
    assert state.total_distance == 0.0
    assert state.unlocked == {"stage-2"}


def test_progression_projection_is_deterministic_and_attested():
    raw = {
        "best": {"a": 15.0, "b": 9.0},
        "medals": {"a": 2, "b": 4},
        "total_distance": 123.0,
        "unlocked": ["c"],
    }
    first = inspect_progression(raw, known_stages=["a", "b", "c"])
    second = inspect_progression(raw, known_stages=["a", "b", "c"])
    assert first == second
    assert first["completion_pct"] == 66.7
    assert first["elite_stages"] == ["b"]
    assert verify_progression_projection(first) is True
    tampered = {**first, "completed_stages": 99}
    assert verify_progression_projection(tampered) is False


def test_production_deployment_plan_is_conservative_and_attested():
    plan = compile_deployment_plan({
        "environment": "production",
        "strategy": "canary",
        "target": "api",
        "artifact": "sha256:abc",
        "canary_percent": 40,
    })
    assert plan["phases"][0]["traffic_pct"] == 25
    assert "change.approval_present" in plan["preflight"]
    assert plan["rollback"]["automatic"] is True
    assert verify_deployment_plan(plan) is True
    tampered = {**plan, "target": "evil"}
    assert verify_deployment_plan(tampered) is False


def test_deployment_plan_rejects_unverifiable_inputs():
    with pytest.raises(ValueError, match="artifact"):
        compile_deployment_plan({"environment": "production", "target": "api"})
    with pytest.raises(ValueError, match="unsupported"):
        compile_deployment_plan({"environment": "moon", "target": "api", "artifact": "x"})
