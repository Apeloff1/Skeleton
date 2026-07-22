"""Iteration 78 — Final Build async streaming endpoints + sync + play/download.

Covers the live CI-pipeline-style streaming console wiring:
- POST /api/galaxy-studio/final-build/package/async -> job_id, status=running, stages_total=7
- GET /api/galaxy-studio/final-build/job/{job_id} -> streams stages 1..7 with gates
- 404 on unknown job
- Sync /package still returns full 7-stage result
- /play HTML and /game.zip downloads after a build
"""
from __future__ import annotations

import os
import time
import zipfile
import io

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/") or \
           "http://localhost:8001"

API = f"{BASE_URL}/api/galaxy-studio/final-build"


def _payload(build_id: str) -> dict:
    return {
        "build_id": build_id,
        "genre": "rpg",
        "era": "8bit",
        "seed": 1,
        "persist": True,
        "config": {"graphic_style": "cel_shaded", "dimension": "3d"},
    }


@pytest.fixture(scope="module")
def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── ASYNC STREAMING ─────────────────────────────────────────────────────────

class TestAsyncStreaming:
    def test_async_kickoff_returns_job_id(self, session):
        r = session.post(f"{API}/package/async",
                         json=_payload("TEST_fb_async_kick"), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "running"
        assert d.get("stages_total") == 7
        assert isinstance(d.get("job_id"), str) and len(d["job_id"]) >= 8

    def test_async_streams_stages_and_finishes(self, session):
        bid = "TEST_fb_async_stream"
        r = session.post(f"{API}/package/async", json=_payload(bid), timeout=15)
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]

        # Poll for streaming behaviour. Pacing is 0.45s per stage (~3-4s total).
        observed_steps: set[int] = set()
        last_step = 0
        final = None
        for _ in range(80):  # up to ~16s safety
            time.sleep(0.2)
            jr = session.get(f"{API}/job/{job_id}", timeout=10)
            assert jr.status_code == 200, jr.text
            j = jr.json()
            cur = j.get("current_step", 0)
            observed_steps.add(cur)
            # current_step must never go backwards (monotonic)
            assert cur >= last_step
            last_step = cur
            for s in j.get("stages", []):
                assert "gate" in s and "passed" in s["gate"] and "score" in s["gate"]
                assert isinstance(s["step"], int)
                assert isinstance(s["stage"], str)
            if j.get("status") == "done":
                final = j
                break
            if j.get("status") == "error":
                pytest.fail(f"job errored: {j.get('error')}")

        assert final is not None, "job did not finish in time"
        assert final["current_step"] == 7
        # We expect to have observed intermediate steps (i.e. >1 distinct step seen)
        assert len(observed_steps) >= 2, \
            f"streaming did not advance incrementally: observed={observed_steps}"

        res = final.get("result") or {}
        assert res.get("can_ship") is True
        assert res.get("gates_passed") == 7
        assert isinstance(res.get("overall_score"), int) and res["overall_score"] >= 95
        assert isinstance(res.get("totals"), dict)
        assert res["totals"].get("gamefiles", 0) > 0
        play = res.get("playable") or {}
        assert play.get("playable") is True
        assert play.get("play_url", "").endswith(f"/api/galaxy-studio/final-build/{bid}/play")
        assert play.get("download_url", "").endswith(f"/api/galaxy-studio/final-build/{bid}/game.zip")
        assert len(res.get("stages", [])) == 7

    def test_job_404_for_unknown(self, session):
        r = session.get(f"{API}/job/this_is_not_a_real_job_id", timeout=10)
        assert r.status_code == 404


# ── SYNC ────────────────────────────────────────────────────────────────────

class TestSyncPackage:
    def test_sync_package_returns_full_result(self, session):
        bid = "TEST_fb_sync"
        r = session.post(f"{API}/package", json=_payload(bid), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d.get("stages", [])) == 7
        steps = [s["step"] for s in d["stages"]]
        assert steps == [1, 2, 3, 4, 5, 6, 7]
        assert d.get("can_ship") is True
        assert d.get("gates_passed") == 7
        for s in d["stages"]:
            assert s["gate"]["passed"] is True
            assert s["gate"]["score"] >= 95
        assert d["playable"]["playable"] is True


# ── PLAY + DOWNLOAD (after a build) ─────────────────────────────────────────

class TestPlayAndDownload:
    @pytest.fixture(scope="class")
    def built_id(self, session) -> str:
        bid = "TEST_fb_play_dl"
        r = session.post(f"{API}/package", json=_payload(bid), timeout=30)
        assert r.status_code == 200, r.text
        return bid

    def test_play_html(self, session, built_id):
        r = session.get(f"{API}/{built_id}/play", timeout=15)
        assert r.status_code == 200, r.text[:300]
        ctype = r.headers.get("content-type", "")
        assert "text/html" in ctype, ctype
        body = r.text.lower()
        assert "<html" in body or "<!doctype" in body

    def test_game_zip(self, session, built_id):
        r = session.get(f"{API}/{built_id}/game.zip", timeout=15)
        assert r.status_code == 200
        ctype = r.headers.get("content-type", "")
        assert "zip" in ctype, ctype
        # Validate zip is well-formed and has index.html
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = set(zf.namelist())
        assert "index.html" in names
        assert "game.json" in names or "README.txt" in names
