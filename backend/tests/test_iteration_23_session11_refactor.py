"""Iteration 23 — Session 11.1 refactor regression + Live-Ops XP wiring."""
import os
import pytest
import requests

BASE = os.environ.get('EXPO_BACKEND_URL', 'https://gemini-game-craft.preview.emergentagent.com').rstrip('/')
PID = "7b640a5ebf0c4bc0807b8640d757df76"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ── Refactor regression: moved finetune / bugsquash endpoints ──
class TestEditRefactor:
    def test_finetune_bad_pid(self, s):
        r = s.post(f"{BASE}/api/playable/does_not_exist_xyz/finetune/async", json={"instruction": "make it red"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json(); assert j.get("error") == "not found", j

    def test_bugsquash_bad_pid(self, s):
        r = s.post(f"{BASE}/api/playable/does_not_exist_xyz/bugsquash/async", json={"instruction": "fix the bug"}, timeout=20)
        assert r.status_code == 200; assert r.json().get("error") == "not found"

    def test_finetune_short_instruction(self, s):
        r = s.post(f"{BASE}/api/playable/{PID}/finetune/async", json={"instruction": "ab"}, timeout=20)
        assert r.status_code == 200
        j = r.json(); assert "too short" in (j.get("error") or "").lower(), j

    def test_bugsquash_short_instruction(self, s):
        r = s.post(f"{BASE}/api/playable/{PID}/bugsquash/async", json={"instruction": ""}, timeout=20)
        assert r.status_code == 200; assert "too short" in (r.json().get("error") or "").lower()

    def test_finetune_kick(self, s):
        r = s.post(f"{BASE}/api/playable/{PID}/finetune/async", json={"instruction": "make the score bigger and brighter"}, timeout=20)
        assert r.status_code == 200
        j = r.json(); assert j.get("job_id"); assert j.get("job_status") == "running", j

    def test_bugsquash_kick(self, s):
        r = s.post(f"{BASE}/api/playable/{PID}/bugsquash/async", json={"instruction": "the game doesn't restart after losing"}, timeout=20)
        assert r.status_code == 200
        j = r.json(); assert j.get("job_id"); assert j.get("job_status") == "running"


# ── Core /api/playable regression ──
class TestPlayableCore:
    def test_list(self, s):
        r = s.get(f"{BASE}/api/playable/list?limit=5", timeout=15)
        assert r.status_code == 200
        j = r.json(); assert isinstance(j.get("playables"), list)

    def test_get_one(self, s):
        r = s.get(f"{BASE}/api/playable/{PID}", timeout=15)
        assert r.status_code == 200
        j = r.json(); assert j.get("playable_id") == PID

    def test_raw(self, s):
        r = s.get(f"{BASE}/api/playable/{PID}/raw", timeout=15)
        assert r.status_code == 200
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()

    def test_lineage(self, s):
        r = s.get(f"{BASE}/api/playable/{PID}/lineage", timeout=15)
        assert r.status_code == 200
        j = r.json(); assert "ancestors" in j and "children" in j

    def test_leaderboard(self, s):
        r = s.get(f"{BASE}/api/playable/leaderboard?limit=5", timeout=15)
        assert r.status_code == 200; assert "leaderboard" in r.json()

    def test_trending(self, s):
        r = s.get(f"{BASE}/api/playable/trending?limit=5", timeout=15)
        assert r.status_code == 200

    def test_collections(self, s):
        r = s.get(f"{BASE}/api/collections", timeout=15)
        assert r.status_code == 200; assert "collections" in r.json()


# ── Live-Ops XP wiring ──
class TestLiveOpsXp:
    VID = "TEST_iter23_visitor"
    ACTIONS = ["play", "vote", "react", "generate", "remix", "purchase", "share"]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_xp_action(self, s, action):
        r = s.post(f"{BASE}/api/liveops/xp", json={"visitor_id": self.VID, "action": action}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert isinstance(j.get("gained"), int) and j["gained"] > 0, j

    def test_pass_accumulates(self, s):
        r = s.get(f"{BASE}/api/liveops/pass?visitor_id={self.VID}", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert isinstance(j.get("xp"), int) and j["xp"] > 0, j
        assert "tier" in j
