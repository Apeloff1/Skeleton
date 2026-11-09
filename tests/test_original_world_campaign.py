"""Playable campaign tests: real actions, causality, persistence and recovery."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_world_campaign import (
    ACTION_MECHANICS, ENGINE_VERSION, SCENARIOS, CampaignAction,
    CampaignError, CampaignState, Sector, create_campaign, edges,
    export_save, import_save, neighbors, replay, shortest_path, step,
    validate_state,
)
from skeleton.game.generation.original_mechanic_catalog import MECHANICS
from skeleton.game.generation.original_world_catalog import WORLDS


def go(state, verb: str, target: int = -1, amount: int = 1, option: str = ""):
    return step(state, CampaignAction(verb, target, amount, option))[0]


def tile_with(state, **changes):
    tiles = list(state.sectors)
    tiles[state.position] = replace(tiles[state.position], **changes)
    return replace(state, sectors=tuple(tiles))


def test_four_original_world_laws_and_34_concrete_player_verbs() -> None:
    assert len(SCENARIOS) == 4
    assert set(SCENARIOS).issubset(WORLDS)
    assert len(ACTION_MECHANICS) == 35
    assert ACTION_MECHANICS["end_turn"] is None
    assert all(mid in MECHANICS and MECHANICS[mid].cost_specified
               for mid in ACTION_MECHANICS.values() if mid is not None)
    assert len({v for v in ACTION_MECHANICS.values() if v is not None}) >= 32


@pytest.mark.parametrize("world_id", sorted(SCENARIOS))
def test_all_world_adapters_initialize_reproducibly(world_id: str) -> None:
    first = create_campaign(world_id, "world-seed")
    assert first == create_campaign(world_id, "world-seed")
    validate_state(first)
    assert first.world_id == world_id
    assert first.action_points == 4
    assert first.event_head == "0" * 64
    assert len(first.sectors) == 12
    assert first.position in first.explored
    assert len(edges(first)) >= 12
    assert shortest_path(first, 11)[0] == 0
    assert shortest_path(first, 11)[-1] == 11


def test_movement_reveals_sectors_and_consumes_actions() -> None:
    start = create_campaign("topology-02", "move-seed")
    target = neighbors(start)[0]
    s, receipt = step(start, CampaignAction("move", target))
    assert s.position == target
    assert target in s.explored
    assert s.knowledge == start.knowledge + 2
    assert s.energy == start.energy - 1
    assert s.event_count == 1
    assert receipt.before != receipt.after
    assert receipt.event_id == s.event_head
    assert start.position == 0
    assert len(shortest_path(s, 0)) >= 2
    with pytest.raises(CampaignError):
        go(s, "move", target=s.position)


def test_unseen_labyrinth_changes_but_all_sectors_stay_accessible() -> None:
    start = create_campaign("topology-02", "maze-shift")
    before = edges(start)
    later = go(start, "end_turn")
    assert later.maze_phase == 1
    assert edges(later) != before
    assert all(shortest_path(replace(later, position=room,
                                     explored=(0, room) if room else (0,)), 0)[-1] == 0
               for room in range(12))
    fixed = go(start, "stabilize_route", target=5)
    assert (0, 5) in fixed.anchors
    with pytest.raises(CampaignError):
        go(start, "stabilize_route", target=1)
    shifted = go(fixed, "end_turn")
    assert (0, 5) in edges(shifted)


def test_observation_delays_blindside_rewiring() -> None:
    start = create_campaign("topology-02")
    observed = go(start, "observe", amount=1)
    assert observed.observed_until == 2
    a = go(observed, "end_turn")
    assert a.maze_phase == 0
    b = go(a, "end_turn")
    assert b.maze_phase == 1


def test_rain_herds_conserve_moisture_and_change_ecology() -> None:
    start = create_campaign("ecology-03")
    moved = go(start, "redirect_rain", option="west", amount=2)
    assert (moved.rain_west, moved.rain_east) == (8, 4)
    for _ in range(12):
        moved = go(moved, "end_turn")
        assert moved.rain_west + moved.rain_east == 12
    assert moved.turn == 12
    assert moved.sectors != start.sectors
    with pytest.raises(CampaignError):
        go(create_campaign("topology-02"), "redirect_rain", option="west")


def test_honored_promises_physically_construct_civic_architecture() -> None:
    base = create_campaign("civilization-01", "civic")
    pledged = go(base, "pledge")
    assert pledged.promises == 1
    finished = go(pledged, "fulfill")
    assert finished.promises == 0
    assert finished.honored_promises == 1
    assert finished.sectors[0].building == "civic"
    assert finished.civic_buildings == 1
    assert finished.trust > pledged.trust
    with pytest.raises(CampaignError):
        go(base, "fulfill")
    other = go(go(create_campaign("serenity-05"), "pledge"), "fulfill")
    assert other.sectors[0].building == ""
    assert other.civic_buildings == 0


def test_quilt_is_expanding_cozy_world_without_forced_victory() -> None:
    start = create_campaign("serenity-05")
    a = go(start, "weave", amount=2)
    assert a.quilt == 4
    assert a.wood == start.wood - 2
    assert a.trust > start.trust
    energy = a.energy
    b = go(a, "rest")
    assert b.energy >= energy
    with pytest.raises(CampaignError):
        go(create_campaign("ecology-03"), "weave")


def test_farming_is_actual_local_resource_loop() -> None:
    s = create_campaign("serenity-05", "farm")
    before_water = s.water
    s = go(s, "plant", amount=2)
    assert s.sectors[0].crop == 2
    assert s.seeds == 0
    assert s.water == before_water - 2
    s = go(s, "irrigate")
    assert s.sectors[0].fertility >= 1
    s = go(s, "harvest")
    assert s.food == 5
    assert s.sectors[0].crop == 1
    s = go(s, "end_turn")
    assert s.action_points == 4
    assert s.sectors[0].crop >= 1


def test_market_conserves_individual_accounting_and_requires_a_village() -> None:
    s = create_campaign("civilization-01")
    bought = go(s, "trade", option="buy_food", amount=2)
    assert bought.coins == s.coins - 4
    assert bought.food == s.food + 2
    sold = go(bought, "trade", option="sell_wood")
    assert sold.wood == bought.wood - 1
    assert sold.coins == bought.coins + 2
    moved = go(s, "move", target=neighbors(s)[0])
    with pytest.raises(CampaignError):
        go(moved, "trade", option="buy_food")


def test_actions_cover_distinct_domains_and_are_not_just_narrative_text() -> None:
    reference = create_campaign("serenity-05", "coverage")
    scenarios = {
        "move": CampaignAction("move", neighbors(reference)[0]),
        "observe": CampaignAction("observe"),
        "forage": CampaignAction("forage"),
        "gather_wood": CampaignAction("gather_wood"),
        "collect_stone": CampaignAction("collect_stone"),
        "draw_water": CampaignAction("draw_water"),
        "plant": CampaignAction("plant"),
        "irrigate": CampaignAction("irrigate"),
        "harvest": CampaignAction("harvest"),
        "rest": CampaignAction("rest"),
        "eat": CampaignAction("eat"),
        "build_shelter": CampaignAction("build_shelter"),
        "repair": CampaignAction("repair"),
        "build_garden": CampaignAction("build_garden"),
        "craft_tool": CampaignAction("craft_tool"),
        "trade": CampaignAction("trade", option="buy_food"),
        "talk": CampaignAction("talk"),
        "gift": CampaignAction("gift"),
        "assist": CampaignAction("assist"),
        "research": CampaignAction("research"),
        "survey": CampaignAction("survey"),
        "teach": CampaignAction("teach"),
        "pledge": CampaignAction("pledge"),
        "fulfill": CampaignAction("fulfill"),
        "vote": CampaignAction("vote"),
        "weave": CampaignAction("weave"),
        "guide_herd": CampaignAction("guide_herd"),
        "heal": CampaignAction("heal"),
        "watch": CampaignAction("watch"),
        "defend": CampaignAction("defend"),
        "restore": CampaignAction("restore"),
        "explore": CampaignAction("explore"),
        "end_turn": CampaignAction("end_turn"),
    }
    for verb, action in scenarios.items():
        tile = reference.sectors[reference.position]
        starting = replace(
            reference, action_points=4, energy=16, wood=20,
            stone=20, water=20, food=20, seeds=20,
            medicine=10, coins=40, knowledge=30, trust=30, promises=2,
        )
        if verb in ("irrigate", "harvest"):
            starting = tile_with(starting, crop=3)
        elif verb == "repair":
            starting = tile_with(starting, building="shelter", contamination=3)
        s, event = step(starting, action)
        assert s != starting, verb
        assert s.event_count == starting.event_count + 1
        assert event.action.verb == verb
        assert event.messages
        assert event.event_id == s.event_head
        validate_state(s)


def test_postgame_continues_when_a_chapter_finishes() -> None:
    s = replace(create_campaign("serenity-05"), trust=100)
    chapter = go(s, "talk")
    assert chapter.chapter_complete
    assert chapter.postgame
    after = go(chapter, "end_turn")
    assert after.postgame
    assert after.turn == 1
    assert after.sectors != ()


def test_bounded_savegame_round_trip_with_checksum_and_replay() -> None:
    actions = (
        CampaignAction("forage", amount=2),
        CampaignAction("observe"),
        CampaignAction("move", target=1),
        CampaignAction("end_turn"),
        CampaignAction("research"),
        CampaignAction("end_turn"),
    )
    one, events = replay("topology-02", "save-world", actions)
    two, again = replay("topology-02", "save-world", actions)
    assert one == two and events == again
    assert one.event_count == len(actions)
    saved = export_save(one)
    assert import_save(saved) == one
    assert json.loads(saved)["payload"]["schema"] == ENGINE_VERSION
    same = import_save(export_save(one))
    advanced = go(same, "end_turn")
    assert advanced.event_count == one.event_count + 1
    envelope = json.loads(saved)
    envelope["payload"]["state"]["coins"] = 9999
    with pytest.raises(CampaignError):
        import_save(json.dumps(envelope))
    with pytest.raises(CampaignError):
        import_save("not json")


@pytest.mark.parametrize("invalid", [
    CampaignAction("unsupported"),
    CampaignAction("forage", amount=0),
    CampaignAction("forage", amount=4),
    CampaignAction("forage", amount=True),
    CampaignAction("move", target=-1),
    CampaignAction("move", target=12),
    CampaignAction("move", target=True),
    CampaignAction("forage", option="x" * 33),
    CampaignAction("redirect_rain", option="unknown"),
    CampaignAction("trade", option="unknown"),
])
def test_invalid_operations_fail_closed(invalid: CampaignAction) -> None:
    s = create_campaign("ecology-03")
    before = asdict(s)
    with pytest.raises(CampaignError):
        step(s, invalid)
    assert asdict(s) == before


def test_corrupt_state_is_denied() -> None:
    state = create_campaign("topology-02")
    for corrupt in (
        replace(state, rain_east=7),
        replace(state, position=11),
        replace(state, seeds=-1),
        replace(state, action_points=True),
        replace(state, event_head="x" * 64),
        replace(state, anchors=((1, 1),)),
        replace(state, postgame=True),
    ):
        with pytest.raises(CampaignError):
            validate_state(corrupt)


def test_unimplemented_catalog_worlds_cannot_masquerade_as_playable() -> None:
    with pytest.raises(CampaignError):
        create_campaign("time-01")
    with pytest.raises(CampaignError):
        create_campaign("not-an-id")
    with pytest.raises(CampaignError):
        create_campaign("serenity-05", "")
    with pytest.raises(CampaignError):
        replay("serenity-05", "seed", "unexpected")
    with pytest.raises(CampaignError):
        replay("serenity-05", "seed", (CampaignAction("rest"),) * 1025)


def test_endless_world_is_resource_bounded_not_free_infinite_action() -> None:
    s = create_campaign("serenity-05")
    with pytest.raises(CampaignError):
        step(replace(s, event_count=1024), CampaignAction("end_turn"))
    exhaustion = replace(s, energy=0)
    with pytest.raises(CampaignError):
        go(exhaustion, "move", target=neighbors(s)[0])
    recharged = go(exhaustion, "rest")
    assert recharged.energy > 0
