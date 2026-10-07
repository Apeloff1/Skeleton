"""Tests for the Item Foundry (Agent Item Creation Workflow)."""
from core import item_foundry as f


def _agent(code="A0001", cat="visual_design", name="Vega"):
    return {"code": code, "agent": name, "category": cat}


def test_forge_item_is_complete():
    it = f.forge_item("b1", "world", _agent(), {"genre": "rpg"}, seed=1, base_grade=2)
    for key in ("item_id", "name", "definition", "skin", "code", "placement"):
        assert it[key]
    assert it["definition"]["archetype"]
    assert len(it["skin"]["palette"]) >= 3
    assert "export const" in it["code"]
    assert it["placement"]["region"]


def test_grade_above_base():
    for s in range(6):
        it = f.forge_item("b1", "mechanics", _agent(), {"genre": "rpg", "base_grade": 2}, seed=s, base_grade=2)
        assert it["grade"] > 2


def test_deterministic():
    a = f.forge_item("b1", "world", _agent(), {"genre": "rpg"}, seed=7)
    b = f.forge_item("b1", "world", _agent(), {"genre": "rpg"}, seed=7)
    assert a == b


def test_validate_accepts_good_item():
    it = f.forge_item("b1", "world", _agent(), {"genre": "rpg"}, seed=1, base_grade=2)
    v = f.validate_and_reflect(it, {"genre": "rpg"}, base_grade=2)
    assert v["accepted"] is True
    assert v["issues"] == []


def test_validate_rejects_low_grade():
    it = f.forge_item("b1", "world", _agent(), {"genre": "rpg"}, seed=1, base_grade=2)
    it["grade"] = 1
    v = f.validate_and_reflect(it, {"genre": "rpg"}, base_grade=2)
    assert v["accepted"] is False


def test_forge_build_all_agents_all_stages():
    m = f.forge_build("b1", {"genre": "rpg", "base_grade": 2}, seed=1, platoon_size=4, persist=False)
    assert {s["stage"] for s in m["stages"]} == set(f.ITEM_STAGES)
    # every agent in every item-bearing stage produced an item
    assert m["totals"]["items_forged"] == len(f.ITEM_STAGES) * 4
    assert m["totals"]["accepted"] == m["totals"]["items_forged"]  # all valid
    assert m["totals"]["grade_above_base"] is True
    assert m["totals"]["distinct_archetypes"] >= 2


def test_variety_across_agents():
    agents = [_agent(f"A{i:04d}", "visual_design") for i in range(8)]
    names = {f.forge_item("b1", "world", a, {"genre": "rpg"}, seed=1)["name"] for a in agents}
    assert len(names) >= 5  # wide variety
