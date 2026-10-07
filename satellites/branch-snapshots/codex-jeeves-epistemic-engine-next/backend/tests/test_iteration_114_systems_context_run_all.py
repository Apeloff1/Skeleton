"""Iteration 114 — Systems Forge expansion (22/287/2151), Creator Context, Run-All 14 gates."""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"

API = f"{BASE_URL}/api/galaxy-studio"
S = requests.Session()
S.headers.update({"Content-Type": "application/json"})

NEW_SYSTEMS = ["crafting", "stealth", "vehicle", "weather_time", "social",
               "audio_director", "tutorial", "save_checkpoint", "accessibility", "telemetry"]


# ── Catalog: 22 systems / 287 knobs / 2151 options ────────────────────
class TestSystemsCatalog:
    def test_list_totals(self):
        r = S.get(f"{API}/systems", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # The header should report the 22/287/2151
        sys_count = len(d.get("systems") or [])
        total_knobs = d.get("total_knobs")
        total_options = d.get("total_options")
        assert sys_count == 22, f"system_count={sys_count}"
        assert total_knobs == 287, f"total_knobs={total_knobs}"
        assert total_options == 2151, f"total_options={total_options}"

    @pytest.mark.parametrize("key", NEW_SYSTEMS)
    def test_new_system_in_catalog(self, key):
        d = S.get(f"{API}/systems", timeout=30).json()
        keys = {s.get("key") for s in d.get("systems", [])}
        assert key in keys, f"missing new system: {key}"


# ── Generate works for the 10 NEW systems ─────────────────────────────
class TestGenerateNewSystems:
    @pytest.mark.parametrize("system", NEW_SYSTEMS)
    def test_generate_new_system(self, system):
        body = {"build_id": "itest1", "seed": 1, "mount": True, "enrich": False}
        r = S.post(f"{API}/systems/{system}/generate", json=body, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        bp = d.get("blueprint") or {}
        assert isinstance(bp.get("model"), dict) and bp["model"], f"empty model for {system}: {bp.get('model')}"
        # 'upgrades' KPIs should exist somewhere on blueprint
        ups = bp.get("upgrades") or bp.get("kpis") or bp.get("derived_kpis") or {}
        assert ups, f"no upgrades/kpis on {system}: keys={list(bp.keys())}"


# ── Creator Context: GET + POST round-trip with 20k cap ───────────────
class TestCreatorContext:
    def test_get_returns_3_fields_and_meta(self):
        r = S.get(f"{API}/systems/crafting/context?build_id=itest1", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("vision", "implementation", "quality"):
            assert k in d, f"missing field {k} in {list(d.keys())}"
        assert d.get("max_chars") == 20000, f"max_chars={d.get('max_chars')}"
        meta = d.get("fields_meta") or []
        assert isinstance(meta, list) and len(meta) == 3, f"fields_meta len={len(meta)}"

    def test_save_round_trip_and_counts(self):
        payload = {
            "build_id": "itest1",
            "vision": "TEST_vision_" + ("a" * 50),
            "implementation": "TEST_impl_" + ("b" * 60),
            "quality": "TEST_qa_" + ("c" * 70),
        }
        r = S.post(f"{API}/systems/crafting/context", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        cc = d.get("char_counts") or {}
        assert cc.get("vision") == len(payload["vision"]), f"vision count: {cc}"
        assert cc.get("implementation") == len(payload["implementation"]), f"impl count: {cc}"
        assert cc.get("quality") == len(payload["quality"]), f"quality count: {cc}"

        # Read back
        r2 = S.get(f"{API}/systems/crafting/context?build_id=itest1", timeout=20)
        d2 = r2.json()
        assert d2.get("vision") == payload["vision"]
        assert d2.get("implementation") == payload["implementation"]
        assert d2.get("quality") == payload["quality"]

    def test_20000_char_cap(self):
        big = "x" * 25000  # over the cap
        payload = {"build_id": "itest1", "vision": big, "implementation": "", "quality": ""}
        r = S.post(f"{API}/systems/crafting/context", json=payload, timeout=25)
        assert r.status_code == 200, r.text
        cc = r.json().get("char_counts") or {}
        assert cc.get("vision") == 20000, f"vision should be capped at 20000, got {cc.get('vision')}"

        # And the GET should return exactly 20000 chars
        d = S.get(f"{API}/systems/crafting/context?build_id=itest1", timeout=20).json()
        assert len(d.get("vision") or "") == 20000


# ── Run a single gate on a system; check >=97 for deterministic gate ──
class TestSingleGateRun:
    def test_refine_system_passes(self):
        body = {"build_id": "itest1", "kind": "system", "key": "crafting", "seed": 1, "ai": False}
        r = S.post(f"{API}/gates/refine/run", json=body, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        fs = d.get("final_score")
        assert isinstance(fs, (int, float)), f"final_score type {type(fs)}"
        # Deterministic gates should land >= 97 (or at least be passed boolean true near threshold)
        assert d.get("passed") is True, f"refine should pass for crafting; got {d}"
        assert fs >= 97, f"final_score={fs} below 97"

    def test_construct_kind_does_not_crash(self):
        body = {"build_id": "itest1", "kind": "construct", "key": "nonexistent_construct_zzz",
                "seed": 1, "ai": False}
        r = S.post(f"{API}/gates/refine/run", json=body, timeout=30)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        assert ("final_score" in d) or ("error" in d), f"unexpected response: {d}"


# ── Run-all on build itest1 ───────────────────────────────────────────
class TestRunAll14:
    def test_run_all_returns_systems_times_14(self):
        body = {"build_id": "itest1", "seed": 1, "ai": False, "include_panel": True}
        r = S.post(f"{API}/gates/build/itest1/run-all", json=body, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("gate_count") == 14, f"gate_count={d.get('gate_count')}"
        ran = d.get("ran")
        passed = d.get("passed")
        sys_count = d.get("system_count") or d.get("systems_count") or 0
        assert isinstance(ran, int) and ran > 0, f"ran={ran}"
        # ran should be systems × 14
        if sys_count:
            assert ran == sys_count * 14, f"ran={ran} sys_count={sys_count}"
        assert isinstance(passed, int) and passed >= 0, f"passed={passed}"
        assert passed <= ran
