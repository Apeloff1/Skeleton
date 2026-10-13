"""Playable era-specific technology and invented theology behavior tests."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_world_campaign import (
    CampaignAction, CampaignError,
)
from skeleton.game.generation.original_world_era_runtime import (
    ERA_LEVELS, TECH_ACTIONS, THEOLOGY_ACTIONS, StyledAction,
    create_styled_world, styled_restore, styled_save, styled_step,
    validate_styled,
)
from skeleton.game.generation.world_styling import (
    ERAS, THEOLOGIES, WorldStyling,
)


def style(**kwargs) -> WorldStyling:
    return WorldStyling(**kwargs)


def use(state, verb, amount=1):
    return styled_step(state, StyledAction(verb, amount))[0]


def test_all_40_eras_and_24_cosmologies_have_explicit_capability_gates() -> None:
    assert len(ERA_LEVELS) == len(ERAS) == 40
    assert set(ERA_LEVELS) == set(ERAS)
    assert set(THEOLOGY_ACTIONS) == set(THEOLOGIES)
    assert len(THEOLOGY_ACTIONS) == 24
    assert len(TECH_ACTIONS) == 10
    assert all(0 <= tier <= 8 for tier in ERA_LEVELS.values())
    assert all("reflection" in actions for actions in THEOLOGY_ACTIONS.values())


def test_prehistoric_knapping_and_later_smelting_have_tangible_costs() -> None:
    s = create_styled_world("serenity-05", styling=style(era="paleolithic"))
    s = use(s, "knap")
    assert s.world.wood == 2 and s.world.stone == 1
    assert s.world.tools == 2
    with pytest.raises(CampaignError):
        use(s, "smelt")
    later = create_styled_world("serenity-05", styling=style(era="iron-age"))
    heated = use(later, "smelt")
    assert heated.metal == 1
    assert heated.world.wood == later.world.wood - 2
    assert heated.world.sectors[0].contamination == 1


def test_energy_grid_and_robots_require_real_resources_and_energy() -> None:
    starting = create_styled_world(
        "serenity-05", styling=style(era="digital-network")
    )
    ready = replace(starting, metal=3, grid_power=0)
    powered = use(ready, "power_grid")
    assert powered.grid_power == 3
    assert powered.metal == 1
    assert powered.world.coins == starting.world.coins - 2
    informed = replace(powered, world=replace(powered.world, knowledge=3))
    automated = use(informed, "automation")
    assert automated.robots == 1
    assert automated.grid_power == 2
    baseline, _ = styled_step(replace(automated, robots=0),
                              CampaignAction("end_turn"))
    after, receipt = styled_step(automated, CampaignAction("end_turn"))
    assert after.world.food == baseline.world.food + 1
    assert after.world.sectors[0].food == baseline.world.sectors[0].food - 1
    assert after.grid_power == 1
    assert "Automated harvest" in " ".join(receipt.effects)


def test_drone_reveals_an_actually_unexplored_sector() -> None:
    s = create_styled_world("topology-02", styling=style(era="digital-network"))
    s = replace(s, robots=1, grid_power=2)
    surveyed = use(s, "survey_drone")
    assert surveyed.probes == 1
    assert len(surveyed.world.explored) == 2
    assert 1 in surveyed.world.explored
    assert surveyed.world.position == 0
    assert surveyed.grid_power == 1


def test_theology_permissions_are_causal_not_just_art_style() -> None:
    atheist = create_styled_world(
        "serenity-05", styling=style(theology="atheist-world")
    )
    with pytest.raises(CampaignError):
        use(atheist, "weather_invocation")
    assert use(atheist, "reflection").world.knowledge == atheist.world.knowledge + 1
    faith = create_styled_world(
        "serenity-05", styling=style(theology="faith-as-power")
    )
    before = faith.world.rain_west + faith.world.rain_east
    changed = use(faith, "weather_invocation")
    assert changed.world.rain_west == faith.world.rain_west + 1
    assert changed.world.rain_east == faith.world.rain_east - 1
    assert changed.world.rain_west + changed.world.rain_east == before
    assert changed.world.food == faith.world.food - 1
    assert changed.world.water == faith.world.water - 1
    assert changed.devotion == faith.devotion + 1


def test_ancestor_memory_and_oracle_produce_different_outcomes() -> None:
    ancient = create_styled_world(
        "serenity-05", styling=style(theology="ancestor-veneration")
    )
    ancient = replace(ancient, world=replace(ancient.world, knowledge=2))
    recorded = use(ancient, "ancestor_memory")
    assert recorded.heritage == 1
    assert recorded.world.trust == ancient.world.trust + 1
    assert recorded.world.food == ancient.world.food - 1
    omen = create_styled_world(
        "serenity-05", styling=style(theology="oracular")
    )
    omen = replace(omen, world=replace(omen.world, knowledge=2))
    spoken, receipt = styled_step(omen, StyledAction("oracle"))
    assert spoken.visions == 1
    assert spoken.last_vision in {
        "migration-west", "migration-east", "drought-risk",
    }
    assert spoken.last_vision in " ".join(receipt.effects)
    assert spoken.world.knowledge == omen.world.knowledge - 1


def test_cozy_and_harsh_risk_setting_have_distinct_gameplay_costs() -> None:
    easy = create_styled_world(
        "serenity-05", styling=style(comfort=100, tone="ultra-snuggly")
    )
    hard = create_styled_world(
        "serenity-05", styling=style(comfort=0, tone="nightmarish")
    )
    for _ in range(4):
        easy = styled_step(easy, CampaignAction("end_turn"))[0]
        hard = styled_step(hard, CampaignAction("end_turn"))[0]
    assert easy.world.hunger == 0
    assert hard.world.hunger == 8
    assert easy.world.tick == hard.world.tick == 4


def test_time_loop_repeats_temporal_phase_but_keeps_history() -> None:
    a = create_styled_world(
        "topology-02", styling=style(chronology="time-loop")
    )
    for _ in range(8):
        a = styled_step(a, CampaignAction("end_turn"))[0]
    assert a.loops == 1
    assert a.world.tick == 8
    assert a.world.maze_phase == 0
    assert a.events == 8


def test_original_world_styling_save_and_replay_are_exact() -> None:
    original = create_styled_world(
        "serenity-05",
        seed="styling",
        styling=style(
            era="iron-age", theology="animist-invented",
            chronology="cyclical-time", comfort=91, realism=70,
        ),
    )
    first = use(original, "smelt")
    second = use(first, "communal_rite")
    assert second == styled_restore(styled_save(second))
    assert second.event_head != first.event_head
    assert second.events == 2
    assert use(original, "smelt") == first
    saved = json.loads(styled_save(second))
    saved["payload"]["extras"]["metal"] = 999
    with pytest.raises(CampaignError):
        styled_restore(json.dumps(saved))


def test_high_tech_prohibited_in_old_eras_and_costs_must_be_paid() -> None:
    old = create_styled_world(
        "serenity-05", styling=style(era="paleolithic")
    )
    for verb in ("smelt", "power_grid", "automation", "survey_drone",
                 "terraform"):
        with pytest.raises(CampaignError):
            use(old, verb)
    future = create_styled_world(
        "serenity-05", styling=style(era="interplanetary")
    )
    with pytest.raises(CampaignError):
        use(future, "terraform")
    ready = replace(future, grid_power=4, metal=2)
    updated = use(ready, "terraform")
    assert updated.grid_power == 2
    assert updated.metal == 1
    assert updated.world.water == future.world.water - 1
    assert updated.world.sectors[0].fertility >= future.world.sectors[0].fertility + 2


def test_incompatible_prehuman_era_cannot_claim_human_civic_world() -> None:
    with pytest.raises(CampaignError):
        create_styled_world(
            "civilization-01", styling=style(era="primordial-earth")
        )


@pytest.mark.parametrize("invalid", [
    StyledAction("missing"),
    StyledAction("knap", amount=0),
    StyledAction("knap", amount=True),
    StyledAction("knap", amount=4),
    StyledAction("knap", option="secret"),
])
def test_invalid_experience_actions_do_not_mutate_play_state(invalid) -> None:
    state = create_styled_world("serenity-05")
    before = asdict(state)
    with pytest.raises(CampaignError):
        styled_step(state, invalid)
    assert asdict(state) == before
