"""
Iteration 62 retest — 10-level snowball audit + hard 95 delivery gate + heal apply/apply-all.
Test game id: d02790d6d8174ff59bf7005221cd7609
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL", os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")
if not BASE_URL:
    # fallback to local for direct call where ingress unavailable
    BASE_URL = "http://localhost:8001"

PID = "d02790d6d8174ff59bf7005221cd7609"

EXPECTED_LEVEL_KEYS = {
    "completeness", "canon_consistency", "reference_integrity", "narrative_depth",
    "mechanical_coherence", "world_density", "asset_coverage", "build_readiness",
    "freshness", "playability_qa",
}


# --- snowball audit (fast / deterministic) ---
class TestSnowballAuditShallow:
    def test_audit_shallow_returns_10_levels(self):
        r = requests.get(f"{BASE_URL}/api/snowball/{PID}/audit", params={"deep": "false"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "levels" in data and isinstance(data["levels"], list)
        assert len(data["levels"]) == 10
        keys = {lv["key"] for lv in data["levels"]}
        assert keys == EXPECTED_LEVEL_KEYS
        for lv in data["levels"]:
            assert {"key", "label", "score", "band", "pass", "fix_route"} <= set(lv)
            assert 0 <= int(lv["score"]) <= 100
            assert lv["band"] in {"S", "A", "B", "C", "D"}
            assert isinstance(lv["pass"], bool)
        assert "deterministic_overall" in data
        assert "gate_floor" in data and 0 <= int(data["gate_floor"]) <= 100
        assert "deliverable" in data and isinstance(data["deliverable"], bool)
        assert "blockers" in data and isinstance(data["blockers"], list)
        assert "band" in data
        # shallow should NOT contain llm
        assert data.get("llm") in (None,)


# --- snowball audit (deep / LLM) ---
class TestSnowballAuditDeep:
    def test_audit_deep_includes_llm(self):
        r = requests.get(f"{BASE_URL}/api/snowball/{PID}/audit", params={"deep": "true"}, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["levels"]) == 10
        llm = data.get("llm")
        assert llm is not None, "deep audit must include llm object"
        assert {"quality", "parse_confidence", "recall", "notes", "model"} <= set(llm)
        for k in ("quality", "parse_confidence", "recall"):
            assert 0 <= int(llm[k]) <= 100
        # gate_floor = min(levels min, llm quality, parse, recall)
        det_min = min(lv["score"] for lv in data["levels"])
        expected_floor = min(det_min, llm["quality"], llm["parse_confidence"], llm["recall"])
        assert data["gate_floor"] == expected_floor


# --- deliver hard gate ---
class TestDeliverHardGate:
    def test_deliver_blocks_below_95(self):
        r = requests.post(f"{BASE_URL}/api/snowball/{PID}/deliver", timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        # This game is below 95 per request context — must be blocked.
        assert d.get("delivered") is False, f"must NOT mark delivered, got {d}"
        assert d.get("blocked") is True
        assert "gate_floor" in d and int(d["gate_floor"]) < 95
        assert d.get("threshold") == 95
        assert isinstance(d.get("blockers"), list) and len(d["blockers"]) >= 1
        assert "message" in d and isinstance(d["message"], str)


# --- audit history (must grow) ---
class TestAuditHistory:
    def test_history_grows_after_audit(self):
        before = requests.get(f"{BASE_URL}/api/snowball/{PID}/audit/history", timeout=30).json()
        assert isinstance(before.get("history"), list)
        n0 = before["count"]
        # trigger a fresh shallow audit
        requests.get(f"{BASE_URL}/api/snowball/{PID}/audit", params={"deep": "false"}, timeout=30)
        after = requests.get(f"{BASE_URL}/api/snowball/{PID}/audit/history", timeout=30).json()
        assert after["count"] >= n0 + 1, f"history should grow: {n0} -> {after['count']}"
        # newest first ordering
        ats = [h["at"] for h in after["history"]]
        assert ats == sorted(ats, reverse=True)
        first = after["history"][0]
        assert "gate_floor" in first


# --- scorecard PNG ---
class TestScorecardPng:
    def test_scorecard_returns_1080x1080_png(self):
        r = requests.get(f"{BASE_URL}/api/snowball/{PID}/scorecard.png", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 4000
        # validate dimensions via PIL
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(r.content))
        assert img.size == (1080, 1080)


# --- canon graph audit (no internal leakage) ---
class TestCanonGraphAudit:
    def test_public_issues_have_no_internal_keys(self):
        r = requests.get(f"{BASE_URL}/api/graph/{PID}/audit", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "issues" in d
        for it in d["issues"]:
            assert set(it.keys()) <= {"severity", "type", "message"}, f"leakage: {it}"
            assert "etype" not in it
            assert "entity" not in it


# --- heal apply (single) ---
class TestHealApply:
    def test_apply_valid_fix(self):
        payload = {"entity": "TEST_Entity", "etype": "Character",
                   "title": "TEST patch", "patch": "TEST patch body", "links": ["X"]}
        r = requests.post(f"{BASE_URL}/api/graph/{PID}/heal/apply", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("marked_stale") == "quest_db"
        assert d.get("applied", {}).get("title") == "TEST patch"

    def test_apply_missing_game_returns_error(self):
        r = requests.post(f"{BASE_URL}/api/graph/MISSING_GAME_xxx/heal/apply",
                          json={"entity": "X", "etype": "Character", "title": "t", "patch": "p", "links": []},
                          timeout=15)
        assert r.status_code == 200
        assert "error" in r.json()


# --- heal apply-all (batch) ---
class TestHealApplyAll:
    def test_apply_all(self):
        body = {"fixes": [
            {"entity": "TEST_A", "etype": "Character", "title": "t1", "patch": "p1", "links": []},
            {"entity": "TEST_R", "etype": "Region",    "title": "t2", "patch": "p2", "links": []},
        ]}
        r = requests.post(f"{BASE_URL}/api/graph/{PID}/heal/apply-all", json=body, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("applied_count") == 2
        marked = set(d.get("marked_stale") or [])
        assert {"quest_db", "lore_graph"} <= marked

    def test_apply_all_empty_returns_not_ok(self):
        r = requests.post(f"{BASE_URL}/api/graph/{PID}/heal/apply-all", json={"fixes": []}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is False
        assert d.get("applied_count") == 0
