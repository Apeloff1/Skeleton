"""Iteration 111 — Systems Forge SOTA scale-up: 12 systems / 102 knobs / 593 options,
12 engine models, 10 big-win playbooks, markdown exports & GDD integration."""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL")
            or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or "https://player-retention.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api/galaxy-studio/systems"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── catalog totals
def test_systems_catalog_totals(s):
    r = s.get(API, timeout=15); assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("count") == 12, d.get("count")
    assert d.get("total_knobs") == 102, f"total_knobs={d.get('total_knobs')}"
    assert d.get("total_options") == 593, f"total_options={d.get('total_options')}"
    assert len(d.get("pipeline", [])) == 7
    for sys_item in d.get("systems", []):
        assert sys_item.get("knob_count", 0) > 0
        assert sys_item.get("option_count", 0) > 0


# ── 10 big-wins playbooks
def test_big_wins_listing(s):
    r = s.get(f"{API}/big-wins", timeout=15); assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("count") == 10, d.get("count")
    bws = d.get("big_wins") or []
    assert len(bws) == 10
    for bw in bws:
        assert bw.get("system_count", 0) >= 2
        assert isinstance(bw.get("systems"), list) and len(bw["systems"]) == bw["system_count"]


# ── engine models per system
@pytest.mark.parametrize("system,expected_model", [
    ("progression", "xp_curve"),
    ("economy", "economy_ledger"),
    ("loot", "loot_table"),
    ("ai_director", "tension_envelope"),
    ("narrative", "beat_map"),
    ("difficulty", "dda_envelope"),
    ("spawning", "spawn_schedule"),
    ("quest", "quest_graph"),
    ("faction", "faction_matrix"),
    ("dialogue", "dialogue_thresholds"),
    ("monetization", "monetization_calendar"),
    ("balance", "power_budget"),
])
def test_blueprint_has_engine_model(s, system, expected_model):
    r = s.get(f"{API}/{system}/blueprint?seed=2", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    model = d.get("model") or {}
    assert model.get("model") == expected_model, f"{system} model={model.get('model')}"
    assert isinstance(d.get("parameters"), dict) and d["parameters"]
    assert isinstance(d.get("knobs"), dict) and d["knobs"]


def test_progression_blueprint_samples_array(s):
    r = s.get(f"{API}/progression/blueprint?seed=2", timeout=15)
    assert r.status_code == 200, r.text
    model = r.json().get("model") or {}
    assert model.get("model") == "xp_curve"
    samples = model.get("samples")
    assert isinstance(samples, list) and len(samples) >= 1
    assert all(isinstance(x, int) for x in samples)


def test_ai_director_tension_envelope_samples(s):
    r = s.get(f"{API}/ai_director/blueprint?seed=2", timeout=15)
    assert r.status_code == 200, r.text
    model = r.json().get("model") or {}
    assert model.get("model") == "tension_envelope"
    assert isinstance(model.get("samples"), list) and len(model["samples"]) == 16


# ── apply big-win
def test_apply_roguelike_meta_mounts_four_systems(s):
    payload = {"build_id": "qa_be_bw", "enrich": False}
    r = s.post(f"{API}/big-wins/roguelike_meta/apply", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("applied") == 4, d.get("applied")
    results = d.get("results") or []
    assert len(results) == 4
    for res in results:
        assert res.get("mounted") is True, res
        assert res.get("blueprint"), res


def test_list_build_systems_qa_be_bw(s):
    r = s.get(f"{API}/build/qa_be_bw", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("count") >= 4, d
    keys = {it.get("system") for it in d.get("systems", [])}
    # roguelike_meta mounts: progression, difficulty, loot, spawning
    assert {"progression", "difficulty", "loot", "spawning"}.issubset(keys), keys


# ── markdown export (build-level)
def test_export_build_md_contains_systems_section(s):
    r = s.get(f"{API}/build/qa_be_bw/export.md", timeout=15)
    assert r.status_code == 200, r.text
    md = r.text
    assert "## 🧩 Game Systems Blueprints" in md, md[:400]
    # at least one of the four mounted systems must be present
    assert any(tag in md for tag in ("Progression", "Difficulty", "Loot", "Spawn")), md[:400]
    assert "Content-Disposition" in {k.title() for k in r.headers.keys()} or \
           "content-disposition" in r.headers


# ── per-system markdown (works even without mount → preview)
def test_export_narrative_md_preview(s):
    r = s.get(f"{API}/narrative/export.md?build_id=qa_be_bw", timeout=15)
    assert r.status_code == 200, r.text
    md = r.text
    assert "Narrative" in md or "narrative" in md
    assert "Systems Brief" in md or "Engine model" in md or "Knobs" in md


# ── enrich path (live Claude)
def test_dialogue_generate_with_enrich(s):
    payload = {"build_id": "qa_be_enrich", "knobs": {"style": "wheel"},
               "seed": 7, "mount": True, "enrich": True}
    r = s.post(f"{API}/dialogue/generate", json=payload, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    bp = d.get("blueprint") or {}
    assert bp.get("llm_enriched") is True, f"enrich didn't succeed: {d}"
    notes = bp.get("designer_notes") or []
    assert len(notes) >= 1, f"no designer_notes: {bp}"
    assert d.get("mounted") is True
    assert bp.get("knobs", {}).get("style") == "wheel"


# ── GDD integration via snowball
def test_systems_forge_markdown_module_function():
    """Direct call: build_systems_markdown returns the systems section
    when a build has mounted systems."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import systems_forge as sf
    md = sf.build_systems_markdown("qa_be_bw")
    assert "## 🧩 Game Systems Blueprints" in md, md[:400]


def test_snowball_gdd_endpoint_still_returns_200(s):
    """Smoke: /api/snowball/<pid>/gdd.md should respond. Use an arbitrary pid;
    even if game not found, it should not be 500."""
    r = s.get(f"{BASE_URL}/api/snowball/qa_be_bw/gdd.md", timeout=20)
    # accept 200 (game exists) OR 404 (game not found). 500 would be a bug.
    assert r.status_code in (200, 404), f"unexpected status {r.status_code}: {r.text[:200]}"
