"""Tests for iteration 112: Refine/Polish/QC gate stages + Systems Forge SOTA scale (12/155/1150 + 20 big-wins + upgrades)."""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"

API = f"{BASE_URL}/api/galaxy-studio"
S = requests.Session()
S.headers.update({"Content-Type": "application/json"})


# ── Systems-Forge: scale-up totals ───────────────────────────────────────
class TestSystemsScale:
    def test_systems_totals(self):
        r = S.get(f"{API}/systems", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] == 12, f"count={d.get('count')}"
        assert d["total_knobs"] == 155, f"total_knobs={d.get('total_knobs')}"
        assert d["total_options"] == 1150, f"total_options={d.get('total_options')}"

    def test_big_wins_count(self):
        r = S.get(f"{API}/systems/big-wins", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] == 20, f"big_wins count={d.get('count')}"
        keys = {b["key"] for b in d["big_wins"]}
        for must in ("cozy_sim", "roguelike_meta", "live_service_loop"):
            assert must in keys


# ── Upgrade derivations on every blueprint ───────────────────────────────
class TestUpgradeDerivations:
    def test_economy_upgrades_and_model(self):
        r = S.get(f"{API}/systems/economy/blueprint", timeout=30)
        assert r.status_code == 200, r.text
        bp = r.json()
        up = bp.get("upgrades") or {}
        assert isinstance(up, dict) and up, "no upgrades object"
        for kpi in ("session_length_target_min", "retention_d1_d7_d30", "churn_risk_band"):
            assert kpi in up, f"missing KPI {kpi}: have {list(up.keys())}"
        model = bp.get("model") or {}
        assert isinstance(model, dict) and model.get("model"), f"missing model: {model}"


# ── Apply-Big-Win batch + AI enrich (live Claude) ────────────────────────
class TestApplyBigWinAI:
    def test_apply_enrich_false_fast(self):
        body = {"build_id": "qa_bwai_fast", "enrich": False}
        r = S.post(f"{API}/systems/big-wins/cozy_sim/apply", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["applied"] == 4, f"applied={d.get('applied')}"
        assert d["ai_enriched"] is False
        for res in d["results"]:
            assert res["mounted"] is True
            assert res["blueprint"]["llm_enriched"] is False

    def test_apply_enrich_true_live_ai(self):
        body = {"build_id": "qa_bwai", "enrich": True}
        # Generous timeout for 4 live Claude calls
        r = S.post(f"{API}/systems/big-wins/cozy_sim/apply", json=body, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["applied"] == 4
        assert d["ai_enriched"] is True
        for res in d["results"]:
            bp = res["blueprint"]
            assert bp["llm_enriched"] is True, f"system {res['system']} not enriched"


# ── Gate stages catalog ──────────────────────────────────────────────────
class TestGateStagesCatalog:
    def test_stages_shape(self):
        r = S.get(f"{API}/gates/stages", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stage_count"] == 3
        keys = [s["key"] for s in d["stages"]]
        assert keys == ["refine", "polish", "qc"], keys
        for st in d["stages"]:
            assert len(st["segments"]) == 7, f"{st['key']} segments={len(st['segments'])}"
        gates = [g["key"] for g in d["gates"]]
        assert gates == ["query", "acquire", "refine"], gates


# ── Gate run (3 stages, deterministic) ───────────────────────────────────
@pytest.fixture(scope="module")
def seeded_build():
    """Seed system on build qa_gate."""
    r = S.post(f"{API}/systems/economy/generate",
               json={"build_id": "qa_gate"}, timeout=60)
    assert r.status_code == 200, r.text
    return "qa_gate"


class TestGateRun:
    @pytest.mark.parametrize("stage", ["refine", "polish", "qc"])
    def test_stage_run_shape(self, seeded_build, stage):
        body = {"build_id": seeded_build, "kind": "system",
                "key": "economy", "seed": 1, "ai": False}
        r = S.post(f"{API}/gates/{stage}/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stage"] == stage
        qg = d.get("quality_gate") or {}
        assert isinstance(qg.get("score"), (int, float)), f"missing quality_gate.score: {qg}"
        assert len(d.get("segments") or []) == 7, f"segments={len(d.get('segments') or [])}"
        for seg in d["segments"]:
            assert "inbound_score" in seg and "outbound_score" in seg
            gate_keys = [g["gate"] for g in seg["gates"]]
            assert gate_keys == ["query", "acquire", "refine"], gate_keys
        assert isinstance(d.get("final_score"), (int, float))
        assert "passed" in d


class TestGateAI:
    def test_qc_ai_run(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system",
                "key": "economy", "ai": True}
        r = S.post(f"{API}/gates/qc/run", json=body, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ai_reviewed") is True, f"ai_reviewed={d.get('ai_reviewed')}; keys={list(d.keys())}"
        notes = d.get("ai_notes") or []
        assert isinstance(notes, list) and len(notes) >= 1, f"ai_notes={notes}"


# ── Coverage + run-all ──────────────────────────────────────────────────
class TestCoverage:
    def test_coverage_shape(self, seeded_build):
        r = S.get(f"{API}/gates/build/{seeded_build}/coverage", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stage_keys"] == ["refine", "polish", "qc"]
        assert isinstance(d.get("systems"), list) and len(d["systems"]) == 12
        for row in d["systems"]:
            assert "mounted" in row and "stages_passed" in row
        assert isinstance(d.get("mounted_count"), int)
        assert isinstance(d.get("total"), int) and d["total"] == 12
        assert isinstance(d.get("mounted_pct"), (int, float))


class TestRunAll:
    def test_run_all(self, seeded_build):
        # Apply a big-win first to mount multiple systems
        S.post(f"{API}/systems/big-wins/cozy_sim/apply",
               json={"build_id": seeded_build, "enrich": False}, timeout=60)
        time.sleep(0.5)
        cov = S.get(f"{API}/gates/build/{seeded_build}/coverage", timeout=30).json()
        mounted = cov["mounted_count"]
        assert mounted >= 1
        r = S.post(f"{API}/gates/build/{seeded_build}/run-all",
                   json={"build_id": seeded_build}, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ran"] == mounted * 3, f"ran={d['ran']}, expected={mounted*3}"
        assert d["stages"] == 3
        assert d["systems"] == mounted
        assert isinstance(d["results"], list) and len(d["results"]) == d["ran"]
        for res in d["results"]:
            for k in ("system", "stage", "score", "passed"):
                assert k in res, f"missing {k} in {res}"
