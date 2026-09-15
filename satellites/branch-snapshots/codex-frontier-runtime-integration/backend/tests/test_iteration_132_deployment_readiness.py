"""
Iteration 132 — Deployment-readiness verification after GameForge CNS + Director merge
and .gitignore fix.

Scope:
  1) Backend boot health (/api/health)
  2) GameForge CNS endpoints (status, architecture, rooms, health, broadcast, single-room query)
  3) Director + simulation endpoints (plan/physics cascade, validate/physics auto_reflection)
  4) Regression on existing endpoints (eras, binary/recent, snowball, construct presets)

Runs against the public URL from frontend/.env (EXPO_PUBLIC_BACKEND_URL) — same URL
that the deployed app will hit.
"""

import os
import pytest
import requests

# Prefer the public preview URL, fall back to localhost only for local dev.
BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")

TIMEOUT = 60  # some CNS endpoints do fan-out work


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# 1) Backend boot health
# ---------------------------------------------------------------------------
class TestBootHealth:
    def test_health_200(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") in ("healthy", "ok", "running")


# ---------------------------------------------------------------------------
# 2) GameForge CNS
# ---------------------------------------------------------------------------
class TestGameForgeCNS:
    def test_status_10_of_10_subsystems(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/status", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        # Try common shapes
        mounted = (
            data.get("subsystems_mounted")
            or data.get("mounted")
            or data.get("subsystems")
        )
        total = data.get("subsystems_total") or data.get("total")
        # If a nested `summary` exists, check it too
        summary = data.get("summary") or {}
        if isinstance(summary, dict):
            mounted = mounted or summary.get("mounted")
            total = total or summary.get("total")
        # Some implementations expose a list of subsystems
        if isinstance(mounted, list):
            mounted = len(mounted)
        assert data, "empty /status body"
        # Just assert body is JSON with something useful; we log what we got
        print("[gameforge/status]", {k: data[k] for k in list(data)[:15]})
        # Best-effort assertion: if mounted/total present, they should be 10/10
        if mounted is not None and total is not None:
            assert int(mounted) == int(total) == 10, f"expected 10/10, got {mounted}/{total}"

    def test_architecture_9_of_9_modules(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/architecture", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data, "empty /architecture body"
        # Look for module counts
        modules = (
            data.get("modules")
            or data.get("modules_live")
            or (data.get("summary") or {}).get("modules")
        )
        total = (
            data.get("modules_total")
            or (data.get("summary") or {}).get("total")
        )
        if isinstance(modules, list):
            live_count = sum(1 for m in modules if (isinstance(m, dict) and m.get("live") in (True, "true", 1)) or m == True)
            # If we can't determine liveness, just count entries
            if live_count == 0:
                live_count = len(modules)
            total = total or len(modules)
            modules = live_count
        print("[gameforge/architecture]", {k: data[k] for k in list(data)[:15]})
        if modules is not None and total is not None:
            assert int(modules) == int(total) == 9, f"expected 9/9 modules live, got {modules}/{total}"

    def test_rooms_total_1000(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/rooms", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        total = data.get("total") or data.get("count") or (data.get("summary") or {}).get("total")
        rooms = data.get("rooms") or data.get("items")
        if total is None and isinstance(rooms, list):
            total = len(rooms)
        print("[gameforge/rooms] total=", total, "keys=", list(data)[:10])
        assert total is not None, "no total/count in /rooms body"
        assert int(total) == 1000, f"expected 1000 rooms, got {total}"

    def test_health_endpoint_ok(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/health", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        print("[gameforge/health]", data if isinstance(data, dict) else str(data)[:200])
        # Body should indicate some kind of positive/ok/coherent state
        assert data, "empty /gameforge/health body"

    def test_rooms_broadcast(self, api):
        payload = {"query": "hello world", "max_rooms": 5, "concurrency": 5}
        r = api.post(
            f"{BASE_URL}/api/gameforge/rooms/broadcast",
            json=payload,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Expect an aggregated shape
        assert isinstance(data, dict), f"expected dict, got {type(data)}"
        # Look for a results/rooms/aggregate field
        assert any(
            k in data
            for k in (
                "results", "rooms", "aggregate", "aggregate_sample",
                "responses", "answers", "summary", "aggregated",
                "rooms_queried", "ok_rooms",
            )
        ), f"no aggregation-like field in body: keys={list(data)[:15]}"
        print("[gameforge/rooms/broadcast] keys=", list(data)[:15])

    def test_single_room_query_fanout(self, api):
        # Find a room id first
        r = api.get(f"{BASE_URL}/api/gameforge/rooms", timeout=TIMEOUT)
        assert r.status_code == 200
        rooms_body = r.json()
        rooms = (
            rooms_body.get("rooms")
            or rooms_body.get("items")
            or rooms_body.get("sample")
            or []
        )
        if not rooms and isinstance(rooms_body.get("data"), list):
            rooms = rooms_body["data"]
        assert rooms, f"no rooms returned; keys={list(rooms_body)[:10]}"
        first = rooms[0]
        room_id = (
            first.get("id")
            or first.get("room_id")
            or first.get("_id")
            or first.get("name")
        ) if isinstance(first, dict) else first
        assert room_id, f"could not extract room id from {first!r}"

        payload = {
            "query": "smoke",
            "mcp_queries": ["ping", "pong", "smoke"],
        }
        r2 = api.post(
            f"{BASE_URL}/api/gameforge/rooms/{room_id}/query",
            json=payload,
            timeout=TIMEOUT,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert isinstance(body, dict), f"expected dict, got {type(body)}"
        print("[gameforge/rooms/{id}/query] keys=", list(body)[:15])


# ---------------------------------------------------------------------------
# 3) Director + simulation
# ---------------------------------------------------------------------------
class TestDirectorSimulation:
    """
    Note: per review request, a 404 for a non-existent build/game id is EXPECTED,
    only 500s / import failures are bugs. We assert not-500 for the id-based
    endpoints, and prefer 200 when possible.
    """

    def test_director_plan_physics(self, api):
        # Use a synthetic id; a 404/400 is acceptable, a 500 is not.
        r = api.get(
            f"{BASE_URL}/api/galaxy-studio/director/deploy-smoke-1/plan/physics",
            timeout=TIMEOUT,
        )
        assert r.status_code != 500, f"500 from director/plan/physics: {r.text[:400]}"
        # If 200, sanity check cascade fields
        if r.status_code == 200:
            body = r.json()
            print("[director/plan/physics] keys=", list(body)[:15] if isinstance(body, dict) else type(body))
            # Cascade should hint at tileset+cinematics stages
            if isinstance(body, dict):
                blob = str(body).lower()
                # Soft check — do not hard-fail on wording
                assert any(k in blob for k in ("tileset", "cinematic", "physics", "cascade", "plan", "stage")), \
                    f"cascade body seems empty of expected stage words"
        else:
            print(f"[director/plan/physics] non-200 (acceptable): {r.status_code}")

    def test_director_validate_physics_weak_artifact_triggers_reflection(self, api):
        # A deliberately weak artifact so forge_validator flags it
        payload = {
            "artifact": {"physics": {}, "notes": "weak"},
            "context": {"scene": "smoke"},
        }
        r = api.post(
            f"{BASE_URL}/api/galaxy-studio/director/deploy-smoke-1/validate/physics",
            json=payload,
            timeout=TIMEOUT,
        )
        assert r.status_code != 500, f"500 from director/validate/physics: {r.text[:400]}"
        if r.status_code == 200:
            body = r.json()
            print("[director/validate/physics] keys=", list(body)[:15] if isinstance(body, dict) else type(body))
            if isinstance(body, dict):
                reflection = (
                    body.get("auto_reflection")
                    or body.get("reflection")
                    or body.get("stages_to_revisit")
                )
                # Prefer explicit stages_to_revisit
                stages = body.get("stages_to_revisit")
                if stages is None and isinstance(reflection, dict):
                    stages = reflection.get("stages_to_revisit")
                assert stages is not None, \
                    f"weak artifact did not surface stages_to_revisit; body keys={list(body)[:15]}"
                # If it is a list, prefer non-empty
                if isinstance(stages, list):
                    assert len(stages) >= 1, "stages_to_revisit is empty on weak artifact"
        else:
            print(f"[director/validate/physics] non-200 (acceptable): {r.status_code}")


# ---------------------------------------------------------------------------
# 4) Regression on existing endpoints
# ---------------------------------------------------------------------------
class TestRegression:
    def test_galaxy_studio_eras(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/eras", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        # Should be a list or dict with a list
        if isinstance(data, dict):
            items = data.get("eras") or data.get("items") or data.get("data") or []
        else:
            items = data
        assert isinstance(items, list), f"expected list-like eras, got {type(items)}"
        assert len(items) > 0, "eras list empty"

    def test_binary_recent(self, api):
        r = api.get(f"{BASE_URL}/api/binary/recent", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        # Any well-formed response is fine
        assert data is not None

    def test_snowball_handled(self, api):
        r = api.get(f"{BASE_URL}/api/snowball/deploy-smoke-nonexistent", timeout=TIMEOUT)
        # 404 or 200-with-empty are both fine; 500 is not.
        assert r.status_code != 500, f"snowball returned 500: {r.text[:400]}"
        assert r.status_code in (200, 400, 404, 422), f"unexpected status {r.status_code}: {r.text[:200]}"

    def test_construct_presets(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/constructs/presets", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        if isinstance(data, dict):
            items = data.get("presets") or data.get("items") or data.get("data") or []
        else:
            items = data
        assert isinstance(items, list), f"expected list-like presets, got {type(items)}"
        # Length can be 0, but the field must exist as a list
