"""
Iteration 146 — Agent Tool System (/api/gameforge/tools) tests.
Endpoints are OPEN (no auth needed).
Covers: registry list/register, use → capability profile growth, permissions,
versioning + rollback, evolution (improve / flag_for_deprecation),
combination synergy scoring, status.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "https://player-retention.preview.emergentagent.com"
).rstrip("/")
TOOLS = f"{BASE_URL}/api/gameforge/tools"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---- registry list (seeded) ----
def test_list_seeded_tools(sess):
    r = sess.get(TOOLS, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["count"] >= 4
    ids = {t["tool_id"] for t in d["tools"]}
    for req in ["CodeQualityEnhancerTool", "GameBalanceAnalyzerTool",
                "NarrativeIntegratorTool", "FeatureIterationAcceleratorTool"]:
        assert req in ids, f"missing seeded tool {req}"
    for t in d["tools"]:
        assert "tool_id" in t and "name" in t and "version" in t
        assert "stats" in t and "uses" in t["stats"] and "success_rate" in t["stats"]


# ---- register new tool ----
def test_register_new_tool(sess):
    tid = f"TEST_Tool_{uuid.uuid4().hex[:8]}"
    payload = {"tool_id": tid, "name": "Test Registered Tool", "domain": "engineering",
               "min_trust": 10, "min_mastery": 5, "boosts": "Debugging"}
    r = sess.post(f"{TOOLS}/register", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    r2 = sess.get(TOOLS, timeout=20)
    ids = {t["tool_id"] for t in r2.json()["tools"]}
    assert tid in ids


# ---- use → boosts capability every 3rd successful use ----
def test_use_boosts_capability_profile(sess):
    tid = f"TEST_BoostTool_{uuid.uuid4().hex[:8]}"
    sess.post(f"{TOOLS}/register", json={
        "tool_id": tid, "name": "Boost Tool", "domain": "engineering",
        "min_trust": 0, "min_mastery": 0, "boosts": "Code Quality"
    }, timeout=20)
    aid = f"TEST_agent_{uuid.uuid4().hex[:6]}"

    r1 = sess.post(f"{TOOLS}/use", json={"agent_id": aid, "tool_id": tid, "success": True}, timeout=20).json()
    r2 = sess.post(f"{TOOLS}/use", json={"agent_id": aid, "tool_id": tid, "success": True}, timeout=20).json()
    r3 = sess.post(f"{TOOLS}/use", json={"agent_id": aid, "tool_id": tid, "success": True}, timeout=20).json()

    assert r1.get("ok") and r2.get("ok") and r3.get("ok")
    # Only 3rd use should boost
    assert r1.get("boosted") in (None,)
    assert r2.get("boosted") in (None,)
    assert r3.get("boosted") == "Code Quality", f"expected boost on 3rd use, got {r3}"

    # profile shows capability increased by 5 above default (50)
    prof = sess.get(f"{TOOLS}/agent/{aid}/profile", timeout=20).json()
    assert prof["ok"] is True
    assert prof["capabilities"]["Code Quality"] == 55, prof
    assert prof["tool_usage"][tid] == 3


# ---- permission check ----
def test_permissions_check(sess):
    # Use FeatureIterationAcceleratorTool (min_trust=40, min_mastery=30)
    tid = "FeatureIterationAcceleratorTool"
    r_low = sess.post(f"{TOOLS}/permissions/check", json={
        "agent_id": "TEST_perm", "tool_id": tid, "trust": 5, "mastery": 5
    }, timeout=20).json()
    assert r_low.get("ok") is True
    assert r_low.get("allowed") is False
    assert "trust" in r_low.get("reason", "").lower()

    r_ok = sess.post(f"{TOOLS}/permissions/check", json={
        "agent_id": "TEST_perm", "tool_id": tid, "trust": 80, "mastery": 80
    }, timeout=20).json()
    assert r_ok.get("allowed") is True
    assert r_ok.get("reason") == "granted"


# ---- versioning & rollback ----
def test_version_and_rollback(sess):
    tid = f"TEST_VersionTool_{uuid.uuid4().hex[:8]}"
    sess.post(f"{TOOLS}/register", json={
        "tool_id": tid, "name": "Version Tool", "domain": "engineering",
        "min_trust": 0, "min_mastery": 0
    }, timeout=20)

    r = sess.post(f"{TOOLS}/{tid}/version", json={"changes": {"note": "bump"}}, timeout=20).json()
    assert r.get("ok") is True
    assert r.get("version") == 2

    r2 = sess.post(f"{TOOLS}/{tid}/rollback", json={"version": 1}, timeout=20).json()
    assert r2.get("ok") is True
    assert r2.get("rolled_back_to") == 1


# ---- evolve: improve on high success rate ----
def test_evolve_improved(sess):
    tid = f"TEST_EvolveGood_{uuid.uuid4().hex[:8]}"
    sess.post(f"{TOOLS}/register", json={
        "tool_id": tid, "name": "Evolve Good Tool", "domain": "engineering",
        "min_trust": 0, "min_mastery": 0
    }, timeout=20)
    aid = f"TEST_agent_{uuid.uuid4().hex[:6]}"
    # 10 successful uses → success_rate = 1.0 > 0.85
    for _ in range(10):
        sess.post(f"{TOOLS}/use", json={"agent_id": aid, "tool_id": tid, "success": True}, timeout=20)
    r = sess.post(f"{TOOLS}/{tid}/evolve", timeout=20).json()
    assert r.get("ok") is True
    assert r.get("action") == "improved", r
    assert r.get("new_version", 0) >= 2


# ---- evolve: flag for deprecation on low success rate ----
def test_evolve_flagged_deprecation(sess):
    tid = f"TEST_EvolveBad_{uuid.uuid4().hex[:8]}"
    sess.post(f"{TOOLS}/register", json={
        "tool_id": tid, "name": "Evolve Bad Tool", "domain": "engineering",
        "min_trust": 0, "min_mastery": 0
    }, timeout=20)
    aid = f"TEST_agent_{uuid.uuid4().hex[:6]}"
    for _ in range(10):
        sess.post(f"{TOOLS}/use", json={"agent_id": aid, "tool_id": tid, "success": False}, timeout=20)
    r = sess.post(f"{TOOLS}/{tid}/evolve", timeout=20).json()
    assert r.get("ok") is True
    assert r.get("action") == "flagged_for_deprecation", r


# ---- combination synergy scoring ----
def test_combination_score(sess):
    tools_resp = sess.get(TOOLS, timeout=20).json()
    ids = [t["tool_id"] for t in tools_resp["tools"] if not t.get("deprecated")][:3]
    assert len(ids) == 3, "need 3 non-deprecated tools"

    r = sess.post(f"{TOOLS}/combination/score", json={"tool_ids": ids}, timeout=20).json()
    assert r.get("ok") is True
    assert isinstance(r.get("total_score"), int)
    assert isinstance(r.get("synergies"), int)
    assert isinstance(r.get("conflicts"), int)
    assert r.get("rating") in {"excellent", "good", "neutral", "risky"}
    assert isinstance(r.get("pairs"), list)
    # 3 tools → 3 pairs
    assert len(r["pairs"]) == 3
    for p in r["pairs"]:
        assert "pair" in p and "type" in p and "score" in p


# ---- status ----
def test_status(sess):
    r = sess.get(f"{TOOLS}/status", timeout=20).json()
    assert r.get("ok") is True
    for k in ("tools", "deprecated", "usage_events", "profiled_agents"):
        assert k in r, f"missing {k}"
        assert isinstance(r[k], int)
    assert r["tools"] >= 4
