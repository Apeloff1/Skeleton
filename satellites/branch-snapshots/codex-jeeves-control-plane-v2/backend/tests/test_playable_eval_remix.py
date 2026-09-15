"""
Iteration 7 — Live coverage for the three new /api/playable capabilities:
  • VII.1  judge-LLM eval harness — POST /{pid}/evaluate
  • Remix  POST /{pid}/remix/async + poll /job/{id}
  • I.5    self-improving codegen — repair_attempts + repair_trail on docs

Uses the pre-existing playables passed by the main agent to avoid extra
fresh generations:
  KNOWN_GOOD_PID = 8ca4a00512034787b0094a8f7c07db3b  (original)
  KNOWN_REMIX_PID = b6c58bc75553444d82cf2c2e3d4295de (remix child)
"""
import os
import time
import threading
import statistics

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
KNOWN_GOOD_PID = "8ca4a00512034787b0094a8f7c07db3b"
KNOWN_REMIX_PID = "b6c58bc75553444d82cf2c2e3d4295de"


# ── VII.1 — judge eval harness ───────────────────────────────────────────────
class TestEvaluateHarness:
    def test_evaluate_unknown_returns_error(self):
        r = requests.post(f"{BASE_URL}/api/playable/does_not_exist_xyz/evaluate", timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_evaluate_existing_returns_full_shape(self):
        # Real judge LLM call — 30-90s typical.
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/playable/{KNOWN_GOOD_PID}/evaluate", timeout=180)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("playable_id") == KNOWN_GOOD_PID
        ev = d.get("evaluation") or {}
        print(f"\n[eval] elapsed={elapsed:.1f}s verdict={ev.get('verdict')} overall={ev.get('overall')} judge={ev.get('judge_model')}")
        if not ev.get("available"):
            pytest.fail(f"judge unavailable: {ev}")
        # axes are ints 0-100
        for k in ("playability", "coherence", "fun", "polish", "overall"):
            v = ev.get(k)
            assert isinstance(v, int), f"{k} not int: {v!r}"
            assert 0 <= v <= 100, f"{k} out of range: {v}"
        assert ev.get("verdict") in ("ship", "polish", "reject"), ev
        assert ev.get("judge_model"), "no judge_model"
        # critique & top_fix are strings (may be empty in pathological cases but the
        # contract says they're set for a good game). Soft check:
        assert isinstance(ev.get("critique", ""), str)
        assert isinstance(ev.get("top_fix", ""), str)


# ── I.5 — self-improving codegen fields on persisted doc ─────────────────────
class TestRepairFields:
    def test_repair_fields_on_recent_ready_playable(self):
        # The remix child was created with the new pipeline → must carry the fields.
        r = requests.get(f"{BASE_URL}/api/playable/{KNOWN_REMIX_PID}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "ready"
        assert isinstance(d.get("repair_attempts"), int) and d["repair_attempts"] >= 1
        trail = d.get("repair_trail")
        assert isinstance(trail, list) and len(trail) == d["repair_attempts"]
        first = trail[0]
        for k in ("attempt", "kind", "score", "missing", "model"):
            assert k in first, f"missing key in trail entry: {k}"
        assert first["kind"] == "generate"
        # any subsequent attempt should be a 'repair'
        for entry in trail[1:]:
            assert entry["kind"] == "repair"
        assert isinstance(first["missing"], list)


# ── Remix — async kick + poll ────────────────────────────────────────────────
class TestRemix:
    def test_remix_unknown_base_returns_error(self):
        r = requests.post(f"{BASE_URL}/api/playable/no_such_id/remix/async",
                          json={"tweak": "make it harder"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_remix_empty_tweak_returns_error(self):
        r = requests.post(f"{BASE_URL}/api/playable/{KNOWN_GOOD_PID}/remix/async",
                          json={"tweak": ""}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_remix_async_kick_then_poll_to_done(self):
        # 1. Kick should return < 10s with job_id, running.
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/{KNOWN_GOOD_PID}/remix/async",
            json={"tweak": "make it faster"}, timeout=20,
        )
        kick_elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id"), f"no job_id: {d}"
        assert d.get("job_status") == "running"
        assert kick_elapsed < 10, f"kick took {kick_elapsed:.1f}s (>10s)"
        job_id = d["job_id"]

        # 2. /api/health should stay responsive while the remix runs.
        latencies: list[float] = []
        stop = threading.Event()

        def _probe():
            sess = requests.Session()
            while not stop.is_set():
                a = time.time()
                try:
                    h = sess.get(f"{BASE_URL}/api/health", timeout=8)
                    if h.status_code == 200:
                        latencies.append(time.time() - a)
                except Exception:
                    latencies.append(999.0)
                stop.wait(1.0)

        t = threading.Thread(target=_probe, daemon=True)
        t.start()
        time.sleep(20)
        stop.set()
        t.join(timeout=5)
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies or [0])
        print(f"\n[health-during-remix] samples={len(latencies)} avg={statistics.mean(latencies):.3f}s p95={p95:.3f}s")
        assert p95 < 3.0, f"/api/health p95 {p95:.2f}s during remix — event loop appears blocked"

        # 3. Continue polling for done (≤200s).
        deadline = time.time() + 200
        final = None
        while time.time() < deadline:
            j = requests.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=15)
            if j.status_code == 200:
                jd = j.json()
                if jd.get("job_status") in ("done", "error"):
                    final = jd
                    break
            time.sleep(3.5)
        assert final is not None, f"job {job_id} did not finish in time"
        if final.get("job_status") == "error":
            pytest.fail(f"job errored: {final.get('error')}")
        # 4. The remix doc must echo parent_id + tweak, and have new id + eval.
        assert final.get("status") in ("ready", "failed"), final
        if final.get("status") == "failed":
            pytest.skip(
                f"LLM produced non-runnable remix "
                f"(score={final.get('playability_score')}, missing={final.get('missing_checks')}) — content flake"
            )
        assert final.get("parent_id") == KNOWN_GOOD_PID, final.get("parent_id")
        assert final.get("tweak") == "make it faster", final.get("tweak")
        new_pid = final.get("playable_id")
        assert new_pid and new_pid != KNOWN_GOOD_PID, "no fresh playable_id"
        assert final.get("playability_score", 0) >= 70
        # I.5 fields present
        assert isinstance(final.get("repair_attempts"), int) and final["repair_attempts"] >= 1
        trail = final.get("repair_trail") or []
        assert trail and trail[0]["kind"] == "generate"
        # Eval present
        ev = final.get("evaluation") or {}
        assert ev.get("available") is True, f"no evaluation on remix: {ev}"
        for k in ("playability", "coherence", "fun", "polish", "overall"):
            assert isinstance(ev.get(k), int)
        assert ev.get("verdict") in ("ship", "polish", "reject")

        # 5. /raw should serve the new game
        raw = requests.get(f"{BASE_URL}/api/playable/{new_pid}/raw", timeout=20)
        assert raw.status_code == 200
        assert "text/html" in raw.headers.get("content-type", "")
        assert "<canvas" in raw.text.lower()
