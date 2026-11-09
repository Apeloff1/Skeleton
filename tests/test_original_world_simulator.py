"""Tests for the actually implemented abstract original-world rule kernels."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from skeleton.game.generation.original_mechanic_catalog import MECHANICS
from skeleton.game.generation.original_world_simulator import (
    EXECUTABLE_RULE_IDS, WorldRuleAction, WorldRuleError, WorldRuleState,
    advance_tick, apply_rule, replay_rules, route_edges,
)


def test_all_sample_kernels_map_to_specified_authored_mechanics() -> None:
    assert len(EXECUTABLE_RULE_IDS) == 8
    assert all(rule in MECHANICS for rule in EXECUTABLE_RULE_IDS)
    assert all(MECHANICS[rule].cost_specified for rule in EXECUTABLE_RULE_IDS)


def test_future_collateral_has_real_next_tick_debt() -> None:
    state, receipt = apply_rule(WorldRuleState(),
                                WorldRuleAction("time-m01", amount=3))
    assert state.action_points == 4
    assert state.future_action_debt == 3
    assert len(receipt.event_digest) == 64
    state, _ = advance_tick(state)
    assert state.action_points == 0
    assert state.future_action_debt == 1
    state, _ = advance_tick(state)
    assert state.action_points == 1
    assert state.future_action_debt == 0
    state, _ = advance_tick(state)
    assert state.action_points == 2


def test_mutable_topology_preserves_all_rooms_and_replay() -> None:
    initial = WorldRuleState()
    result, receipt = apply_rule(
        initial, WorldRuleAction("topology-m02", mode="unobserved"),
        seed="moving-maze",
    )
    assert result.route_order[0] == "r0"
    assert result.route_order != initial.route_order
    assert set(result.route_order) == set(initial.route_order)
    assert len(route_edges(result)) == 5
    assert len(set(vertex for edge in route_edges(result) for vertex in edge)) == 5
    repeat, other = apply_rule(
        initial, WorldRuleAction("topology-m02", mode="unobserved"),
        seed="moving-maze",
    )
    assert result == repeat and receipt == other


def test_last_train_rewires_actual_graph() -> None:
    state, receipt = apply_rule(
        WorldRuleState(), WorldRuleAction("infrastructure-m01", mode="last_train")
    )
    assert state.route_order != WorldRuleState().route_order
    assert state.event_head == receipt.event_digest


def test_rain_herding_conserves_total_precipitation() -> None:
    old = WorldRuleState()
    result, _ = apply_rule(old, WorldRuleAction(
        "ecology-m02", amount=3, mode="west-to-east"
    ))
    assert result.rainfall == (2, 8)
    assert sum(result.rainfall) == sum(old.rainfall)
    reverse, _ = apply_rule(result, WorldRuleAction(
        "ecology-m02", amount=2, mode="east-to-west"
    ))
    assert reverse.rainfall == (4, 6)
    with pytest.raises(WorldRuleError):
        apply_rule(old, WorldRuleAction(
            "ecology-m02", amount=2, mode="nowhere"
        ))


def test_rest_cannot_overheal_and_costs_action() -> None:
    state, _ = apply_rule(
        WorldRuleState(energy=9), WorldRuleAction("serenity-m01", amount=3)
    )
    assert state.energy == 10
    assert state.action_points == 1
    assert state.tick == 0


def test_gather_repair_and_shadow_momentum_are_bound() -> None:
    initial = WorldRuleState()
    food, _ = apply_rule(initial, WorldRuleAction("survival-m01", amount=3))
    assert food.food == 3 and food.wild_food == 7
    shelter, _ = apply_rule(food, WorldRuleAction("crafting-m04"))
    assert shelter.wood == 2
    assert shelter.shelter_durability == 6
    assert shelter.energy == 5
    tick, _ = advance_tick(shelter)
    shadow, _ = apply_rule(tick, WorldRuleAction(
        "physics-m02", amount=2, mode="left"
    ))
    assert shadow.shadow_momentum == -2
    assert shadow.energy == 4
    assert initial == WorldRuleState()


def test_executable_rules_replay_same_identity_and_digest() -> None:
    actions = (
        WorldRuleAction("time-m01", amount=2),
        WorldRuleAction("topology-m02", mode="unobserved"),
        WorldRuleAction("ecology-m02", amount=1, mode="west-to-east"),
        WorldRuleAction("world.tick"),
        WorldRuleAction("world.tick"),
        WorldRuleAction("serenity-m01", amount=2),
        WorldRuleAction("survival-m01", amount=1),
        WorldRuleAction("world.tick"),
        WorldRuleAction("crafting-m04"),
        WorldRuleAction("physics-m02", amount=1, mode="right"),
        WorldRuleAction("world.tick"),
        WorldRuleAction("infrastructure-m01", mode="last_train"),
    )
    first, events = replay_rules(actions, seed="same-seed")
    second, again = replay_rules(actions, seed="same-seed")
    assert first == second
    assert events == again
    assert first.event_count == len(actions)
    assert events[0].prior_state_digest != events[0].next_state_digest
    assert events[-1].event_digest == first.event_head
    assert all(event.rule_status == "simulated-abstract" for event in events)


@pytest.mark.parametrize("action", [
    WorldRuleAction("law-m01"),
    WorldRuleAction("serenity-m01", amount=0),
    WorldRuleAction("serenity-m01", amount=4),
    WorldRuleAction("serenity-m01", amount=True),
    WorldRuleAction("topology-m02"),
    WorldRuleAction("infrastructure-m01"),
    WorldRuleAction("ecology-m02"),
    WorldRuleAction("survival-m01", amount=3, mode="secret"),
    WorldRuleAction("physics-m02", mode="diagonal"),
])
def test_unsupported_or_invalid_actions_fail_closed(action: WorldRuleAction) -> None:
    start = WorldRuleState()
    before = asdict(start)
    with pytest.raises(WorldRuleError):
        apply_rule(start, action)
    assert asdict(start) == before


def test_resource_depletion_and_debt_ceiling() -> None:
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(wild_food=0),
                   WorldRuleAction("survival-m01"))
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(future_action_debt=12),
                   WorldRuleAction("time-m01"))
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(wood=0),
                   WorldRuleAction("crafting-m04"))
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(action_points=0),
                   WorldRuleAction("serenity-m01"))


def test_untrusted_state_and_replays_are_rejected() -> None:
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(rainfall=(9, 9)),
                   WorldRuleAction("serenity-m01"))
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(route_order=("r0",) * 5),
                   WorldRuleAction("serenity-m01"))
    with pytest.raises(WorldRuleError):
        apply_rule(WorldRuleState(event_head="0" * 63 + "g"),
                   WorldRuleAction("serenity-m01"))
    with pytest.raises(WorldRuleError):
        replay_rules((WorldRuleAction("world.tick"),) * 4097)
    with pytest.raises(WorldRuleError):
        replay_rules([WorldRuleAction("serenity-m01")])
    with pytest.raises(WorldRuleError):
        replay_rules((WorldRuleAction("world.tick"),), seed="")
    with pytest.raises(WorldRuleError):
        replay_rules((WorldRuleAction("world.tick"), "invalid"))
