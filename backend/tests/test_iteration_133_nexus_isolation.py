"""
Iteration 133 — Verify NEW /api/nexus router + isolation-guard non-regression.

Scope (backend-only):
  1) NEW /api/nexus endpoints respond correctly:
     - GET /api/nexus/status → domains list (>=1, ideally 12) + module_count (~69)
     - GET /api/nexus/orchestrator → {ok:true, orchestrator:"NexusOrchestrator"}
     - POST /api/nexus/event → {ok:true, result:...} OR clean 207 (NOT 500)
  2) CRITICAL — isolation guard must not shadow/break backend modules AFTER
     calling any nexus endpoint. Regression-check:
     - GET /api/health 200
     - GET /api/galaxy-studio/eras 200
     - GET /api/gameforge/status 200
     - GET /api/binary/recent 200
  3) 83-file gameforge merge regression:
     - GET /api/gameforge/architecture → 9/9 live
     - GET /api/gameforge/rooms → total == 1000
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")

TIMEOUT = 30


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─────────────────────────────────────────────────────────────────────
# 1) /api/nexus — new router
# ─────────────────────────────────────────────────────────────────────
class TestNexusRouter:
    def test_nexus_status_shape_and_counts(self, api):
        r = api.get(f"{BASE_URL}/api/nexus/status", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "domains" in data, data
        assert "module_count" in data, data
        assert isinstance(data["domains"], list)
        assert isinstance(data["module_count"], int)
        # Expected: 12 domains, ~69 modules per problem statement.
        assert len(data["domains"]) >= 1, f"expected non-empty domains: {data}"
        assert data["module_count"] >= 1, f"expected module_count > 0: {data}"
        print(
            f"[nexus/status] domains={len(data['domains'])} "
            f"module_count={data['module_count']} names={data['domains']}"
        )
        # Log — main agent target is 12 and 69
        if len(data["domains"]) != 12 or data["module_count"] != 69:
            print(
                f"[WARN] domains/module_count not exactly (12,69): "
                f"got ({len(data['domains'])}, {data['module_count']})"
            )

    def test_nexus_orchestrator_ok(self, api):
        r = api.get(f"{BASE_URL}/api/nexus/orchestrator", timeout=TIMEOUT)
        # Contract: 200 with ok:true OR 207 with ok:false. Must NOT be 500.
        assert r.status_code in (200, 207), r.text
        data = r.json()
        if r.status_code == 200:
            assert data.get("ok") is True, data
            assert data.get("orchestrator") == "NexusOrchestrator", data
        else:
            assert data.get("ok") is False, data
            print(f"[nexus/orchestrator] clean 207 error: {data.get('error')}")

    def test_nexus_event_ok_or_clean_207(self, api):
        payload = {"event": "test important event", "source": "test"}
        r = api.post(f"{BASE_URL}/api/nexus/event", json=payload, timeout=TIMEOUT)
        # Contract: 200 with ok:true OR clean 207. Must NOT be 500.
        assert r.status_code in (200, 207), r.text
        data = r.json()
        if r.status_code == 200:
            assert data.get("ok") is True, data
            assert "result" in data, data
            print(f"[nexus/event] ok result keys={list((data.get('result') or {}).keys()) if isinstance(data.get('result'), dict) else type(data.get('result')).__name__}")
        else:
            assert data.get("ok") is False, data
            print(f"[nexus/event] clean 207 error: {data.get('error')}")


# ─────────────────────────────────────────────────────────────────────
# 2) CRITICAL — isolation guard non-regression check
#    These endpoints MUST still work AFTER nexus endpoints were hit.
# ─────────────────────────────────────────────────────────────────────
class TestIsolationGuardNoRegression:
    """Run these AFTER hitting the nexus endpoints to verify sys.path /
    sys.modules were restored and the vendored utils/security/testing
    directories didn't shadow the live backend."""

    def _prime_nexus(self, api):
        # Touch each nexus endpoint so isolation guard is exercised.
        api.get(f"{BASE_URL}/api/nexus/status", timeout=TIMEOUT)
        api.get(f"{BASE_URL}/api/nexus/orchestrator", timeout=TIMEOUT)
        api.post(
            f"{BASE_URL}/api/nexus/event",
            json={"event": "prime", "source": "regression"},
            timeout=TIMEOUT,
        )

    def test_health_still_ok(self, api):
        self._prime_nexus(api)
        r = api.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_eras_still_ok(self, api):
        self._prime_nexus(api)
        r = api.get(f"{BASE_URL}/api/galaxy-studio/eras", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        # Should be a non-empty list of era objects.
        body = r.json()
        assert body, f"expected non-empty eras: {body}"

    def test_gameforge_status_still_ok(self, api):
        self._prime_nexus(api)
        r = api.get(f"{BASE_URL}/api/gameforge/status", timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_binary_recent_still_ok(self, api):
        self._prime_nexus(api)
        r = api.get(f"{BASE_URL}/api/binary/recent", timeout=TIMEOUT)
        assert r.status_code == 200, r.text


# ─────────────────────────────────────────────────────────────────────
# 3) 83-file gameforge merge regression
# ─────────────────────────────────────────────────────────────────────
class TestGameForgeMergeRegression:
    def test_architecture_9_of_9_live(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/architecture", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        # Look for 9/9 semantics — the response should indicate 9 modules live.
        # Accept a variety of shapes: {"live": 9, "total": 9} or
        # {"modules_live": 9, "modules_total": 9} or a "summary" string.
        live_ok = False
        for key_live, key_total in (
            ("live", "total"),
            ("modules_live", "modules_total"),
            ("live_modules", "total_modules"),
        ):
            if data.get(key_live) == 9 and data.get(key_total) == 9:
                live_ok = True
                break
        if not live_ok:
            # Fallback: count modules in a "modules" list where each has
            # status == "live".
            mods = data.get("modules") or data.get("architecture") or []
            if isinstance(mods, list) and len(mods) == 9:
                statuses = [m.get("status") or m.get("state") for m in mods if isinstance(m, dict)]
                if all(s == "live" for s in statuses):
                    live_ok = True
        assert live_ok, f"expected 9/9 live modules; got shape={list(data.keys())} data={str(data)[:400]}"

    def test_rooms_total_1000(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/rooms", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total") == 1000, (
            f"expected total=1000; got total={data.get('total')} keys={list(data.keys())}"
        )
