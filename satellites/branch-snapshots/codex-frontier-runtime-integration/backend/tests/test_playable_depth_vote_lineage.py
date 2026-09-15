"""
Iteration 8 — Verifies the new DEPTH toggle (fast/studio) + vs-Play voting +
lineage + derive regression. Uses depth='fast' for any new generation to keep
runtime low.
"""
import os
import time
import pytest
import requests


def _base_url() -> str:
    base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
    if not base:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    assert base
    return base


BASE_URL = _base_url()
PID_ORIGINAL = "8ca4a00512034787b0094a8f7c07db3b"
PID_REMIX = "b6c58bc75553444d82cf2c2e3d4295de"


def _poll_job(job_id: str, max_wait: int = 180) -> dict:
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=30)
        d = r.json()
        last = d
        if d.get("job_status") in ("done", "error"):
            return d
        time.sleep(3)
    return last or {"job_status": "timeout"}


# ── health stays responsive ──────────────────────────────────────────────────
class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert r.status_code == 200


# ── DEPTH=fast end-to-end generation ─────────────────────────────────────────
class TestDepthFast:
    def test_fast_generate_kicks_quickly_and_completes(self):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/generate/async",
            json={"brief": "a quick tap reflex game", "depth": "fast"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("job_id"), body
        assert body.get("job_status") == "running"
        assert (time.time() - t0) < 10, "fast kick must return well under 10s"

        # Poll to completion (fast mode targets ~30-90s).
        out = _poll_job(body["job_id"], max_wait=180)
        assert out.get("job_status") == "done", out
        assert out.get("status") == "ready", out
        assert out.get("depth") == "fast", out
        assert out.get("playability_score", 0) >= 70, out

        trail = out.get("repair_trail") or []
        assert trail, "repair_trail must have at least one entry"
        kinds = {t.get("kind") for t in trail}
        # In fast mode the quality-refinement loop must be skipped.
        assert "quality_repair" not in kinds, f"fast mode should NOT run quality_repair, got: {kinds}"
        assert "generate" in kinds, f"missing 'generate' entry: {kinds}"

    def test_health_during_fast_generate(self):
        # Ensure /api/health stays 200 while a job runs.
        kick = requests.post(
            f"{BASE_URL}/api/playable/generate/async",
            json={"brief": "tiny dodge the dot game", "depth": "fast"},
            timeout=20,
        ).json()
        job_id = kick.get("job_id")
        assert job_id
        # Hit health 5 times spaced over a few seconds.
        for _ in range(5):
            h = requests.get(f"{BASE_URL}/api/health", timeout=30)
            assert h.status_code == 200
            time.sleep(1)


# ── DEPTH=studio wiring (we only verify kick + running state, NOT completion)
class TestDepthStudio:
    def test_studio_kick_runs(self):
        r = requests.post(
            f"{BASE_URL}/api/playable/generate/async",
            json={"brief": "an arcade dodger with waves", "depth": "studio"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("job_id") and body.get("job_status") == "running"

        # Within ~6s the job should still be 'running' (studio takes minutes).
        time.sleep(2)
        j = requests.get(f"{BASE_URL}/api/playable/job/{body['job_id']}", timeout=30).json()
        assert j.get("job_status") in ("running", "done"), j  # tolerate ultra-fast complete
        # depth on the job doc not yet present until done; just confirm kind=generate
        assert j.get("kind") == "generate"


# ── vs-Play voting ───────────────────────────────────────────────────────────
class TestVote:
    def test_vote_winner_is_this(self):
        r = requests.post(
            f"{BASE_URL}/api/playable/{PID_REMIX}/vote",
            json={"opponent_id": PID_ORIGINAL, "winner_id": PID_REMIX},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("winner_id") == PID_REMIX, d
        assert "this" in d and "opponent" in d
        for side in ("this", "opponent"):
            assert isinstance(d[side]["wins"], int)
            assert isinstance(d[side]["matches"], int)
            assert d[side]["matches"] >= 1
        # this side should have at least 1 win after this vote
        assert d["this"]["wins"] >= 1

    def test_vote_winner_is_opponent(self):
        r = requests.post(
            f"{BASE_URL}/api/playable/{PID_REMIX}/vote",
            json={"opponent_id": PID_ORIGINAL, "winner_id": PID_ORIGINAL},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("winner_id") == PID_ORIGINAL
        assert d["opponent"]["wins"] >= 1

    def test_vote_invalid_winner_returns_error(self):
        r = requests.post(
            f"{BASE_URL}/api/playable/{PID_REMIX}/vote",
            json={"opponent_id": PID_ORIGINAL, "winner_id": "deadbeef"},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json().get("error")

    def test_vote_missing_opponent_returns_error(self):
        r = requests.post(
            f"{BASE_URL}/api/playable/{PID_REMIX}/vote",
            json={"winner_id": PID_REMIX},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json().get("error")

    def test_vote_both_must_exist(self):
        r = requests.post(
            f"{BASE_URL}/api/playable/{PID_REMIX}/vote",
            json={"opponent_id": "nonexistent12345", "winner_id": PID_REMIX},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json().get("error")


# ── lineage ──────────────────────────────────────────────────────────────────
class TestLineage:
    def test_lineage_for_remix_child(self):
        r = requests.get(f"{BASE_URL}/api/playable/{PID_REMIX}/lineage", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "node" in d and "ancestors" in d and "children" in d
        assert d["node"]["playable_id"] == PID_REMIX
        # The remix is a child of the original ⇒ at least 1 ancestor.
        assert len(d["ancestors"]) >= 1
        anc_ids = [a["playable_id"] for a in d["ancestors"]]
        assert PID_ORIGINAL in anc_ids, anc_ids

    def test_lineage_unknown_returns_error(self):
        r = requests.get(f"{BASE_URL}/api/playable/doesnotexist/lineage", timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")


# ── derive regression (remix in fast mode) ───────────────────────────────────
class TestDeriveFast:
    def test_remix_fast_kicks_quickly(self):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/{PID_ORIGINAL}/remix/async",
            json={"tweak": "make it harder", "depth": "fast"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id") and d.get("job_status") == "running"
        assert (time.time() - t0) < 10

        # Poll until done — fast mode keeps it under ~2 min.
        out = _poll_job(d["job_id"], max_wait=180)
        assert out.get("job_status") == "done", out
        assert out.get("status") == "ready", out
        assert out.get("parent_id") == PID_ORIGINAL, out
        assert out.get("derive_mode") == "remix", out
        assert out.get("depth") == "fast", out
        assert "quality_repair" not in {t.get("kind") for t in (out.get("repair_trail") or [])}
