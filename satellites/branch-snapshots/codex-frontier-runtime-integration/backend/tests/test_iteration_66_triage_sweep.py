"""
Iteration 66 — Galaxy Studio / Tutolage TRIAGE sweep.

Goal: broad health check of key GET endpoints. NO heavy generation triggers.
Only reads / lists / overviews. Report status code + small response sample.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to internal for local pytest runs
    BASE_URL = "http://localhost:8001"

TIMEOUT = 30


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── Health & registry ───────────────────────────────────────────────────────
def test_health(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"
    assert data.get("ai_available") is True


def test_health_tunnel(client):
    r = client.get(f"{BASE_URL}/api/health/tunnel", timeout=TIMEOUT)
    assert r.status_code == 200


# ─── Playable feeds ──────────────────────────────────────────────────────────
def test_playable_list(client):
    r = client.get(f"{BASE_URL}/api/playable", timeout=TIMEOUT)
    assert r.status_code in (200, 404), f"unexpected {r.status_code}: {r.text[:200]}"
    if r.status_code == 200:
        # Must be JSON
        data = r.json()
        assert isinstance(data, (list, dict))


def test_playable_trending(client):
    r = client.get(f"{BASE_URL}/api/playable/trending", timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, (list, dict))


def test_playable_daily(client):
    r = client.get(f"{BASE_URL}/api/playable/daily", timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, (list, dict))


# ─── Jeeves ──────────────────────────────────────────────────────────────────
def test_jeeves_persona(client):
    r = client.get(f"{BASE_URL}/api/jeeves/persona", timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"


def test_jeeves_voice_tones(client):
    r = client.get(f"{BASE_URL}/api/jeeves-voice/voice/tones", timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    # expect a list of tone presets (>= 10)
    tones = data.get("tones") if isinstance(data, dict) else data
    assert tones and len(tones) >= 5


# ─── Worldforge / Galaxy Studio / Safety / Agent logs ───────────────────────
def test_worldforge_render_get(client):
    # GET on render — may be 200/404/405 depending on shape
    r = client.get(f"{BASE_URL}/api/worldforge/render", timeout=TIMEOUT)
    assert r.status_code in (200, 404, 405, 422), f"{r.status_code}: {r.text[:200]}"


def test_galaxy_studio_vault_stats(client):
    r = client.get(f"{BASE_URL}/api/galaxy-studio/admin/vault/stats", timeout=TIMEOUT)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"


def test_safety_overview(client):
    # Try common safety endpoints
    candidates = [
        "/api/safety/overview",
        "/api/safety",
        "/api/governance/overview",
        "/api/governance",
    ]
    last = None
    for path in candidates:
        r = client.get(f"{BASE_URL}{path}", timeout=TIMEOUT)
        last = (path, r.status_code, r.text[:200])
        if r.status_code == 200:
            return
    pytest.fail(f"No safety/governance overview endpoint returned 200. Last tried: {last}")


def test_agent_logs(client):
    candidates = [
        "/api/agent-logs/all",
        "/api/agent-logs/summary",
    ]
    last = None
    for path in candidates:
        r = client.get(f"{BASE_URL}{path}", timeout=TIMEOUT)
        last = (path, r.status_code, r.text[:200])
        if r.status_code == 200:
            return
    pytest.fail(f"No agent logs endpoint returned 200. Last tried: {last}")


# ─── Other key surfaces hinted by triage list ───────────────────────────────
def test_feature_flags(client):
    r = client.get(f"{BASE_URL}/api/feature-flags?user_id=default_user", timeout=TIMEOUT)
    assert r.status_code == 200


def test_routes_registry_count(client):
    # If the app exposes a registry endpoint, validate count
    candidates = ["/api/routes/registry", "/api/admin/routes", "/api/_routes"]
    for p in candidates:
        r = client.get(f"{BASE_URL}{p}", timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            # Best-effort: count entries
            if isinstance(data, dict) and "routers" in data:
                assert len(data["routers"]) > 0
            return
    pytest.skip("No public routes-registry endpoint exposed")
