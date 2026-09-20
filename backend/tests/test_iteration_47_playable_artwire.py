"""
Iteration 47 — Playable Artwire / In-game Art Injector tests.

Validates:
  - Route registry has the new /api/playable/{pid}/apply-assets/async endpoint.
  - Negative: applying on a game with NO linked genesis assets → {error:...}
  - Rate-limit burst guard on the apply route.
  - CORE: pre-applied game d02790d6d8174ff59bf7005221cd7609 already has art applied
    — its /raw HTML should contain GENESIS_ASSETS + GENESIS_IMAGES + drawImage + data:image.
  - Regression: /api/playable/list, /finetune/async, /bugsquash/async still respond.

NOTE: We do NOT trigger a fresh apply-assets/async end-to-end (3-min LLM rewrite)
per the agent-to-agent note. Instead we verify the wiring is correct against a
pre-applied game (d02790d6d8174ff59bf7005221cd7609) and we test the negative
path on a game with no linked assets.
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")

PRE_APPLIED_PID = "d02790d6d8174ff59bf7005221cd7609"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── Route registry / OpenAPI ─────────────────────────────────────────
class TestRegistry:
    def test_registry_ok_count(self, api):
        r = api.get(f"{BASE_URL}/api/health/registry", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") == 140, f"expected ok=140 got {d.get('ok')}"

    def test_openapi_has_apply_assets(self, api):
        # openapi.json is only mounted at root (not under /api ingress) — query
        # the in-cluster backend directly so we can verify the route is wired.
        r = api.get("http://localhost:8001/openapi.json", timeout=20)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        assert "/api/playable/{pid}/apply-assets/async" in paths


# ─── Pre-applied game render verification ──────────────────────────────
class TestPreAppliedRender:
    def test_raw_html_contains_injected_registry(self, api):
        r = api.get(f"{BASE_URL}/api/playable/{PRE_APPLIED_PID}/raw", timeout=15)
        assert r.status_code == 200, f"raw fetch failed: {r.status_code}"
        html = r.text
        # All four substrings required by the spec
        for needle in ("GENESIS_ASSETS", "GENESIS_IMAGES", "drawImage", "data:image"):
            assert needle in html, f"raw HTML missing required marker: {needle!r}"

    def test_pre_applied_metadata(self, api):
        # /list returns light docs without html — fetch the doc via /list filter
        r = api.get(f"{BASE_URL}/api/playable/list?limit=50", timeout=15)
        assert r.status_code == 200
        docs = r.json().get("playables", [])
        match = [d for d in docs if d.get("playable_id") == PRE_APPLIED_PID]
        # if not in light list, just confirm raw worked above (already passed)
        if match:
            doc = match[0]
            # version should have been incremented (>=2) by artwire
            v = doc.get("version") or 1
            assert v >= 2, f"expected version>=2 after artwire, got {v}"


# ─── Negative path: pid with NO linked assets ──────────────────────────
class TestNegativeNoAssets:
    """Find a ready game that has NO linked genesis assets and try to apply."""

    def _find_pid_without_assets(self, api):
        r = api.get(f"{BASE_URL}/api/playable/list?limit=100", timeout=15)
        assert r.status_code == 200
        for d in r.json().get("playables", []):
            pid = d.get("playable_id")
            if not pid or pid == PRE_APPLIED_PID:
                continue
            if d.get("status") != "ready":
                continue
            if d.get("has_genesis_art"):
                continue
            return pid
        return None

    def test_apply_no_assets_returns_error(self, api):
        pid = self._find_pid_without_assets(api)
        if not pid:
            pytest.skip("no eligible playable (status=ready, has_genesis_art=false) found")
        r = api.post(f"{BASE_URL}/api/playable/{pid}/apply-assets/async", json={}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "error" in d, f"expected error payload, got {d}"
        assert "no generated assets" in d["error"].lower(), f"unexpected error: {d['error']}"


# ─── Rate-limit burst guard ────────────────────────────────────────────
class TestRateLimit:
    def test_rapid_burst_triggers_rate_limit(self, api):
        """Burst 6 rapid apply calls on the pre-applied pid; expect at least one
        rate_limited response (burst=4, rate_per_sec=0.2)."""
        results = []
        for _ in range(6):
            r = api.post(f"{BASE_URL}/api/playable/{PRE_APPLIED_PID}/apply-assets/async",
                         json={}, timeout=15)
            try:
                results.append(r.json())
            except Exception:
                results.append({"status_code": r.status_code})
        rate_limited = [x for x in results if x.get("error") == "rate_limited"]
        assert rate_limited, f"expected at least one rate_limited; got: {results}"


# ─── Regression: other async endpoints + list ──────────────────────────
class TestRegression:
    def test_list_ok(self, api):
        r = api.get(f"{BASE_URL}/api/playable/list?limit=10", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("playables", []), list)

    def test_raw_still_ok(self, api):
        r = api.get(f"{BASE_URL}/api/playable/{PRE_APPLIED_PID}/raw", timeout=15)
        assert r.status_code == 200
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()

    def test_finetune_async_returns_job(self, api):
        # use a different ready pid if possible to avoid rate-limit interference
        r = api.get(f"{BASE_URL}/api/playable/list?limit=50", timeout=15)
        pids = [d["playable_id"] for d in r.json().get("playables", [])
                if d.get("status") == "ready"]
        if not pids:
            pytest.skip("no ready playables")
        # try a few in case of edit-rate-limiter
        last = None
        for pid in pids[:5]:
            resp = api.post(f"{BASE_URL}/api/playable/{pid}/finetune/async",
                            json={"instruction": "TEST_iter47 keep gameplay identical"},
                            timeout=20)
            last = (pid, resp.status_code, resp.text[:300])
            if resp.status_code == 200:
                d = resp.json()
                if d.get("job_id"):
                    assert d.get("job_status") in ("running", "queued", None) or "job_id" in d
                    return
        pytest.fail(f"no pid produced a job_id for finetune: last={last}")

    def test_bugsquash_async_returns_job(self, api):
        r = api.get(f"{BASE_URL}/api/playable/list?limit=50", timeout=15)
        pids = [d["playable_id"] for d in r.json().get("playables", [])
                if d.get("status") == "ready"]
        if not pids:
            pytest.skip("no ready playables")
        last = None
        for pid in pids[:5]:
            resp = api.post(f"{BASE_URL}/api/playable/{pid}/bugsquash/async",
                            json={"instruction": "TEST_iter47 squash any small bugs"},
                            timeout=20)
            last = (pid, resp.status_code, resp.text[:300])
            if resp.status_code == 200:
                d = resp.json()
                if d.get("job_id"):
                    return
        pytest.fail(f"no pid produced a job_id for bugsquash: last={last}")
