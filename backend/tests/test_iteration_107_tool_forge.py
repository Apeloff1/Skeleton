"""Iteration 107 — Tool Forge framework + Variations + expanded 5 axes."""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
TOOLS_BASE = f"{BASE_URL}/api/galaxy-studio/tools"
UF_BASE = f"{BASE_URL}/api/galaxy-studio/forge"

EXPECTED_TOOLS = {"npc", "world", "vfx", "combat", "props", "loot", "scifi", "nature", "ui"}
PIPELINE_KEYS = ["plan", "forge", "style", "variate", "enrich", "validate", "mount"]


class TestToolsList:
    def test_tools_list_shape(self):
        r = requests.get(TOOLS_BASE, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "tools" in data and "pipeline" in data
        keys = {t["key"] for t in data["tools"]}
        assert EXPECTED_TOOLS.issubset(keys), f"Missing tools: {EXPECTED_TOOLS - keys}"
        assert len(data["tools"]) == 9

        for t in data["tools"]:
            for f in ("key", "label", "icon", "blurb", "category_count", "axis_count"):
                assert f in t, f"missing field {f} in tool {t.get('key')}"
            assert t["category_count"] > 0
            assert t["axis_count"] > 0

        # pipeline must be 7 steps
        assert len(data["pipeline"]) == 7
        assert [s["key"] for s in data["pipeline"]] == PIPELINE_KEYS


class TestToolsCatalog:
    @pytest.mark.parametrize("tool", ["npc", "vfx", "combat"])
    def test_catalog_shape(self, tool):
        r = requests.get(f"{TOOLS_BASE}/{tool}/catalog", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("tool", {}).get("key") == tool
        assert len(d.get("pipeline", [])) == 7
        cats = d.get("categories") or []
        assert len(cats) >= 1
        for c in cats:
            assert isinstance(c.get("thumb_palette"), list)
            assert len(c["thumb_palette"]) == 5
            for hx in c["thumb_palette"]:
                assert isinstance(hx, str) and hx.startswith("#")
        axes = d.get("axes") or []
        assert len(axes) >= 1
        for a in axes:
            assert "key" in a and "label" in a and isinstance(a.get("options"), list)

    def test_combat_axes_scope(self):
        """combat must include metal_grade/engraving and exclude illuminescence."""
        r = requests.get(f"{TOOLS_BASE}/combat/catalog", timeout=20)
        assert r.status_code == 200
        keys = {a["key"] for a in r.json().get("axes", [])}
        assert "metal_grade" in keys
        assert "engraving" in keys
        # not applicable for weapons → must be dropped
        assert "illuminescence" not in keys


class TestToolAsset:
    def test_asset_light_vs_full(self):
        # First get a valid category key from combat
        cat = requests.get(f"{TOOLS_BASE}/combat/catalog", timeout=20).json()
        cat_key = cat["categories"][0]["key"]

        # light (default)
        r_light = requests.get(
            f"{TOOLS_BASE}/combat/asset",
            params={"id": cat_key, "seed": 3},
            timeout=20,
        )
        assert r_light.status_code == 200
        light = r_light.json()
        assert light.get("tool") == "combat"
        assert "geometry" not in light
        assert "thumb_palette" in light
        assert "part_count" in light and isinstance(light["part_count"], int)

        # full
        r_full = requests.get(
            f"{TOOLS_BASE}/combat/asset",
            params={"id": cat_key, "full": 1, "seed": 3},
            timeout=20,
        )
        assert r_full.status_code == 200
        full = r_full.json()
        assert full.get("tool") == "combat"
        assert isinstance(full.get("geometry"), list)
        assert len(full["geometry"]) >= 1


class TestCombatPipeline:
    def test_combat_pipeline_drops_inapplicable_axes(self):
        body = {
            "build_id": "qa_tool_build",
            "era": "fantasy",
            "seed": 2,
            "count": 8,
            "mount": True,
            "axes": {
                "metal_grade": "mythril",
                "engraving": "runic",
                "illuminescence": "brilliant",
            },
        }
        r = requests.post(
            f"{TOOLS_BASE}/combat/pipeline",
            json=body,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mounted") is True
        assert (d.get("forged") or 0) >= 1
        applied = d.get("applied_axes") or {}
        assert applied.get("metal_grade") == "mythril"
        assert applied.get("engraving") == "runic"
        assert "illuminescence" not in applied
        trace = d.get("pipeline") or []
        assert len(trace) == 7
        for s in trace:
            assert s.get("ok") is True


class TestForgeAxesAndExpansion:
    def test_forge_asset_axes_json_query(self):
        axes_str = json.dumps({"illuminescence": "brilliant"})
        r = requests.get(
            f"{UF_BASE}/asset",
            params={"id": "sword", "era": "fantasy", "seed": 17, "axes": axes_str, "full": 1},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("geometry"), list)
        assert len(d["geometry"]) >= 1

    def test_expanded_axes_have_15_to_17_options(self):
        r = requests.get(f"{UF_BASE}/styles", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # The shape varies — find axes lookup
        axes = data.get("axes") or data.get("style_axes") or []
        # Normalize to dict by key
        if isinstance(axes, list):
            ax_map = {a["key"]: a for a in axes}
        else:
            ax_map = axes
        for key in ("illuminescence", "decals", "symbols", "scribbles", "sparkles"):
            assert key in ax_map, f"axis {key} missing"
            opts = ax_map[key].get("options") or []
            n = len(opts) if isinstance(opts, list) else len(opts.keys())
            assert 14 <= n <= 20, f"{key} has {n} options (expected ~15-17)"
