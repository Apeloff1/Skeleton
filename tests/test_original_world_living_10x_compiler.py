"""Twelve-million -> 122.88m: precise nested indexing and living actor rules."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_systems import (
    SYSTEMS, SYSTEM_BY_ID,
)
from skeleton.game.generation.original_world_living_10x_compiler import (
    LIVING_FOUNDATIONS, LIVING_CONFIGURATIONS, LIVING_SYSTEM_COUNT,
    living_at, living_foundation_at, living_for, living_from_id,
    living_from_seed, living_inventory, page_living,
)
from skeleton.game.generation.original_world_living_10x_runtime import (
    LivingAction, create_living, step_living, replay_living,
    save_living, restore_living, validate_living,
)
from skeleton.game.generation.original_world_tenfold_compiler import tenfold_at

FORM_ACTIONS = {
    "platform": ("jump", -1),
    "puzzle": ("toggle", 0),
    "tactics": ("guard", -1),
    "survival": ("scavenge", -1),
    "colony": ("construct", -1),
    "racing": ("accelerate", -1),
    "stealth": ("sneak", -1),
    "commerce": ("buy", -1),
    "exploration": ("explore", -1),
    "rhythm": ("tap", 0),
}


def choose(system, architecture="lattice", genre="puzzle", arc="sandbox"):
    return create_living(living_for(0, genre, architecture, system, arc).index)


def use(state, layer, verb, amount=1, target=-1):
    return step_living(state, LivingAction(layer, verb, amount, target))[0]


def turn(state, n=1):
    for _ in range(n):
        state = use(state, "causal", "end_turn")
    return state


def test_10x_index_count_excludes_cosmetics_and_individual_authorship_claims() -> None:
    assert len(SYSTEMS) == LIVING_SYSTEM_COUNT == 10
    assert len(SYSTEM_BY_ID) == 10
    assert LIVING_FOUNDATIONS == 10_240_000
    assert LIVING_CONFIGURATIONS == 122_880_000
    inventory = living_inventory()
    assert inventory["living_foundations"] == 10_240_000
    assert inventory["living_advanced_configurations"] == 122_880_000
    assert inventory["authored_living_player_interventions"] == 30
    assert inventory["authored_original_world_roots"] == 1424
    assert inventory["worlds_individually_handwritten_by_composition"] == 0
    assert inventory["certified_native_games"] == 0
    assert inventory["styles_hardware_seeds_eras_as_multipliers"] == 0
    assert inventory["formerly_assigned_indices_unchanged"]


def test_ten_living_laws_have_individual_authorial_interventions() -> None:
    assert len({x.title.casefold() for x in SYSTEMS}) == 10
    assert len({x.autonomous_process.casefold() for x in SYSTEMS}) == 10
    assert len({x.world_premise.casefold() for x in SYSTEMS}) == 10
    assert len({verb for x in SYSTEMS for verb in x.commands}) == 30
    assert all(len(x.commands) == 3 for x in SYSTEMS)
    assert all(x.scarce_resource and x.critical_failure for x in SYSTEMS)


@pytest.mark.parametrize("index", [
    0, 1, 11, 12, 119, 120, 121, 1199, 1200, 1201,
    100000, 1228799, 1228800, 12345678, 55777777,
    100000000, 122879997, 122879998, 122879999,
])
def test_exact_rank_unrank_preserves_source_world_and_bijection(index) -> None:
    entry = living_at(index)
    assert entry.index == index
    assert entry.world_id == f"livingworld-{index:09d}"
    assert living_from_id(entry.world_id) == entry
    base_spatial = index // 120
    system_i = (index // 12) % 10
    arc_i = index % 12
    assert entry.foundation.index == base_spatial * 10 + system_i
    assert entry.foundation.system == SYSTEMS[system_i]
    assert entry.source == tenfold_at(base_spatial * 12 + arc_i)
    assert living_for(
        entry.source.advanced.mode.base.foundation_index,
        entry.source.advanced.mode.form.form_id,
        entry.source.spatial.architecture.architecture_id,
        entry.foundation.system.system_id,
        entry.source.advanced.arc.arc_id,
    ) == entry
    data = entry.as_dict()
    data["foundation"]["system"] = "tampered"
    assert entry.foundation.system.system_id != "tampered"


def test_bounded_paging_and_sparse_sampling_do_not_allocate_all_122m_worlds() -> None:
    assert [x.index for x in page_living(start=122879997, limit=24)] == [
        122879997, 122879998, 122879999,
    ]
    assert len(list(page_living(start=0, limit=128))) == 128
    seen = set()
    for i in range(0, LIVING_CONFIGURATIONS, 127777):
        entry = living_at(i)
        assert entry.design_id not in seen
        seen.add(entry.design_id)
    assert len(seen) > 900
    assert living_from_seed("dragon-world-123") == living_from_seed("dragon-world-123")


@pytest.mark.parametrize("bad", [-1, 122880000, True, None, "4", 1.5])
def test_invalid_living_index_fails_closed(bad) -> None:
    with pytest.raises(FoundationError):
        living_at(bad)


def test_all_ten_world_actor_rules_have_real_player_intervention_and_clock() -> None:
    transitions = set()
    for law in SYSTEMS:
        s = choose(law.system_id)
        before = asdict(s.metrics)
        intervened, receipt = step_living(
            s, LivingAction("living", law.commands[0]),
        )
        assert intervened.events == 1
        assert intervened.event_head == receipt.event_hash
        assert intervened.spatial.game.causal.action_points == 3
        assert asdict(intervened.metrics) != before
        advanced, result = step_living(intervened, LivingAction("causal", "end_turn"))
        assert advanced.living_turns == 1
        assert advanced.spatial.tick == 1
        assert advanced.events == 2
        assert result.changes
        validate_living(advanced)
        footprint = tuple(sorted(
            (field, getattr(advanced.metrics, field))
            for field in advanced.metrics.__dataclass_fields__
            if getattr(advanced.metrics, field) != getattr(s.metrics, field)
        ))
        assert footprint
        transitions.add(footprint)
    assert len(transitions) == 10


def test_all_100_living_actor_to_spatial_architectures_retain_causal_play() -> None:
    from skeleton.game.generation.original_world_tenfold_architectures import ARCHITECTURES
    for system in SYSTEMS:
        for arch in ARCHITECTURES:
            world = choose(system.system_id, arch.architecture_id)
            after = use(world, "living", system.commands[0])
            after = use(after, "causal", "end_turn")
            assert after.events == 2
            assert after.living_turns == 1
            assert after.spatial.world_id == living_for(
                0, "puzzle", arch.architecture_id, system.system_id, "sandbox"
            ).source.tenfold_id


def test_all_120_genre_progression_pairs_support_nested_play_with_living_systems() -> None:
    from skeleton.game.generation.original_world_play_forms import PLAY_FORMS, PROGRESSION_LAWS
    for genre in PLAY_FORMS:
        for arc in PROGRESSION_LAWS:
            system = SYSTEMS[(len(genre.form_id) + len(arc.arc_id)) % 10]
            state = choose(system.system_id, genre=genre.form_id, arc=arc.arc_id)
            genre_verb, target = FORM_ACTIONS[genre.form_id]
            state = use(state, "mode", genre_verb, target=target)
            state = use(state, "living", system.commands[0])
            state = turn(state)
            assert state.spatial.game.mode.actions == 1
            assert state.spatial.game.causal.tick == 1
            assert state.events == 3
            validate_living(state)


def test_trophic_food_web_consumes_vegetation_and_prey_instead_of_minting_them() -> None:
    s = choose("trophic")
    s = use(s, "living", "graze", amount=2)
    assert s.metrics.vegetation == 12
    assert s.metrics.grazers == 8
    s = turn(s)
    assert s.metrics.vegetation <= 17
    assert s.metrics.seedlings < 5
    assert s.metrics.grazers <= 8


def test_settlement_cannot_accept_more_households_than_real_houses() -> None:
    s = choose("settlement")
    s = use(s, "living", "welcome")
    assert s.metrics.households == 4
    with pytest.raises(FoundationError):
        use(s, "living", "welcome")
    s = turn(s)
    assert s.metrics.food == 8
    s = use(s, "living", "house")
    assert s.metrics.housing == 5


def test_caravans_arrive_on_clock_and_unload_only_delivered_goods() -> None:
    s = choose("caravans")
    with pytest.raises(FoundationError):
        use(s, "living", "unload")
    s = use(s, "living", "dispatch", amount=2)
    assert s.metrics.cargo == 4 and s.metrics.in_transit == 2
    assert s.spatial.fuel == 7
    s = turn(s)
    assert s.metrics.in_transit == 2 and s.metrics.transit_due == 1
    s = turn(s)
    assert s.metrics.in_transit == 0
    assert s.metrics.delivered == 2
    s = use(s, "living", "unload", amount=2)
    assert s.metrics.delivered == 0 and s.metrics.credit == 12


def test_reservoir_water_is_never_free_and_floods_are_durable() -> None:
    s = choose("watershed")
    s = use(s, "living", "irrigate", amount=3)
    assert s.metrics.reservoir == 6 and s.metrics.soil == 11
    s = use(s, "living", "dam")
    assert s.spatial.materials == 6
    s = turn(s, 8)
    assert 0 <= s.metrics.reservoir <= 20
    assert s.metrics.dam_strength == 2


def test_power_grid_burns_real_source_fuel_and_shortages_accumulate() -> None:
    s = choose("power")
    initial = s.spatial.fuel
    s = use(s, "living", "generate")
    assert s.spatial.fuel == initial - 1
    s = turn(s, 5)
    assert s.spatial.fuel <= initial - 1
    assert s.metrics.grid_wear > 0 or s.metrics.outages > 0


def test_fictional_spore_cohort_population_conserved() -> None:
    s = choose("spores")
    total = s.metrics.unaffected + s.metrics.affected + s.metrics.recovered
    s = use(s, "living", "isolate")
    s = turn(s)
    assert s.metrics.unaffected + s.metrics.affected + s.metrics.recovered == total
    s = use(s, "living", "remedy")
    assert s.metrics.unaffected + s.metrics.affected + s.metrics.recovered == total


def test_robots_consume_components_and_wear_until_serviced() -> None:
    s = choose("fabrication")
    s = use(s, "living", "design")
    assert s.metrics.orders == 1
    s = turn(s)
    assert s.metrics.completed == 1
    assert s.metrics.components == 7
    assert s.metrics.wear >= 1
    s = use(s, "living", "service")
    assert s.spatial.materials == 7


def test_knowledge_requires_two_observations_plus_actual_peer_evidence() -> None:
    s = choose("knowledge")
    s = use(s, "living", "observe")
    assert s.metrics.observations == 4
    s = use(s, "living", "verify")
    assert s.metrics.proven == 1
    assert s.spatial.game.causal.evidence == 1
    s = use(s, "living", "teach")
    assert s.metrics.proven == 0 and s.metrics.shared == 2
    assert s.spatial.game.causal.supplies == 11


def test_diplomacy_pledges_cost_actual_stores_and_persist_obligations() -> None:
    s = choose("diplomacy")
    s = use(s, "living", "pledge")
    assert s.metrics.promises == 2
    assert s.spatial.game.causal.supplies == 10
    s = turn(s, 4)
    assert s.metrics.tension >= 4
    s = use(s, "living", "mediate")
    assert s.metrics.tension < 6
    assert s.metrics.promises == 1


def test_echoes_cannot_delete_history_and_unpaid_debt_is_permanent() -> None:
    s = choose("echoes")
    s = use(s, "living", "record")
    prior = s.event_head
    assert s.metrics.queued_echoes == 1
    assert s.metrics.time_debt == 3
    s = turn(s)
    assert s.metrics.queued_echoes == 1
    s = turn(s)
    assert s.metrics.queued_echoes == 0
    assert s.metrics.time_debt == 3
    assert s.event_head != prior
    s = use(s, "living", "reconcile")
    assert s.metrics.time_debt == 2


def test_game_actions_and_actual_spatial_travel_share_one_save_envelope() -> None:
    s = choose("spores", architecture="lattice", genre="puzzle", arc="endless")
    s = use(s, "spatial", "travel", target=1)
    s = use(s, "mode", "toggle", target=0)
    s = use(s, "living", "isolate")
    s = turn(s)
    assert s.spatial.position == 1
    assert s.spatial.game.mode.switches == 1
    assert s.metrics.isolation == 1
    assert s.living_turns == 1
    assert restore_living(save_living(s)) == s


def test_deterministic_receipt_replay_and_tamper_rejection() -> None:
    law = living_for(123, "puzzle", "phase", "knowledge", "dynasty")
    actions = (
        LivingAction("living", "observe"),
        LivingAction("living", "verify"),
        LivingAction("mode", "toggle", target=0),
        LivingAction("causal", "end_turn"),
    )
    a, proof = replay_living(law.index, actions)
    b, again = replay_living(law.index, actions)
    assert a == b and proof == again
    assert len({p.event_hash for p in proof}) == len(proof)
    assert restore_living(save_living(a)) == a
    corrupted = json.loads(save_living(a))
    corrupted["payload"]["metrics"]["proven"] = 999
    with pytest.raises(FoundationError):
        restore_living(json.dumps(corrupted))
    mismatched = json.loads(save_living(a))
    mismatched["payload"]["world_id"] = "livingworld-000000000"
    with pytest.raises(FoundationError):
        restore_living(json.dumps(mismatched))


@pytest.mark.parametrize("bad_action", [
    LivingAction("unsupported", "reseed"),
    LivingAction("living", "warp"),
    LivingAction("living", "reseed", amount=0),
    LivingAction("living", "reseed", amount=True),
    LivingAction("living", "reseed", amount=4),
    LivingAction("living", "reseed", target=100),
])
def test_invalid_actions_are_fail_closed_and_do_not_mutate_state(bad_action) -> None:
    s = choose("trophic")
    before = asdict(s)
    with pytest.raises(FoundationError):
        step_living(s, bad_action)
    assert asdict(s) == before
