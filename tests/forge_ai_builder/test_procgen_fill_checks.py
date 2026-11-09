import copy

import pytest

from skeleton.forge.ai_builder.procgen import (EconomyLootSource, ProcgenConfig, ProcgenError, canonical_bytes,
                                               check_procgen, check_procgen_reachability, damage_curve, fill_plan,
                                               generate, score_plan_procgen)
from skeleton.forge.ai_builder.validate import score_plan
from skeleton.simulation.economy.sim import CurrencySpec, EconomySim, FaucetSpec, ItemSpec

from skeleton.forge.validator import Severity

from .plan_fixtures import good_plan


def econ():
    return EconomyLootSource(EconomySim([CurrencySpec("gold")],
                                        [ItemSpec("potion", "gold", 5, 20, 8), ItemSpec("gem", "gold", 1, 200, 80),
                                         ItemSpec("arrow", "gold", 50, 2, 1)], [FaucetSpec("kill", "gold", 5)]))


@pytest.mark.parametrize("dungeon", ["bsp", "graph"])
def test_same_seed_byte_identical_different_seed_differs(dungeon):
    cfg = ProcgenConfig(dungeon=dungeon)
    a = fill_plan(good_plan(), 1234, config=cfg, loot_source=econ())
    b = fill_plan(good_plan(), 1234, config=cfg, loot_source=econ())
    c = fill_plan(good_plan(), 1235, config=cfg, loot_source=econ())
    assert canonical_bytes(a) == canonical_bytes(b)
    assert canonical_bytes(a) != canonical_bytes(c)


def test_input_not_mutated_and_owned_fields_kept():
    p = good_plan()
    out = fill_plan(p, 1)
    assert p == good_plan()
    assert out["title"] == p["title"] and out["player"] == p["player"] and out["triggers"] == p["triggers"]
    assert "combat" in out["systems"]
    assert out["start_level"].startswith("pg_") and len(out["goal_levels"]) == 1


@pytest.mark.parametrize("dungeon", ["bsp", "graph"])
@pytest.mark.parametrize("seed", range(8))
def test_filled_plan_accepted_without_regressions(dungeon, seed):
    out = fill_plan(good_plan(), seed, config=ProcgenConfig(dungeon=dungeon), loot_source=econ())
    base = score_plan(good_plan())
    v = score_plan(out)
    assert v.verdict == "accept" and v.score >= base.score
    assert not v.errors
    pv = score_plan_procgen(out)
    assert pv.verdict == "accept" and not [p for p in pv.problems if p.rule.startswith("procgen")]


def test_default_score_plan_unchanged_by_opt_in_rules():
    p = good_plan()
    assert score_plan(p).as_dict() == score_plan(good_plan()).as_dict()
    assert check_procgen(p) == []  # no procgen section -> rules are silent
    assert score_plan_procgen(p).verdict == score_plan(p).verdict


def test_provenance_section():
    r = generate(good_plan(), "seed-x", loot_source=econ())
    meta = r.plan["procgen"]
    assert meta["seed"] == "seed-x" and meta["version"]
    assert {"terrain", "dungeon/keys", "encounters", "loot"} <= set(meta["streams"]["streams"])
    assert len(meta["terrain"]["receipt"]["height_digest"]) == 64
    assert meta["solution"]["solvable"]
    assert meta["loot"]["source"]["source"].endswith("EconomySim")
    assert meta["pruned"] == {"scenes": ["gate", "yard"], "assets": ["crab", "tiles"]}
    for lv in r.plan["levels"]:
        assert lv["scene"] in {s["id"] for s in r.plan["scenes"]}
        assert "loot" in lv["procgen"]
    assert len(damage_curve(r.plan)) == len(meta["layout"]["critical_path"])


def test_no_loot_without_source():
    out = fill_plan(good_plan(), 3)
    assert out["procgen"]["loot"] is None
    assert all("loot" not in lv["procgen"] for lv in out["levels"])


def test_keep_existing_levels_mode():
    out = fill_plan(good_plan(), 3, config=ProcgenConfig(replace_levels=False))
    ids = {lv["id"] for lv in out["levels"]}
    assert {"l1", "l2", "l3"} <= ids and any(i.startswith("pg_") for i in ids)
    assert {"e1", "e2"} <= {e["id"] for e in out["encounters"]}


def test_reachability_rule_catches_broken_key():
    out = fill_plan(good_plan(), 5, config=ProcgenConfig(locks=2))
    assert out["procgen"]["locks"]
    k = out["procgen"]["locks"][0][2]
    gone = copy.deepcopy(out)
    del gone["procgen"]["keys"][k]
    probs = check_procgen_reachability(gone)
    assert any(p.severity is Severity.ERROR and "no key" in p.message for p in probs)
    v = score_plan_procgen(gone)
    # review item 8: the default score_plan now runs the procgen checks too
    assert v.verdict == "repair" and score_plan(gone).verdict == "repair"


def test_pacing_rule_flags_spike():
    out = fill_plan(good_plan(), 2)
    path = out["procgen"]["layout"]["critical_path"]
    mid = next(lv for lv in out["levels"] if lv["id"] == path[1])
    out["encounters"].append({"id": "spike", "system": "combat", "enemy_hp": 70, "enemy_dps": 10})
    mid["encounters"] = ["spike"]
    msgs = [p.message for p in check_procgen(out) if p.rule == "procgen_pacing"]
    assert any("spike" in m for m in msgs)


def test_config_from_mapping():
    cfg = ProcgenConfig.from_mapping({"dungeon": "graph", "locks": 1, "graph": {"rooms": 6},
                                      "encounters": {"pacing": {"jitter": 0.0}}})
    assert cfg.graph.rooms == 6 and cfg.encounters.pacing.jitter == 0.0
    with pytest.raises(ProcgenError):
        ProcgenConfig.from_mapping({"nope": 1})
    with pytest.raises(ProcgenError):
        ProcgenConfig.from_mapping({"graph": {"nope": 1}})
    p = good_plan()
    p["procgen_config"] = {"dungeon": "graph", "graph": {"rooms": 6}}
    assert fill_plan(p, 1)["procgen"]["layout"]["method"] == "graph"


def test_bad_player_rejected():
    p = good_plan()
    p["player"] = {"hp": 0, "dps": 1}
    with pytest.raises(ProcgenError):
        fill_plan(p, 1)
    with pytest.raises(ProcgenError):
        fill_plan([], 1)  # type: ignore[arg-type]
