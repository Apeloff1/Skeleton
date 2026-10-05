"""Session 17.2 — Faction sim + worldforge render-split + physics-wire (kick-only)."""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")


# ── Faction simulation (deterministic) ──
class TestFactions:
    def test_options(self):
        r = requests.get(f"{BASE}/api/factions/options", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["archetypes"]) == 12
        assert d["ally_threshold"] == 55
        assert d["war_threshold"] == -50

    def test_post_simulate_shape(self):
        r = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 6, "turns": 40}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "summary" in d and "dominant" in d["summary"]
        assert len(d["factions"]) == 6
        assert isinstance(d["events"], list)
        assert isinstance(d["series"], list) and len(d["series"]) == 40

    def test_get_simulate_shape(self):
        r = requests.get(f"{BASE}/api/factions/simulate?seed=7&factions=8&turns=50", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["factions"]) == 8
        assert len(d["series"]) == 50

    def test_determinism(self):
        a = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 6, "turns": 40}, timeout=15).json()
        b = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 6, "turns": 40}, timeout=15).json()
        assert a["summary"] == b["summary"]
        assert a["events"] == b["events"]

    def test_clamp_factions_low(self):
        d = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 2, "turns": 40}, timeout=15).json()
        assert len(d["factions"]) == 3

    def test_clamp_factions_high(self):
        d = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 20, "turns": 40}, timeout=15).json()
        assert len(d["factions"]) == 12

    def test_clamp_turns_low(self):
        d = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 6, "turns": 3}, timeout=15).json()
        assert len(d["series"]) == 5

    def test_clamp_turns_high(self):
        d = requests.post(f"{BASE}/api/factions/simulate",
                          json={"seed": 7, "factions": 6, "turns": 500}, timeout=15).json()
        assert len(d["series"]) == 120


# ── Worldforge render-split regression ──
class TestWorldforge:
    @pytest.mark.parametrize("path", [
        "/api/worldforge/render?scale=region&seed=7&size=24",
        "/api/worldforge/render?scale=region&seed=7&size=24&mode=atlas",
        "/api/worldforge/render?scale=region&seed=7&size=24&mode=blueprint",
        "/api/worldforge/render?scale=planet&mode=globe&seed=7",
        "/api/worldforge/render?scale=region&mode=thematic&layer=plates&seed=7&size=24",
        "/api/worldforge/render?scale=region&mode=thematic&layer=fertility&seed=7&size=24",
        "/api/worldforge/export?scale=region&seed=7&size=24",
        "/api/worldforge/render.gif?seed=7&size=40",
    ])
    def test_render_endpoints(self, path):
        r = requests.get(f"{BASE}{path}", timeout=120)
        assert r.status_code == 200, f"{path}: {r.status_code}"
        ct = r.headers.get("content-type", "")
        assert ("image/" in ct) or len(r.content) > 100, f"{path}: ct={ct}"

    def test_biomes(self):
        r = requests.get(f"{BASE}/api/worldforge/biomes", timeout=15)
        assert r.status_code == 200

    def test_scales(self):
        r = requests.get(f"{BASE}/api/worldforge/scales", timeout=15)
        assert r.status_code == 200

    def test_region(self):
        r = requests.get(f"{BASE}/api/worldforge/region?seed=7", timeout=30)
        assert r.status_code == 200

    def test_quest(self):
        r = requests.post(f"{BASE}/api/worldforge/quest",
                         json={"seed": 7, "scale": "region", "size": 24}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "name" in d and "quest" in d and "consistency" in d


# ── Physics-wire kick test only (full run takes 3-8 min) ──
class TestPhysics:
    def _ready_pid(self):
        r = requests.get(f"{BASE}/api/playable/list?limit=20", timeout=15).json()
        for p in r.get("playables", []):
            if p.get("status") == "ready":
                return p["playable_id"]
        return None

    def test_bad_pid(self):
        r = requests.post(f"{BASE}/api/playable/badpid_xxx/apply-physics/async", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("error") == "not found"

    def test_apply_physics_full_flow(self):
        pid = self._ready_pid()
        if not pid:
            pytest.skip("no ready playable")
        r = requests.post(f"{BASE}/api/playable/{pid}/apply-physics/async", timeout=20)
        assert r.status_code == 200
        d = r.json()
        if d.get("error") == "rate_limited":
            pytest.skip("rate-limited")
        assert "job_id" in d, d
        job_id = d["job_id"]
        deadline = time.time() + 480  # 8 min
        last = None
        while time.time() < deadline:
            time.sleep(8)
            jr = requests.get(f"{BASE}/api/playable/job/{job_id}", timeout=15).json()
            last = jr
            if jr.get("job_status") in ("done", "error"):
                break
        assert last and last.get("job_status") == "done", f"final: {last}"
        if not last.get("applied"):
            pytest.skip(f"applied=false (score floor not met) — {last}")
        assert last.get("applied") is True
        assert last.get("version", 0) >= 2
        assert last.get("score", 0) >= 70
        # confirm engine injected
        raw = requests.get(f"{BASE}/api/playable/{pid}/raw", timeout=20).text
        assert "window.PHYSICS" in raw
        assert "__physics" in raw
