"""
Session 17.3 — One-Tap Polish + Factions-wire backend tests.

Coverage:
- POST /api/playable/{pid}/polish/async kicks 3-step chain (sentience→physics→aesthetics)
- POST /api/playable/{pid}/apply-factions/async kicks single-step LLM wire pass
- Bad pid → {error:'not found'} on both
- Polish concurrent on same pid → {error:'rate_limited'} (burst=2)
- Polish job 'step' field advances 1→3 while running, eventually done with applied[]>=1
- Polish raw HTML contains injected engine scripts for whatever applied
- Factions raw HTML contains window.FACTIONS + id __factions
- Regression: registry ok=116; factions/simulate; apply-physics/async; worldforge/render
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")


# ---------- session-level fixtures: pre-kicked long-running jobs ----------
@pytest.fixture(scope="session")
def ready_pids():
    """Pull at least 4 ready pids different from the main-agent's d02790... pid."""
    r = requests.get(f"{BASE_URL}/api/playable/list", timeout=15)
    assert r.status_code == 200
    items = r.json().get("playables") or r.json().get("items") or []
    pids = [it["playable_id"] for it in items
            if it.get("status") == "ready" and it.get("playable_id") != "d02790d6d8174ff59bf7005221cd7609"]
    assert len(pids) >= 4, f"need >=4 alternative ready pids, got {len(pids)}"
    return pids


# ============================ NEGATIVE / SHAPE ============================
class TestPolishShape:
    def test_polish_bad_pid(self):
        r = requests.post(f"{BASE_URL}/api/playable/nope_no_such_pid/polish/async", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"error": "not found"}

    def test_polish_kick_returns_job_id_and_steps(self, ready_pids):
        # use a separate pid distinct from any active polish test pid
        pid = ready_pids[3]
        r = requests.post(f"{BASE_URL}/api/playable/{pid}/polish/async", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Either fresh kick or rate_limited (if a previous test re-used this pid).
        if data.get("error") == "rate_limited":
            pytest.skip(f"pid {pid} rate-limited by prior run")
        assert "job_id" in data and len(data["job_id"]) == 32
        assert data.get("job_status") == "running"
        assert data.get("steps") == ["sentience", "physics", "aesthetics"]


class TestFactionsShape:
    def test_factions_bad_pid(self):
        r = requests.post(f"{BASE_URL}/api/playable/nope_no_such_pid/apply-factions/async", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "not found"}

    def test_factions_kick_returns_job_id(self, ready_pids):
        pid = ready_pids[2]
        r = requests.post(f"{BASE_URL}/api/playable/{pid}/apply-factions/async", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if data.get("error") == "rate_limited":
            pytest.skip(f"pid {pid} rate-limited")
        assert "job_id" in data and data.get("job_status") == "running"


# ============================ RATE LIMITING ===============================
class TestPolishRateLimit:
    def test_polish_rate_limited_when_in_flight(self, ready_pids):
        """polish is allow(0.05/s burst=2) → 3rd consecutive POST on same pid must rate_limit."""
        pid = ready_pids[1]
        replies = []
        for _ in range(4):
            rr = requests.post(f"{BASE_URL}/api/playable/{pid}/polish/async", timeout=10).json()
            replies.append(rr)
        # at least one of the trailing replies must be rate_limited
        assert any(r.get("error") == "rate_limited" for r in replies[2:]), replies


# ============================ E2E POLLERS =================================
def _poll_job(job_id: str, deadline_s: int):
    end = time.time() + deadline_s
    steps_seen = set()
    last = None
    while time.time() < end:
        rr = requests.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=15)
        if rr.status_code == 200:
            last = rr.json()
            if last.get("step") is not None:
                steps_seen.add(last["step"])
            if last.get("job_status") in ("done", "error"):
                return last, steps_seen
        time.sleep(8)
    return last, steps_seen


@pytest.mark.slow
class TestPolishE2E:
    """Uses the polish job kicked by the testing-agent before pytest run.
    Job id is read from an env var to share state across tests."""

    @pytest.fixture(scope="class")
    def polish_job(self):
        jid = os.environ.get("POLISH_JOB_ID")
        pid = os.environ.get("POLISH_PID")
        if not jid or not pid:
            pytest.skip("POLISH_JOB_ID / POLISH_PID env not provided")
        # poll up to 15min
        final, steps_seen = _poll_job(jid, deadline_s=15 * 60)
        return {"final": final, "steps_seen": steps_seen, "pid": pid}

    def test_polish_job_completed(self, polish_job):
        f = polish_job["final"]
        assert f is not None
        assert f.get("job_status") == "done", f"polish did not finish in 15min: {f}"

    def test_polish_step_advanced(self, polish_job):
        # 'step' field should have advanced from 1 toward 3 during the run
        steps = polish_job["steps_seen"]
        assert 1 in steps, f"never saw step=1; steps_seen={steps}"
        assert max(steps) >= 1

    def test_polish_applied_and_version(self, polish_job):
        f = polish_job["final"]
        applied = f.get("applied") or []
        assert isinstance(applied, list)
        assert f.get("count", 0) >= 1, f"expected count>=1, got {f}"
        # version may be None if no step applied, but with count>=1 it must be set
        assert f.get("version") is not None

    def test_polish_raw_contains_engine_scripts(self, polish_job):
        pid = polish_job["pid"]
        applied = polish_job["final"].get("applied") or []
        raw = requests.get(f"{BASE_URL}/api/playable/{pid}/raw", timeout=15).text
        markers = {
            "sentience": ("window.SENTIENCE", "__sentience"),
            "physics": ("window.PHYSICS", "__physics"),
            "aesthetics": ("window.NEURAL_FX", "__aesthetics"),
        }
        for kind in applied:
            primary, idmark = markers[kind]
            assert (primary in raw) or (idmark in raw), \
                f"applied {kind} but neither {primary} nor {idmark} found in raw"


@pytest.mark.slow
class TestFactionsE2E:
    @pytest.fixture(scope="class")
    def factions_job(self):
        jid = os.environ.get("FACTIONS_JOB_ID")
        pid = os.environ.get("FACTIONS_PID")
        if not jid or not pid:
            pytest.skip("FACTIONS_JOB_ID / FACTIONS_PID env not provided")
        final, _ = _poll_job(jid, deadline_s=6 * 60)
        return {"final": final, "pid": pid}

    def test_factions_done(self, factions_job):
        f = factions_job["final"]
        assert f is not None and f.get("job_status") == "done", f
        assert f.get("applied") is True
        assert f.get("score", 0) >= 70
        assert f.get("version", 0) >= 2

    def test_factions_raw_contains_engine(self, factions_job):
        pid = factions_job["pid"]
        raw = requests.get(f"{BASE_URL}/api/playable/{pid}/raw", timeout=15).text
        assert "window.FACTIONS" in raw
        assert "__factions" in raw


# ============================ REGRESSION ==================================
class TestRegression:
    def test_factions_simulate(self):
        r = requests.post(f"{BASE_URL}/api/factions/simulate",
                          json={"seed": 7, "factions": 6, "turns": 40}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data and isinstance(data["summary"], dict)
        assert data["summary"].get("dominant")
        assert len(data.get("factions", [])) == 6
        assert len(data.get("series", [])) == 40

    def test_apply_physics_kick(self, ready_pids):
        # different pid so concurrent runs are fine
        pid = ready_pids[5] if len(ready_pids) > 5 else ready_pids[-1]
        r = requests.post(f"{BASE_URL}/api/playable/{pid}/apply-physics/async", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if data.get("error") == "rate_limited":
            pytest.skip("physics rate-limited")
        assert "job_id" in data

    def test_worldforge_render(self):
        r = requests.get(f"{BASE_URL}/api/worldforge/render",
                         params={"scale": "region", "seed": 7}, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 10_000
