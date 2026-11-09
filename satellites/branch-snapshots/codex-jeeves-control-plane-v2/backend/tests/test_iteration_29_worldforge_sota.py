"""
Session 12+ — SOTA Worldforge upgrade tests:
  - Biomes count is now 16 (added river/lake/wetland)
  - Region response now includes: name, pois, rivers, stats(land_pct, water_pct,
    river_tiles, lakes, settlements, peak_elevation)
  - Determinism: same seed+coords → identical full response
  - Seamless tiling: rx=1 col 0 ~= rx=0 col last (low elev diff)
  - AI lore: POST /api/worldforge/lore returns {name, region, lore, model, summary}
  - Playable & Agent Memory regressions still green
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
TIMEOUT = 30


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── WORLDFORGE SOTA ──────────────────────────────────────────────────────────
class TestWorldforgeSOTA:
    def test_biomes_now_16(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/biomes", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["count"] == 16
        assert len(j["biomes"]) == 16
        ids = {b["id"] for b in j["biomes"]}
        # SOTA hydrology biomes must be present
        assert {"river", "lake", "wetland"} <= ids
        # core check
        assert {"ocean", "shallow", "beach", "desert", "savanna", "grassland",
                "shrubland", "temperate_forest", "tropical_forest", "taiga",
                "tundra", "bare", "snow"} <= ids

    def test_region_includes_name_pois_rivers_stats(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/region?seed=42&size=32&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        # name is a non-empty capitalized string
        assert isinstance(j.get("name"), str) and len(j["name"]) >= 3
        # pois list with required fields
        assert isinstance(j.get("pois"), list)
        for p in j["pois"]:
            assert {"x", "y", "kind", "icon", "name"} <= set(p.keys())
            assert isinstance(p["x"], int) and isinstance(p["y"], int)
        # rivers is a list of [x,y] pairs
        assert isinstance(j.get("rivers"), list)
        if j["rivers"]:
            assert len(j["rivers"][0]) == 2
        # stats include SOTA keys
        stats = j["stats"]
        for k in ("land_pct", "water_pct", "river_tiles", "lakes",
                  "settlements", "peak_elevation", "tiles", "biomes"):
            assert k in stats, f"missing stat key: {k}"
        # sanity: land_pct + water_pct ≈ 100
        assert abs((stats["land_pct"] + stats["water_pct"]) - 100.0) < 1.0
        # settlements count matches pois length
        assert stats["settlements"] == len(j["pois"])

    def test_tile_colors_hillshaded(self, s):
        """Land tiles should mostly NOT equal their base biome color (hillshade applied);
        water tiles must equal their base biome color."""
        r = s.get(f"{BASE_URL}/api/worldforge/region?seed=11&size=24&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT)
        j = r.json()
        biomes_r = s.get(f"{BASE_URL}/api/worldforge/biomes", timeout=TIMEOUT).json()
        base = {b["id"]: b["color"] for b in biomes_r["biomes"]}
        WATER = {"ocean", "shallow", "lake", "river"}
        land_total = 0
        land_diff = 0
        for row in j["grid"]:
            for t in row:
                if t["b"] in WATER:
                    assert t["c"] == base[t["b"]], f"water tile {t['b']} should keep base color"
                else:
                    land_total += 1
                    if t["c"] != base[t["b"]]:
                        land_diff += 1
        # at least some land tiles should be shaded different from base
        if land_total > 0:
            assert land_diff / land_total > 0.3, "hillshade barely applied to land tiles"

    def test_determinism_full_response(self, s):
        url = f"{BASE_URL}/api/worldforge/region?seed=7777&size=20&rx=3&ry=2&scale=0.08"
        a = s.get(url, timeout=TIMEOUT).json()
        b = s.get(url, timeout=TIMEOUT).json()
        assert a == b  # full response identical, not just grid

    def test_seamless_tiling_low_seam_diff(self, s):
        size, seed, scale = 24, 1234, 0.08
        a = s.get(f"{BASE_URL}/api/worldforge/region?seed={seed}&size={size}&rx=0&ry=0&scale={scale}",
                  timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region?seed={seed}&size={size}&rx=1&ry=0&scale={scale}",
                  timeout=TIMEOUT).json()
        diffs = [abs(a["grid"][y][size - 1]["e"] - b["grid"][y][0]["e"]) for y in range(size)]
        avg = sum(diffs) / len(diffs)
        assert avg < 0.20, f"seam discontinuous: avg elev diff {avg:.3f}"

    def test_post_region_matches_get(self, s):
        body = {"seed": 314, "size": 16, "rx": 2, "ry": 1, "scale": 0.08}
        a = s.post(f"{BASE_URL}/api/worldforge/region", json=body, timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region"
                  f"?seed=314&size=16&rx=2&ry=1&scale=0.08", timeout=TIMEOUT).json()
        assert a == b

    def test_name_deterministic_per_region(self, s):
        a = s.get(f"{BASE_URL}/api/worldforge/region?seed=42&size=16&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region?seed=42&size=16&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT).json()
        assert a["name"] == b["name"]
        # Different rx,ry → likely different name
        c = s.get(f"{BASE_URL}/api/worldforge/region?seed=42&size=16&rx=5&ry=7&scale=0.08",
                  timeout=TIMEOUT).json()
        # Not strictly required to differ, but extremely likely with this name space
        assert isinstance(c["name"], str)

    @pytest.mark.timeout(120)
    def test_ai_lore_live_llm(self, s):
        """LIVE LLM ~5-15s — single call, slowness is expected."""
        r = s.post(f"{BASE_URL}/api/worldforge/lore",
                   json={"seed": 1337, "size": 24, "rx": 0, "ry": 0, "scale": 0.07},
                   timeout=90)
        assert r.status_code == 200
        j = r.json()
        if "error" in j:
            pytest.fail(f"lore returned error: {j['error']} model={j.get('model')}")
        assert isinstance(j.get("name"), str) and len(j["name"]) >= 3
        assert isinstance(j.get("region"), dict)
        assert isinstance(j.get("lore"), str) and len(j["lore"]) > 30
        assert isinstance(j.get("model"), str) and len(j["model"]) > 0
        summary = j.get("summary") or {}
        assert "terrain" in summary and "settlements" in summary and "stats" in summary


# ── REGRESSION: PLAYABLE ─────────────────────────────────────────────────────
class TestPlayableRegression:
    def test_list(self, s):
        r = s.get(f"{BASE_URL}/api/playable/list", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "playables" in r.json()

    def test_leaderboard(self, s):
        assert s.get(f"{BASE_URL}/api/playable/leaderboard", timeout=TIMEOUT).status_code == 200

    def test_trending(self, s):
        assert s.get(f"{BASE_URL}/api/playable/trending", timeout=TIMEOUT).status_code == 200

    def test_get_bad_pid(self, s):
        r = s.get(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID_XYZ", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"

    def test_lineage_bad_pid(self, s):
        r = s.get(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID_XYZ/lineage", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"

    def test_raw_bad_pid_404(self, s):
        r = s.get(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID/raw", timeout=TIMEOUT)
        assert r.status_code == 404

    def test_evaluate_bad_pid(self, s):
        r = s.post(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID/evaluate", json={}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"

    def test_repair_bad_pid(self, s):
        r = s.post(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID/repair", json={}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"


# ── REGRESSION: AGENT MEMORY ─────────────────────────────────────────────────
AGENT_ID = f"TEST_agent_{uuid.uuid4().hex[:8]}"


class TestAgentMemoryRegression:
    def test_remember_empty_guardrail(self, s):
        r = s.post(f"{BASE_URL}/api/agent-memory/remember",
                   json={"agent_id": AGENT_ID, "content": ""}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_remember_no_agent(self, s):
        r = s.post(f"{BASE_URL}/api/agent-memory/remember",
                   json={"agent_id": "", "content": "hello"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_remember_then_recall(self, s):
        for c, tags in [
            ("Dragon quest acid breath lesson", ["dragon"]),
            ("Stealth route avoided line of sight", ["stealth"]),
            ("Healing potion scarcity issue", ["resources"]),
        ]:
            r = s.post(f"{BASE_URL}/api/agent-memory/remember",
                       json={"agent_id": AGENT_ID, "content": c, "tags": tags,
                             "importance": 0.7, "kind": "episode"}, timeout=TIMEOUT)
            assert r.status_code == 200 and r.json().get("memory_id")
        rc = s.get(f"{BASE_URL}/api/agent-memory/recall?agent_id={AGENT_ID}&q=dragon",
                   timeout=TIMEOUT)
        assert rc.status_code == 200 and rc.json()["count"] >= 1

    def test_agents_list_has_agent(self, s):
        j = s.get(f"{BASE_URL}/api/agent-memory/agents", timeout=TIMEOUT).json()
        assert AGENT_ID in [a["agent_id"] for a in j["agents"]]

    def test_profile(self, s):
        j = s.get(f"{BASE_URL}/api/agent-memory/{AGENT_ID}/profile", timeout=TIMEOUT).json()
        assert j["memories"] >= 3
        assert "by_kind" in j

    def test_delete_agent(self, s):
        r = s.delete(f"{BASE_URL}/api/agent-memory/{AGENT_ID}", timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["deleted"] >= 3
        rc = s.get(f"{BASE_URL}/api/agent-memory/recall?agent_id={AGENT_ID}", timeout=TIMEOUT)
        assert rc.json()["count"] == 0
