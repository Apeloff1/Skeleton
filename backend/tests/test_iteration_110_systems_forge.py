"""Iteration 110 — Systems Forge backend smoke + enrich tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://player-retention.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api/galaxy-studio/systems"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- list systems
def test_list_systems_returns_12_with_pipeline(s):
    r = s.get(API, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("count") == 12, f"got count={d.get('count')}"
    assert len(d.get("systems", [])) == 12
    assert len(d.get("pipeline", [])) == 7
    for sys_item in d["systems"]:
        assert sys_item["knob_count"] > 0
        assert sys_item["option_count"] > 0


# --- narrative detail
def test_narrative_detail_has_knobs_and_options(s):
    r = s.get(f"{API}/narrative", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("system", {}).get("key") == "narrative"
    knobs = d.get("knobs") or []
    assert len(knobs) >= 1
    for k in knobs:
        assert "options" in k and len(k["options"]) >= 1
        assert "key" in k


# --- blueprint deterministic
def test_blueprint_deterministic(s):
    r1 = s.get(f"{API}/economy/blueprint?seed=5", timeout=15)
    r2 = s.get(f"{API}/economy/blueprint?seed=5", timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    assert d1.get("knobs") == d2.get("knobs")
    assert d1.get("parameters") == d2.get("parameters")
    assert d1.get("brief")
    assert "seed" in d1


# --- generate without enrich + mount + listing
def test_generate_economy_mount_no_enrich(s):
    payload = {"build_id": "qa_be_sys", "knobs": {"model": "hybrid"}, "seed": 3, "mount": True, "enrich": False}
    r = s.post(f"{API}/economy/generate", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("mounted") is True
    bp = d.get("blueprint") or {}
    assert bp.get("llm_enriched") is False
    assert bp.get("knobs", {}).get("model") == "hybrid"


def test_list_build_systems_after_mount(s):
    r = s.get(f"{API}/build/qa_be_sys", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("count", 0) >= 1
    assert any(it.get("system") == "economy" for it in d.get("systems", []))


# --- enrich path (slow Claude call)
def test_generate_narrative_with_enrich(s):
    payload = {"build_id": "qa_be_enrich", "knobs": {"tone": "noir"}, "seed": 2, "mount": True, "enrich": True}
    r = s.post(f"{API}/narrative/generate", json=payload, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    bp = d.get("blueprint") or {}
    assert bp.get("llm_enriched") is True, f"enrich did not succeed: {d}"
    assert bp.get("brief"), "brief empty"
    notes = bp.get("designer_notes") or []
    assert len(notes) >= 1, f"no designer_notes: {bp}"
    assert d.get("mounted") is True
    assert bp.get("knobs", {}).get("tone") == "noir"


# --- bogus system graceful
def test_bogus_system_returns_unknown(s):
    r = s.get(f"{API}/bogus", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("error") == "unknown_system"
