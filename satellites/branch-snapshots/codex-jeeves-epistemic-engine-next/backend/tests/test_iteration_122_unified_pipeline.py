"""Iteration 122 — unified gamefile pipeline (14 gates, equal-systems, crosswired).

Validates:
  • GET /api/galaxy-studio/gamefile-pipeline/gates       → 14 gates, 10 features each, crosswire+system
  • POST .../{key}/generate then POST .../pipeline/{build_id}/{gid}/run
      (auto_mint=false): 14 stages, scores 0-100, overall_score, aaa block, minted>=1
  • Same with auto_mint_enhancer=true: enhancer stage auto_minted=true, total minted_count grows,
      list endpoint surfaces extra companions
  • GET /api/galaxy-studio/gamefile-pipeline/controller/status:
      controller{gates:14, crosswired:true}, traffic metrics, systems[14] each with order+crosswire+feature_count=10
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE:
    # fall back to local in-cluster
    BASE = "http://localhost:8001"
API = f"{BASE}/api/galaxy-studio"

EXPECTED_ORDER = [
    "triage", "architecture", "structure", "design", "system", "page_scale",
    "audit_incoming", "extender", "extrapolator", "enhancer",
    "quality_control", "fidelity_control", "consolidation", "audit_outward",
]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def build_id():
    return f"qa_uni_{int(time.time())}"


# ── 1. Gates manifest ───────────────────────────────────────────────────────
class TestGatesManifest:
    def test_gates_endpoint(self, session):
        r = session.get(f"{API}/gamefile-pipeline/gates", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gate_count"] == 14, f"expected 14 gates, got {d.get('gate_count')}"
        assert d["features_per_gate"] == 10
        gates = d["gates"]
        assert [g["key"] for g in gates] == EXPECTED_ORDER, "gate order mismatch"
        for g in gates:
            assert "system" in g and g["system"], f"gate {g['key']} missing system"
            assert "crosswire" in g and isinstance(g["crosswire"], list), f"gate {g['key']} missing crosswire"
            assert len(g["features"]) == 10, f"gate {g['key']} has {len(g['features'])} features, expected 10"
            assert "order" in g
        # controller info
        ctrl = d.get("controller") or {}
        assert ctrl.get("crosswired") is True
        assert ctrl.get("ordering") == "strict"


# ── 2. Forge a quest gamefile, run pipeline w/o auto-mint ──────────────────
class TestPipelineRunNoAutoMint:
    def test_generate_quest(self, session, build_id):
        payload = {
            "build_id": build_id,
            "text": "A perilous quest in the ember marshes to retrieve the moonshard from a corrupted lich.",
            "enrich": False,
        }
        r = session.post(f"{API}/text-gamefile/quest_from_text/generate", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        gf = r.json()
        assert gf.get("id")
        pytest.quest_id = gf["id"]
        # additionally mint a boss gamefile for auto-mint test
        boss_payload = {
            "build_id": build_id,
            "text": "Vorath, the obsidian lich, drains memory with sorrowful whispers; phases shift across mirrors.",
            "enrich": False,
        }
        r2 = session.post(f"{API}/text-gamefile/boss_design/generate", json=boss_payload, timeout=20)
        assert r2.status_code == 200, r2.text
        pytest.boss_id = r2.json()["id"]

    def test_run_pipeline_no_auto_mint(self, session, build_id):
        gid = pytest.quest_id
        r = session.post(
            f"{API}/gamefile-pipeline/{build_id}/{gid}/run",
            json={"persist": True, "auto_mint_enhancer": False},
            timeout=45,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # 14 stages strict order
        assert d["gate_count"] == 14
        assert len(d["stages"]) == 14
        assert [s["key"] for s in d["stages"]] == EXPECTED_ORDER
        # numeric scores 0-100 + passed booleans
        for s in d["stages"]:
            score = s.get("score")
            assert isinstance(score, (int, float)), f"{s['key']} score not numeric: {score}"
            assert 0 <= score <= 100, f"{s['key']} score out of range: {score}"
            assert isinstance(s.get("passed"), bool)
        # overall + aaa
        assert "overall_score" in d and isinstance(d["overall_score"], (int, float))
        aaa = d.get("aaa") or {}
        assert "overall_score" in aaa
        assert "aaa_passed" in aaa
        # pages = choices * 200
        vol = d["volume"]
        assert vol["pages_per_choice"] == 200
        assert d["pages"] == vol["choices"] * 200
        # minted_count >=1 from extrapolator
        assert d["minted_count"] >= 1, f"expected at least 1 minted, got {d['minted_count']}"
        # record for later compare
        pytest.no_automint_minted = d["minted_count"]


# ── 3. Run with auto-mint enhancer ─────────────────────────────────────────
class TestPipelineAutoMint:
    def test_list_before(self, session, build_id):
        r = session.get(f"{API}/text-gamefile/{build_id}/list", timeout=15)
        assert r.status_code == 200
        pytest.list_before = len(r.json().get("gamefiles") or [])

    def test_run_pipeline_auto_mint(self, session, build_id):
        gid = pytest.boss_id
        r = session.post(
            f"{API}/gamefile-pipeline/{build_id}/{gid}/run",
            json={"persist": True, "auto_mint_enhancer": True},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # locate enhancer stage
        enhancer = next((s for s in d["stages"] if s["key"] == "enhancer"), None)
        assert enhancer is not None, "enhancer stage missing"
        rep = enhancer["report"]
        assert rep.get("auto_minted") is True, "enhancer auto_minted should be True"
        assert rep.get("minted_count", 0) > 0, "enhancer minted_count should be > 0"
        # total minted higher than no-auto-mint run
        assert d["minted_count"] > pytest.no_automint_minted, (
            f"auto-mint minted {d['minted_count']} should exceed {pytest.no_automint_minted}"
        )
        assert d.get("auto_mint_enhancer") is True

    def test_list_grew(self, session, build_id):
        r = session.get(f"{API}/text-gamefile/{build_id}/list", timeout=15)
        assert r.status_code == 200
        after = len(r.json().get("gamefiles") or [])
        assert after > pytest.list_before, f"list should grow: before={pytest.list_before} after={after}"


# ── 4. Controller status ────────────────────────────────────────────────────
class TestControllerStatus:
    def test_controller_status(self, session):
        r = session.get(f"{API}/gamefile-pipeline/controller/status", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        ctrl = d["controller"]
        assert ctrl["gates"] == 14
        assert ctrl["crosswired"] is True
        assert ctrl["ordering"] == "strict"
        # traffic metrics present
        traffic = d.get("traffic") or {}
        for k in ("concurrency_cap", "in_flight", "dispatched_total", "rate_per_window"):
            assert k in traffic, f"traffic missing {k}"
        # systems[14] each with order+crosswire+feature_count=10
        systems = d.get("systems") or []
        assert len(systems) == 14
        for s in systems:
            assert "order" in s
            assert "crosswire" in s and isinstance(s["crosswire"], list)
            assert s.get("feature_count") == 10, f"{s.get('gate')} feature_count={s.get('feature_count')}"
            assert s.get("system")
            assert s.get("gate")
