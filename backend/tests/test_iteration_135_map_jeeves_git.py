"""
Iteration 135 — CNS Map surface + Jeeves self-training + Git readiness.
Covers: /api/gameforge/activate, /map/*, /studio/jeeves/*, /studio/git/*,
questionnaire/steps/forge/deploy build flow.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api/gameforge"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Activate regression ────────────────────────────────────────────────────────
class TestActivate:
    def test_activate(self, s):
        r = s.post(f"{API}/activate", timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["activated"] == 4
        assert j["total"] == 4
        assert j["status"] == "live"


# ── CNS Map surface ────────────────────────────────────────────────────────────
class TestMap:
    def test_overview(self, s):
        j = s.get(f"{API}/map/overview", timeout=30).json()
        assert j["rooms"] == 1000
        assert j["role_categories"] == 202
        assert j["total_roles"] == 1833
        assert j["total_seats"] == 20200
        assert j["skill_categories"] == 8
        assert j["total_skills"] == 64
        assert j["systems_live"] == 19
        assert j["systems_total"] == 19

    def test_systems_all_live(self, s):
        j = s.get(f"{API}/map/systems", timeout=30).json()
        assert j["live"] == 19 and j["total"] == 19
        assert j["systems"].get("aaahrag_librarian") == "live"
        assert all(v == "live" for v in j["systems"].values())

    def test_mastermap(self, s):
        j = s.get(f"{API}/map/mastermap", timeout=30).json()
        assert j["ok"] is True
        assert "mastermap" in j and j["mastermap"]

    def test_rooms(self, s):
        j = s.get(f"{API}/map/rooms", timeout=30).json()
        assert j["total"] == 1000
        assert "divisions" in j
        assert "structure" in j
        assert isinstance(j["sample"], list) and j["sample"]

    def test_room_detail(self, s):
        rooms = s.get(f"{API}/map/rooms", timeout=30).json()
        rid = rooms["sample"][0]
        j = s.get(f"{API}/map/room/{rid}", timeout=30).json()
        assert j["ok"] is True
        assert "registry" in j
        assert "toolbox" in j
        assert "skill_tree_template" in j

    def test_skills(self, s):
        j = s.get(f"{API}/map/skills", timeout=30).json()
        assert j["ok"] is True
        assert j["master_skill_bank"]
        cats = j["master_skill_bank"].get("skill_categories", {})
        assert len(cats) == 8

    def test_toolbox(self, s):
        j = s.get(f"{API}/map/toolbox", timeout=30).json()
        assert j["ok"] is True
        assert j["per_room_assignment"]
        assert j["mishima_toolbox"]
        assert j["delegation_status"] is not None

    def test_seats(self, s):
        j = s.get(f"{API}/map/seats", timeout=30).json()
        assert j["total_categories"] == 202
        assert j["total_seats"] == 20200

    def test_seat_roles_and_assign(self, s):
        cats = s.get(f"{API}/map/seats/roles", timeout=30).json()
        assert cats["ok"] is True
        one = cats["categories"][0]
        roles = s.get(f"{API}/map/seats/roles", params={"category": one}, timeout=30).json()
        assert roles["ok"] is True and roles["roles"]
        r = s.post(f"{API}/map/seats/assign",
                   json={"category": one, "seat_number": 1, "agent_id": "TEST_agent"},
                   timeout=30).json()
        assert r["ok"] is True and r["assigned"] is True
        assert r["seat"]["role_name"]
        assert isinstance(r["seat"]["skills"], list)

    def test_fast_travel_and_nav(self, s):
        j = s.post(f"{API}/map/navigation/fast-travel",
                   json={"agent_id": "TEST_agent", "start": "room_0000", "goal": "room_0999"},
                   timeout=30).json()
        assert j["ok"] is True and "result" in j
        n = s.get(f"{API}/map/navigation", timeout=30).json()
        assert n["fast_travel"] is True and n["nav_map"] is True

    def test_rag(self, s):
        j = s.get(f"{API}/map/rag", timeout=30).json()
        assert j["ok"] is True
        for k in ("hybrid_rag_engine", "omni_advanced_rag", "room_hybrid_rag",
                  "rag_nav_synergy", "aaahrag_librarian"):
            assert j[k] is True, f"rag flag {k} not true"


# ── Jeeves self-training ───────────────────────────────────────────────────────
class TestJeeves:
    def test_train(self, s):
        j = s.post(f"{API}/studio/jeeves/train", timeout=60).json()
        assert j.get("ok") is True
        assert j.get("fill_percent") == 50
        assert j.get("target") == 108

    def test_knowledge(self, s):
        j = s.get(f"{API}/studio/jeeves/knowledge", timeout=30).json()
        assert j["ok"] is True
        st = j["status"]
        assert st["knowledge_count"] == 54
        assert st["skill_count"] == 64
        assert st["fill_percent"] == 50
        bd = st["by_domain"]
        assert bd["game_logic"] == 14
        assert bd["coding"] == 20
        assert bd["game_design"] == 20

    def test_recall_coding(self, s):
        j = s.post(f"{API}/studio/jeeves/command",
                   json={"message": "how should I handle errors in code?"}, timeout=30).json()
        assert j["ok"] is True
        rep = j["reply"].lower()
        assert any(w in rep for w in ("boundary", "boundaries", "fail fast", "validate"))

    def test_recall_game_design(self, s):
        j = s.post(f"{API}/studio/jeeves/command",
                   json={"message": "roguelike mechanics"}, timeout=30).json()
        rep = j["reply"].lower()
        assert "roguelike" in rep or "procedural" in rep or "permadeath" in rep

    def test_command_actions(self, s):
        j = s.post(f"{API}/studio/jeeves/command",
                   json={"message": "run forges and deploy Studio", "game_name": "TEST_Studio"},
                   timeout=120).json()
        assert j["ok"] is True
        assert "ran_forges" in j["actions"]
        assert "deployed" in j["actions"]


# ── Git readiness ──────────────────────────────────────────────────────────────
class TestGit:
    def test_git_status(self, s):
        j = s.get(f"{API}/studio/git/status", timeout=30).json()
        assert j["repo_ready"] is True
        assert j["push_active"] is False

    def test_commit_from_vault(self, s):
        put = s.post(f"{API}/studio/vault/put",
                     json={"filename": "TEST_iter135.md",
                           "content": "TEST vault ping iter135",
                           "is_base64": False, "metadata": {}}, timeout=30).json()
        assert put.get("ok") is True
        fid = put["file_id"]
        r = s.post(f"{API}/studio/git/commit-from-vault",
                   json={"file_id": fid, "version": 1,
                         "message": "TEST iter135 commit"}, timeout=30).json()
        assert r.get("committed") is True

    def test_push_ready_but_inactive(self, s):
        j = s.post(f"{API}/studio/git/push", timeout=30).json()
        assert j.get("ok") is False
        err = (j.get("error") or "").upper()
        assert "GITHUB_REMOTE" in err and "GITHUB_TOKEN" in err


# ── Build flow ─────────────────────────────────────────────────────────────────
class TestBuildFlow:
    def test_questions(self, s):
        j = s.get(f"{API}/studio/questionnaire/questions", timeout=30).json()
        assert j["ok"] is True
        assert len(j["questions"]) == 6

    def test_steps(self, s):
        j = s.get(f"{API}/studio/steps", timeout=30).json()
        assert len(j["steps"]) == 7

    def test_complete_step(self, s):
        j = s.post(f"{API}/studio/step/step_1_concept/complete", timeout=30).json()
        assert j["ok"] is True
        assert j["status"] == "completed"

    def test_forge_run(self, s):
        j = s.post(f"{API}/studio/forge/run", json={}, timeout=120).json()
        assert j["ok"] is True
        keys = set(j["results"].keys())
        for k in ("asset", "mechanic", "world", "code", "ui", "balance"):
            assert k in keys, f"missing forge key {k} (got {keys})"

    def test_deploy(self, s):
        j = s.post(f"{API}/studio/deploy", json={"game_name": "TEST_Studio"}, timeout=120).json()
        assert j["ok"] is True
        dep = j["deployment"]
        assert "platforms" in dep or "signed_binaries" in dep or dep
