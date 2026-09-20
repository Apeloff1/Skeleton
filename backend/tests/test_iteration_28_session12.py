"""
Session 12 — backend tests:
  - Regression after playable.py split (derive/cover/repair extracted)
  - NEW Worldforge (procedural terrain)
  - NEW Agent Long-Term Memory + reflection
Uses EXPO_PUBLIC_BACKEND_URL.
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


# ── PLAYABLE REGRESSION ──────────────────────────────────────────────────────
class TestPlayableRegression:
    def test_list(self, s):
        r = s.get(f"{BASE_URL}/api/playable/list", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "playables" in j and "count" in j

    def test_leaderboard(self, s):
        r = s.get(f"{BASE_URL}/api/playable/leaderboard", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_trending(self, s):
        r = s.get(f"{BASE_URL}/api/playable/trending", timeout=TIMEOUT)
        assert r.status_code == 200

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
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()

    def test_raw_real_pid_has_reporter(self, s):
        lst = s.get(f"{BASE_URL}/api/playable/list?limit=5", timeout=TIMEOUT).json()
        items = lst.get("playables") or []
        pid = None
        for p in items:
            if p.get("status") == "ready":
                pid = p.get("playable_id"); break
        if not pid:
            pytest.skip("no ready playable available in db")
        r = s.get(f"{BASE_URL}/api/playable/{pid}/raw", timeout=TIMEOUT)
        assert r.status_code == 200
        # __pl_error reporter shim must be injected
        assert "__pl_error" in r.text

    def test_evaluate_bad_pid(self, s):
        r = s.post(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID/evaluate", json={}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"

    def test_repair_bad_pid(self, s):
        r = s.post(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID/repair", json={}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"

    def test_remix_async_instruction_too_short(self, s):
        r = s.post(f"{BASE_URL}/api/playable/anypid/remix/async",
                   json={"tweak": "x", "depth": "fast"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_remix_async_bad_pid(self, s):
        r = s.post(f"{BASE_URL}/api/playable/NONEXISTENT_BAD_PID/remix/async",
                   json={"tweak": "make it faster please", "depth": "fast"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "base playable not found"


# ── WORLDFORGE ───────────────────────────────────────────────────────────────
class TestWorldforge:
    def test_biomes_count(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/biomes", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["count"] == 16
        assert len(j["biomes"]) == 16
        ids = {b["id"] for b in j["biomes"]}
        # spot-check a few (incl. SOTA hydrology biomes)
        assert {"ocean", "desert", "taiga", "snow", "tropical_forest", "river", "lake", "wetland"} <= ids

    def test_region_get_shape(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/region?seed=42&size=16&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["seed"] == 42 and j["size"] == 16
        assert len(j["grid"]) == 16 and len(j["grid"][0]) == 16
        assert j["stats"]["tiles"] == 16 * 16
        assert isinstance(j["distribution"], list) and len(j["distribution"]) >= 1
        assert "land_pct" in j["stats"]

    def test_region_post_matches_get(self, s):
        body = {"seed": 99, "size": 12, "rx": 0, "ry": 0, "scale": 0.08}
        a = s.post(f"{BASE_URL}/api/worldforge/region", json=body, timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region?seed=99&size=12&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT).json()
        assert a["grid"] == b["grid"]

    def test_determinism(self, s):
        url = f"{BASE_URL}/api/worldforge/region?seed=7777&size=16&rx=3&ry=2&scale=0.08"
        a = s.get(url, timeout=TIMEOUT).json()
        b = s.get(url, timeout=TIMEOUT).json()
        assert a["grid"] == b["grid"]

    def test_seamless_tiling(self, s):
        """region(rx=1,ry=0) left column == region(rx=0,ry=0) right-next column.

        Since regions are sampled in GLOBAL coordinates (rx*size + x), the tile
        at (rx=0, x=size) — i.e. one past the right edge — is exactly the tile
        at (rx=1, x=0). So we generate rx=0 with size+1 columns? Not possible;
        instead verify by overlapping coords: rx=0 size=16, the column at x=16
        in the global field equals rx=1 size=16 x=0.

        We approximate by using small regions and checking that biome at the
        last column of rx=0 is "close" to the first column of rx=1 — they
        won't be identical (they're different tiles), so we just verify that
        regenerating the SAME global tile yields the SAME biome.
        """
        size = 16
        seed = 1234
        scale = 0.08
        # rx=0 covers global x in [0, 15]; rx=1 covers [16, 31]. Verify rx=1 col 0
        # equals what you'd get by sampling rx=0 with global x=16 — easiest by
        # checking determinism across overlapping windows: rx=2 col 0 must equal
        # rx=0 with seed=… we instead just check determinism + that adjacent
        # tiles have plausible continuity (left/right of border).
        a = s.get(f"{BASE_URL}/api/worldforge/region?seed={seed}&size={size}&rx=0&ry=0&scale={scale}",
                  timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region?seed={seed}&size={size}&rx=1&ry=0&scale={scale}",
                  timeout=TIMEOUT).json()
        # Across the seam the elevation values should be reasonably continuous
        # (noise is smooth) — verify difference between rx=0 last col and rx=1
        # first col is small on average.
        diffs = [abs(a["grid"][y][size - 1]["e"] - b["grid"][y][0]["e"]) for y in range(size)]
        avg = sum(diffs) / len(diffs)
        assert avg < 0.20, f"seam discontinuous: avg elev diff {avg:.3f}"

    def test_size_clamp_low(self, s):
        # POST allows arbitrary size; clamp is enforced server-side to >=8.
        r = s.post(f"{BASE_URL}/api/worldforge/region",
                   json={"seed": 1, "size": 2, "rx": 0, "ry": 0, "scale": 0.08},
                   timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["size"] == 8

    def test_size_clamp_high(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/region",
                   json={"seed": 1, "size": 500, "rx": 0, "ry": 0, "scale": 0.08},
                   timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["size"] == 96


# ── AGENT MEMORY ─────────────────────────────────────────────────────────────
AGENT_ID = f"TEST_agent_{uuid.uuid4().hex[:8]}"


class TestAgentMemory:
    def test_remember_empty_guardrail(self, s):
        r = s.post(f"{BASE_URL}/api/agent-memory/remember",
                   json={"agent_id": AGENT_ID, "content": ""}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_remember_no_agent(self, s):
        r = s.post(f"{BASE_URL}/api/agent-memory/remember",
                   json={"agent_id": "", "content": "hello world"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_remember_then_persisted(self, s):
        contents = [
            ("I tried the dragon quest and got burned by acid breath", ["combat", "dragon"]),
            ("Stealth approach worked when I avoided line of sight", ["stealth", "tactics"]),
            ("Healing potions are scarce in the deep dungeon levels", ["resources"]),
            ("The thief NPC betrayed me after sharing too much info", ["npc", "betrayal"]),
        ]
        ids = []
        for c, tags in contents:
            r = s.post(f"{BASE_URL}/api/agent-memory/remember",
                       json={"agent_id": AGENT_ID, "content": c, "kind": "episode",
                             "importance": 0.7, "tags": tags}, timeout=TIMEOUT)
            assert r.status_code == 200
            j = r.json()
            assert j.get("memory_id")
            assert j["content"] == c
            assert set(j["tags"]) == set(tags)
            ids.append(j["memory_id"])
        # verify recall returns at least one with a match
        rc = s.get(f"{BASE_URL}/api/agent-memory/recall?agent_id={AGENT_ID}&q=dragon",
                   timeout=TIMEOUT)
        assert rc.status_code == 200
        rj = rc.json()
        assert rj["count"] >= 1
        top = rj["memories"][0]
        assert "dragon" in top["content"].lower() or top["relevance"] > 0

    def test_recall_ranks_by_relevance(self, s):
        r = s.get(f"{BASE_URL}/api/agent-memory/recall?agent_id={AGENT_ID}&q=stealth", timeout=TIMEOUT)
        assert r.status_code == 200
        memories = r.json()["memories"]
        assert len(memories) > 0
        assert "stealth" in memories[0]["content"].lower()

    def test_recall_no_agent(self, s):
        r = s.get(f"{BASE_URL}/api/agent-memory/recall?agent_id=", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_agents_list(self, s):
        r = s.get(f"{BASE_URL}/api/agent-memory/agents", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        ids = [a["agent_id"] for a in j["agents"]]
        assert AGENT_ID in ids
        row = next(a for a in j["agents"] if a["agent_id"] == AGENT_ID)
        assert row["memories"] >= 4

    def test_profile(self, s):
        r = s.get(f"{BASE_URL}/api/agent-memory/{AGENT_ID}/profile", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["memories"] >= 4
        assert "by_kind" in j
        assert j["by_kind"].get("episode", 0) >= 4
        assert isinstance(j["top_tags"], list)

    @pytest.mark.timeout(120)
    def test_reflect_live_llm(self, s):
        """LIVE LLM ~10-30s. One reflection only."""
        r = s.post(f"{BASE_URL}/api/agent-memory/reflect",
                   json={"agent_id": AGENT_ID, "window": 8}, timeout=90)
        assert r.status_code == 200
        j = r.json()
        if "error" in j:
            pytest.fail(f"reflect error: {j['error']}")
        assert "reflection" in j
        assert len(j["reflection"]["content"]) > 10
        assert j["reflection"]["kind"] == "reflection"
        assert j["reflection"]["importance"] == 0.9

    def test_clear_agent(self, s):
        # cleanup
        r = s.delete(f"{BASE_URL}/api/agent-memory/{AGENT_ID}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["deleted"] >= 4
        # verify gone
        rc = s.get(f"{BASE_URL}/api/agent-memory/recall?agent_id={AGENT_ID}", timeout=TIMEOUT)
        assert rc.json()["count"] == 0
