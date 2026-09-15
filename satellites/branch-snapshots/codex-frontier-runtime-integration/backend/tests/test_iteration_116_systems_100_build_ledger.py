"""
Iteration 116: Test Systems Forge 100-system upgrade + per-build context ledger.

Covers:
  - GET /api/galaxy-studio/systems → count=100, total_knobs=990, total_options=7776, no dupes
  - GET /api/galaxy-studio/systems/{system} for several NEW systems
  - POST /api/galaxy-studio/systems/{system}/generate → _generic_model + ledger event
  - GET/POST /api/galaxy-studio/builds/* (context, ledger, list, log)
  - POST /api/galaxy-studio/axes/derive with build_id logs axis_selection event
  - Regression: /api/galaxy-studio/axes/stats still returns 37 axes / 229 options
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

NEW_SYSTEMS = [
    "inventory", "stealth", "crime_law", "deck_building",
    "weapon_ballistics", "player_trading", "npc_schedules", "fast_travel",
]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Systems Forge: 100-system catalogue ----------

class TestSystemsForgeCatalogue:
    def test_systems_count_knobs_options(self, session):
        r = session.get(f"{BASE_URL}/api/galaxy-studio/systems", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 100, f"expected 100 systems, got {body['count']}"
        assert body["total_knobs"] == 990, f"expected 990 knobs, got {body['total_knobs']}"
        assert body["total_options"] == 7776, f"expected 7776 options, got {body['total_options']}"

    def test_no_duplicate_keys(self, session):
        body = session.get(f"{BASE_URL}/api/galaxy-studio/systems", timeout=30).json()
        keys = [s["key"] for s in body["systems"]]
        assert len(keys) == len(set(keys)), f"duplicate system keys detected: {len(keys)} total vs {len(set(keys))} unique"
        assert len(keys) == 100

    @pytest.mark.parametrize("system", NEW_SYSTEMS)
    def test_new_system_detail(self, system, session):
        r = session.get(f"{BASE_URL}/api/galaxy-studio/systems/{system}", timeout=30)
        assert r.status_code == 200, f"{system}: {r.text}"
        d = r.json()
        # `knobs` is a list of {key, label, options:[{key,label}, ...]}
        knobs = d.get("knobs") or []
        assert isinstance(knobs, list) and len(knobs) >= 5, f"{system} should have >=5 knobs: got {len(knobs)}"
        for knob in knobs:
            opts = knob.get("options") or []
            assert len(opts) >= 4, f"{system}.{knob.get('key')} should have >=4 options: {opts}"
            # Ensure options have real keys (not synthetic)
            for opt in opts:
                assert opt.get("key"), f"empty option in {system}.{knob.get('key')}: {opt}"


# ---------- System generation + ledger logging ----------

class TestSystemGenerateLedger:
    def test_generate_inventory_logs_ledger(self, session):
        build_id = f"TEST_build_{uuid.uuid4().hex[:8]}"
        # Generate inventory system
        r = session.post(
            f"{BASE_URL}/api/galaxy-studio/systems/inventory/generate",
            json={"build_id": build_id, "seed": 7, "mount": True},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        res = r.json()
        assert "error" not in res or not res["error"], res
        # Model is nested inside `blueprint`
        blueprint = res.get("blueprint") or {}
        model = blueprint.get("model") or {}
        assert model, f"model should be non-empty: {res}"
        # Generic model shape (inventory uses _generic_model)
        assert model.get("model") == "configured_system", f"expected configured_system, got {model}"
        assert "complexity_index" in model, f"missing complexity_index: {model}"
        assert "fidelity_tier" in model, f"missing fidelity_tier: {model}"

        # Ledger should have at least one system_generated event
        lr = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/ledger", timeout=30)
        assert lr.status_code == 200, lr.text
        led = lr.json()
        events = led.get("events", [])
        kinds = [e["kind"] for e in events]
        assert "system_generated" in kinds, f"system_generated event missing. kinds={kinds}"
        # Check event data
        sg = [e for e in events if e["kind"] == "system_generated"][0]
        assert sg["data"]["system"] == "inventory"

    def test_generate_multiple_new_systems(self, session):
        build_id = f"TEST_multi_{uuid.uuid4().hex[:8]}"
        for sys_key in ["stealth", "deck_building", "weapon_ballistics"]:
            r = session.post(
                f"{BASE_URL}/api/galaxy-studio/systems/{sys_key}/generate",
                json={"build_id": build_id, "seed": 1, "mount": True},
                timeout=30,
            )
            assert r.status_code == 200, f"{sys_key}: {r.text}"
            blueprint = r.json().get("blueprint") or {}
            assert blueprint.get("model"), f"{sys_key} returned empty blueprint.model"

        ctx = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/context", timeout=30).json()
        assert ctx.get("systems_count", 0) >= 3, f"context should track 3 systems: {ctx}"
        assert set(["stealth", "deck_building", "weapon_ballistics"]).issubset(set(ctx.get("systems", [])))


# ---------- Build Ledger endpoints ----------

class TestBuildLedger:
    def test_context_rolling_summary_shape(self, session):
        build_id = f"TEST_ctx_{uuid.uuid4().hex[:8]}"
        # Seed an event
        session.post(
            f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/log",
            json={"kind": "spec", "data": {"genre": "rpg", "era": "medieval", "dimension": "3d", "seed": 42}},
            timeout=30,
        )
        r = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/context", timeout=30)
        assert r.status_code == 200, r.text
        ctx = r.json()
        for key in ["snowball_choices", "axis_selections", "axis_directives",
                    "systems", "gate_runs", "spec", "events"]:
            assert key in ctx, f"context missing key '{key}': {ctx}"
        assert ctx["spec"].get("genre") == "rpg"

    def test_ledger_append_only(self, session):
        build_id = f"TEST_led_{uuid.uuid4().hex[:8]}"
        for i in range(3):
            r = session.post(
                f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/log",
                json={"kind": "build_event", "data": {"idx": i}, "step": f"step_{i}"},
                timeout=30,
            )
            assert r.status_code == 200, r.text
        r = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/ledger", timeout=30)
        assert r.status_code == 200, r.text
        led = r.json()
        assert led["count"] >= 3, led
        # Sequence numbers should be monotonic
        seqs = [e["seq"] for e in led["events"]]
        assert seqs == sorted(seqs), f"seq not sorted: {seqs}"

    def test_list_builds_includes_test_build(self, session):
        build_id = f"TEST_list_{uuid.uuid4().hex[:8]}"
        session.post(
            f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/log",
            json={"kind": "build_event", "data": {"hello": "world"}},
            timeout=30,
        )
        time.sleep(0.3)
        r = session.get(f"{BASE_URL}/api/galaxy-studio/builds?limit=500", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "builds" in body and "count" in body
        ids = {b.get("build_id") for b in body["builds"]}
        assert build_id in ids, f"build {build_id} not listed (count={body['count']})"

    def test_custom_log_event_persists(self, session):
        build_id = f"TEST_custom_{uuid.uuid4().hex[:8]}"
        r = session.post(
            f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/log",
            json={"kind": "custom_kind", "data": {"foo": "bar"}, "step": "phase_x"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        evt = r.json()
        assert evt.get("kind") == "custom_kind"
        assert evt.get("data", {}).get("foo") == "bar"
        # Verify GET
        lr = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/ledger", timeout=30).json()
        kinds = [e["kind"] for e in lr["events"]]
        assert "custom_kind" in kinds


# ---------- Axes /derive crosswire to ledger ----------

class TestAxesCrosswire:
    def test_axes_derive_logs_axis_selection(self, session):
        build_id = f"TEST_axes_{uuid.uuid4().hex[:8]}"
        # Pick any valid axis option. Use catalog stats to be safe.
        cat = session.get(f"{BASE_URL}/api/galaxy-studio/axes?advanced_only=false", timeout=30).json()
        # Find first axis with at least one option
        axes = cat.get("axes") or []
        if not axes:
            pytest.skip("no axes returned by catalog")
        selections = {}
        for ax in axes[:2]:
            opts = ax.get("options") or []
            if opts:
                key = ax.get("key") or ax.get("id")
                opt_id = opts[0].get("id")
                if key and opt_id:
                    selections[key] = opt_id
            if len(selections) >= 1:
                break
        assert selections, f"could not find any axis selection: axes[0]={axes[0] if axes else None}"

        # Get pre-count
        pre = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/ledger", timeout=30).json()
        pre_count = pre["count"]

        # Derive
        r = session.post(
            f"{BASE_URL}/api/galaxy-studio/axes/derive",
            json={"selections": selections, "spec": {"genre": "rpg", "era": "modern", "dimension": "3d"},
                  "stage_index": 99, "build_id": build_id},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        derived = r.json()
        assert "applied" in derived and "directives" in derived, derived

        post = session.get(f"{BASE_URL}/api/galaxy-studio/builds/{build_id}/ledger", timeout=30).json()
        assert post["count"] == pre_count + 1, f"ledger should have incremented by 1: pre={pre_count} post={post['count']}"
        last = post["events"][-1]
        assert last["kind"] == "axis_selection", f"last event should be axis_selection: {last}"
        assert "applied" in last["data"] and "directives" in last["data"]


# ---------- Regression: axes/stats + boot registration ----------

class TestRegression:
    def test_axes_stats(self, session):
        r = session.get(f"{BASE_URL}/api/galaxy-studio/axes/stats", timeout=30)
        assert r.status_code == 200, r.text
        stats = r.json()
        # Expecting 37 axes / 229 options per problem statement
        axes_count = stats.get("axes") or stats.get("axes_count") or stats.get("total_axes")
        opts_count = stats.get("options") or stats.get("options_count") or stats.get("total_options")
        assert axes_count == 37, f"expected 37 axes, got {axes_count}; full={stats}"
        assert opts_count == 229, f"expected 229 options, got {opts_count}; full={stats}"

    def test_systems_context_endpoint_works(self, session):
        # legacy/regression: per-system context endpoint
        build_id = f"TEST_regctx_{uuid.uuid4().hex[:8]}"
        # POST save
        r = session.post(
            f"{BASE_URL}/api/galaxy-studio/systems/inventory/context",
            json={"build_id": build_id, "vision": "v", "implementation": "i", "quality": "q"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        # GET back
        r2 = session.get(
            f"{BASE_URL}/api/galaxy-studio/systems/inventory/context?build_id={build_id}",
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
