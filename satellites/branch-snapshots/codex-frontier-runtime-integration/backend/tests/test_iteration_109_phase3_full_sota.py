"""Phase 3 Full SOTA backend regression — verifies all axes ≥9 options,
axis-tree groupings, 22 tools, per-build Style Pack persistence, and pipeline
honouring applied pack axes."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")

EXPECTED_NEW_TOOLS = {
    "magic", "vehicle", "architecture", "wearable", "consumable", "boss",
    "terrain", "foliage", "environment", "decor", "icon", "aquatic", "siege",
}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── /forge/styles — 135 axes, all >=9 options ──────────────────────────
class TestForgeStyles:
    def test_styles_axes_count_and_option_floor(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/forge/styles", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        axes = d.get("axes") or d.get("style_axes") or []
        # support either shape — list of {key,options} or dict {key:{options}}
        if isinstance(axes, dict):
            axes_list = [{"key": k, **v} for k, v in axes.items()]
        else:
            axes_list = axes
        assert len(axes_list) >= 130, f"expected ~135 axes, got {len(axes_list)}"
        # No axis under 9 options
        below = [a for a in axes_list if len(a.get("options", [])) < 9]
        assert not below, f"axes with <9 options: {[(a.get('key'), len(a.get('options', []))) for a in below[:5]]}"
        total_opts = sum(len(a.get("options", [])) for a in axes_list)
        assert total_opts >= 1200, f"expected >=1200 options total, got {total_opts}"


# ── /forge/axis-tree — groups returned ─────────────────────────────────
class TestAxisTree:
    def test_axis_tree_groups(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/forge/axis-tree", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        groups = d.get("groups") or d.get("tree") or []
        assert groups, "axis-tree returned no groups"
        # check we have a few of the expected group families
        labels = " ".join(str(g.get("group", g.get("label", g.get("name", "")))).lower() for g in groups)
        for needle in ["look", "material", "magic", "biolog"]:
            assert needle in labels, f"missing group containing '{needle}'. got: {labels[:300]}"
        # count axes + options across the tree
        total_axes = 0
        total_options = 0
        for g in groups:
            for a in (g.get("axes") or []):
                total_axes += 1
                total_options += len(a.get("options") or [])
        assert total_axes >= 130, f"axis_count via tree only {total_axes}"
        assert total_options >= 1200, f"option_count via tree only {total_options}"


# ── /tools — 22 tools with new ones ────────────────────────────────────
class TestTools:
    def test_tools_22_and_new_present(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/tools", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        tools = d.get("tools") or []
        assert len(tools) >= 22, f"expected >=22 tools, got {len(tools)}"
        keys = {t.get("key") for t in tools}
        missing = EXPECTED_NEW_TOOLS - keys
        assert not missing, f"missing tools: {missing}"
        # Every tool has non-zero category_count and axis_count
        weak = [t["key"] for t in tools if not t.get("category_count") or not t.get("axis_count")]
        assert not weak, f"tools with 0 category_count or axis_count: {weak}"


# ── /forge/style-pack — POST + GET ─────────────────────────────────────
class TestStylePackPerBuild:
    BUILD = "qa_sp1"

    def test_save_and_list_pack(self, api):
        payload = {
            "build_id": self.BUILD,
            "label": "Cosmic Gold",
            "axes": {"cosmic": "galaxy", "legendary_flair": "mythic"},
        }
        r = api.post(f"{BASE_URL}/api/galaxy-studio/forge/style-pack",
                     json=payload, timeout=15)
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved.get("id") or saved.get("pack", {}).get("id"), f"no id in save response: {saved}"

        r2 = api.get(f"{BASE_URL}/api/galaxy-studio/forge/style-pack",
                     params={"build_id": self.BUILD}, timeout=15)
        assert r2.status_code == 200, r2.text
        listed = r2.json()
        packs = listed.get("packs") or []
        assert any(p.get("label") == "Cosmic Gold" for p in packs), \
            f"saved pack not returned in list: {packs}"


# ── boss tool pipeline with applied pack axes ──────────────────────────
class TestBossPipelineWithAxes:
    def test_boss_pipeline_keeps_applicable_axes(self, api):
        payload = {
            "build_id": "qa_boss",
            "count": 6,
            "mount": True,
            "mode": "consecutive",
            "axes": {
                "biological_monstrosity": "tentacled",
                "legendary_flair": "mythic",
            },
        }
        r = api.post(f"{BASE_URL}/api/galaxy-studio/tools/boss/pipeline",
                     json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("forged") == 6, f"expected forged=6, got {d.get('forged')}: {d}"
        assert d.get("mounted") is True, f"not mounted: {d}"
        applied = d.get("applied_axes") or {}
        # at least one of the requested axes must be preserved as applicable
        assert any(k in applied for k in ("biological_monstrosity", "legendary_flair")), \
            f"none of the requested axes survived applicable filter: {applied}"
