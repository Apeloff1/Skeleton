"""Iteration 108 — Phase 2.5: 135 axes, 15 tools, precise/consecutive pipeline, AAA quality gate."""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
UF_BASE = f"{BASE_URL}/api/galaxy-studio/forge"
TOOLS_BASE = f"{BASE_URL}/api/galaxy-studio/tools"

NEW_AXES = [
    "biological", "biological_aberrant", "biological_monstrosity",
    "starlight", "cosmic", "subsurface", "meteorite",
    "weight", "size", "height", "legendary_flair",
]
EXPECTED_TOOLS = {
    "npc", "world", "vfx", "combat", "props", "loot", "scifi", "nature", "ui",
    "magic", "vehicle", "architecture", "wearable", "consumable", "boss",
}
PIPELINE_KEYS = ["plan", "forge", "style", "variate", "enrich", "validate", "mount"]


# ── styles axes ──
class TestStylesAxes:
    def test_total_axes_around_135_and_new_axes_present(self):
        r = requests.get(f"{UF_BASE}/styles", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        axes = d.get("axes") or d.get("style_axes") or []
        if isinstance(axes, list):
            ax_map = {a["key"]: a for a in axes}
        else:
            ax_map = axes
        # ~135 total axes
        assert 130 <= len(ax_map) <= 145, f"axes count={len(ax_map)}"
        # All 12 new axes present + each has options
        for k in NEW_AXES:
            assert k in ax_map, f"missing new axis: {k}"
            opts = ax_map[k].get("options") or []
            n = len(opts) if isinstance(opts, list) else len(opts.keys())
            assert n >= 3, f"axis {k} has only {n} options"


# ── tools list ──
class TestToolsList:
    def test_15_tools_with_nonzero_counts(self):
        r = requests.get(TOOLS_BASE, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        tools = d.get("tools") or []
        keys = {t["key"] for t in tools}
        assert EXPECTED_TOOLS.issubset(keys), f"missing tools: {EXPECTED_TOOLS - keys}"
        assert len(tools) == 15
        for t in tools:
            assert t.get("category_count", 0) > 0
            assert t.get("axis_count", 0) > 0
        # 7-step pipeline still present
        assert len(d.get("pipeline") or []) == 7
        assert [s["key"] for s in d["pipeline"]] == PIPELINE_KEYS


# ── catalogs for new tools include scoped layered axes ──
class TestNewToolsCatalogs:
    @pytest.mark.parametrize(
        "tool,must_have_axes",
        [
            ("magic", {"cosmic", "starlight", "subsurface"}),
            ("boss", {"biological_monstrosity"}),
            ("wearable", {"weight", "size", "height", "legendary_flair"}),
        ],
    )
    def test_catalog_axes_and_categories(self, tool, must_have_axes):
        r = requests.get(f"{TOOLS_BASE}/{tool}/catalog", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        cats = d.get("categories") or []
        assert len(cats) >= 1
        # thumb palette 5 colours
        for c in cats[:5]:
            tp = c.get("thumb_palette") or []
            assert len(tp) == 5
            for hx in tp:
                assert isinstance(hx, str) and hx.startswith("#")
        axes_keys = {a["key"] for a in d.get("axes") or []}
        missing = must_have_axes - axes_keys
        assert not missing, f"{tool} missing axes {missing}"


# ── pipeline: consecutive vs precise ──
class TestMagicPipeline:
    def test_consecutive_count_8(self):
        body = {"build_id": "qa_c", "count": 8,
                "axes": {"cosmic": "nebula", "legendary_flair": "mythic"}}
        r = requests.post(f"{TOOLS_BASE}/magic/pipeline", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mode") == "consecutive"
        assert d.get("forged") == 8
        assert d.get("mounted") is True
        applied = d.get("applied_axes") or {}
        assert applied.get("cosmic") == "nebula"
        assert applied.get("legendary_flair") == "mythic"
        trace = d.get("pipeline") or []
        assert len(trace) == 7
        assert all(s.get("ok") is True for s in trace)

    def test_precise_uses_real_category_keys(self):
        cat_r = requests.get(f"{TOOLS_BASE}/magic/catalog", timeout=20)
        assert cat_r.status_code == 200
        keys = [c["key"] for c in cat_r.json()["categories"][:3]]
        assert len(keys) == 3
        body = {"build_id": "qa_p", "mode": "precise",
                "categories": keys, "axes": {"cosmic": "galaxy"}}
        r = requests.post(f"{TOOLS_BASE}/magic/pipeline", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mode") == "precise"
        assert d.get("forged") == 3
        assert d.get("categories_used") == 3
        assert d.get("mounted") is True
        assert (d.get("applied_axes") or {}).get("cosmic") == "galaxy"
        assert all(s.get("ok") is True for s in d.get("pipeline") or [])


# ── forge/asset accepts new axes JSON ──
class TestForgeAssetNewAxes:
    def test_asset_with_new_axes(self):
        axes_str = json.dumps({
            "biological": "chitinous",
            "cosmic": "nebula",
            "legendary_flair": "legendary",
        })
        r = requests.get(
            f"{UF_BASE}/asset",
            params={"id": "sword", "era": "fantasy", "seed": 5,
                    "axes": axes_str, "full": 1},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("geometry"), list)
        assert len(d["geometry"]) >= 1


# ── AAA quality gate (ONE LLM call) ──
class TestQualityGate:
    def test_llm_generate_returns_quality_metadata(self):
        r = requests.post(
            f"{UF_BASE}/generate",
            json={"category": "sword", "era": "fantasy", "use_llm": True},
            timeout=180,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
        d = r.json()
        # fidelity_score is int in [0,100]
        fs = d.get("fidelity_score")
        assert isinstance(fs, int), f"fidelity_score not int: {fs!r}"
        assert 0 <= fs <= 100
        # quality_passed bool
        assert isinstance(d.get("quality_passed"), bool)
        # palette ≥ 5
        palette = d.get("palette") or []
        assert isinstance(palette, list) and len(palette) >= 5, f"palette len={len(palette)}"
        # materials ≥ 3
        materials = d.get("materials") or []
        assert isinstance(materials, list) and len(materials) >= 3, f"materials len={len(materials)}"
        # verbose descriptor ~128 words (allow ≥ 80)
        desc = d.get("descriptor") or ""
        assert isinstance(desc, str) and len(desc.split()) >= 80, \
            f"descriptor only {len(desc.split())} words"
