"""
Iteration 63 — Session 24: Canon Auto-Heal (NEW).

POST /api/graph/{pid}/heal — LLM proposes grounded canon patches for the
auditor's fixable gaps (orphans, thin quests). Also re-verifies the audit
payload shape after the shared _compute_issues refactor.

Game under test: d02790d6d8174ff59bf7005221cd7609 (fully-built canon).
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

PID = "d02790d6d8174ff59bf7005221cd7609"
MISSING_PID = "ffffffffffffffffffffffffffffffff"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


class TestAuditRegression:
    def test_audit_public_shape(self, s):
        r = s.get(f"{BASE_URL}/api/graph/{PID}/audit", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "score" in d and 0 <= d["score"] <= 100
        assert d["issue_count"] == len(d["issues"])  # capped consistently
        for it in d["issues"]:
            # internal grounding keys must NOT leak into the public audit payload
            assert set(it.keys()) == {"severity", "type", "message"}
            assert it["severity"] in ("error", "warn", "info")


class TestCanonHeal:
    def test_heal_returns_grounded_fixes(self, s):
        r = s.post(f"{BASE_URL}/api/graph/{PID}/heal", timeout=130)
        assert r.status_code == 200
        d = r.json()
        assert d.get("game_id") == PID
        assert "fixable_count" in d
        assert isinstance(d.get("fixes"), list)
        # this game has orphan factions + thin quests → there ARE fixes
        assert d["fixable_count"] >= 1
        assert len(d["fixes"]) == d["fixable_count"]
        for f in d["fixes"]:
            assert f["entity"], "fix must name the entity it heals"
            assert f["type"] in ("orphan", "thin-quest")
            assert f["etype"] in ("Faction", "Character", "Region", "Quest")
            assert f["issue"]  # carries the original audit message
            assert f["title"] and len(f["title"]) <= 120
            assert isinstance(f["links"], list)
        assert d.get("model"), "should report the model used"

    def test_heal_missing_game(self, s):
        r = s.post(f"{BASE_URL}/api/graph/{MISSING_PID}/heal", timeout=30)
        assert r.status_code == 200
        assert r.json().get("error") == "game not found"
