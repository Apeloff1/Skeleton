"""Review fixes for feat/mb-procgen: tiles match the door graph, directed solve with
softlocks, scaled spikes, lock/key limits, area fight cap, layout metrics, wiring."""
import copy
from dataclasses import dataclass, replace
from typing import Optional

import pytest

from skeleton.forge.ai_builder.procgen import (Corridor, EncounterConfig, LayoutLimits, ProcgenCompletabilitySolver,
                                               ProcgenConfig, ProcgenError, Rect, Room, canonical_bytes,
                                               check_procgen, fill_plan, generate, layout_metrics,
                                               metric_violations, pacing_report, place_locks, softlocks,
                                               spike_threshold, tile_links, tile_report)
from skeleton.forge.ai_builder.procgen.layout import carve_l
from skeleton.forge.ai_builder.procgen.rng import DeterministicRng
from skeleton.forge.ai_builder.validate import score_plan, validate_plan
from skeleton.forge.validator import Severity

from .plan_fixtures import good_plan


def errors(plan, rule=None):
    return [p for p in check_procgen(plan) if p.severity is Severity.ERROR and (rule is None or p.rule == rule)]


def locked_layout(seed=5, dungeon="bsp"):
    r = generate(good_plan(), seed, config=ProcgenConfig(locks=2, dungeon=dungeon))
    assert r.layout.locks()
    return r.layout


# --- blocker 1: tiles match the door graph -------------------------------------------------

def test_corridor_through_room_links_via_that_room():
    rooms = [Room("a", Rect(1, 1, 3, 3)), Room("b", Rect(7, 1, 3, 3)), Room("c", Rect(13, 1, 3, 3))]
    cells = carve_l(rooms[0].rect.center, rooms[2].rect.center, True)   # straight line through b
    links = {(a, b) for a, b, *_ in tile_links(rooms, [("a", "c", cells)])}
    assert links == {("a", "b"), ("b", "c")}


def test_tile_route_bypassing_lock_is_detected():
    lay = locked_layout()
    assert tile_report(lay)["ok"]
    a, b = lay.room(lay.start).rect.center, lay.room(lay.goal).rect.center
    sneak = replace(lay, corridors=lay.corridors + (Corridor(lay.start, lay.goal, carve_l(a, b, True)),))
    rep = tile_report(sneak)
    assert rep["bypassed_locks_into"] and not rep["ok"]


@pytest.mark.parametrize("dungeon", ["bsp", "graph"])
def test_locks_sit_on_lockable_door_tiles(dungeon):
    lay = locked_layout(dungeon=dungeon)
    for d in lay.doors:
        if d.key:
            assert d.lockable and d.cell is not None
            x, y = d.cell
            assert lay.tiles()[y][x] not in ".#"


# --- blocker 2: directed solve + softlocks -------------------------------------------------

def test_one_way_drop_into_locked_pocket_is_softlock():
    adj = {"s": ["p", "x"], "x": ["s"], "p": ["q"], "q": ["p", "g"], "g": ["q"]}   # s->p is a drop
    rep = softlocks(adj, "s", ["g"], {("g", "q"): "k"}, {"k": "x"})
    assert rep["goal_reachable"] and set(rep["softlock_rooms"]) >= {"p", "q"}
    assert softlocks(adj, "s", ["g"], {}, {})["softlock_rooms"] == []


def test_one_way_drop_softlock_in_plan_is_error():
    out = fill_plan(good_plan(), 5, config=ProcgenConfig(locks=1))
    lid = {lv["id"]: lv for lv in out["levels"]}
    start = out["start_level"]
    pocket = "pg_pocket"
    out["levels"].append({**copy.deepcopy(lid[start]), "id": pocket, "exits": [], "encounters": []})
    lid[start]["exits"] = lid[start]["exits"] + [pocket]      # one-way drop, no way out
    errs = errors(out, "procgen_reachability")
    assert any("softlock" in p.message and pocket in p.message for p in errs)
    assert validate_plan(out) and score_plan(out).verdict != "accept"


# --- item 5: lock gating 0 rooms / shortfall ------------------------------------------------

def test_lock_gating_zero_rooms_is_error():
    out = fill_plan(good_plan(), 5, config=ProcgenConfig(locks=1))
    a, b, k = out["procgen"]["locks"][0]
    lv = {x["id"]: x for x in out["levels"]}
    s = out["start_level"]     # walk-around exits: the lock now gates nothing
    lv[s]["exits"] = sorted(set(lv[s]["exits"]) | {a, b} - {s})
    for x in (a, b):
        if x != s:
            lv[x]["exits"] = sorted(set(lv[x]["exits"]) | {s})
    assert any("gates 0" in p.message for p in errors(out, "procgen_reachability"))


def test_lock_shortfall_recorded_and_strict_raises():
    lay = locked_layout()
    bare = lay.with_doors(tuple(replace(d, key=None) for d in lay.doors), {})
    got = place_locks(bare, DeterministicRng(1), 50)
    assert got.locks_requested == 50 and len(got.locks()) < 50
    with pytest.raises(ProcgenError):
        place_locks(bare, DeterministicRng(1), 50, strict=True)


# --- item 6: key distance ------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(8))
def test_keys_near_their_locks(seed):
    out = fill_plan(good_plan(), seed, config=ProcgenConfig(locks=2))
    assert not [p for p in check_procgen(out) if "doors from its lock" in p.message]


# --- items 3/4: spikes and rest dips -------------------------------------------------------

def test_spike_threshold_scales_with_cap_and_fires():
    assert spike_threshold(0.7) == pytest.approx(0.21) and spike_threshold(0.5) == pytest.approx(0.15)
    assert pacing_report([0.0, 0.1, 0.15, 0.4], cap=0.7)["spikes"] == [3]
    assert pacing_report([0.0, 0.1, 0.2, 0.05, 0.3], cap=0.7)["spikes"] == []   # rest-dip recovery


def test_rest_rooms_dip_despite_jitter():
    pc = EncounterConfig().pacing
    for seed in range(30):
        for i in range(1, 12):
            if pc.is_rest(0.5, i):
                assert pc.value(0.5, i, DeterministicRng(seed)) < \
                    pc.value(0.5, i, DeterministicRng(seed), allow_rest=False)


# --- item 7: small-room fight cap ----------------------------------------------------------

def test_small_room_fight_cap():
    cfg = EncounterConfig()
    assert cfg.fights_for(9) == 1 and cfg.fights_for(24) == 2 and cfg.fights_for(10_000) == cfg.max_per_room
    for seed in range(10):
        r = generate(good_plan(), seed)
        for room in r.layout.rooms:
            assert len(r.encounters.rooms[room.id].encounters) <= cfg.fights_for(room.rect.area)


# --- items 9/10: metrics, intensity ---------------------------------------------------------

def test_layout_metrics_and_limits():
    adj = {"a": ["b"], "b": ["a", "c", "d"], "c": ["b", "d"], "d": ["b", "c", "e"], "e": ["d"]}
    m = layout_metrics(adj, ["a", "b", "d"], "a", "d")
    assert m["loops"] == 1 and m["dead_ends"] == ["e"] and m["critical_path_share"] == pytest.approx(0.6)
    assert metric_violations(m, LayoutLimits(max_loops=0))
    assert not metric_violations(m, LayoutLimits())


def test_metrics_and_intensity_in_plan():
    out = fill_plan(good_plan(), 3)
    meta = out["procgen"]
    assert set(meta["layout"]["metrics"]) >= {"critical_path_share", "dead_end_ratio", "loops"}
    inten = meta["difficulty"]["intensity"]
    for lv in out["levels"]:
        assert isinstance(lv["procgen"]["intensity"], float) and inten[lv["id"]] == lv["procgen"]["intensity"]


# --- item 8: score_plan wiring --------------------------------------------------------------

def test_default_score_plan_runs_procgen_checks():
    out = fill_plan(good_plan(), 5, config=ProcgenConfig(locks=2))
    del out["procgen"]["keys"][out["procgen"]["locks"][0][2]]
    assert any(p.rule.startswith("procgen") for p in score_plan(out).problems)


# --- CompletabilitySolver adapter (quest-branch protocol shape, local dataclasses) -----------

@dataclass(frozen=True)
class QDoor:
    to: str
    requires: Optional[str] = None


@dataclass(frozen=True)
class QRoom:
    key: str
    doors: tuple = ()
    keys: tuple = ()
    goal: bool = False


def test_completability_adapter():
    solver = ProcgenCompletabilitySolver()
    ok = [QRoom("s", (QDoor("k"), QDoor("g", "red"))), QRoom("k", (QDoor("s"),), ("red",)), QRoom("g", goal=True)]
    v = solver.check(ok, "s", frozenset())
    assert v.completable and not v.softlocked
    no_key = [QRoom("s", (QDoor("g", "red"),)), QRoom("g", goal=True)]
    v = solver.check(no_key, "s", frozenset())
    assert not v.completable and "red" in v.reason
    assert solver.check(no_key, "s", frozenset({"red"})).completable
    drop = [QRoom("s", (QDoor("p"), QDoor("g", "red"), QDoor("k"))), QRoom("k", (QDoor("s"),), ("red",)),
            QRoom("p"), QRoom("g", goal=True)]                  # s->p is a one-way drop
    v = solver.check(drop, "s", frozenset())
    assert v.completable and v.softlocked and "p" in v.reason


# --- sweep ----------------------------------------------------------------------------------

@pytest.mark.parametrize("dungeon", ["bsp", "graph"])
@pytest.mark.parametrize("seed", range(40))
def test_sweep_deterministic_accepted_tiles_ok(dungeon, seed):
    cfg = ProcgenConfig(dungeon=dungeon, locks=2)
    a, b = fill_plan(good_plan(), seed, config=cfg), fill_plan(good_plan(), seed, config=cfg)
    assert canonical_bytes(a) == canonical_bytes(b)
    assert a["procgen"]["layout"]["tile_check"]["ok"]
    assert not errors(a)
    assert score_plan(a).verdict == "accept"
