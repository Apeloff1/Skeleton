"""Actual-cost route planning and stale itinerary protection."""
from __future__ import annotations

from dataclasses import asdict
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_tenfold_compiler import tenfold_for
from skeleton.game.generation.original_world_tenfold_runtime import (
    TenfoldAction, create_tenfold, step_tenfold, passages,
)
from skeleton.game.generation.original_world_tenfold_navigation import (
    MODES, plan_tenfold_route, execute_tenfold_route,
)
from skeleton.game.generation.original_world_tenfold_cli import main


def world(space: str):
    return create_tenfold(tenfold_for(0, "puzzle", space, "sandbox").index)


@pytest.mark.parametrize("space", [
    "lattice", "spiral", "labyrinth", "archipelago", "strata",
    "canopy", "orbit", "pocket", "phase", "abyss",
])
def test_all_ten_worlds_plan_real_affordable_nearby_paths(space) -> None:
    s = world(space)
    target = passages(s)[0]
    for priority in MODES:
        itinerary = plan_tenfold_route(s, target, priority=priority)
        assert itinerary.nodes[0] == s.position
        assert itinerary.nodes[-1] == target
        assert itinerary.moves == 1
        assert itinerary.can_finish_this_turn
        assert itinerary.energy > 0
        after, receipts = execute_tenfold_route(s, itinerary)
        assert after.position == target
        assert after.events == 1
        assert receipts == (after.event_head,)
        assert s.position == 0
        assert after.fuel == s.fuel - itinerary.fuel
        assert after.oxygen == s.oxygen - itinerary.oxygen
        assert after.game.causal.energy == s.game.causal.energy - itinerary.energy


def test_ferry_graph_rejects_unfunded_cross_island_route() -> None:
    s = world("archipelago")
    with pytest.raises(FoundationError):
        plan_tenfold_route(s, 6)
    repaired, _ = step_tenfold(s, TenfoldAction("spatial", "ferry"))
    plan = plan_tenfold_route(repaired, 6)
    assert plan.nodes[0] == 0 and plan.nodes[-1] == 6
    assert plan.fuel == 2
    assert plan.moves == 2
    arrived, receipts = execute_tenfold_route(repaired, plan)
    assert arrived.position == 6
    assert arrived.fuel == repaired.fuel - 2
    assert len(receipts) == 2


def test_pocket_requires_consent_and_oxygen_before_route_exists() -> None:
    s = world("pocket")
    with pytest.raises(FoundationError):
        plan_tenfold_route(s, 12)
    prepared, _ = step_tenfold(s, TenfoldAction("spatial", "attune"))
    plan = plan_tenfold_route(prepared, 12)
    assert plan.oxygen == 1
    arrived, _ = execute_tenfold_route(prepared, plan)
    assert arrived.position == 12
    assert arrived.oxygen == prepared.oxygen - 1


def test_plan_refuses_stale_topology_after_world_tick_or_new_action() -> None:
    s = world("phase")
    p = plan_tenfold_route(s, 1)
    advanced, _ = step_tenfold(s, TenfoldAction("causal", "end_turn"))
    with pytest.raises(FoundationError):
        execute_tenfold_route(advanced, p)
    changed, _ = step_tenfold(s, TenfoldAction("spatial", "stabilize"))
    with pytest.raises(FoundationError):
        execute_tenfold_route(changed, p)


def test_multi_turn_routes_dont_partially_modify_player_state() -> None:
    s = world("spiral")
    plan = plan_tenfold_route(s, 6)
    assert plan.moves == 6
    assert not plan.can_finish_this_turn
    before = asdict(s)
    with pytest.raises(FoundationError):
        execute_tenfold_route(s, plan)
    assert asdict(s) == before


def test_route_to_present_node_requires_no_energy_and_no_event() -> None:
    s = world("abyss")
    plan = plan_tenfold_route(s, 0)
    assert plan.nodes == (0,)
    assert plan.energy == plan.oxygen == plan.fuel == plan.moves == 0
    after, receipts = execute_tenfold_route(s, plan)
    assert after == s
    assert not receipts


@pytest.mark.parametrize("bad", [
    True, 24, -1, 1.5, "3",
])
def test_invalid_destination_rejected(bad) -> None:
    with pytest.raises(FoundationError):
        plan_tenfold_route(world("lattice"), bad)


def test_cli_can_quote_and_execute_preflighted_route(capsys) -> None:
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--arc", "sandbox", "--route-target", "1", "--execute-route",
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["planned_route"]["nodes"] == [0, 1]
    assert packet["state"]["space"]["position"] == 1
    assert len(packet["executed_route_event_ids"]) == 1


def test_cli_refuses_route_outside_action_budget_without_partial_game_save(capsys) -> None:
    with pytest.raises(SystemExit):
        main([
            "--base", "0", "--form", "puzzle", "--architecture", "spiral",
            "--arc", "sandbox", "--route-target", "6", "--execute-route",
        ])
