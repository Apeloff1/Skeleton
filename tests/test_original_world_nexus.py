"""Crossover world integration: resources never duplicate across realms."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_world_campaign import (
    CampaignAction, CampaignError, Sector,
)
from skeleton.game.generation.original_world_nexus import (
    REALM_IDS, MAX_NEXUS_EVENTS, act, active_world, connections,
    create_nexus, nexus_replay, nexus_restore, nexus_save, recharge,
    travel, validate_nexus,
)


def total_portable(state, field: str) -> int:
    return sum(getattr(realm, field) for realm in state.realms)


def test_four_authored_worlds_share_one_nonduplicated_player() -> None:
    initial = create_nexus("connected")
    assert tuple(w.world_id for w in initial.realms) == REALM_IDS
    assert initial.current_realm == 0
    assert connections(initial) == (1, 3)
    assert initial.charges == 8
    assert total_portable(initial, "wood") == 3
    assert total_portable(initial, "coins") == 7
    assert initial.archive == ()
    assert create_nexus("connected") == initial


def test_realm_travel_moves_entire_player_inventory_without_cloning() -> None:
    original = create_nexus("portal-travel")
    moved, receipt = travel(original, 1)
    assert moved.current_realm == 1
    assert moved.charges == original.charges - 1
    assert moved.realms[0].wood == 0
    assert moved.realms[0].health == 0
    assert moved.realms[1].wood == 3
    assert moved.realms[1].health == original.realms[0].health
    assert total_portable(moved, "wood") == total_portable(original, "wood")
    assert total_portable(moved, "coins") == total_portable(original, "coins")
    assert receipt.from_realm == 0 and receipt.to_realm == 1
    assert receipt.event_id == moved.event_head
    assert original.realms[0].wood == 3


def test_world_specific_causal_laws_survive_portal_transfers() -> None:
    s = create_nexus("varied-worlds")
    s, _ = travel(s, 1)  # topology-02
    changed, _ = act(s, CampaignAction("end_turn"))
    assert changed.realms[1].maze_phase == 1
    assert changed.realms[0].maze_phase == 0
    assert changed.realms[0].turn == 1
    assert all(sum((w.rain_west, w.rain_east)) == 12 for w in changed.realms)
    assert all(w.turn == 1 for w in changed.realms)
    assert all(w.health == 0 for i, w in enumerate(changed.realms)
               if i != changed.current_realm)
    validate_nexus(changed)


def test_realm_specific_progress_and_postgame_remain_local() -> None:
    s = create_nexus("progress")
    realm0 = replace(s.realms[0], trust=100)
    s = replace(s, realms=(realm0, *s.realms[1:]))
    s, _ = act(s, CampaignAction("talk"))
    assert s.realms[0].postgame
    assert s.completed_realms == (0,)
    s, _ = travel(s, 1)
    assert not s.realms[1].postgame
    s, _ = act(s, CampaignAction("end_turn"))
    assert s.realms[0].postgame
    assert s.completed_realms == (0,)
    assert s.archive[0].startswith("chapters:")


def test_recharge_consumes_real_materials_and_cannot_mint_energy() -> None:
    original = create_nexus("resources")
    fueled, _ = recharge(original, 2)
    assert fueled.charges == original.charges + 2
    assert fueled.realms[0].wood == original.realms[0].wood - 2
    assert fueled.realms[0].stone == original.realms[0].stone - 2
    assert fueled.realms[0].coins == original.realms[0].coins - 2
    with pytest.raises(CampaignError):
        recharge(original, 3)
    with pytest.raises(CampaignError):
        recharge(original, 0)


def test_portal_requires_link_resources_and_safe_location() -> None:
    s = create_nexus()
    for destination in (-1, 0, 2, 4, True):
        with pytest.raises(CampaignError):
            travel(s, destination)
    with pytest.raises(CampaignError):
        travel(replace(s, charges=0), 1)
    low_energy = replace(s.realms[0], energy=1)
    with pytest.raises(CampaignError):
        travel(replace(s, realms=(low_energy, *s.realms[1:])), 1)
    distant = replace(s.realms[0], position=1, explored=(0, 1))
    with pytest.raises(CampaignError):
        travel(replace(s, realms=(distant, *s.realms[1:])), 1)


def test_travel_around_ring_then_return_retains_all_world_changes() -> None:
    s = create_nexus("four-systems")
    s, _ = act(s, CampaignAction("weave", amount=2))
    assert s.realms[0].quilt == 4
    first_head = s.realms[0].event_head
    for destination in (1, 2, 3, 0):
        s, _ = travel(s, destination)
        s, _ = act(s, CampaignAction("end_turn"))
    assert s.current_realm == 0
    assert s.realms[0].quilt == 4
    assert s.realms[0].event_head != first_head
    assert s.realms[1].maze_phase != 0
    assert total_portable(s, "wood") == 1
    assert s.charges == 4
    validate_nexus(s)


def test_nexus_replay_event_chain_is_stable() -> None:
    commands = (
        ("act", CampaignAction("weave", amount=2)),
        ("act", CampaignAction("end_turn")),
        ("travel", 1),
        ("act", CampaignAction("observe")),
        ("travel", 2),
        ("act", CampaignAction("redirect_rain", option="west")),
        ("act", CampaignAction("end_turn")),
        ("travel", 3),
        ("act", CampaignAction("pledge")),
        ("act", CampaignAction("fulfill")),
    )
    one, events = nexus_replay("replay-worlds", commands)
    two, again = nexus_replay("replay-worlds", commands)
    assert one == two
    assert events == again
    assert len(events) == len(commands)
    assert events[-1].event_id == one.event_head
    assert sum(w.civic_buildings for w in one.realms) == 1
    assert one.realms[2].rain_west + one.realms[2].rain_east == 12


def test_nexus_export_and_import_resume_identically() -> None:
    s = create_nexus("persistence")
    s, _ = act(s, CampaignAction("forage", amount=2))
    s, _ = travel(s, 1)
    s, _ = act(s, CampaignAction("end_turn"))
    serialized = nexus_save(s)
    assert nexus_restore(serialized) == s
    reloaded, receipt = act(nexus_restore(serialized), CampaignAction("observe"))
    assert reloaded.event_head == receipt.event_id
    assert reloaded.event_count == s.event_count + 1
    payload = json.loads(serialized)
    payload["payload"]["state"]["charges"] = 55
    with pytest.raises(CampaignError):
        nexus_restore(json.dumps(payload))
    with pytest.raises(CampaignError):
        nexus_restore("not json")


def test_crafted_duplicate_inventory_cannot_be_declared_valid() -> None:
    s = create_nexus()
    forged_realm = replace(s.realms[1], wood=3)
    bad = replace(s, realms=(s.realms[0], forged_realm, *s.realms[2:]))
    with pytest.raises(CampaignError):
        validate_nexus(bad)


def test_nexus_bounded_and_unavailable_worlds_fail_closed() -> None:
    s = create_nexus()
    with pytest.raises(CampaignError):
        act(replace(s, event_count=MAX_NEXUS_EVENTS), CampaignAction("end_turn"))
    with pytest.raises(CampaignError):
        nexus_replay("bad", (("unknown", 4),))
    with pytest.raises(CampaignError):
        nexus_replay("bad", (("act", "not an action"),))
    with pytest.raises(CampaignError):
        nexus_replay("bad", (("act", CampaignAction("rest")),) * 1025)
    with pytest.raises(CampaignError):
        create_nexus("")
