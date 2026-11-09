"""Iteration 113 — 14-gate Galaxy Studio engine (3-pass quality + multi-pass gates + panel gates)."""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"

API = f"{BASE_URL}/api/galaxy-studio"
S = requests.Session()
S.headers.update({"Content-Type": "application/json"})

EXPECTED_STAGE_KEYS = {
    "refine", "polish", "qc", "fine_tuning", "intricacy", "detail",
    "quality_enhancement", "quality_improvement", "fidelity",
    "super_sampling", "production_grade", "consumer_quality",
    "approval", "consensus",
}


# ── /gates/stages: 14 stages, 5 reviewers in panel ──────────────────────
class TestStagesCatalog:
    def test_stage_count_and_keys(self):
        r = S.get(f"{API}/gates/stages", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stage_count"] == 14, f"stage_count={d.get('stage_count')}"
        keys = {s["key"] for s in d["stages"]}
        missing = EXPECTED_STAGE_KEYS - keys
        assert not missing, f"missing stage keys: {missing}; got {keys}"

    def test_panel_has_five_reviewers(self):
        d = S.get(f"{API}/gates/stages", timeout=30).json()
        assert isinstance(d.get("panel"), list) and len(d["panel"]) == 5

    def test_intricacy_intensity_and_count(self):
        d = S.get(f"{API}/gates/stages", timeout=30).json()
        s = next(x for x in d["stages"] if x["key"] == "intricacy")
        assert s["intensity"] == "tremendous"
        assert len(s["segments"]) == 14

    def test_detail_intensity_and_count(self):
        d = S.get(f"{API}/gates/stages", timeout=30).json()
        s = next(x for x in d["stages"] if x["key"] == "detail")
        assert s["intensity"] == "excruciating"
        assert len(s["segments"]) == 18

    def test_super_sampling_samples_field(self):
        d = S.get(f"{API}/gates/stages", timeout=30).json()
        s = next(x for x in d["stages"] if x["key"] == "super_sampling")
        assert s["samples"] == 16


# ── Seeded build fixture ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def seeded_build():
    r = S.post(f"{API}/systems/economy/generate",
               json={"build_id": "qa_g"}, timeout=60)
    assert r.status_code == 200, r.text
    return "qa_g"


# ── Multi-pass: quality_enhancement → 3 passes + 3-pass quality gate ────
class TestMultiPassGates:
    def test_quality_enhancement_3_passes(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system",
                "key": "economy", "ai": False, "seed": 0}
        r = S.post(f"{API}/gates/quality_enhancement/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["passes"] == 3, f"passes={d.get('passes')}"
        assert len(d["pass_scores"]) == 3, f"pass_scores={d.get('pass_scores')}"
        qg = d["quality_gate"]
        assert isinstance(qg.get("passes"), list) and len(qg["passes"]) == 3, f"qg.passes={qg.get('passes')}"
        assert d["final_score"] >= 95, f"final_score={d['final_score']}"
        assert d["passed"] is True

    def test_fine_tuning_3_passes(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system", "key": "economy", "ai": False}
        r = S.post(f"{API}/gates/fine_tuning/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["passes"] == 3
        assert len(d["pass_scores"]) == 3

    def test_polish_3_passes(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system", "key": "economy", "ai": False}
        r = S.post(f"{API}/gates/polish/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["passes"] == 3
        assert len(d["pass_scores"]) == 3


# ── Segment counts + intensity ──────────────────────────────────────────
class TestSegmentRuns:
    def test_intricacy_run(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system", "key": "economy", "ai": False}
        r = S.post(f"{API}/gates/intricacy/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["segments"]) == 14, f"segments={len(d['segments'])}"
        assert d.get("intensity") == "tremendous"

    def test_detail_run(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system", "key": "economy", "ai": False}
        r = S.post(f"{API}/gates/detail/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["segments"]) == 18
        assert d.get("intensity") == "excruciating"

    def test_super_sampling_run(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "system", "key": "economy", "ai": False}
        r = S.post(f"{API}/gates/super_sampling/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("samples") == 16
        assert isinstance(d.get("final_score"), (int, float))


# ── Panel gates (approval + consensus) deterministic ────────────────────
class TestPanelGates:
    @pytest.mark.parametrize("stage", ["approval", "consensus"])
    def test_panel_deterministic(self, seeded_build, stage):
        body = {"build_id": seeded_build, "kind": "system",
                "key": "economy", "ai": False}
        r = S.post(f"{API}/gates/{stage}/run", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "panel", f"kind={d.get('kind')}"
        panel = d["panel"]
        assert isinstance(panel.get("votes"), list) and len(panel["votes"]) == 5
        assert isinstance(panel.get("consensus_score"), (int, float))
        assert isinstance(d.get("passed"), bool)


# ── Panel AI: must gracefully fall back on failure ──────────────────────
class TestPanelAIGracefulFallback:
    def test_approval_ai_returns_votes(self, seeded_build):
        """ai=true should ALWAYS return 5 votes — live LLM or deterministic fallback."""
        body = {"build_id": seeded_build, "kind": "system",
                "key": "economy", "ai": True}
        r = S.post(f"{API}/gates/approval/run", json=body, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        panel = d.get("panel") or {}
        votes = panel.get("votes") or []
        # graceful: either llm_group_chat (5 votes) or simulated_board (5 votes)
        assert len(votes) == 5, f"votes len={len(votes)}; mode={panel.get('mode')}"
        assert panel.get("mode") in ("llm_group_chat", "simulated_board")


# ── Coverage: 14 gates, ship_ready needs all 14 ─────────────────────────
class TestCoverage14:
    def test_coverage_14_stage_keys(self, seeded_build):
        r = S.get(f"{API}/gates/build/{seeded_build}/coverage", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gate_count"] == 14, f"gate_count={d.get('gate_count')}"
        assert len(d["stage_keys"]) == 14
        # ship_ready requires all 14
        for row in d["systems"]:
            sp = set(row.get("stages_passed") or [])
            expected_ready = len(sp) >= 14
            assert row["ship_ready"] is expected_ready, f"ship_ready mismatch on {row['system']}: passed={sp}"


# ── Construct target: must not 500 ──────────────────────────────────────
class TestConstructTargetGraceful:
    def test_refine_construct_does_not_500(self, seeded_build):
        body = {"build_id": seeded_build, "kind": "construct",
                "key": "anyid_does_not_exist", "ai": False}
        r = S.post(f"{API}/gates/refine/run", json=body, timeout=60)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        # Either a valid report or a clean error dict
        assert ("final_score" in d) or ("error" in d), f"unexpected response: {d}"
