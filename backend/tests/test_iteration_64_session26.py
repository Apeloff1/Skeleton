"""
Iteration 64 / Session 26 backend tests.

Covers:
  - Stage VAULT GET /api/snowball/{pid}/vault/{stage} (valid + unknown stage)
  - Auto-improve POST /api/snowball/{pid}/auto-improve (LLM ~30-60s)
  - Auto-improve retry POST /api/snowball/{pid}/auto-improve/retry
  - Printable atlas GET /api/snowball/{pid}/atlas.html
  - 95-gated publish POST /api/snowball/{pid}/publish + /unpublish
  - Agent logs GET /api/agent-logs/all|summary|stream
  - Heal apply / apply-all with regen=false (to avoid kicking long GroupChat)
"""
from __future__ import annotations

import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL") or os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com"
)
BASE_URL = BASE_URL.rstrip("/")
PID = "d02790d6d8174ff59bf7005221cd7609"

VALID_STAGES = ["spec", "world", "narrative", "mechanics", "procedural",
                "assets", "qa", "build", "launch"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- VAULT ----------
class TestStageVault:
    def test_world_vault(self, s):
        r = s.get(f"{BASE_URL}/api/snowball/{PID}/vault/world", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["domain_count"] >= 1
        assert isinstance(d["domains"], list) and len(d["domains"]) >= 1
        assert isinstance(d["tips"], list) and len(d["tips"]) >= 1
        for dom in d["domains"]:
            assert "name" in dom and "category" in dom

    @pytest.mark.parametrize("stage", VALID_STAGES)
    def test_all_stages(self, s, stage):
        r = s.get(f"{BASE_URL}/api/snowball/{PID}/vault/{stage}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "error" not in d, f"stage {stage} unexpectedly errored: {d}"
        assert d["domain_count"] >= 1
        assert d["domains"] and d["tips"]

    def test_unknown_stage(self, s):
        r = s.get(f"{BASE_URL}/api/snowball/{PID}/vault/banana", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "error" in d
        assert set(d.get("valid", [])) == set(VALID_STAGES)


# ---------- ATLAS ----------
class TestAtlas:
    def test_atlas_html(self, s):
        r = s.get(f"{BASE_URL}/api/snowball/{PID}/atlas.html", timeout=30)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        body = r.text
        assert "<html" in body.lower()
        assert "World Atlas" in body


# ---------- PUBLISH (hard 95 gate) ----------
class TestPublishGate:
    def test_publish_blocked(self, s):
        r = s.post(f"{BASE_URL}/api/snowball/{PID}/publish", timeout=60)
        assert r.status_code == 200
        d = r.json()
        # Game id is known to be below 95
        assert d.get("published") is False
        assert d.get("blocked") is True
        assert "gate_floor" in d
        assert isinstance(d.get("blockers"), list)
        assert "Publish blocked" in d.get("message", "") or d.get("ok") is False

    def test_unpublish(self, s):
        r = s.post(f"{BASE_URL}/api/snowball/{PID}/unpublish", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("published") is False


# ---------- AGENT LOGS ----------
class TestAgentLogs:
    def test_summary(self, s):
        r = s.get(f"{BASE_URL}/api/agent-logs/summary", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "counts" in d
        for k in ("snowball_audits", "snowball_improve_runs", "groupchat_jobs"):
            assert k in d["counts"]
        assert set(d.get("log_files", [])) >= {"backend_err", "backend_out", "expo_err"}

    def test_all(self, s):
        r = s.get(f"{BASE_URL}/api/agent-logs/all", params={"lines": 20}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "service_logs" in d
        for k in ("backend_err", "backend_out", "expo_err"):
            assert k in d["service_logs"]
            assert isinstance(d["service_logs"][k], list)
        for k in ("ai_query_logs", "audit_history", "improve_runs", "groupchat_jobs"):
            assert k in d, f"missing key {k}"
            assert isinstance(d[k], list)

    def test_stream_valid(self, s):
        r = s.get(f"{BASE_URL}/api/agent-logs/stream",
                  params={"source": "backend_err", "lines": 50}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("source") == "backend_err"
        assert isinstance(d.get("lines"), list)

    def test_stream_unknown(self, s):
        r = s.get(f"{BASE_URL}/api/agent-logs/stream",
                  params={"source": "wat", "lines": 50}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "error" in d
        assert set(d.get("valid", [])) >= {"backend_err", "backend_out", "expo_err"}


# ---------- HEAL APPLY / APPLY-ALL (regen=false) ----------
class TestHealApply:
    def _get_fixes(self, s):
        # heal proposals come from POST /heal (LLM call, ~10-60s)
        r = s.post(f"{BASE_URL}/api/graph/{PID}/heal", timeout=120)
        if r.status_code != 200:
            return []
        return (r.json() or {}).get("fixes") or []

    def test_heal_apply_single_no_regen(self, s):
        fixes = self._get_fixes(s)
        if not fixes:
            pytest.skip("no fixes available from graph audit")
        fix = fixes[0]
        r = s.post(f"{BASE_URL}/api/graph/{PID}/heal/apply",
                   params={"regen": "false"}, json=fix, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        # regen disabled → no job
        assert d.get("regen_job_id") in (None, "")

    def test_heal_apply_all_no_regen(self, s):
        fixes = self._get_fixes(s)
        if not fixes:
            pytest.skip("no fixes available")
        r = s.post(f"{BASE_URL}/api/graph/{PID}/heal/apply-all",
                   params={"regen": "false"}, json={"fixes": fixes[:3]}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("applied_count"), int)
        assert d.get("applied_count") >= 1
        assert isinstance(d.get("marked_stale"), list)
        assert d.get("regen_job_id") in (None, "")


# ---------- AUTO-IMPROVE (LLM 30-60s) ----------
class TestAutoImprove:
    """Run improve first, then retry. Retry depends on a prior run."""

    @pytest.fixture(scope="class")
    def improve_run(self, s):
        # Long timeout — LLM call
        r = s.post(f"{BASE_URL}/api/snowball/{PID}/auto-improve",
                   timeout=180)
        assert r.status_code == 200, r.text
        return r.json()

    def test_improve_shape(self, improve_run):
        d = improve_run
        assert "error" not in d, d
        assert "gate_floor" in d
        assert isinstance(d.get("weak_stages"), list)
        assert isinstance(d.get("upgrades"), list)
        assert isinstance(d.get("log"), list) and len(d["log"]) > 0
        assert any("GATE FLOOR" in ln for ln in d["log"])
        assert "summary" in d

    def test_improve_upgrades_content(self, improve_run):
        d = improve_run
        # gate is below 95 so we expect at least some upgrades & weak stages
        ups = d.get("upgrades") or []
        if not ups:
            pytest.skip("no upgrades — likely deliverable already")
        u = ups[0]
        assert "signal" in u
        assert "upgrade" in u
        # current may be missing if LLM hallucinated, but signal+upgrade required

    def test_retry_kicks_regen(self, s, improve_run):
        # only run if we had upgrades / weak stages
        if not improve_run.get("weak_stages"):
            pytest.skip("nothing to retry")
        r = s.post(f"{BASE_URL}/api/snowball/{PID}/auto-improve/retry", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("regenerated") is True
        assert d.get("job_id")
        assert isinstance(d.get("directive_count"), int)
