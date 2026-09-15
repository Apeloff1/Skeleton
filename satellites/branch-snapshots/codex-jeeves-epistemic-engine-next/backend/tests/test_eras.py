"""Tests for era-sensitivity: catalog, era-aware assets, choices ledger."""
from core import asset_forge
from core import eras
from core import game_choices
from core import snowball_forge as sf


def test_era_catalog_complete():
    cat = eras.catalog()
    keys = [e["key"] for e in cat]
    assert keys == ["8bit", "16bit", "early3d", "64bit", "earlyhd", "modern", "nextgen"]
    # ordered earliest → latest
    assert [e["order"] for e in cat] == sorted(e["order"] for e in cat)
    # next-gen reaches the 250-500 GB range
    ng = eras.get_era("nextgen")
    assert ng["storage_bytes"][0] >= 250 * 1024**3
    assert ng["storage_bytes"][1] <= 500 * 1024**3


def test_era_alias_resolution():
    assert eras.get_era("8-Bit")["key"] == "8bit"
    assert eras.get_era("PS5")["key"] == "modern"
    assert eras.get_era(None)["key"] == eras.DEFAULT_ERA
    assert eras.get_era("garbage")["key"] == eras.DEFAULT_ERA


def test_2d_eras_skip_meshes():
    item = {"item_id": "i1", "stage": "world",
            "skin": {"era": "8bit", "palette": ["#111"], "material": "x"}}
    pack = asset_forge.forge_assets_for_item(item, seed=1, era="8bit")
    types = {a["type"] for a in pack}
    assert "lod_mesh" not in types and "normal_map" not in types
    assert types <= set(eras.get_era("8bit")["asset_types"])
    # chiptune audio format for 8-bit
    sfx = [a for a in pack if a["type"] == "sfx"][0]
    assert sfx["format"] == "nsf"


def test_modern_era_full_pack_and_polys():
    item = {"item_id": "i2", "stage": "assets",
            "skin": {"era": "modern", "palette": ["#111", "#222"]}}
    pack = asset_forge.forge_assets_for_item(item, seed=1, era="modern")
    assert len(pack) == 10
    mesh = [a for a in pack if a["type"] == "lod_mesh"][0]
    assert mesh["poly"] > 0  # 3D era has polygons


def test_era_size_scales_up():
    base = {"item_id": "i", "stage": "world", "skin": {"palette": ["#1"]}}
    small = asset_forge.forge_build_assets("b8", [{**base, "skin": {"era": "8bit", "palette": ["#1"]}}], era="8bit")
    big = asset_forge.forge_build_assets("bN", [{**base, "skin": {"era": "nextgen", "palette": ["#1"]}}], era="nextgen", persist=False)
    assert big["total_bytes"] > small["total_bytes"]


def test_escalate_is_era_sensitive_8bit():
    m = sf.escalate("era_test_8bit", genre="rpg", seed=4, era="8bit", persist=False)
    assert m["era"] == "8bit"
    # 8-bit pack has fewer asset types than modern → fewer assets per item
    assert m["totals"]["assets_per_item"] == len(eras.get_era("8bit")["asset_types"])
    assert m["totals"]["assets"] == m["totals"]["gamefiles"] * m["totals"]["assets_per_item"]
    # storage budget tracked against the era cap
    assert m["storage"]["cap_bytes"] == eras.get_era("8bit")["storage_bytes"][1]
    assert "used_pct" in m["storage"]
    # era compliance gate present in quality
    floors = [r["grade_floor"] for r in m["ladder"]]
    assert floors == sorted(floors)


def test_choice_ledger_logged_and_parsed():
    bid = "era_choice_test"
    game_choices.clear(bid)
    m = sf.escalate(bid, genre="platformer", seed=2, era="16bit", persist=False)
    # game_setup + 6 stage_forge entries logged
    led = m["choices"]
    kinds = [e["kind"] for e in led]
    assert "game_setup" in kinds
    assert kinds.count("stage_forge") == 6
    # awareness parses era + all stages
    aw = m["awareness"]
    assert aw["era"] == "16bit"
    assert len(aw["stages_done"]) == 6
    assert aw["choices_logged"] == len(led)


def test_asset_capacity_outshine_anchors():
    assert eras.get_era("8bit")["asset_capacity"] >= 1400
    assert eras.get_era("modern")["asset_capacity"] >= 1_400_000
    for k in eras.ERA_ORDER:
        assert eras.get_era(k)["outshine_pct"] == 40
    caps = [eras.get_era(k)["asset_capacity"] for k in eras.ERA_ORDER]
    assert caps == sorted(caps)  # capacity grows era over era


def test_era_ladder_growth_story():
    d = sf.era_ladder("ladtest", "8bit", "modern", genre="rpg", seed=1)
    assert d["a"]["era"] == "8bit" and d["b"]["era"] == "modern"
    assert d["b"]["storage_bytes"] > d["a"]["storage_bytes"]
    assert d["storage_multiplier"] > 1
    assert d["capacity_growth_pct"] > 0
    assert "headline" in d


def test_forge_registry_deferred_catalog():
    from core import forge_registry
    cat = forge_registry.catalog()
    assert cat["deferred_count"] > 150
    assert cat["active_count"] >= 1
    keys = [f["key"] for f in cat["deferred"]]
    assert "clothing" in keys and "spaceship" in keys
    assert len(keys) == len(set(keys))  # de-duped
