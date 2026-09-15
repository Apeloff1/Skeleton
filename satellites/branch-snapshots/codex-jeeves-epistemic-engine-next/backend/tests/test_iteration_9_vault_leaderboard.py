"""
Iteration 9 — Vault Import + Leaderboard + Vote regression.
Verifies the new EXPANSION features: vault import flow, public leaderboard,
and that voting still affects leaderboard rankings.
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
DEMO_BUILD = "demo-build-1"
PID_A = "8ca4a00512034787b0094a8f7c07db3b"
PID_B = "b6c58bc75553444d82cf2c2e3d4295de"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestHealth:
    def test_health(self, session):
        r = session.get(f"{BASE}/api/health", timeout=30)
        assert r.status_code == 200


class TestVaultImportList:
    def test_list_importable_builds_contains_demo(self, session):
        r = session.get(f"{BASE}/api/playable/import/builds", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "builds" in data and "count" in data
        assert isinstance(data["builds"], list)
        assert data["count"] == len(data["builds"])
        ids = [b.get("build_id") for b in data["builds"]]
        assert DEMO_BUILD in ids, f"demo-build-1 not found among {ids[:10]}"
        demo = next(b for b in data["builds"] if b.get("build_id") == DEMO_BUILD)
        assert demo.get("title") == "Neon Drift Racer"
        assert demo.get("genre") == "racing"


class TestImportErrors:
    def test_import_missing_build_id(self, session):
        r = session.post(f"{BASE}/api/playable/import-build/async", json={}, timeout=30)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_import_unknown_build_id(self, session):
        r = session.post(f"{BASE}/api/playable/import-build/async",
                         json={"build_id": "NOPE_NONEXISTENT_BUILD_ZZZ"}, timeout=30)
        assert r.status_code == 200
        assert "error" in r.json()


class TestVaultImportFlow:
    """Live LLM — ~30-90s in fast mode. Kick + poll."""
    imported_pid = None

    def test_import_kick_and_poll(self, session):
        t0 = time.time()
        r = session.post(f"{BASE}/api/playable/import-build/async",
                         json={"build_id": DEMO_BUILD, "depth": "fast"}, timeout=30)
        kick_dt = time.time() - t0
        assert kick_dt < 10, f"kick took {kick_dt:.1f}s"
        assert r.status_code == 200
        body = r.json()
        assert "job_id" in body and body.get("job_status") == "running"
        job_id = body["job_id"]

        # Poll up to 180s
        deadline = time.time() + 180
        last = None
        while time.time() < deadline:
            time.sleep(4)
            jr = session.get(f"{BASE}/api/playable/job/{job_id}", timeout=30)
            assert jr.status_code == 200
            last = jr.json()
            if last.get("job_status") in ("done", "error"):
                break

        assert last is not None
        assert last.get("job_status") == "done", f"job didn't finish: {last}"
        assert last.get("status") == "ready", f"status={last.get('status')} missing={last.get('missing_checks')}"
        assert last.get("imported") is True
        assert last.get("source_build_id") == DEMO_BUILD
        # Title derived from build (case-insensitive contain)
        title = (last.get("title") or "").lower()
        assert "neon" in title and "drift" in title, f"title={last.get('title')}"
        assert (last.get("genre") or "").lower() == "racing"
        assert last.get("playability_score", 0) >= 70
        TestVaultImportFlow.imported_pid = last.get("playable_id")

    def test_health_responsive_after_import(self, session):
        r = session.get(f"{BASE}/api/health", timeout=30)
        assert r.status_code == 200


class TestLeaderboard:
    def test_leaderboard_structure_and_ordering(self, session):
        r = session.get(f"{BASE}/api/playable/leaderboard?limit=10", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "leaderboard" in data
        lb = data["leaderboard"]
        assert isinstance(lb, list)
        assert len(lb) > 0
        for i, row in enumerate(lb):
            assert row.get("rank") == i + 1
            assert "playable_id" in row
            assert "title" in row
            assert "score" in row
            assert "wins" in row and "matches" in row
            assert "overall" in row
            assert "intricacy" in row
        # ordering: descending score
        scores = [row["score"] for row in lb]
        assert scores == sorted(scores, reverse=True), f"not desc: {scores}"

    def test_imported_game_appears_in_leaderboard(self, session):
        # Need bigger limit since new game may not be top-10
        r = session.get(f"{BASE}/api/playable/leaderboard?limit=100", timeout=30)
        assert r.status_code == 200
        ids = [row["playable_id"] for row in r.json().get("leaderboard", [])]
        pid = TestVaultImportFlow.imported_pid
        if pid:
            assert pid in ids, f"imported PID {pid} not in leaderboard (top 100)"


class TestVoteRegression:
    def test_vote_updates_tallies(self, session):
        r = session.post(f"{BASE}/api/playable/{PID_A}/vote",
                         json={"opponent_id": PID_B, "winner_id": PID_A}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "this" in data and "opponent" in data
        assert data.get("winner_id") == PID_A
        assert isinstance(data["this"].get("wins"), int)
        assert isinstance(data["this"].get("matches"), int)
        assert isinstance(data["opponent"].get("matches"), int)
        assert data["this"]["wins"] >= 1
        assert data["this"]["matches"] >= 1
        assert data["opponent"]["matches"] >= 1
