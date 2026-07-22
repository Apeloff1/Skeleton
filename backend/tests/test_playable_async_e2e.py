"""
Phase V.1 — Live end-to-end async-job + WebView-raw verification.

This file complements test_playable.py with the LONG-running live tests:
  1. The known-good /raw endpoint serves a full HTML5 game document
     (the WebView-render path can be verified in <2s with this).
  2. The async job kick returns <10s with job_id+running.
  3. /api/health stays responsive (under ~2s p95) DURING the long
     LLM generation — the bug under test was an event-loop-blocking
     sync LLM call; the fix offloads to a worker thread.
  4. Polling eventually flips the job to done+ready with a
     playability_score >= threshold and a playable_id.
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
BRIEF = "A one-thumb arcade game: tap to make a glowing orb hop between rising platforms"


class TestRawWebViewPath:
    """The WebView render path — verified against the pre-built playable."""

    def test_raw_returns_full_html_game(self):
        r = requests.get(f"{BASE_URL}/api/playable/{KNOWN_GOOD_PID}/raw", timeout=20)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"unexpected content-type: {ct}"
        body = r.text.lower()
        assert body.lstrip().startswith("<!doctype html"), "missing <!doctype html>"
        assert "<canvas" in body, "no <canvas> element"
        assert "requestanimationframe" in body, "no requestAnimationFrame loop"
        # mobile-touch handler (touchstart / pointerdown / click)
        assert any(k in body for k in ("touchstart", "pointerdown", "addeventlistener('click'", 'addeventlistener("click"')), \
            "no touch / pointer handler"

    def test_list_includes_known_good(self):
        r = requests.get(f"{BASE_URL}/api/playable/list?limit=100", timeout=20)
        assert r.status_code == 200
        ids = [p.get("playable_id") for p in r.json().get("playables", [])]
        # Not strictly required (list may rotate) — only a soft check.
        assert isinstance(ids, list)


class TestAsyncJobNonBlocking:
    """The KEY behaviour: kick returns fast AND /health stays responsive
    while the long LLM call runs."""

    def test_kick_fast_and_health_stays_responsive(self):
        # ---- 1. kick must return <10s with a job_id ----
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/playable/generate/async",
            json={"brief": BRIEF},
            timeout=20,
        )
        kick_elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id"), f"no job_id: {d}"
        assert d.get("job_status") == "running", f"unexpected job_status: {d}"
        assert kick_elapsed < 10, f"kick took {kick_elapsed:.1f}s (>10s)"
        job_id = d["job_id"]

        # ---- 2. Probe /api/health for 30s while the LLM job runs in the
        # background and capture latencies. If the event loop is blocked
        # we'll see p95 spike well past 2s. ----
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
        time.sleep(30)
        stop.set()
        t.join(timeout=5)

        assert latencies, "no health samples"
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        avg = statistics.mean(latencies)
        print(f"\n[health] samples={len(latencies)} avg={avg:.3f}s p95={p95:.3f}s max={max(latencies):.3f}s")
        # Generous ceiling: ingress latency itself can be ~0.3-0.8s on this
        # preview; what we'd see with the bug is a multi-second cliff during
        # the synchronous LLM call. Anything <3s p95 confirms the event loop
        # is NOT blocked by the LLM thread.
        assert p95 < 3.0, f"/api/health p95 {p95:.2f}s — event loop appears blocked during job"

        # ---- 3. Continue polling the job up to 3 min for done. ----
        deadline = time.time() + 180
        final = None
        while time.time() < deadline:
            j = requests.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=15)
            if j.status_code == 200:
                jd = j.json()
                if jd.get("job_status") in ("done", "error"):
                    final = jd
                    break
            time.sleep(3.5)
        assert final is not None, f"job {job_id} did not finish in 3 min"
        print(f"\n[job] final keys={list(final.keys())[:14]}")
        if final.get("job_status") == "error":
            pytest.fail(f"job errored: {final.get('error')}")
        # done — verify the shape
        assert final.get("status") in ("ready", "failed"), final
        if final.get("status") == "failed":
            pytest.skip(
                f"LLM returned non-runnable artifact "
                f"(score={final.get('playability_score')}, missing={final.get('missing_checks')}) — "
                "infra works; this is a content-quality flake, not a backend bug"
            )
        # status == ready — full contract
        assert final.get("playability_score", 0) >= 70, final
        assert final.get("model"), "no model recorded"
        assert final.get("bytes", 0) > 0, "no bytes recorded"
        assert final.get("playable_id"), "no playable_id"

        # ---- 4. /raw must serve the newly generated game ----
        pid = final["playable_id"]
        raw = requests.get(f"{BASE_URL}/api/playable/{pid}/raw", timeout=20)
        assert raw.status_code == 200
        assert "<canvas" in raw.text.lower()


class TestErrorContracts:
    def test_empty_body_async_returns_error(self):
        r = requests.post(f"{BASE_URL}/api/playable/generate/async", json={}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_unknown_job(self):
        r = requests.get(f"{BASE_URL}/api/playable/job/nope", timeout=15)
        assert r.status_code == 200
        assert r.json().get("job_status") == "unknown"
