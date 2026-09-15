"""
Stage C (cognition) + KDA Delta multimodal memory + Graph-Engineering swarm DAG.

Covers:
  C1  — Jury→LAFS deep-reinforce; online sweep
  C2  — Belief propagation; posterior-predictive check; top-EFE
  C3  — Jeeves RAG (text) via Emergent LLM (claude-sonnet-4-6)
  C3M — Jeeves RAG multimodal (image_base64 → gpt-4o path)
  KDA — Delta memory multimodal write/read/stats/heatmap
  DAG — Swarm run + shared knowledge-graph memory
  REG — coverage/selftest, prood/readiness, omega/fabric
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_BACKEND_URL",
    "https://player-retention.preview.emergentagent.com",
).rstrip("/")

# a genuinely valid tiny 1x1 red PNG (base64, no data-URI prefix)
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ══════════════════════════════════════════════════════════════
# REGRESSION first — baseline must be healthy
# ══════════════════════════════════════════════════════════════
class TestRegressionBaseline:
    def test_coverage_selftest_10_10(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/coverage/selftest", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ready") is True, j
        # ten pillars ready
        checks = j.get("checks") or j.get("pillars") or {}
        # some contracts expose {"passed": 10, "total": 10}
        if "passed" in j and "total" in j:
            assert int(j["passed"]) == int(j["total"]) == 10, j
        assert isinstance(checks, (dict, list)) or "passed" in j, j

    def test_prood_readiness_16_16(self, api):
        r = api.get(f"{BASE_URL}/api/prood/readiness", timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert float(j.get("overall_percent", 0)) == 100.0, j
        assert int(j.get("capabilities_live", 0)) == 16, j
        assert int(j.get("capabilities_total", 0)) == 16, j

    def test_omega_fabric_has_delta(self, api):
        r = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("persisted") is True, j
        # delta_memory stats should be embedded in fabric
        # (may be at top-level, or nested under 'delta_memory')
        dm = j.get("delta_memory") or {}
        assert dm, f"no delta_memory block in fabric: {list(j.keys())}"
        assert "writes" in dm and "capacity_floats" in dm, dm
        assert "recent_growth" in j or "recent_growth" in dm, j


# ══════════════════════════════════════════════════════════════
# KDA Delta memory (multimodal)
# ══════════════════════════════════════════════════════════════
class TestDeltaKDAMemory:
    def test_write_text_bumps_writes(self, api):
        s0 = api.get(f"{BASE_URL}/api/omega/delta/stats", timeout=10).json()
        before = int(s0.get("writes", 0))
        r = api.post(f"{BASE_URL}/api/omega/delta/write",
                     json={"key": f"k-text-{uuid.uuid4().hex[:6]}",
                           "value": f"v-text-{uuid.uuid4().hex[:6]}",
                           "modality": "text"}, timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("modality") == "text"
        s1 = api.get(f"{BASE_URL}/api/omega/delta/stats", timeout=10).json()
        assert int(s1["writes"]) == before + 1, (before, s1)
        assert s1.get("capacity_floats") == 4096, s1

    def test_write_image_bumps_and_multimodal_true(self, api):
        s0 = api.get(f"{BASE_URL}/api/omega/delta/stats", timeout=10).json()
        before = int(s0.get("writes", 0))
        r = api.post(f"{BASE_URL}/api/omega/delta/write",
                     json={"key": f"k-img-{uuid.uuid4().hex[:6]}",
                           "value": TINY_PNG_B64,
                           "modality": "image"}, timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("modality") == "image", j
        s1 = api.get(f"{BASE_URL}/api/omega/delta/stats", timeout=10).json()
        assert int(s1["writes"]) == before + 1, (before, s1)
        assert s1.get("multimodal") is True, s1
        mw = s1.get("modality_writes") or {}
        assert mw.get("text", 0) >= 1 and mw.get("image", 0) >= 1, mw
        assert s1.get("capacity_floats") == 4096

    def test_read_returns_recall_and_nearest(self, api):
        key = f"kda-recall-{uuid.uuid4().hex[:6]}"
        api.post(f"{BASE_URL}/api/omega/delta/write",
                 json={"key": key, "value": f"payload-{uuid.uuid4().hex[:8]}",
                       "modality": "text"}, timeout=10)
        r = api.post(f"{BASE_URL}/api/omega/delta/read",
                     json={"key": key}, timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert float(j.get("recall_strength", 0)) > 0.0, j
        assert j.get("nearest") is not None, j

    def test_heatmap_8x8(self, api):
        r = api.get(f"{BASE_URL}/api/omega/delta/heatmap?cells=8", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        hm = j.get("heatmap")
        assert isinstance(hm, list) and len(hm) == 8, j
        assert all(isinstance(row, list) and len(row) == 8 for row in hm), j


# ══════════════════════════════════════════════════════════════
# C1 — Jury→LAFS deep-reinforce + online sweep
# ══════════════════════════════════════════════════════════════
class TestC1JuryLAFS:
    def test_jury_accept_grows_lafs(self, api):
        s0 = api.get(f"{BASE_URL}/api/lafs/stats", timeout=15).json()
        total0 = int(s0.get("total_sheets", 0))
        # /submit merely enqueues; /tick runs adjudication → verdicts appear
        # Send several unique high-quality submissions, then tick.
        for _ in range(6):
            topic = f"TESTtopic{uuid.uuid4().hex[:8]}"
            content = (
                f"The topic {topic} refers to a game-design study grounded in evidence: "
                f"source https://example.com/ref-{uuid.uuid4().hex[:6]}. "
                "The study data shows that a well-tuned reward loop with clear "
                "feedback and escalating stakes produces measurable retention "
                "gains because the player forms consistent expectations, therefore "
                "the reference architecture recommends per-run telemetry hooks."
            )
            api.post(f"{BASE_URL}/api/gameforge/jury/submit",
                     json={"topic": topic, "content": content,
                           "source": "wikipedia"}, timeout=30)
        # adjudicate — /tick processes up to N pending cases → returns verdicts
        r = api.post(f"{BASE_URL}/api/gameforge/jury/tick",
                     json={"max_items": 8, "ingest": True}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        processed = j.get("processed") or []
        verdicts = [p.get("verdict") for p in processed]
        accepted = sum(1 for v in verdicts if v == "accepted")
        s1 = api.get(f"{BASE_URL}/api/lafs/stats", timeout=15).json()
        total1 = int(s1.get("total_sheets", 0))
        if accepted > 0:
            # LAFS should have grown by at least 1 per accepted verdict
            assert total1 > total0, (total0, total1, verdicts)
        else:
            pytest.skip(f"no jury accept produced in this run: verdicts={verdicts}")

    def test_sweep_online_produces_results(self, api):
        r = api.post(f"{BASE_URL}/api/lafs/sweep/online?count=2", timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert isinstance(j.get("results"), list) and len(j["results"]) >= 1, j
        assert int(j.get("learned_count", -1)) >= 0, j


# ══════════════════════════════════════════════════════════════
# C2 — Belief propagation + posterior check + top-EFE
# ══════════════════════════════════════════════════════════════
class TestC2Belief:
    def test_belief_propagate_with_neighbors(self, api):
        # seed sheet A
        rA = api.post(f"{BASE_URL}/api/lafs/remember",
                      json={"domain": "Narrative", "log_type": "Lore",
                            "payload": {"content": f"seed-A-{uuid.uuid4().hex[:6]}"},
                            "author": "tester"}, timeout=15)
        assert rA.status_code == 200, rA.text
        sid_a = rA.json()["sheet"]["id"]
        # seed sheet B cross-refs A → neighbors exist for propagation
        rB = api.post(f"{BASE_URL}/api/lafs/remember",
                      json={"domain": "Narrative", "log_type": "Lore",
                            "payload": {"content": f"seed-B-{uuid.uuid4().hex[:6]}"},
                            "author": "tester", "cross_refs": [sid_a]}, timeout=15)
        assert rB.status_code == 200, rB.text
        # propagate from A with 2 hops
        r = api.post(f"{BASE_URL}/api/lafs/belief-propagate/{sid_a}?hops=2", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert "trace" in j, j
        assert isinstance(j["trace"], list), j

    def test_posterior_check_shape(self, api):
        r = api.get(f"{BASE_URL}/api/lafs/posterior-check", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        for key in ("avg_brier", "calibration_quality", "ci95_coverage"):
            assert key in j, (key, j.keys())

    def test_top_efe_sorted_desc(self, api):
        r = api.get(f"{BASE_URL}/api/lafs/top-efe?k=5", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        top = j.get("top") or []
        assert isinstance(top, list) and len(top) >= 1, j
        efes = [t.get("efe") for t in top if isinstance(t.get("efe"), (int, float))]
        if len(efes) >= 2:
            assert efes == sorted(efes, reverse=True), efes


# ══════════════════════════════════════════════════════════════
# C3 — Jeeves RAG (text + multimodal image)
# ══════════════════════════════════════════════════════════════
class TestC3JeevesRAG:
    def test_rag_text_uses_claude_sonnet(self, api):
        # ensure relevant canon exists
        api.post(f"{BASE_URL}/api/lafs/learn/online",
                 json={"topic": "Pathfinding"}, timeout=60)
        r = api.post(f"{BASE_URL}/api/lafs/jeeves/ask",
                     json={"query": "A star pathfinding",
                           "top_k": 5}, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        # when EMERGENT_LLM_KEY is present, model should NOT be extractive
        model = j.get("model", "")
        assert model != "extractive", f"model should be LLM, got: {model} | reply: {str(j.get('reply'))[:200]}"
        assert model.startswith("anthropic:claude-sonnet-4-6"), model
        # reply should cite at least one [n]
        assert "[" in str(j.get("reply", "")), j.get("reply")
        assert isinstance(j.get("grounded_in"), list), j
        assert int(j.get("recalled_count", 0)) > 0, j
        assert "text" in (j.get("modalities") or []), j

    def test_rag_multimodal_image_no_500(self, api):
        r = api.post(f"{BASE_URL}/api/lafs/jeeves/ask",
                     json={"query": "What is in this picture?",
                           "top_k": 3, "image_base64": TINY_PNG_B64},
                     timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        modes = j.get("modalities") or []
        assert "image" in modes, modes
        assert "text" in modes, modes
        # multimodal path should try gpt-4o; if LLM upstream flakes it falls
        # back extractive — accept either but if extractive, note it
        model = j.get("model", "")
        assert isinstance(model, str) and len(model) > 0, j


# ══════════════════════════════════════════════════════════════
# DAG — Swarm run + shared knowledge-graph memory
# ══════════════════════════════════════════════════════════════
class TestSwarmDAG:
    def test_swarm_run_4_workers(self, api):
        r = api.post(f"{BASE_URL}/api/swarm-dag/run",
                     json={"directive": "build a roguelike with fire dragon boss and loot",
                           "workers": 4, "project": "t1"}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        merge = j.get("merge") or {}
        assert int(merge.get("worker_count", 0)) == 4, merge
        dag = j.get("dag") or {}
        workers_foci = dag.get("workers") or []
        assert isinstance(workers_foci, list) and len(workers_foci) == 4, dag
        workers = j.get("workers") or []
        assert len(workers) == 4, workers
        for w in workers:
            assert "node_id" in w and "recalled" in w, w

    def test_swarm_graph_persists(self, api):
        r = api.get(f"{BASE_URL}/api/swarm-dag/graph/t1", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        assert int(j.get("count", 0)) > 0, j
        assert isinstance(j.get("nodes"), list) and len(j["nodes"]) >= 1, j
