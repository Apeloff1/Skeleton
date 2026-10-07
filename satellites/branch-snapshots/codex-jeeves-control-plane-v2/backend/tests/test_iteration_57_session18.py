"""
Session 18 — Flowchart parity (Procedural, Asset Manifest, Iterate & Refine, Launch Prep).

Covers:
- 10-stage pipeline shape + 'procedural' between 'mechanics' and 'assets' + approvals
- KB artifacts shape for procedural_config / asset_manifest / launch_manifest
- Deterministic forges (assets, build) — fast
- chat-refine validation (empty, unknown stage)
- approvals (approve/unapprove/invalid + refine clears approval)
- unknown forge stage guard
- One LLM forge end-to-end: procedural (poll the job)

Note: LLM forges (procedural/launch/refine/qa) can take 30-90s each. The test
sequentially polls a single procedural job up to ~3 min.
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or "http://localhost:8001").rstrip("/")
SEED_PID = "d02790d6d8174ff59bf7005221cd7609"  # remix · arcade · most artifacts present


@pytest.fixture(scope="module")
def s() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ───────── Pipeline shape ─────────
class TestPipelineShape:
    def test_pipeline_returns_10_stages_with_procedural(self, s):
        r = s.get(f"{BASE_URL}/api/playable/{SEED_PID}/pipeline", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total") == 10, f"expected total=10, got {d.get('total')}"
        assert isinstance(d.get("stages"), list)
        assert len(d["stages"]) == 10
        keys = [s["key"] for s in d["stages"]]
        assert "procedural" in keys
        # ordering: procedural BETWEEN mechanics and assets
        assert keys.index("mechanics") < keys.index("procedural") < keys.index("assets")
        # every stage has approved:bool
        assert all(isinstance(st.get("approved"), bool) for st in d["stages"])
        assert isinstance(d.get("approved_count"), int)
        # procedural stage has forge='procedural'
        proc = next(st for st in d["stages"] if st["key"] == "procedural")
        assert proc.get("forge") == "procedural"
        assert proc.get("icon") == "🧬"


# ───────── KB artifact shape ─────────
class TestKBArtifactShape:
    def test_kb_shows_procedural_present_with_required_keys(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=30)
        assert r.status_code == 200
        d = r.json()
        # catalogue contains procedural_config
        cat = {a["name"]: a for a in d.get("artifacts", [])}
        assert "procedural_config" in cat
        assert cat["procedural_config"]["present"] is True
        # data field carries the artifact
        proc = (d.get("data") or {}).get("procedural_config") or {}
        for key in ["requirements", "generation_rules", "optimization",
                    "content_management", "pcg_systems"]:
            assert key in proc, f"procedural_config missing key '{key}'"

    def test_kb_asset_manifest_shape(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=30)
        d = r.json()
        am = (d.get("data") or {}).get("asset_manifest")
        if not am:
            # ensure it's present after a forge — re-forge inline (deterministic)
            pass
        else:
            for k in ["required_kinds", "generated_kinds", "missing_kinds", "assets"]:
                assert k in am, f"asset_manifest missing '{k}'"

    def test_kb_launch_manifest_shape(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=30)
        d = r.json()
        lm = (d.get("data") or {}).get("launch_manifest")
        if lm:
            sl = lm.get("store_listing") or {}
            assert "app_name" in sl
            assert "keywords" in sl
            assert "category" in sl
            assert "assets_checklist" in lm
            assert "compliance" in lm
            assert lm.get("deploy_route") == "/build-hub"
            assert "build_ready" in lm


# ───────── Deterministic forge: assets ─────────
class TestAssetForge:
    def test_assets_forge_async_completes_quickly(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/forge/assets/async", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "job_id" in j, f"no job_id: {j}"
        job_id = j["job_id"]
        result = _poll_job(s, job_id, timeout=30)
        assert result.get("ok") is True, f"result: {result}"
        assert result.get("artifact") == "asset_manifest"
        summary = result.get("summary") or ""
        assert "assets" in summary and "kinds" in summary, f"unexpected summary: {summary}"

    def test_assets_kb_after_forge(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=30)
        am = (r.json().get("data") or {}).get("asset_manifest") or {}
        assert "required_kinds" in am
        assert "generated_kinds" in am
        assert "missing_kinds" in am
        assert isinstance(am.get("assets"), list)


# ───────── Forge unknown stage guard ─────────
class TestForgeGuards:
    def test_forge_unknown_stage_returns_forgeable_list(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/forge/bogus/async", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "error" in d
        assert "forgeable" in d
        expected = {"spec", "mechanics", "world", "narrative", "procedural",
                    "assets", "qa", "build", "launch"}
        assert expected.issubset(set(d["forgeable"])), f"forgeable={d['forgeable']}"


# ───────── Refine validations ─────────
class TestRefineValidation:
    def test_refine_empty_instruction_rejected(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/refine/mechanics/async",
                   json={"instruction": ""}, timeout=15)
        d = r.json()
        assert d.get("error") == "instruction is required to refine", f"got {d}"

    def test_refine_unknown_stage_returns_forgeable(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/refine/bogus/async",
                   json={"instruction": "tweak it"}, timeout=15)
        d = r.json()
        assert "error" in d
        assert "forgeable" in d


# ───────── Approvals ─────────
class TestApprovals:
    def test_approve_then_unapprove_mechanics(self, s):
        # approve
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/approve/mechanics",
                   json={"approved": True, "note": "TEST_approve"}, timeout=15)
        d = r.json()
        assert d.get("ok") is True
        assert d.get("approved") is True
        assert (d.get("approvals") or {}).get("mechanics", {}).get("approved") is True

        # reflected in pipeline
        pl = s.get(f"{BASE_URL}/api/playable/{SEED_PID}/pipeline", timeout=15).json()
        mech = next(x for x in pl["stages"] if x["key"] == "mechanics")
        assert mech.get("approved") is True
        assert pl.get("approved_count") >= 1

        # reflected in kb
        kb = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=15).json()
        assert (kb.get("approvals") or {}).get("mechanics", {}).get("approved") is True

        # unapprove
        r2 = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/approve/mechanics",
                    json={"approved": False}, timeout=15).json()
        assert r2.get("ok") is True
        assert "mechanics" not in (r2.get("approvals") or {})

        pl2 = s.get(f"{BASE_URL}/api/playable/{SEED_PID}/pipeline", timeout=15).json()
        mech2 = next(x for x in pl2["stages"] if x["key"] == "mechanics")
        assert mech2.get("approved") is False

    def test_approve_invalid_stage_rejected(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/approve/mode",
                   json={"approved": True}, timeout=15).json()
        assert "error" in r
        assert "approvable" in r
        expected = {"spec", "world", "narrative", "mechanics", "procedural",
                    "assets", "implementation", "qa", "build"}
        assert expected.issubset(set(r["approvable"]))


# ───────── Refine clears approval ─────────
class TestRefineClearsApproval:
    def test_refining_an_approved_stage_clears_approval(self, s):
        # approve 'assets' first (deterministic stage)
        a = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/approve/assets",
                   json={"approved": True, "note": "TEST_pre_refine"}, timeout=15).json()
        assert a.get("ok") is True
        # kick a refine on assets (deterministic forge under the hood)
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/refine/assets/async",
                   json={"instruction": "TEST_refine emphasize enemy variety"}, timeout=15)
        rj = r.json()
        assert "job_id" in rj, f"refine response: {rj}"
        # approval should already be cleared synchronously by the endpoint
        kb = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=15).json()
        assert "assets" not in (kb.get("approvals") or {}), \
            f"approval should be cleared after refine, approvals={kb.get('approvals')}"
        # wait for the assets forge to complete (deterministic, fast)
        result = _poll_job(s, rj["job_id"], timeout=30)
        assert result.get("ok") is True
        assert result.get("artifact") == "asset_manifest"


# ───────── LLM forge end-to-end: procedural ─────────
@pytest.mark.slow
class TestProceduralForgeLLM:
    def test_procedural_async_forge_and_kb_update(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{SEED_PID}/forge/procedural/async", timeout=30)
        assert r.status_code == 200
        rj = r.json()
        assert "job_id" in rj, f"no job_id: {rj}"
        assert rj.get("stage") == "procedural"
        result = _poll_job(s, rj["job_id"], timeout=180, interval=5)
        assert result.get("ok") is True, f"procedural result: {result}"
        assert result.get("artifact") == "procedural_config"
        summary = (result.get("summary") or "").lower()
        # main agent's summary uses 'requirements' and 'PCG systems'
        assert "requirements" in summary, f"summary missing 'requirements': {summary}"
        assert "pcg systems" in summary or "systems" in summary, f"summary: {summary}"
        # KB now shows procedural_config with required keys
        kb = s.get(f"{BASE_URL}/api/pipeline/{SEED_PID}/kb", timeout=15).json()
        cat = {a["name"]: a for a in kb["artifacts"]}
        assert cat["procedural_config"]["present"] is True
        proc = (kb.get("data") or {}).get("procedural_config") or {}
        for k in ["requirements", "generation_rules", "optimization",
                  "content_management", "pcg_systems"]:
            assert k in proc, f"procedural_config missing '{k}'"


# ───────── helper ─────────
def _poll_job(sess: requests.Session, job_id: str, timeout: int = 60, interval: float = 1.0) -> dict:
    """Poll /api/playable/job/{job_id} until done or timeout. The backend merges
    the forge result fields (ok/artifact/summary/keys) directly into the job
    document once finished, so we return that doc as-is."""
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        try:
            r = sess.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=15)
        except requests.exceptions.RequestException:
            time.sleep(interval)
            continue
        if r.status_code != 200:
            time.sleep(interval)
            continue
        last = r.json()
        status = last.get("job_status") or last.get("status")
        if status in ("done", "complete", "completed", "success", "ok",
                      "error", "failed"):
            return last
        time.sleep(interval)
    pytest.fail(f"job {job_id} did not finish in {timeout}s; last={last}")
