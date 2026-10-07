"""
Iteration 69 — 4-Wins wave testing:
  Win3: GET /api/agent-memory/{agent_id}/bias (after seeding via /remember + /reflect)
  Win4: POST /api/multiplayer/scaffold/zip
  Win5: POST /api/imagine/cover   (image-gen is MOCKED in sandbox — expect 200, no crash)
  Win7: POST /api/snowball/{pid}/remaster (uses real pid from marketplace)
"""
import os
import base64
import io
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Win3: Agent Memory Bias ────────────────────────────────────────────────
class TestAgentMemoryBias:
    AGENT = "WorldForgeAgent"

    def test_remember_seeds_memory(self, api):
        # Make sure agent has memories. Seed two so bias has something to work with.
        for content, tags in [
            ("Neon rain biomes scored highest", ["neon", "biome"]),
            ("Players love verticality and parkour zones",   ["neon", "parkour"]),
        ]:
            r = api.post(f"{BASE_URL}/api/agent-memory/remember", json={
                "agent_id": self.AGENT, "content": content,
                "tags": tags, "kind": "outcome", "importance": 0.8,
            })
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("memory_id") and j.get("agent_id") == self.AGENT

    def test_bias_returns_has_bias_and_top_tags(self, api):
        # Bias requires reflections OR strong themes — top_tags is built from tags directly.
        r = api.get(f"{BASE_URL}/api/agent-memory/{self.AGENT}/bias")
        assert r.status_code == 200, r.text
        j = r.json()
        assert "has_bias" in j
        assert isinstance(j.get("top_tags"), list)
        assert "neon" in j["top_tags"], f"expected 'neon' tag in top_tags, got {j['top_tags']}"
        # has_bias may be True from themes alone
        assert j["has_bias"] is True, f"has_bias should be True after seeding, payload={j}"
        assert isinstance(j.get("bias"), str) and len(j["bias"]) > 0


# ── Win4: Multiplayer Scaffold Zip ─────────────────────────────────────────
class TestMultiplayerScaffoldZip:
    def test_scaffold_zip_lockstep_for_rts(self, api):
        r = api.post(f"{BASE_URL}/api/multiplayer/scaffold/zip", json={
            "game": "Skybreakers", "genre": "rts", "max_players": 16
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["filename"].endswith(".zip"), j
        assert j["size_bytes"] > 0
        assert j["model"] == "lockstep", f"genre=rts should pick lockstep, got {j['model']}"
        assert j.get("zip_base64"), "zip_base64 should be non-empty"
        # Decode & validate it's a real zip with expected entries
        raw = base64.b64decode(j["zip_base64"])
        assert len(raw) == j["size_bytes"]
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist()
            assert "server/index.js" in names
            assert "server/lobby.js" in names
            assert "shared/protocol.ts" in names
            assert "client/netClient.ts" in names
            assert "README.md" in names


# ── Win5: Cover image (MOCKED in sandbox — must not crash) ─────────────────
class TestCoverImageMocked:
    def test_cover_returns_200_with_status(self, api):
        r = api.post(f"{BASE_URL}/api/imagine/cover", json={
            "title": "Neon Drifters", "genre": "cyberpunk",
            "lore": "Drifters race to wake a city",
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert "status" in j, f"missing status field, payload keys={list(j.keys())}"
        # Image gen is mocked → images may be empty / status may be 'failed'. Just ensure no crash.
        assert "images" in j
        assert isinstance(j["images"], list)


# ── Win7: One-tap Remaster ─────────────────────────────────────────────────
class TestRemaster:
    def test_remaster_real_pid_from_marketplace(self, api):
        # Fetch a real playable_id from marketplace listings
        listings = api.get(f"{BASE_URL}/api/marketplace/listings")
        assert listings.status_code == 200, listings.text
        ldata = listings.json()
        items = ldata if isinstance(ldata, list) else ldata.get("listings") or ldata.get("items") or []
        assert items, f"no listings available, payload={ldata}"
        pid = items[0].get("playable_id") or items[0].get("pid") or items[0].get("id")
        assert pid, f"no playable_id in first listing: {items[0]}"

        # LLM call ~60s, allow up to 120s
        r = api.post(f"{BASE_URL}/api/snowball/{pid}/remaster", timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "before" in j and "after_projected" in j
        before_overall = j["before"].get("overall")
        after_overall = j["after_projected"].get("overall")
        assert isinstance(before_overall, (int, float))
        assert isinstance(after_overall, (int, float))
        assert after_overall >= before_overall, f"after({after_overall}) should be >= before({before_overall})"
        levels = j.get("levels_diff")
        assert isinstance(levels, list) and len(levels) == 10, f"expected 10 levels_diff, got {len(levels) if levels else 0}"
        upgrades = j.get("upgrades")
        assert isinstance(upgrades, list), f"upgrades should be a list, got {type(upgrades)}"
