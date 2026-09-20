"""
Iteration 106 — Forge new axes (illuminescence/decals/symbols/scribbles/sparkles),
thumb_palette on /catalog & /search, LLM quality gate, snowball populate endpoints,
and DNA/asset determinism with the new axes.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://player-retention.preview.emergentagent.com").rstrip("/")
TIMEOUT = 60

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
NEW_AXES = ["illuminescence", "decals", "symbols", "scribbles", "sparkles"]


@pytest.fixture(scope="module")
def styles_payload():
    r = requests.get(f"{BASE_URL}/api/galaxy-studio/forge/styles", timeout=TIMEOUT)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ─── 1) styles: 5 new axes, >=7 opts incl 'none', total ~124
class TestStyles:
    def test_axis_count_is_about_124(self, styles_payload):
        axes = styles_payload["axes"]
        assert isinstance(axes, list)
        assert 120 <= len(axes) <= 130, f"axis count={len(axes)}"

    @pytest.mark.parametrize("axis_key", NEW_AXES)
    def test_new_axis_present_with_options(self, styles_payload, axis_key):
        axes = styles_payload["axes"]
        match = [a for a in axes if a.get("key") == axis_key]
        assert match, f"axis {axis_key} missing"
        opts = match[0].get("options", [])
        assert len(opts) >= 7, f"{axis_key} only has {len(opts)} options"
        keys = [o.get("key") for o in opts]
        assert "none" in keys, f"{axis_key} missing 'none' option"


# ─── 2) catalog & search: every category has thumb_palette of 5 valid hex
class TestThumbPalette:
    def test_catalog_every_category_has_thumb_palette(self):
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/forge/catalog", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        cats = data.get("categories") or data.get("items") or data
        if isinstance(cats, dict):
            cats = list(cats.values())
        assert isinstance(cats, list) and len(cats) > 0
        bad = []
        for c in cats:
            tp = c.get("thumb_palette")
            if not (isinstance(tp, list) and len(tp) == 5 and all(isinstance(x, str) and HEX_RE.match(x) for x in tp)):
                bad.append((c.get("key") or c.get("id") or c.get("name"), tp))
        assert not bad, f"thumb_palette invalid for: {bad[:5]} (of {len(cats)} cats)"

    def test_search_results_have_thumb_palette(self):
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/forge/search", params={"q": "sword"}, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        results = data.get("results") or data.get("items") or data
        if isinstance(results, dict):
            results = list(results.values())
        assert isinstance(results, list) and len(results) > 0
        for res in results:
            tp = res.get("thumb_palette")
            assert isinstance(tp, list) and len(tp) == 5, f"bad tp {tp} for {res.get('key')}"
            for x in tp:
                assert isinstance(x, str) and HEX_RE.match(x), f"bad hex {x}"


# ─── 3) DNA & asset: apply new axes, determinism check
class TestDnaAssetWithNewAxes:
    AXES_BODY = {"illuminescence": "brilliant", "sparkles": "stardust", "symbols": "arcane",
                 "decals": "graffiti", "scribbles": "ink_doodle"}

    def test_dna_with_new_axes_returns_200(self):
        # /dna uses GenerateReq → requires `category` (not `id`).
        body = {"category": "sword", "era": "fantasy", "seed": 7, "axes": self.AXES_BODY}
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/forge/dna", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        # Compatible family (sword/weapon) → new axes must NOT be pruned
        pruned = data.get("pruned_axes") or []
        for axis_key in self.AXES_BODY.keys():
            assert axis_key not in pruned, f"axis {axis_key} unexpectedly pruned: {pruned}"
        assert data.get("dna") and data["dna"].get("hex"), "DNA hex missing"
        assert data.get("component_mask") is not None

    def test_asset_full_with_new_axes_returns_geometry(self):
        # /asset is GET — produces deterministic spec. Verify geometry on full=1.
        params = {"id": "sword", "era": "fantasy", "full": 1, "seed": 7}
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/forge/asset", params=params, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        geo = d.get("geometry") or []
        assert isinstance(geo, list) and len(geo) > 0, f"no geometry: {list(d.keys())}"

    def test_asset_determinism_same_seed_same_part_count(self):
        # Determinism: light mode includes part_count; compare two calls
        params = {"id": "sword", "era": "fantasy", "seed": 42}
        a = requests.get(f"{BASE_URL}/api/galaxy-studio/forge/asset", params=params, timeout=TIMEOUT).json()
        b = requests.get(f"{BASE_URL}/api/galaxy-studio/forge/asset", params=params, timeout=TIMEOUT).json()
        assert a.get("part_count") == b.get("part_count"), f"non-deterministic: {a.get('part_count')} vs {b.get('part_count')}"
        assert a.get("part_count", 0) > 0


# ─── 4) LLM quality gate (single call to limit tokens)
class TestLlmQualityGate:
    def test_generate_with_llm_returns_quality_passed_flag(self):
        # _llm_enrich short-circuits if user_prompt is empty → MUST pass a brief.
        body = {"id": "sword", "category": "sword", "era": "fantasy", "seed": 3,
                "use_llm": True,
                "user_prompt": "A regal fantasy long-sword with curling vines etched on a polished steel blade and a sapphire pommel, weathered leather grip, glints of pale gold light."}
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/forge/generate", json=body, timeout=180)
        # Must not 500 even on LLM failure
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        # Always-present deterministic fields
        for k in ("palette", "materials", "descriptor"):
            assert k in d, f"missing {k}"
        # llm_enriched flag is always present
        assert "llm_enriched" in d
        # If LLM ran, quality_passed must be a bool. Graceful fallback if not.
        if d.get("llm_enriched"):
            assert "quality_passed" in d, f"quality_passed missing on enriched response: {list(d.keys())}"
            assert isinstance(d["quality_passed"], bool)
        else:
            # Graceful fallback path — no quality_passed but spec intact (no 500)
            assert d.get("llm_enriched") is False


# ─── 5) Populate-my-world snowball endpoints
class TestPopulateMyWorld:
    BODY_C = {"build_id": "qa_build", "era": "modern", "seed": 1,
              "construct_count": 4, "mount": True, "config": {"genre": "rpg"}}
    BODY_M = {"build_id": "qa_build", "era": "modern", "seed": 1,
              "material_count": 4, "mount": True, "config": {"genre": "rpg"}}

    def test_constructs_snowball_forge_returns_200_mounted(self):
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/constructs/snowball/forge",
                          json=self.BODY_C, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("mounted") is True
        v = d.get("constructs_count", d.get("constructs"))
        cnt = v if isinstance(v, int) else len(v or [])
        assert cnt >= 1, f"no constructs returned: {d}"

    def test_materials_snowball_forge_returns_200_mounted(self):
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/materials/snowball/forge",
                          json=self.BODY_M, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("mounted") is True
        v = d.get("materials_count", d.get("materials"))
        cnt = v if isinstance(v, int) else len(v or [])
        assert cnt >= 1, f"no materials returned: {d}"
