"""
Iteration 11 — Verify the EXPANSION ceiling-lift.

The previous global QUALITY_TIME_BUDGET (210s) was expiring during expansion's
long generation, so the judge-driven quality-refinement loop NEVER ran for
expansion (no `quality_repair` entries in repair_trail, size_mult capped at 3x).

The fix adds a per-mode quality profile so expansion runs the FULL deluxe loop:
  - size_mult 4.0
  - max_refine 2
  - quality_target 92
  - time_budget 1200s (20 min)
  - larger HTML context (28000)
  - forced studio depth

This test kicks an expansion job, polls up to 25 min, and asserts the deluxe
signals — most importantly, that repair_trail now CONTAINS at least one
`quality_repair` entry (the smoking gun that the judge loop actually ran).

Regression: /api/health and /api/playable/leaderboard?limit=5 still 200.
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
# Allow tests to pre-seed a job id (so the long expansion can be kicked
# externally and reused by pytest without re-kicking). Falls back to a fresh
# kick when unset.
PRESEED_JOB = os.environ.get("EXPANSION_JOB_ID", "").strip()


def _poll(job_id: str, deadline_s: int, label: str) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < deadline_s:
        try:
            r = requests.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=20)
            if r.status_code == 200:
                jd = r.json()
                last = jd
                if jd.get("job_status") in ("done", "error"):
                    print(f"[{label}] finished in {time.time() - t0:.1f}s "
                          f"status={jd.get('job_status')}")
                    return jd
        except Exception as e:
            print(f"[{label}] poll error: {e}")
        time.sleep(5)
    raise AssertionError(
        f"[{label}] job {job_id} did not finish in {deadline_s}s; last={last}")


# ─────────────────────────── REGRESSION (fast) ───────────────────────────
class TestRegression:
    def test_health_200(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"

    def test_leaderboard_200_ranked(self):
        r = requests.get(f"{BASE_URL}/api/playable/leaderboard?limit=5", timeout=15)
        assert r.status_code == 200
        d = r.json()
        rows = d.get("leaderboard") or []
        assert 1 <= len(rows) <= 5
        assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))
        scores = [row["score"] for row in rows]
        assert scores == sorted(scores, reverse=True), scores

    def test_base_playable_ready(self):
        r = requests.get(f"{BASE_URL}/api/playable/{BASE_PID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "ready"
        assert d.get("playable_id") == BASE_PID


# ─────────────────────────── EXPANSION CEILING-LIFT ──────────────────────
class TestExpansionCeilingLift:
    """The flagship test — proves the judge-driven quality-refinement loop now
    runs for expansion and the size ceiling has been lifted to 4x."""

    def test_expansion_runs_deluxe_loop(self):
        if PRESEED_JOB:
            job_id = PRESEED_JOB
            print(f"[expansion] reusing pre-seeded job_id={job_id}")
        else:
            t0 = time.time()
            r = requests.post(
                f"{BASE_URL}/api/playable/{BASE_PID}/expansion/async",
                json={},
                timeout=30,
            )
            kick_elapsed = time.time() - t0
            assert r.status_code == 200, r.text
            d = r.json()
            assert d.get("job_id"), d
            assert d.get("job_status") == "running", d
            assert kick_elapsed < 15, f"kick took {kick_elapsed:.1f}s"
            job_id = d["job_id"]
            print(f"[expansion] kicked job_id={job_id} in {kick_elapsed:.1f}s")

        # 25 min deadline — expansion now runs one generation + up to 2
        # judge-driven quality_repair passes on a ~70-100KB file.
        final = _poll(job_id, deadline_s=1500, label="expansion")
        if final.get("job_status") == "error":
            pytest.fail(f"expansion job errored: {final.get('error')}")

        # ── basic shape ──
        assert final.get("status") == "ready", final
        assert final.get("derive_mode") == "expansion", final
        assert final.get("parent_id") == BASE_PID, final
        new_pid = final.get("playable_id")
        assert new_pid and new_pid != BASE_PID, final

        # ── ceiling-lift: size_mult must now be 4.0 (was 3.0) ──
        sm = final.get("size_mult")
        assert sm is not None, final
        assert abs(float(sm) - 4.0) < 0.01, f"expected size_mult==4.0, got {sm}"

        # ── CRITICAL signal: judge-driven refinement loop ran ──
        trail = final.get("repair_trail") or []
        assert isinstance(trail, list) and trail, f"repair_trail missing/empty: {trail}"
        kinds = [t.get("kind") for t in trail]
        assert "quality_repair" in kinds, (
            f"ceiling-lift FAILED — no 'quality_repair' entry in repair_trail. "
            f"kinds seen={kinds!r}. This is the exact regression the fix targets."
        )
        print(f"[expansion] repair_trail kinds={kinds}")

        # ── evaluation present with integer overall ──
        ev = final.get("evaluation") or {}
        assert ev.get("available") is True, f"evaluation not available: {ev}"
        overall = ev.get("overall")
        assert isinstance(overall, int), f"evaluation.overall not int: {overall!r}"
        print(f"[expansion] evaluation.overall={overall}")

        # ── deluxe size envelope: well above ~72KB (3x base ~24KB) ──
        bytes_ = final.get("bytes", 0)
        assert isinstance(bytes_, int) and bytes_ > 72000, (
            f"expansion bytes={bytes_} not clearly larger than the prior 3x ceiling "
            f"(~72KB). Expected well above 72000."
        )
        print(f"[expansion] bytes={bytes_}")

        # ── persistence sanity ──
        g = requests.get(f"{BASE_URL}/api/playable/{new_pid}", timeout=15)
        assert g.status_code == 200
        gd = g.json()
        assert gd.get("derive_mode") == "expansion"
        assert gd.get("parent_id") == BASE_PID
        assert gd.get("status") == "ready"
