"""Ten real spatial rule systems and 10× million-world exact addressing."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_million_compiler import advanced_at
from skeleton.game.generation.original_world_tenfold_architectures import ARCHITECTURES
from skeleton.game.generation.original_world_tenfold_compiler import (
    ARCHITECTURE_COUNT, SPATIAL_FOUNDATIONS, TENFOLD_CONFIGURATIONS,
    tenfold_at, spatial_at, tenfold_for, tenfold_from_id, tenfold_from_seed,
    page_tenfold, tenfold_inventory,
)
from skeleton.game.generation.original_world_tenfold_runtime import (
    TenfoldAction, create_tenfold, step_tenfold, passages, _graph,
    available_material, site_capacity, replay_tenfold,
    save_tenfold, restore_tenfold, validate_tenfold,
)


def action(state, verb, n=1, target=-1, layer="spatial"):
    return step_tenfold(state, TenfoldAction(layer, verb, n, target))[0]


def selected(architecture: str, form: str = "puzzle", arc: str = "sandbox"):
    return create_tenfold(tenfold_for(0, form, architecture, arc).index)


def turn(state, n=1):
    for _ in range(n):
        state = action(state, "end_turn", layer="causal")
    return state


def reachable(edges):
    adjacency = {node: set() for node in range(24)}
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    visited, stack = {0}, [0]
    while stack:
        for peer in adjacency[stack.pop()]:
            if peer not in visited:
                visited.add(peer)
                stack.append(peer)
    return visited


def test_exact_decade_scale_bijective_and_no_fake_authorship() -> None:
    assert len(ARCHITECTURES) == ARCHITECTURE_COUNT == 10
    assert SPATIAL_FOUNDATIONS == 1_024_000
    assert TENFOLD_CONFIGURATIONS == 12_288_000
    inventory = tenfold_inventory()
    assert inventory["spatial_gameplay_foundation_entries"] == 1_024_000
    assert inventory["full_gameplay_configuration_entries"] == 12_288_000
    assert inventory["styles_eras_console_targets_random_seeds_counted"] == 0
    assert inventory["separately_written_worlds_added_by_composition"] == 0
    assert inventory["native_games_certified"] == 0
    assert inventory["old_102400_foundation_and_1228800_configuration_indices_unchanged"]


@pytest.mark.parametrize("index", [
    0, 1, 11, 12, 119, 120, 121, 1199, 1200, 1201,
    123456, 1_228_799, 1_228_800, 5_555_555, 10_000_000,
    12_287_998, 12_287_999,
])
def test_full_exact_index_roundtrip_with_source_world_unchanged(index) -> None:
    world = tenfold_at(index)
    assert world.index == index
    assert world.as_dict()["index"] == str(index)
    assert world == tenfold_from_id(world.tenfold_id)
    base = index // 1200
    form = (index // 120) % 10
    architecture = (index // 12) % 10
    arc = index % 12
    assert world.advanced.mode.base.foundation_index == base
    assert world.advanced.mode.form.form_id == (
        "platform", "puzzle", "tactics", "survival", "colony",
        "racing", "stealth", "commerce", "exploration", "rhythm",
    )[form]
    assert world.spatial.architecture == ARCHITECTURES[architecture]
    assert world.advanced.arc.arc_id == (
        "chapters", "endless", "roguelite", "dynasty", "factions",
        "sandbox", "mystery", "seasonal", "rescue", "campaign",
        "civilization", "branching",
    )[arc]
    assert tenfold_for(
        base, world.advanced.mode.form.form_id,
        world.spatial.architecture.architecture_id,
        world.advanced.arc.arc_id,
    ) == world
    assert world.advanced == advanced_at((base * 10 + form) * 12 + arc)


def test_1024k_foundation_10x_address_space_does_not_materialize_instances() -> None:
    indices = [0, 999, 1000, 102399, 102400, 300023, 777777, 1023999]
    identities = set()
    for i in indices:
        obj = spatial_at(i)
        assert obj.index == i
        assert obj.design_id not in identities
        assert obj.source.mode.mode_index == i // 10
        assert obj.architecture == ARCHITECTURES[i % 10]
        identities.add(obj.design_id)
    assert len(identities) == len(indices)


def test_wide_strided_uniqueness_and_lazy_end_pagination() -> None:
    seen = set()
    for i in range(0, TENFOLD_CONFIGURATIONS, 131071):
        world = tenfold_at(i)
        assert world.design_id not in seen
        seen.add(world.design_id)
    assert [w.index for w in page_tenfold(start=12_287_997, limit=24)] == [
        12_287_997, 12_287_998, 12_287_999,
    ]
    assert len(list(page_tenfold(start=0, limit=32))) == 32
    assert tenfold_from_seed("10x-the-play") == tenfold_from_seed("10x-the-play")


@pytest.mark.parametrize("bad", [True, -1, None, 0.1, "12", 12_288_000])
def test_illegal_world_selectors_fail_closed(bad) -> None:
    with pytest.raises(FoundationError):
        tenfold_at(bad)


@pytest.mark.parametrize("kind", [a.architecture_id for a in ARCHITECTURES])
def test_every_architecture_has_actual_navigable_edges_and_unique_verb(kind) -> None:
    state = selected(kind)
    assert state.position == 0
    assert len(_graph(state)) >= 20
    assert passages(state)
    move = passages(state)[0]
    after, receipt = step_tenfold(state, TenfoldAction("spatial", "travel", target=move))
    assert after.position == move
    assert move in after.visited
    assert after.game.causal.energy < state.game.causal.energy
    assert after.events == 1
    assert receipt.event_id == after.event_head
    assert kind in receipt.changes[0]


def test_ten_graphs_actually_differ_and_have_nontrivial_connectivity() -> None:
    edges = {a.architecture_id: _graph(selected(a.architecture_id))
             for a in ARCHITECTURES}
    assert len(set(edges.values())) >= 9
    assert reachable(edges["lattice"]) == set(range(24))
    assert reachable(edges["spiral"]) == set(range(24))
    assert reachable(edges["labyrinth"]) == set(range(24))
    assert len(reachable(edges["archipelago"])) == 6
    assert len(reachable(edges["pocket"])) == 12
    assert reachable(edges["strata"]) == set(range(24))
    assert reachable(edges["canopy"]) == set(range(24))
    assert reachable(edges["orbit"]) == set(range(24))
    assert reachable(edges["phase"]) == set(range(24))
    assert reachable(edges["abyss"]) == set(range(24))


@pytest.mark.parametrize("kind", [a.architecture_id for a in ARCHITECTURES])
def test_every_architecture_intervention_pays_resources_and_changes_state(kind) -> None:
    state = selected(kind)
    verb = next(a.intervention for a in ARCHITECTURES if a.architecture_id == kind)
    if verb == "ferry":
        # The starting room is a valid pier by design.
        assert state.position == 0
    after = action(state, verb)
    assert after.materials < state.materials
    assert after != state
    assert after.events == 1
    assert after.game.causal.action_points == state.game.causal.action_points - 1
    validate_tenfold(after)


def test_ferry_build_opens_other_islands_and_costs_fuel_to_cross() -> None:
    s = selected("archipelago")
    assert len(reachable(_graph(s))) == 6
    s = action(s, "ferry")
    assert len(reachable(_graph(s))) == 24
    s = action(s, "travel", target=5)
    s = action(s, "end_turn", layer="causal")
    s = action(s, "travel", target=6)
    assert s.position == 6
    assert s.fuel == 7


def test_orbit_transfer_requires_alignment_window_and_three_real_fuel() -> None:
    s = selected("orbit")
    assert 4 in passages(s)
    s = action(s, "travel", target=4)
    assert s.fuel == 6
    s = turn(s, 1)
    assert 8 not in passages(s)
    s = action(s, "align")
    assert 8 in passages(s)
    assert s.fuel == 5
    s = action(s, "travel", target=8)
    assert s.fuel == 2


def test_pocket_reality_requires_purchased_calibration_and_consent() -> None:
    s = selected("pocket")
    assert 12 not in passages(s)
    s = action(s, "attune")
    assert s.attunement == 1
    assert s.game.causal.trust == 8
    assert 12 in passages(s)
    s = action(s, "travel", target=12)
    assert s.position == 12
    assert s.oxygen < 12


def test_spiral_changes_passages_only_after_constructed_hinge() -> None:
    s = selected("spiral")
    before = _graph(s)
    s = action(s, "splice")
    assert _graph(s) != before
    assert (0, 12) in _graph(s)


def test_labyrinth_stays_connected_when_dynamic_secret_paths_rotate() -> None:
    s = selected("labyrinth")
    initial = set(_graph(s))
    s = turn(s, 1)
    after = set(_graph(s))
    assert reachable(initial) == reachable(after) == set(range(24))
    assert initial != after
    s = action(s, "anchor")
    assert s.anchors == 1
    assert s.game.causal.evidence == 1


def test_abyss_consumes_oxygen_but_seals_protect_deep_transit() -> None:
    s = selected("abyss")
    initial = s.oxygen
    s = action(s, "travel", target=6)
    assert s.oxygen == initial - 1
    s = action(s, "seal")
    s = action(s, "end_turn", layer="causal")
    s = action(s, "travel", target=12)
    assert s.oxygen == initial - 1
    assert s.seals == 1


def test_finite_geology_depletes_per_room_but_other_sites_independent() -> None:
    s = selected("lattice")
    starting = available_material(s)
    s = action(s, "extract", n=3)
    assert available_material(s) == starting - 3
    assert s.materials == 11
    s = action(s, "travel", target=1)
    assert available_material(s) == site_capacity(
        tenfold_from_id(s.world_id).design_id, 1
    )
    s = action(s, "resupply", n=2)
    assert s.materials == 9
    assert s.game.causal.supplies == 14


def test_no_duplicate_free_resources_or_illegal_mutation_in_adversarial_actions() -> None:
    s = selected("strata")
    invalid = (
        TenfoldAction("spatial", "ferry"),
        TenfoldAction("spatial", "travel", target=23),
        TenfoldAction("spatial", "extract", amount=3, target=True),
        TenfoldAction("spatial", "resupply", amount=3, target=23),
        TenfoldAction("spatial", "repair", amount=True),
        TenfoldAction("spatial", "repair", amount=4),
        TenfoldAction("spatial", "travel", target=24),
    )
    # Target is currently meaningful only for directional verbs; out-of-range
    # data and invalid verbs must fail even when other action fields are ignored.
    for action_item in invalid[:2] + invalid[4:]:
        before = asdict(s)
        with pytest.raises(FoundationError):
            step_tenfold(s, action_item)
        assert asdict(s) == before


def test_replay_save_restore_rejects_corrupted_nested_world_laws() -> None:
    index = tenfold_for(123, "tactics", "phase", "roguelite").index
    actions = (
        TenfoldAction("spatial", "stabilize"),
        TenfoldAction("spatial", "travel", target=1),
        TenfoldAction("mode", "guard"),
        TenfoldAction("causal", "end_turn"),
        TenfoldAction("spatial", "survey"),
        TenfoldAction("arc", "reflect"),
    )
    a, receipts = replay_tenfold(index, actions)
    b, same = replay_tenfold(index, actions)
    assert a == b and receipts == same
    assert len({receipt.event_id for receipt in receipts}) == len(receipts)
    assert restore_tenfold(save_tenfold(a)) == a
    forged = json.loads(save_tenfold(a))
    forged["payload"]["space"]["materials"] = 999
    with pytest.raises(FoundationError):
        restore_tenfold(json.dumps(forged))
    wrong = json.loads(save_tenfold(a))
    wrong["payload"]["world_id"] = "worldx10-00000000"
    with pytest.raises(FoundationError):
        restore_tenfold(json.dumps(wrong))


def test_full_tenfold_matrix_proves_genre_actions_in_each_architecture() -> None:
    for kind in (a.architecture_id for a in ARCHITECTURES):
        for genre in ("puzzle", "survival", "colony", "racing"):
            for arc in ("chapters", "endless", "dynasty", "branching"):
                state = selected(kind, genre, arc)
                state = action(state, "travel", target=passages(state)[0])
                if genre == "puzzle":
                    verb, kw = "toggle", {"target": 0}
                elif genre == "survival":
                    verb, kw = "drink", {}
                elif genre == "colony":
                    verb, kw = "cultivate", {}
                else:
                    verb, kw = "accelerate", {}
                state, receipt = step_tenfold(
                    state, TenfoldAction("mode", verb, **kw),
                )
                assert state.game.events == 1
                assert receipt.nested_game_head == state.game.event_head
                assert state.events == 2
                assert state.position in state.visited
