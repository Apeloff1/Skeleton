"""Tests for the Vault GDD + Mount module (gamefiles → GDD)."""
from core import item_foundry as foundry
from core import vault_gdd as vg


def _items(build_id="vg1", n_per_stage=3):
    man = foundry.forge_build(build_id, {"genre": "rpg", "base_grade": 2},
                              seed=3, platoon_size=n_per_stage, persist=False)
    items = []
    for s in man["stages"]:
        items.extend(s["items"])
    return items


def test_foundry_stats_shapes():
    items = _items()
    st = vg.foundry_stats(items)
    assert st["total_items"] == len(items)
    assert st["distinct_archetypes"] >= 1
    assert st["grade_histogram"]
    assert all(g["grade"] > 2 for g in st["grade_histogram"])  # all above base
    assert st["avg_fidelity"] > 0
    assert st["top_agents"]


def test_foundry_stats_empty():
    st = vg.foundry_stats([])
    assert st["total_items"] == 0
    assert st["avg_fidelity"] == 0.0
    assert st["grade_histogram"] == []


def test_compile_gdd_contains_sections_and_items():
    items = _items()
    gdd = vg.compile_gdd({"title": "Aether RPG", "genre": "rpg", "build_id": "vg1"},
                         items, {})
    assert "# 🎮 Game Design Document — Aether RPG" in gdd
    assert "## 3. Artifacts & Loot" in gdd
    assert "Vault Knowledge Grounding" in gdd
    assert "Palette Board" in gdd
    # at least one forged item name shows up in the loot table
    assert items[0]["name"].split()[0] in gdd
    assert "| Item | Tier | Grade |" in gdd


def test_compile_gdd_handles_no_items():
    gdd = vg.compile_gdd({"title": "Empty", "genre": "rpg", "build_id": "vg2"}, [], {})
    assert "No gamefiles forged yet" in gdd


def test_mount_forges_when_empty():
    m = vg.mount("vg_mount_test", seed=1, forge_if_empty=True, persist=False)
    assert m["vault_gamefiles"] > 0
    assert m["forged_on_mount"] is True
    assert m["gdd_chars"] > 200
    assert m["coverage_pct"] > 0
    assert m["stages_covered"] <= m["stages_total"]
    assert m["stats"]["total_items"] == m["vault_gamefiles"]
