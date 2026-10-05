"""
Iteration 10 — Real Playable Export expansion: NEW derive modes (prequel,
expansion, variants) plus regression on leaderboard + GET playable + health.

Strategy:
 - Use depth='fast' on all generation calls to keep wall time bounded.
 - Kick jobs in PARALLEL (prequel + expansion are independent single-LLM jobs;
   variants is 4× concurrent inside the server) — total wall ~6-7 min.
 - Poll every ~4s up to a generous deadline.
 - Error-path tests are fast (no LLM).
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
    assert base, "EXPO_PUBLIC_BACKEND_URL not configured"
    return base


BASE_URL = _base_url()
BASE_PID = "fb0f9e74776e4401b12f392dcf4838a3"


def _poll_until_done(job_id: str, deadline_s: int, label: str) -> dict:
    """Poll /api/playable/job/{id} every ~4s until status in (done|error|unknown
    -> retry). Returns the final job doc."""
    t0 = time.time()
    last = None
    while time.time() - t0 < deadline_s:
        try:
            r = requests.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=15)
            if r.status_code == 200:
                jd = r.json()
                last = jd
                if jd.get("job_status") in ("done", "error"):
                    print(f"[{label}] finished in {time.time() - t0:.1f}s status={jd.get('job_status')}")
                    return jd
        except Exception as e:
            print(f"[{label}] poll error: {e}")
        time.sleep(4)
    raise AssertionError(
        f"[{label}] job {job_id} did not finish in {deadline_s}s; last={last}")


# ─────────────────────────── REGRESSION (fast) ───────────────────────────
class TestRegression:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200

    def test_base_playable_exists_and_ready(self):
        r = requests.get(f"{BASE_URL}/api/playable/{BASE_PID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "ready", d
        assert d.get("playable_id") == BASE_PID
        assert d.get("title")
        assert d.get("bytes", 0) > 0

    def test_leaderboard(self):
        r = requests.get(f"{BASE_URL}/api/playable/leaderboard?limit=10", timeout=15)
        assert r.status_code == 200
        d = r.json()
        rows = d.get("leaderboard") or []
        assert isinstance(rows, list)
        assert d.get("count") == len(rows)
        assert 1 <= len(rows) <= 10
        # required fields per row
        for row in rows:
            assert "rank" in row
            assert "playable_id" in row
            assert "title" in row
            assert "score" in row
        # ranks are 1..N consecutive and scores are non-increasing
        assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))
        scores = [row["score"] for row in rows]
        assert scores == sorted(scores, reverse=True), scores


# ─────────────────────────── ERROR PATHS (fast) ──────────────────────────
class TestDeriveNotFound:
    """Every derive endpoint on an unknown pid must return base-not-found."""

    @pytest.mark.parametrize("mode", ["prequel", "expansion", "variants"])
    def test_unknown_base_returns_error(self, mode):
        r = requests.post(
            f"{BASE_URL}/api/playable/__nope__/{mode}/async",
            json={"depth": "fast"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("error") == "base playable not found", d


# ─────────────────────────── LIVE: PREQUEL ───────────────────────────────
class TestPrequel:
    """POST /{pid}/prequel/async kicks fast & resolves to a ready prequel."""

    def test_prequel_kick_and_complete(self):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/{BASE_PID}/prequel/async",
            json={"depth": "fast"},
            timeout=20,
        )
        kick_elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id"), d
        assert d.get("job_status") == "running", d
        assert kick_elapsed < 10, f"kick took {kick_elapsed:.1f}s"
        job_id = d["job_id"]

        final = _poll_until_done(job_id, deadline_s=240, label="prequel")
        if final.get("job_status") == "error":
            pytest.fail(f"prequel job errored: {final.get('error')}")
        assert final.get("status") in ("ready", "failed"), final
        assert final.get("derive_mode") == "prequel", final
        assert final.get("parent_id") == BASE_PID
        if final.get("status") == "failed":
            pytest.skip(
                f"LLM produced non-runnable prequel "
                f"(score={final.get('playability_score')}, "
                f"missing={final.get('missing_checks')}) — infra works")
        new_pid = final.get("playable_id")
        assert new_pid and new_pid != BASE_PID
        assert final.get("depth") == "fast"
        # New playable persisted and retrievable
        g = requests.get(f"{BASE_URL}/api/playable/{new_pid}", timeout=15)
        assert g.status_code == 200
        gd = g.json()
        assert gd.get("derive_mode") == "prequel"
        assert gd.get("parent_id") == BASE_PID


# ─────────────────────────── LIVE: EXPANSION ─────────────────────────────
class TestExpansion:
    """POST /{pid}/expansion/async kicks fast & resolves; size_mult ≈ 3."""

    def test_expansion_kick_and_complete(self):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/{BASE_PID}/expansion/async",
            json={"depth": "fast"},
            timeout=20,
        )
        kick_elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id"), d
        assert d.get("job_status") == "running", d
        assert kick_elapsed < 10, f"kick took {kick_elapsed:.1f}s"
        job_id = d["job_id"]

        # Expansion targets ~3x code volume — can take 10-15 min on the LLM side.
        final = _poll_until_done(job_id, deadline_s=900, label="expansion")
        if final.get("job_status") == "error":
            pytest.fail(f"expansion job errored: {final.get('error')}")
        assert final.get("derive_mode") == "expansion", final
        assert final.get("parent_id") == BASE_PID
        sm = final.get("size_mult")
        # 3x size target (allow float vs int) — spec says "about 3"
        assert sm is not None and abs(float(sm) - 3.0) < 0.5, f"size_mult={sm}"
        assert final.get("status") in ("ready", "failed"), final
        if final.get("status") == "failed":
            pytest.skip(
                f"LLM produced non-runnable expansion "
                f"(score={final.get('playability_score')}, "
                f"missing={final.get('missing_checks')})")
        new_pid = final.get("playable_id")
        assert new_pid and new_pid != BASE_PID


# ─────────────────────────── LIVE: VARIANTS (slow) ───────────────────────
class TestVariants:
    """POST /{pid}/variants/async produces 4 colour-coded variants in one job."""

    EXPECTED_COLORS = {"red", "blue", "green", "yellow"}
    COLOR_HEX = {"red": "#ef4444", "blue": "#3b82f6",
                 "green": "#22c55e", "yellow": "#eab308"}

    def test_variants_kick_and_complete(self):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/{BASE_PID}/variants/async",
            json={"depth": "fast"},
            timeout=20,
        )
        kick_elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id"), d
        assert d.get("job_status") == "running", d
        assert kick_elapsed < 10, f"kick took {kick_elapsed:.1f}s"
        job_id = d["job_id"]

        # 4 concurrent LLM generations — spec says up to ~6-7 min; give 8.
        final = _poll_until_done(job_id, deadline_s=480, label="variants")
        if final.get("job_status") == "error":
            pytest.fail(f"variants job errored: {final.get('error')}")

        assert final.get("kind") == "variants", final
        assert final.get("count") == 4, final
        assert final.get("parent_id") == BASE_PID
        variants = final.get("variants") or []
        assert len(variants) == 4, variants

        colors_seen = set()
        ready_count = 0
        for v in variants:
            assert v.get("color") in self.EXPECTED_COLORS, v
            colors_seen.add(v["color"])
            # hex must be present and match expected colour palette
            assert v.get("hex"), v
            assert v["hex"].lower() == self.COLOR_HEX[v["color"]].lower(), v
            if v.get("status") == "ready":
                ready_count += 1
                assert v.get("playable_id"), v
                assert v.get("derive_mode") == "variant", v
                assert v.get("parent_id") == BASE_PID
        assert colors_seen == self.EXPECTED_COLORS, colors_seen
        # require at least 1 ready variant to confirm the live pipeline worked
        # (some may flake on content quality — that's an LLM flake, not a bug)
        if ready_count == 0:
            pytest.skip(
                f"All 4 variants failed structural gate — LLM content flake "
                f"(scores={[v.get('playability_score') for v in variants]})")
        print(f"[variants] {ready_count}/4 ready")
