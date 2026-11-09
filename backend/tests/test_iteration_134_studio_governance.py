"""
Iteration 134 — CNS Studio Governance & Jeeves Oversight
Tests the /api/gameforge/studio/* surface and /api/gameforge/activate.
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

SB = f"{BASE_URL}/api/gameforge/studio"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── CNS activate ──────────────────────────────────────────────────────────────
class TestActivate:
    def test_activate(self, s):
        r = s.post(f"{BASE_URL}/api/gameforge/activate", json={}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("activated") == 4, d
        assert d.get("total") == 4, d
        assert d.get("status") == "live", d


# ── Flow ──────────────────────────────────────────────────────────────────────
class TestFlow:
    def test_flow(self, s):
        r = s.get(f"{SB}/flow", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("pipeline"), list)
        assert len(d["pipeline"]) == 8, d["pipeline"]
        assert d.get("import_errors") == {} or d.get("import_errors") is None or len(d["import_errors"]) == 0, d.get("import_errors")


# ── Questionnaire ─────────────────────────────────────────────────────────────
class TestQuestionnaire:
    def test_q_log_and_get(self, s):
        payload = {
            "question_id": "TEST_q1",
            "question": "Which genre?",
            "answer": "Action-RPG",
            "confidence": 0.85,
        }
        r = s.post(f"{SB}/questionnaire/log", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("logged") == "TEST_q1"
        rooms = d.get("dispatched_rooms") or []
        assert isinstance(rooms, list) and len(rooms) > 0, d

        g = s.get(f"{SB}/questionnaire", timeout=20)
        assert g.status_code == 200
        gd = g.json()
        assert "responses" in gd
        assert "context" in gd


# ── Steps ─────────────────────────────────────────────────────────────────────
class TestSteps:
    def test_steps_list(self, s):
        r = s.get(f"{SB}/steps", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        steps = d.get("steps") or {}
        assert isinstance(steps, dict)
        assert len(steps) == 7, list(steps.keys())

    def test_step_choice(self, s):
        payload = {"key": "TEST_theme", "value": "cyberpunk-noir"}
        r = s.post(f"{SB}/step/step_1_concept/choice", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("step") == "step_1_concept"
        assert isinstance(d.get("dispatched_rooms"), list) and len(d["dispatched_rooms"]) > 0

    def test_step_invalid(self, s):
        r = s.post(f"{SB}/step/step_bogus_xyz/choice", json={"key": "k", "value": "v"}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is False


# ── Forges ────────────────────────────────────────────────────────────────────
class TestForges:
    def test_forge_run(self, s):
        r = s.post(f"{SB}/forge/run", json={"game_concept": {
            "game_name": "TEST_Game", "genre": "fantasy", "art_style": "pixel",
            "core_mechanic": "core_loop", "core_loop": "explore",
        }}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        results = d.get("results") or {}
        # expected keys per problem statement
        for key in ["asset", "mechanic", "world", "code", "ui", "balance"]:
            assert key in results, f"missing forge '{key}' in {list(results.keys())}"


# ── Governance ────────────────────────────────────────────────────────────────
class TestGovernanceAccept:
    def test_accept_flow(self, s):
        payload = {
            "game_name": "TEST_GovAccept",
            "filename": "spec.md",
            "content": "a clean coherent spec",
            "kind": "spec",
        }
        r = s.post(f"{SB}/boardroom/submit", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("verdict") == "accept", d
        assert d.get("vaulted") is True, d
        assert d.get("gamefiles") is True, d
        trace = d.get("trace") or []
        stages = [t.get("stage") for t in trace]
        assert "evaluation_room:enter" in stages, stages
        assert "boardroom_return" in stages, stages
        assert "persist:vault+gamefiles" in stages, stages
        # verify order
        assert stages.index("evaluation_room:enter") < stages.index("boardroom_return") < stages.index("persist:vault+gamefiles"), stages


class TestGovernanceReject:
    def test_reject_flow(self, s):
        payload = {
            "game_name": "TEST_GovReject",
            "filename": "bad.md",
            "content": "this has bias and contradiction all over it",
            "kind": "spec",
        }
        r = s.post(f"{SB}/boardroom/submit", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("verdict") == "reject", d
        assert d.get("vaulted") is False, d
        assert d.get("held_reason"), d


# ── Boardroom Ledger ──────────────────────────────────────────────────────────
class TestLedger:
    def test_ledger(self, s):
        r = s.get(f"{SB}/boardroom/ledger", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("ledger"), list)
        assert len(d["ledger"]) > 0, "Ledger should have entries after governance tests"


# ── Vault ────────────────────────────────────────────────────────────────────
class TestVault:
    def test_vault_roundtrip(self, s):
        content = "TEST_vault_roundtrip_" + str(int(time.time()))
        put = s.post(f"{SB}/vault/put", json={"filename": "TEST_vault_ping.md", "content": content}, timeout=20)
        assert put.status_code == 200, put.text
        pd = put.json()
        assert pd.get("ok") is True, pd
        file_id = pd.get("file_id")
        assert file_id

        got = s.get(f"{SB}/vault/{file_id}", timeout=20)
        assert got.status_code == 200
        gd = got.json()
        assert gd.get("ok") is True, gd
        assert gd.get("content") == content, gd

    def test_vault_list(self, s):
        r = s.get(f"{SB}/vault", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "files" in d
        assert isinstance(d["files"], list)


# ── Rooms ─────────────────────────────────────────────────────────────────────
class TestRooms:
    def test_rooms_activity(self, s):
        r = s.get(f"{SB}/rooms/activity", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("total_rooms") == 1000, d.get("total_rooms")
        assert isinstance(d.get("activity"), list)

    def test_rooms_context(self, s):
        r = s.get(f"{SB}/rooms/context", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # per problem statement: questionnaire/steps/forge/vault context
        assert "questionnaire" in d, list(d.keys())
        assert "snowball_steps" in d, list(d.keys())
        assert "forge_activity" in d, list(d.keys())
        assert "vault_files" in d, list(d.keys())


# ── Jeeves ────────────────────────────────────────────────────────────────────
class TestJeeves:
    def test_oversight(self, s):
        r = s.get(f"{SB}/jeeves/oversight", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert "steps" in d
        assert "vault_files" in d
        assert d.get("total_rooms") == 1000
        assert "boardroom_ledger" in d

    def test_command_forge_deploy(self, s):
        r = s.post(f"{SB}/jeeves/command", json={"message": "run forges and deploy Studio", "game_name": "TEST_Studio"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        actions = d.get("actions") or []
        assert "ran_forges" in actions, actions
        assert "deployed" in actions, actions

    def test_command_help(self, s):
        r = s.post(f"{SB}/jeeves/command", json={"message": "hey", "game_name": "Studio"}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        actions = d.get("actions") or []
        assert "oversight" in actions
        reply = (d.get("reply") or "").lower()
        assert "oversight" in reply or "forge" in reply or "vault" in reply, d.get("reply")
