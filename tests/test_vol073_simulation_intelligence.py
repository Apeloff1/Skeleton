from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


WORLD = load("vol073_world_test", "skeleton/simulation/world.py")
AUTH = load("vol073_authority_test", "skeleton/simulation/authority.py")

WorldRule = WORLD.WorldRule
WorldRules = WORLD.WorldRules
WorldState = WORLD.WorldState
WorldStateError = WORLD.WorldStateError
SimulationAction = WORLD.SimulationAction
SimulationEvidence = WORLD.SimulationEvidence
verify_transition = WORLD.verify_transition

SimulationResourceBudget = AUTH.SimulationResourceBudget
RolloutRequest = AUTH.RolloutRequest
SimulationAuthorityGuard = AUTH.SimulationAuthorityGuard
SimulationAuthorityError = AUTH.SimulationAuthorityError


def rules() -> WorldRules:
    return WorldRules(
        "arena-rules-v1",
        (
            WorldRule("movement", "Movement consumes one energy.", {"cost": 1}),
            WorldRule("bounds", "Coordinates remain inside the arena.", {"limit": 10}),
        ),
    )


def state(*, uncertainty: float = 0.1, tick: int = 0) -> WorldState:
    return WorldState(
        world_id="arena",
        tick=tick,
        rules_digest=rules().digest,
        values={
            "agent": {"x": 1, "y": 2, "energy": 10},
            "targets": [{"x": 4, "y": 5}],
        },
        uncertainty=uncertainty,
    )


def action(
    *,
    capabilities: tuple[str, ...] = ("simulate.read-state",),
    authority_scope: str = "simulation",
) -> SimulationAction:
    return SimulationAction(
        action_id="move-east",
        actor_id="agent-1",
        intent="Advance one simulated grid cell.",
        parameters={"dx": 1, "dy": 0},
        requested_capabilities=capabilities,
        authority_scope=authority_scope,
    )


def budget(**overrides: object) -> SimulationResourceBudget:
    values = {
        "max_depth": 16,
        "max_branching_factor": 4,
        "max_total_nodes": 128,
        "max_state_bytes": 4096,
        "max_action_bytes": 2048,
        "max_compute_units": 10_000,
        "max_uncertainty": 0.5,
    }
    values.update(overrides)
    return SimulationResourceBudget(**values)


def request(**overrides: object) -> RolloutRequest:
    values = {
        "request_id": "rollout-1",
        "depth": 8,
        "branching_factor": 2,
        "planned_nodes": 32,
        "compute_units": 1000,
    }
    values.update(overrides)
    return RolloutRequest(**values)


def guard(**budget_overrides: object) -> SimulationAuthorityGuard:
    return SimulationAuthorityGuard(
        guard_id="simulation-guard-v1",
        budget=budget(**budget_overrides),
        allowed_capabilities=(
            "simulate.branch",
            "simulate.physics",
            "simulate.read-state",
        ),
    )


def test_rules_are_canonical_and_order_independent() -> None:
    first = rules()
    second = WorldRules("arena-rules-v1", tuple(reversed(first.rules)))
    assert first.digest == second.digest
    assert [rule.rule_id for rule in first.rules] == ["bounds", "movement"]


def test_duplicate_rule_identity_fails_closed() -> None:
    duplicate = WorldRule("movement", "Movement consumes one energy.", {"cost": 1})
    with pytest.raises(WorldStateError, match="duplicate rule_id"):
        WorldRules("arena-rules-v1", (duplicate, duplicate))


def test_world_state_digest_is_order_independent() -> None:
    first = state()
    second = WorldState(
        world_id="arena",
        tick=0,
        rules_digest=rules().digest,
        values={
            "targets": [{"y": 5, "x": 4}],
            "agent": {"energy": 10, "y": 2, "x": 1},
        },
        uncertainty=0.1,
    )
    assert first.digest == second.digest


def test_world_state_values_are_frozen() -> None:
    current = state()
    with pytest.raises(TypeError):
        current.values["new"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        current.values["agent"]["x"] = 99  # type: ignore[index]


def test_nonfinite_state_value_fails_closed() -> None:
    with pytest.raises(WorldStateError, match="non-finite"):
        WorldState(
            world_id="arena",
            tick=0,
            rules_digest=rules().digest,
            values={"bad": float("nan")},
            uncertainty=0.1,
        )


def test_world_state_rejects_invalid_rules_digest() -> None:
    with pytest.raises(WorldStateError, match="rules_digest"):
        WorldState(
            world_id="arena",
            tick=0,
            rules_digest="not-a-digest",
            values={},
            uncertainty=0.1,
        )


def test_evolve_binds_parent_lineage_and_advances_tick() -> None:
    prior = state()
    result = prior.evolve(
        values={"agent": {"x": 2, "y": 2, "energy": 9}},
        uncertainty=0.15,
    )
    assert result.tick == prior.tick + 1
    assert result.parent_state_digest == prior.digest


def test_simulation_state_never_grants_real_authority() -> None:
    current = state()
    assert current.can_support_real_world_fact is False
    assert current.can_satisfy_real_postcondition is False
    with pytest.raises(WorldStateError, match="cannot authorize"):
        current.require_real_world_authority()


def test_action_rejects_non_simulation_authority_scope() -> None:
    with pytest.raises(WorldStateError, match="real authority"):
        action(authority_scope="real")


def test_action_rejects_duplicate_capabilities() -> None:
    with pytest.raises(WorldStateError, match="duplicates"):
        action(capabilities=("simulate.physics", "simulate.physics"))


def test_action_never_grants_real_execution() -> None:
    current = action()
    assert current.can_execute_real_side_effect is False
    with pytest.raises(WorldStateError, match="real execution"):
        current.require_real_execution_authority()


def test_transition_emits_simulation_only_evidence() -> None:
    prior = state()
    result = prior.evolve(
        values={"agent": {"x": 2, "y": 2, "energy": 9}},
        uncertainty=0.2,
    )
    evidence = verify_transition(
        prior=prior,
        action=action(),
        result=result,
        rules=rules(),
        simulation_id="arena-sim",
    )
    assert evidence.evidence_class == "simulation"
    assert evidence.state_digest == prior.digest
    assert evidence.result_state_digest == result.digest
    assert evidence.can_support_real_world_fact is False
    with pytest.raises(WorldStateError, match="cannot authorize"):
        evidence.require_real_world_authority()


def test_transition_rejects_tick_jump() -> None:
    prior = state()
    result = WorldState(
        world_id="arena",
        tick=2,
        rules_digest=rules().digest,
        values={"agent": {"x": 2}},
        uncertainty=0.2,
        parent_state_digest=prior.digest,
    )
    with pytest.raises(WorldStateError, match="tick"):
        verify_transition(
            prior=prior,
            action=action(),
            result=result,
            rules=rules(),
            simulation_id="arena-sim",
        )


def test_transition_rejects_world_identity_drift() -> None:
    prior = state()
    result = WorldState(
        world_id="other-arena",
        tick=1,
        rules_digest=rules().digest,
        values={"agent": {"x": 2}},
        uncertainty=0.2,
        parent_state_digest=prior.digest,
    )
    with pytest.raises(WorldStateError, match="world_id"):
        verify_transition(
            prior=prior,
            action=action(),
            result=result,
            rules=rules(),
            simulation_id="arena-sim",
        )


def test_transition_rejects_parent_lineage_tampering() -> None:
    prior = state()
    result = WorldState(
        world_id="arena",
        tick=1,
        rules_digest=rules().digest,
        values={"agent": {"x": 2}},
        uncertainty=0.2,
        parent_state_digest="0" * 64,
    )
    with pytest.raises(WorldStateError, match="lineage"):
        verify_transition(
            prior=prior,
            action=action(),
            result=result,
            rules=rules(),
            simulation_id="arena-sim",
        )


def test_transition_rejects_rule_drift() -> None:
    prior = state()
    other_rules = WorldRules(
        "other-rules",
        (WorldRule("other", "Other bounded rule.", {}),),
    )
    result = WorldState(
        world_id="arena",
        tick=1,
        rules_digest=other_rules.digest,
        values={"agent": {"x": 2}},
        uncertainty=0.2,
        parent_state_digest=prior.digest,
    )
    with pytest.raises(WorldStateError, match="rule digest"):
        verify_transition(
            prior=prior,
            action=action(),
            result=result,
            rules=other_rules,
            simulation_id="arena-sim",
        )


def test_transition_rejects_decreasing_uncertainty() -> None:
    prior = state(uncertainty=0.2)
    result = prior.evolve(values={"agent": {"x": 2}}, uncertainty=0.1)
    with pytest.raises(WorldStateError, match="cannot decrease"):
        verify_transition(
            prior=prior,
            action=action(),
            result=result,
            rules=rules(),
            simulation_id="arena-sim",
        )


def test_evidence_rejects_escape_from_simulation_class() -> None:
    prior = state()
    with pytest.raises(WorldStateError, match="escape"):
        SimulationEvidence(
            simulation_id="arena-sim",
            state_digest=prior.digest,
            action_digest=action().digest,
            result_state_digest=prior.digest,
            uncertainty=0.1,
            evidence_class="real",
        )


def test_valid_rollout_gets_deterministic_permit() -> None:
    authority = guard()
    first = authority.authorize(
        state=state(), action=action(), request=request()
    )
    second = authority.authorize(
        state=state(), action=action(), request=request()
    )
    assert first == second
    assert first.authority_scope == "simulation"
    assert first.can_execute_real_side_effect is False
    authority.verify(first, state=state(), action=action(), request=request())


def test_permit_never_grants_real_execution() -> None:
    permit = guard().authorize(state=state(), action=action(), request=request())
    with pytest.raises(SimulationAuthorityError, match="real-world"):
        permit.require_real_execution_authority()


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("depth", 17, "depth"),
        ("branching_factor", 5, "branching"),
        ("planned_nodes", 129, "node count"),
        ("compute_units", 10_001, "compute units"),
    ],
)
def test_rollout_shape_budget_is_non_bypassable(
    field_name: str, value: int, message: str
) -> None:
    kwargs = {field_name: value}
    with pytest.raises(SimulationAuthorityError, match=message):
        guard().authorize(state=state(), action=action(), request=request(**kwargs))


def test_state_uncertainty_budget_fails_closed() -> None:
    with pytest.raises(SimulationAuthorityError, match="uncertainty"):
        guard().authorize(
            state=state(uncertainty=0.51),
            action=action(),
            request=request(),
        )


def test_state_byte_budget_fails_closed() -> None:
    with pytest.raises(SimulationAuthorityError, match="state exceeds byte"):
        guard(max_state_bytes=32).authorize(
            state=state(), action=action(), request=request()
        )


def test_action_byte_budget_fails_closed() -> None:
    with pytest.raises(SimulationAuthorityError, match="action exceeds byte"):
        guard(max_action_bytes=32).authorize(
            state=state(), action=action(), request=request()
        )


def test_undeclared_capability_fails_closed() -> None:
    with pytest.raises(SimulationAuthorityError, match="undeclared capability"):
        guard().authorize(
            state=state(),
            action=action(capabilities=("network.write",)),
            request=request(),
        )


def test_permit_tampering_is_detected() -> None:
    authority = guard()
    permit = authority.authorize(state=state(), action=action(), request=request())
    forged = replace(permit, receipt_digest="0" * 64)
    with pytest.raises(SimulationAuthorityError, match="does not match"):
        authority.verify(
            forged,
            state=state(),
            action=action(),
            request=request(),
        )


def test_budget_policy_change_invalidates_permit() -> None:
    original = guard()
    permit = original.authorize(state=state(), action=action(), request=request())
    changed = guard(max_depth=32)
    with pytest.raises(SimulationAuthorityError, match="does not match"):
        changed.verify(
            permit,
            state=state(),
            action=action(),
            request=request(),
        )


def test_action_change_invalidates_permit() -> None:
    authority = guard()
    permit = authority.authorize(state=state(), action=action(), request=request())
    changed_action = SimulationAction(
        action_id="move-east",
        actor_id="agent-1",
        intent="Advance two simulated grid cells.",
        parameters={"dx": 2, "dy": 0},
        requested_capabilities=("simulate.read-state",),
    )
    with pytest.raises(SimulationAuthorityError, match="does not match"):
        authority.verify(
            permit,
            state=state(),
            action=changed_action,
            request=request(),
        )


def test_request_change_invalidates_permit() -> None:
    authority = guard()
    permit = authority.authorize(state=state(), action=action(), request=request())
    with pytest.raises(SimulationAuthorityError, match="does not match"):
        authority.verify(
            permit,
            state=state(),
            action=action(),
            request=request(depth=9),
        )
