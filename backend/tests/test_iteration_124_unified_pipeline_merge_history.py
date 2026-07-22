"""
Iteration 124 — Galaxy Studio unified gamefile pipeline:
  (1) MERGED gate set (set-A AAA panel STAGES + set-B unified pipeline 14 gates).
      Every gate must carry fields from BOTH sets, with per-gate merged score
      that blends specialized_score and set_a score.
  (2) Pipeline history drawer comparing runs (needle-mover).

Backend public URL is used (EXPO_BACKEND_URL). No auth.
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
PIPE = f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline"
TG = f"{BASE_URL}/api/galaxy-studio/text-gamefile"

BUILD_ID = "qa_merge_1"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Gate listing: BOTH sets fielded on every gate ─────────────────────────────
class TestGatesListing:
    def test_gates_count_and_merge_fields(self, s):
        r = s.get(f"{PIPE}/gates", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        gates = data.get("gates")
        assert isinstance(gates, list)
        assert len(gates) == 14, f"expected 14 gates, got {len(gates)}"

        total_segments = 0
        total_features = 0
        for g in gates:
            # set-B fields
            assert isinstance(g.get("features"), list) and len(g["features"]) == 10, \
                f"{g.get('key')} features != 10"
            assert "crosswire" in g and isinstance(g["crosswire"], list)
            assert g.get("system"), f"{g.get('key')} missing system"
            assert isinstance(g.get("order"), int)
            # set-A fields
            assert isinstance(g.get("segments"), list) and len(g["segments"]) == 7, \
                f"{g.get('key')} segments != 7"
            assert isinstance(g.get("passes"), int) and g["passes"] >= 1
            assert isinstance(g.get("pass_threshold"), (int, float))
            assert g.get("intensity") in ("standard", "tremendous", "excruciating")
            assert g.get("panel") is True, f"{g.get('key')} panel not True"
            assert g.get("samples") == 16, f"{g.get('key')} samples != 16"
            total_segments += len(g["segments"])
            total_features += len(g["features"])

        assert total_segments == 98, f"expected 98 segments total, got {total_segments}"
        assert total_features == 140, f"expected 140 features total, got {total_features}"


# ── Forge gamefile, run pipeline, validate per-stage merged scoring ───────────
@pytest.fixture(scope="module")
def forged_gamefile(s):
    payload = {
        "build_id": BUILD_ID,
        "text": "A colossal cathedral boss named TEST_Vermillion guards the prequel gate. "
                "It has three phases, a wide arena, and crushing tells that escalate "
                "on enrage. Defeating it rewards the player with the ember sigil.",
        "enrich": False,
    }
    r = s.post(f"{TG}/boss_design/generate", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    gf = r.json()
    assert gf.get("id"), f"no id: {gf}"
    return gf


class TestPipelineRun:
    def test_run_pipeline_merged_stages(self, s, forged_gamefile):
        gid = forged_gamefile["id"]
        r = s.post(f"{PIPE}/{BUILD_ID}/{gid}/run",
                   json={"persist": True, "auto_mint_enhancer": False},
                   timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("gate_count") == 14
        stages = data.get("stages") or []
        assert len(stages) == 14
        assert "overall_score" in data
        assert "aaa" in data and isinstance(data["aaa"], dict)
        assert "overall_score" in data["aaa"], "aaa block missing overall_score"

        for st in stages:
            # set-B / merge fields on the stage
            assert "specialized_score" in st, f"{st.get('key')} missing specialized_score"
            assert "set_a_score" in st, f"{st.get('key')} missing set_a_score"
            assert "score" in st, f"{st.get('key')} missing merged score"
            # set-A propagated fields on the stage
            for k in ("segments", "passes", "pass_threshold", "intensity",
                      "panel", "samples"):
                assert k in st, f"{st.get('key')} missing {k}"
            assert st["panel"] is True
            assert st["samples"] == 16
            assert isinstance(st["segments"], list) and len(st["segments"]) == 7
            # set_a sub-block carries panel/segment detail
            sa = st.get("set_a") or {}
            assert "segment_scores" in sa
            assert isinstance(sa["segment_scores"], list) and len(sa["segment_scores"]) == 7
            assert "passes" in sa and "pass_threshold" in sa
            panel = sa.get("panel") or {}
            assert "votes" in panel and len(panel["votes"]) == 5
            assert "consensus" in panel
            assert "members" in panel and len(panel["members"]) == 5
            # merged score blend sanity
            spec = st["specialized_score"]
            seta = st["set_a_score"]
            if isinstance(spec, (int, float)) and isinstance(seta, (int, float)):
                expected = round(0.5 * spec + 0.5 * seta, 1)
                assert abs(st["score"] - expected) <= 0.15, \
                    f"{st['key']} merged {st['score']} != blend {expected}"


# ── Pipeline history: run twice, validate delta + needle ──────────────────────
class TestHistoryDrawer:
    def test_history_two_runs_delta_needle(self, s, forged_gamefile):
        gid = forged_gamefile["id"]
        # Run 1 — no auto-mint (already done by previous test, but ensure idempotent)
        r1 = s.post(f"{PIPE}/{BUILD_ID}/{gid}/run",
                    json={"persist": True, "auto_mint_enhancer": False},
                    timeout=120)
        assert r1.status_code == 200, r1.text
        run1 = r1.json()

        time.sleep(0.4)
        # Run 2 — WITH auto-mint
        r2 = s.post(f"{PIPE}/{BUILD_ID}/{gid}/run",
                    json={"persist": True, "auto_mint_enhancer": True},
                    timeout=120)
        assert r2.status_code == 200, r2.text
        run2 = r2.json()

        # auto-mint run should mint MORE
        assert run2.get("minted_count", 0) > run1.get("minted_count", 0), \
            f"auto-mint should produce more minted_count: r1={run1.get('minted_count')} r2={run2.get('minted_count')}"

        # Pull history
        h = s.get(f"{PIPE}/{BUILD_ID}/{gid}/history", timeout=30)
        assert h.status_code == 200, h.text
        hist = h.json()
        assert hist.get("run_count", 0) >= 2, f"run_count too small: {hist}"
        runs = hist.get("runs") or []
        assert len(runs) >= 2
        last = runs[-1]
        # last run record fields
        for f in ("overall_score", "aaa_score", "pages", "minted_count",
                  "auto_mint_enhancer", "gate_scores"):
            assert f in last, f"runs[-1] missing {f}"
        assert last["auto_mint_enhancer"] is True
        # gate_scores must be a dict of 14 keys
        assert isinstance(last["gate_scores"], dict)
        assert len(last["gate_scores"]) == 14

        # delta block
        d = hist.get("delta") or {}
        for f in ("overall", "aaa", "pages", "minted", "needle_gate", "needle_delta"):
            assert f in d, f"delta missing {f}"
        # auto-mint should increase minted delta
        assert d["minted"] > 0, f"minted delta should be positive: {d}"
        # needle_gate should be one of the 14 valid keys
        valid_keys = {
            "triage", "architecture", "structure", "design", "system",
            "page_scale", "audit_incoming", "extender", "extrapolator",
            "enhancer", "quality_control", "fidelity_control",
            "consolidation", "audit_outward",
        }
        assert d["needle_gate"] in valid_keys, f"unexpected needle gate {d['needle_gate']}"
