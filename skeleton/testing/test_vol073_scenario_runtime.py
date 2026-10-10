from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "skeleton/simulation/scenario_runtime.py"
SPEC = importlib.util.spec_from_file_location("vol073_scenario_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ScenarioEdge = MODULE.ScenarioEdge
ScenarioNode = MODULE.ScenarioNode
ScenarioResourceUsage = MODULE.ScenarioResourceUsage
ScenarioRuntime = MODULE.ScenarioRuntime
ScenarioRuntimeError = MODULE.ScenarioRuntimeError
ScenarioStopReason = MODULE.ScenarioStopReason
ScenarioTransition = MODULE.ScenarioTransition
ScenarioTree = MODULE.ScenarioTree
SimulationAction = MODULE.SimulationAction
SimulationAuthority = MODULE.SimulationAuthority
SimulationBudget = MODULE.SimulationBudget
SimulationRule = MODULE.SimulationRule
SimulationRuleSet = MODULE.SimulationRuleSet


def rules(*items: SimulationRule) -> SimulationRuleSet:
    return SimulationRuleSet(
        items
        or (
            SimulationRule(
                rule_id="movement",
                description="Movement changes the simulated position only.",
                parameters={"max_delta": 1},
            ),
        )
    )


def authority(*capabilities: str) -> SimulationAuthority:
    return SimulationAuthority(
        authority_id="authority:test",
        simulation_id="game:test",
        allowed_capabilities=tuple(capabilities or ("move", "wait", "interact")),
    )


def budget(
    *,
    max_depth: int = 3,
    max_branches_per_node: int = 3,
    max_nodes: int = 32,
    max_cost_units: int = 100,
    max_total_actions: int = 31,
) -> SimulationBudget:
    return SimulationBudget(
        max_depth=max_depth,
        max_branches_per_node=max_branches_per_node,
        max_nodes=max_nodes,
        max_cost_units=max_cost_units,
        max_total_actions=max_total_actions,
    )


def action(
    action_id: str,
    *,
    capability: str = "move",
    operation: str = "advance",
    cost_units: int = 1,
    simulation_id: str = "game:test",
    parameters: dict[str, object] | None = None,
) -> SimulationAction:
    return SimulationAction(
        action_id=action_id,
        simulation_id=simulation_id,
        capability=capability,
        operation=operation,
        parameters=parameters or {"delta": 1},
        cost_units=cost_units,
    )


def transition(
    action_id: str,
    position: int,
    *,
    uncertainty: float = 0.1,
    reward: float = 1.0,
    terminal: bool = False,
    cost_units: int = 1,
    capability: str = "move",
) -> ScenarioTransition:
    return ScenarioTransition(
        action=action(
            action_id,
            cost_units=cost_units,
            capability=capability,
            parameters={"to": position},
        ),
        next_state={"position": position},
        local_uncertainty=uncertainty,
        reward=reward,
        terminal=terminal,
    )


def runtime(**budget_overrides: int) -> ScenarioRuntime:
    return ScenarioRuntime(
        simulation_id="game:test",
        authority=authority(),
        budget=budget(**budget_overrides),
        rules=rules(),
    )


def node_by_depth(tree: ScenarioTree, depth: int) -> tuple[ScenarioNode, ...]:
    return tuple(node for node in tree.nodes if node.depth == depth)


def test_deterministic_tree_is_independent_of_expander_order() -> None:
    def forward(state, node):
        if node.depth > 0:
            return ()
        return (
            transition("move.right", 1, uncertainty=0.2),
            transition("move.left", -1, uncertainty=0.1),
        )

    def reverse(state, node):
        return tuple(reversed(forward(state, node)))

    first = runtime().explore({"position": 0}, forward)
    second = runtime().explore({"position": 0}, reverse)

    assert first.digest == second.digest
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.usage.nodes == 3
    assert first.usage.actions == 2


def test_simulation_action_can_never_authorize_real_effect() -> None:
    candidate = action("move.once")
    assert candidate.effect_scope == "simulation_only"
    with pytest.raises(ScenarioRuntimeError, match="real-effect authority"):
        candidate.require_real_effect_authority()
    with pytest.raises(ScenarioRuntimeError, match="real-world side effect"):
        authority().require_real_effect_authority()


def test_non_simulation_effect_scope_fails_at_construction() -> None:
    with pytest.raises(ScenarioRuntimeError, match="simulation_only"):
        SimulationAction(
            action_id="bad.effect",
            simulation_id="game:test",
            capability="move",
            operation="advance",
            parameters={},
            effect_scope="real_world",
        )


def test_action_requires_explicit_simulation_capability() -> None:
    rt = ScenarioRuntime(
        simulation_id="game:test",
        authority=authority("move"),
        budget=budget(),
        rules=rules(),
    )

    def expand(state, node):
        return (
            transition(
                "forbidden.interact",
                1,
                capability="interact",
            ),
        )

    with pytest.raises(ScenarioRuntimeError, match="not authorized"):
        rt.explore({"position": 0}, expand)


def test_action_from_another_simulation_fails_closed() -> None:
    rt = runtime()

    def expand(state, node):
        return (
            ScenarioTransition(
                action=action(
                    "cross.simulation",
                    simulation_id="game:other",
                ),
                next_state={"position": 1},
                local_uncertainty=0.1,
            ),
        )

    with pytest.raises(ScenarioRuntimeError, match="simulation identity mismatch"):
        rt.explore({"position": 0}, expand)


def test_branch_limit_fails_before_tree_publication() -> None:
    rt = runtime(max_branches_per_node=2)

    def expand(state, node):
        return (
            transition("a", 1),
            transition("b", 2),
            transition("c", 3),
        )

    with pytest.raises(ScenarioRuntimeError, match="branching exceeds"):
        rt.explore({"position": 0}, expand)


def test_node_budget_fails_closed_instead_of_truncating_hidden_work() -> None:
    rt = runtime(max_nodes=2, max_branches_per_node=3)

    def expand(state, node):
        if node.depth:
            return ()
        return (
            transition("a", 1),
            transition("b", 2),
        )

    with pytest.raises(ScenarioRuntimeError, match="node count exceeds"):
        rt.explore({"position": 0}, expand)


def test_action_budget_fails_closed() -> None:
    rt = runtime(max_total_actions=1)

    def expand(state, node):
        if node.depth:
            return ()
        return (
            transition("a", 1),
            transition("b", 2),
        )

    with pytest.raises(ScenarioRuntimeError, match="action count exceeds"):
        rt.explore({"position": 0}, expand)


def test_cost_budget_fails_closed() -> None:
    rt = runtime(max_cost_units=3)

    def expand(state, node):
        if node.depth:
            return ()
        return (
            transition("a", 1, cost_units=2),
            transition("b", 2, cost_units=2),
        )

    with pytest.raises(ScenarioRuntimeError, match="cost exceeds"):
        rt.explore({"position": 0}, expand)


def test_depth_limit_is_explicit_in_result_instead_of_infinite_rollout() -> None:
    rt = runtime(max_depth=2)

    def expand(state, node):
        position = int(state["position"])
        return (transition(f"move.{node.depth}", position + 1),)

    tree = rt.explore({"position": 0}, expand)
    leaves = node_by_depth(tree, 2)

    assert len(leaves) == 1
    assert leaves[0].stop_reason is ScenarioStopReason.DEPTH_LIMIT
    assert tree.usage.max_depth_reached == 2
    assert tree.usage.actions == 2


def test_terminal_node_is_never_expanded() -> None:
    calls: list[int] = []

    def expand(state, node):
        calls.append(node.depth)
        return (
            transition(
                "finish",
                1,
                terminal=True,
            ),
        )

    tree = runtime().explore({"position": 0}, expand)

    assert calls == [0]
    leaf = node_by_depth(tree, 1)[0]
    assert leaf.terminal is True
    assert leaf.stop_reason is ScenarioStopReason.TERMINAL


def test_empty_frontier_is_recorded_as_no_actions() -> None:
    tree = runtime().explore({"position": 0}, lambda state, node: ())
    root = tree.nodes[0]

    assert tree.usage.nodes == 1
    assert tree.usage.actions == 0
    assert root.stop_reason is ScenarioStopReason.NO_ACTIONS


def test_uncertainty_propagates_monotonically_per_path() -> None:
    def expand(state, node):
        if node.depth == 0:
            return (transition("first", 1, uncertainty=0.20),)
        if node.depth == 1:
            return (transition("second", 2, uncertainty=0.25),)
        return ()

    tree = runtime().explore(
        {"position": 0},
        expand,
        initial_uncertainty=0.10,
    )
    ordered = sorted(tree.nodes, key=lambda item: item.depth)

    assert ordered[0].cumulative_uncertainty == pytest.approx(0.10)
    assert ordered[1].cumulative_uncertainty == pytest.approx(0.28)
    assert ordered[2].cumulative_uncertainty == pytest.approx(0.46)
    assert all(
        right.cumulative_uncertainty >= left.cumulative_uncertainty
        for left, right in zip(ordered, ordered[1:])
    )


def test_cost_and_action_counts_are_monotonic_per_path() -> None:
    def expand(state, node):
        if node.depth == 0:
            return (transition("first", 1, cost_units=2),)
        if node.depth == 1:
            return (transition("second", 2, cost_units=3),)
        return ()

    tree = runtime().explore({"position": 0}, expand)
    ordered = sorted(tree.nodes, key=lambda item: item.depth)

    assert [node.cumulative_cost_units for node in ordered] == [0, 2, 5]
    assert [node.action_count for node in ordered] == [0, 1, 2]
    assert tree.usage.cost_units == 5


def test_duplicate_action_id_under_parent_is_rejected() -> None:
    def expand(state, node):
        return (
            transition("duplicate", 1),
            transition("duplicate", 2),
        )

    with pytest.raises(ScenarioRuntimeError, match="duplicate action_id"):
        runtime().explore({"position": 0}, expand)


def test_non_json_state_fails_before_expansion() -> None:
    with pytest.raises(ScenarioRuntimeError, match="deterministic JSON"):
        runtime().explore({"bad": object()}, lambda state, node: ())


def test_non_json_action_parameters_fail_at_construction() -> None:
    with pytest.raises(ScenarioRuntimeError, match="deterministic JSON"):
        action("bad.parameters", parameters={"bad": object()})


def test_non_finite_uncertainty_is_rejected() -> None:
    with pytest.raises(ScenarioRuntimeError, match="finite"):
        ScenarioTransition(
            action=action("bad.uncertainty"),
            next_state={"position": 1},
            local_uncertainty=float("nan"),
        )


def test_non_finite_reward_is_rejected() -> None:
    with pytest.raises(ScenarioRuntimeError, match="finite"):
        ScenarioTransition(
            action=action("bad.reward"),
            next_state={"position": 1},
            local_uncertainty=0.1,
            reward=float("inf"),
        )


def test_expander_must_return_finite_sequence() -> None:
    def generator_expander(state, node):
        return (transition(str(index), index) for index in range(2))

    with pytest.raises(ScenarioRuntimeError, match="finite sequence"):
        runtime().explore({"position": 0}, generator_expander)


def test_expander_exception_does_not_return_partial_tree() -> None:
    class DeliberateFailure(RuntimeError):
        pass

    def expand(state, node):
        if node.depth == 0:
            return (transition("first", 1),)
        raise DeliberateFailure("boom")

    with pytest.raises(DeliberateFailure, match="boom"):
        runtime().explore({"position": 0}, expand)


def test_tree_remains_simulation_evidence_even_on_high_reward_terminal_success() -> None:
    def expand(state, node):
        return (
            transition(
                "win",
                999,
                reward=1_000_000.0,
                terminal=True,
            ),
        )

    tree = runtime().explore({"position": 0}, expand)

    assert tree.evidence_class == "simulation"
    assert tree.can_support_real_world_fact is False
    assert tree.can_satisfy_real_postcondition is False
    with pytest.raises(ScenarioRuntimeError, match="real-world postcondition"):
        tree.require_real_world_postcondition_authority()


def test_runtime_verify_rejects_authority_substitution() -> None:
    tree = runtime().explore({"position": 0}, lambda state, node: ())
    forged = replace(tree, authority_digest="0" * 64)

    with pytest.raises(ScenarioRuntimeError, match="authority identity mismatch"):
        runtime().verify(forged)


def test_runtime_verify_rejects_budget_substitution() -> None:
    rt = runtime()
    tree = rt.explore({"position": 0}, lambda state, node: ())
    forged = replace(tree, budget_digest="1" * 64)

    with pytest.raises(ScenarioRuntimeError, match="budget identity mismatch"):
        rt.verify(forged)


def test_tree_constructor_rejects_unreachable_nodes() -> None:
    rt = runtime()
    tree = rt.explore({"position": 0}, lambda state, node: ())
    root = tree.nodes[0]
    orphan = ScenarioNode(
        node_id="node-orphan",
        parent_id="node-missing",
        depth=1,
        state_digest=root.state_digest,
        cumulative_uncertainty=0.0,
        cumulative_cost_units=0,
        action_count=1,
        terminal=False,
        stop_reason=None,
    )

    with pytest.raises(ScenarioRuntimeError, match="unreachable nodes"):
        replace(
            tree,
            nodes=tree.nodes + (orphan,),
            usage=ScenarioResourceUsage(
                nodes=2,
                actions=0,
                cost_units=0,
                max_depth_reached=1,
            ),
        )


def test_tree_constructor_rejects_usage_drift() -> None:
    tree = runtime().explore({"position": 0}, lambda state, node: ())

    with pytest.raises(ScenarioRuntimeError, match="usage.nodes"):
        replace(
            tree,
            usage=ScenarioResourceUsage(
                nodes=2,
                actions=0,
                cost_units=0,
                max_depth_reached=0,
            ),
        )


def test_budget_identity_changes_when_any_limit_changes() -> None:
    base = budget()
    changed = budget(max_cost_units=base.max_cost_units + 1)
    assert base.digest != changed.digest


def test_authority_identity_is_canonical_across_capability_order() -> None:
    first = SimulationAuthority(
        authority_id="authority:test",
        simulation_id="game:test",
        allowed_capabilities=("wait", "move"),
    )
    second = SimulationAuthority(
        authority_id="authority:test",
        simulation_id="game:test",
        allowed_capabilities=("move", "wait"),
    )

    assert first == second
    assert first.digest == second.digest


def test_canonical_and_ai_scenario_runtime_are_byte_identical() -> None:
    canonical = ROOT / "skeleton/simulation/scenario_runtime.py"
    mirror = ROOT / "skeleton/ai/simulation/scenario_runtime.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_tree_constructor_rejects_cost_usage_underreporting() -> None:
    def expand(state, node):
        if node.depth:
            return ()
        return (transition("costly", 1, cost_units=4),)

    tree = runtime().explore({"position": 0}, expand)
    with pytest.raises(ScenarioRuntimeError, match="usage.cost_units"):
        replace(
            tree,
            usage=ScenarioResourceUsage(
                nodes=tree.usage.nodes,
                actions=tree.usage.actions,
                cost_units=0,
                max_depth_reached=tree.usage.max_depth_reached,
            ),
        )


def test_runtime_verify_rejects_child_cost_chain_tampering() -> None:
    def expand(state, node):
        if node.depth:
            return ()
        return (transition("costly", 1, cost_units=4),)

    rt = runtime()
    tree = rt.explore({"position": 0}, expand)
    child = next(node for node in tree.nodes if node.parent_id is not None)
    forged_child = replace(child, cumulative_cost_units=child.cumulative_cost_units + 1)
    forged_nodes = tuple(
        forged_child if node.node_id == child.node_id else node for node in tree.nodes
    )
    forged = replace(tree, nodes=forged_nodes)
    with pytest.raises(ScenarioRuntimeError, match="cumulative cost"):
        rt.verify(forged)


def test_rule_set_is_canonical_and_content_bound() -> None:
    left = SimulationRule(
        rule_id="a-rule",
        description="First deterministic rule.",
        parameters={"value": 1},
    )
    right = SimulationRule(
        rule_id="b-rule",
        description="Second deterministic rule.",
        parameters={"value": 2},
    )
    first = SimulationRuleSet((right, left))
    second = SimulationRuleSet((left, right))

    assert first.rules == second.rules
    assert first.digest == second.digest


def test_duplicate_rule_identity_fails_closed() -> None:
    first = SimulationRule(
        rule_id="same-rule",
        description="First rule.",
        parameters={"value": 1},
    )
    second = SimulationRule(
        rule_id="same-rule",
        description="Conflicting rule.",
        parameters={"value": 2},
    )

    with pytest.raises(ScenarioRuntimeError, match="duplicate simulation rule_id"):
        SimulationRuleSet((first, second))


def test_rule_parameters_must_be_deterministic_json() -> None:
    with pytest.raises(ScenarioRuntimeError, match="deterministic JSON"):
        SimulationRule(
            rule_id="bad-rule",
            description="Invalid rule payload.",
            parameters={"value": object()},
        )


def test_tree_identity_binds_exact_rule_set() -> None:
    rt = runtime()
    tree = rt.explore({"position": 0}, lambda state, node: ())
    assert tree.rule_set_digest == rt.rules.digest

    altered_rules = SimulationRuleSet(
        (
            SimulationRule(
                rule_id="movement",
                description="Movement changes the simulated position only.",
                parameters={"max_delta": 2},
            ),
        )
    )
    altered_runtime = ScenarioRuntime(
        simulation_id="game:test",
        authority=authority(),
        budget=budget(),
        rules=altered_rules,
    )
    with pytest.raises(ScenarioRuntimeError, match="rule-set identity mismatch"):
        altered_runtime.verify(tree)


def test_root_identity_changes_when_rule_contract_changes() -> None:
    first = runtime()
    second = ScenarioRuntime(
        simulation_id="game:test",
        authority=authority(),
        budget=budget(),
        rules=SimulationRuleSet(
            (
                SimulationRule(
                    rule_id="movement",
                    description="Movement changes the simulated position only.",
                    parameters={"max_delta": 9},
                ),
            )
        ),
    )
    first_tree = first.explore({"position": 0}, lambda state, node: ())
    second_tree = second.explore({"position": 0}, lambda state, node: ())

    assert first_tree.root_id != second_tree.root_id
    assert first_tree.digest != second_tree.digest


def test_action_payload_is_deeply_immutable_and_detached_from_caller() -> None:
    source = {"path": {"x": 1}, "items": [1, 2]}
    candidate = action("immutable.action", parameters=source)
    original_digest = candidate.digest

    source["path"]["x"] = 99
    source["items"].append(3)

    assert candidate.digest == original_digest
    assert candidate.parameters["path"]["x"] == 1
    assert candidate.parameters["items"] == (1, 2)
    with pytest.raises(TypeError):
        candidate.parameters["new"] = 1
    with pytest.raises(TypeError):
        candidate.parameters["path"]["x"] = 2


def test_rule_payload_is_deeply_immutable() -> None:
    source = {"limits": {"speed": 3}, "modes": ["walk", "run"]}
    rule = SimulationRule(
        rule_id="immutable-rule",
        description="Immutable nested rule content.",
        parameters=source,
    )
    original_digest = rule.digest

    source["limits"]["speed"] = 999
    source["modes"].append("teleport")

    assert rule.digest == original_digest
    assert rule.parameters["limits"]["speed"] == 3
    assert rule.parameters["modes"] == ("walk", "run")

def test_runtime_verify_rejects_underreported_uncertainty_chain():
    def expand(state, node):
        if node.depth:
            return ()
        return (transition("uncertain", 1, uncertainty=0.9),)

    rt = runtime()
    tree = rt.explore({"position": 0}, expand, initial_uncertainty=0.1)
    child = next(node for node in tree.nodes if node.parent_id is not None)
    forged_child = replace(
        child,
        cumulative_uncertainty=0.1,
    )
    forged = replace(
        tree,
        nodes=tuple(
            forged_child if node.node_id == child.node_id else node
            for node in tree.nodes
        ),
    )
    with pytest.raises(
        ScenarioRuntimeError,
        match="cumulative uncertainty does not match edge uncertainty",
    ):
        rt.verify(forged)
