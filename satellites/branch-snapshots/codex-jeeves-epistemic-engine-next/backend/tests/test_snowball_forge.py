"""Tests for the escalating snowball forge: quality gates, parity, 10× assets."""
from core import asset_forge
from core import forge_quality as gates
from core import snowball_forge as sf


def _item(grade=4, stage="world", fidelity=0.9, region="Ashen Vale"):
    return {
        "grade": grade, "stage": stage,
        "skin": {"fidelity": fidelity, "palette": ["#111", "#222", "#333"],
                 "material": "alloy", "vfx": "glow"},
        "code": "export const itm_x = {};",
        "placement": {"region": region},
        "item_id": "itm_x",
    }


# ── quality gates ─────────────────────────────────────────────────────────
def test_quality_gate_passes_good_item():
    v = gates.evaluate(_item(), stage_index=0, stage_floor_grade=2,
                       gdd_stages={"world"}, regions=["Ashen Vale"])
    assert v["passed"] is True
    assert v["score"] == 1.0
    assert v["failed_gates"] == []


def test_quality_gate_rejects_low_grade_and_parity():
    v = gates.evaluate(_item(grade=2), stage_index=0, stage_floor_grade=2,
                       gdd_stages={"narrative"}, regions=["Nowhere"])
    assert v["passed"] is False
    assert "grade_escalation" in v["failed_gates"]
    assert "gdd_parity" in v["failed_gates"]
    assert "placement_valid" in v["failed_gates"]


def test_fidelity_floor_rises():
    assert gates.fidelity_floor(0) < gates.fidelity_floor(5)


# ── 10× assets ────────────────────────────────────────────────────────────
def test_asset_pack_is_10x():
    pack = asset_forge.forge_assets_for_item(_item(), seed=1)
    assert len(pack) == 10
    assert len({a["type"] for a in pack}) == 10
    assert all(a["palette"] for a in pack)


def test_asset_determinism():
    a = asset_forge.forge_assets_for_item(_item(), seed=3)
    b = asset_forge.forge_assets_for_item(_item(), seed=3)
    assert a == b


# ── escalating snowball ───────────────────────────────────────────────────
def test_escalate_full_build():
    m = sf.escalate("snow_test", genre="rpg", seed=5, platoon_size=4, persist=False)
    # 6 stages, one GDD section per built stage → parity locked every step
    assert len(m["ladder"]) == 6
    assert m["parity_locked"] is True
    assert m["parity_pct"] == 100
    assert m["gdd_sections"] == 6
    # grade floor escalates across stages
    floors = [r["grade_floor"] for r in m["ladder"]]
    assert floors == sorted(floors)
    assert floors[0] < floors[-1]
    # 10× assets per accepted gamefile
    assert m["totals"]["assets"] == m["totals"]["gamefiles"] * 10
    assert m["totals"]["assets_per_item"] == 10
    # every stage section is grounded on the prior stages (snowball)
    assert m["ladder"][-1]["built_on"]  # last stage built on earlier ones


def test_escalate_grade_non_decreasing():
    m = sf.escalate("snow_test2", genre="platformer", seed=2, persist=False)
    maxes = [r["max_grade"] for r in m["ladder"]]
    assert all(maxes[i] <= maxes[i + 1] for i in range(len(maxes) - 1))
    assert m["grade_escalating"] is True
