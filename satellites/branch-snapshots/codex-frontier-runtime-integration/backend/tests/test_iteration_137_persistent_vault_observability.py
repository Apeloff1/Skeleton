"""
Iteration 137 — Persistent Encrypted Vault + Rollback + Observability.

Backend tests for:
  • persistent + encrypted Boardroom Vault (put/get/versions/rollback)
  • Observability dashboard
  • Governance regression (boardroom submit -> vaulted)
  • Regression: activate, map/systems, knowledge/apis
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    # Read directly from frontend .env
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
BASE_URL = (BASE_URL or "http://localhost:8001").rstrip("/")

S = f"{BASE_URL}/api/gameforge/studio"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Persistent Vault ─────────────────────────────────────────────────────────
class TestPersistentVault:
    filename = f"TEST_persist_{int(time.time())}.txt"

    def test_01_put_v1(self, sess):
        r = sess.post(f"{S}/vault/put", json={"filename": self.filename, "content": "v1 content"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("version") == 1
        assert d.get("file_id")
        pytest.file_id = d["file_id"]

    def test_02_put_v2(self, sess):
        r = sess.post(f"{S}/vault/put", json={"filename": self.filename, "content": "v2 content"}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("version") == 2, f"expected version=2 got {d}"

    def test_03_get_latest_decrypted(self, sess):
        r = sess.get(f"{S}/vault/{pytest.file_id}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("content") == "v2 content", d

    def test_04_versions_list(self, sess):
        r = sess.get(f"{S}/vault/{pytest.file_id}/versions", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        versions = [v["version"] for v in d.get("versions", [])]
        assert 1 in versions and 2 in versions, versions

    def test_05_rollback_to_v1(self, sess):
        r = sess.post(f"{S}/vault/{pytest.file_id}/rollback", json={"to_version": 1}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("restored_from") == 1
        assert d.get("new_version") and d["new_version"] > 2, d

    def test_06_get_after_rollback_returns_v1_content(self, sess):
        r = sess.get(f"{S}/vault/{pytest.file_id}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("content") == "v1 content", d

    def test_07_list_files_nonempty(self, sess):
        r = sess.get(f"{S}/vault", timeout=20)
        assert r.status_code == 200
        d = r.json()
        files = d.get("files", [])
        assert isinstance(files, list) and len(files) > 0
        # Confirm our file is present and marked encrypted
        found = [f for f in files if f.get("file_id") == pytest.file_id]
        assert found, f"file_id not found in list: {[f.get('file_id') for f in files]}"
        assert found[0].get("encrypted") is True


# ── Observability Dashboard ──────────────────────────────────────────────────
class TestObservability:
    def test_observability(self, sess):
        r = sess.get(f"{S}/observability", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "health_score" in d
        assert d["health_score"] == 100, d.get("health")
        snow = d.get("snowball", {})
        assert snow.get("total") == 7, snow
        assert "completed" in snow and "progress_percent" in snow
        assert isinstance(d.get("forge_activity"), dict)
        jury = d.get("jury", {})
        assert "total_decisions" in jury
        assert set(jury.get("verdicts", {}).keys()) >= {"accept", "revise", "reject"}
        assert "accept_rate" in jury
        vault = d.get("vault", {})
        assert vault.get("encrypted") is True
        assert "files" in vault
        kn = d.get("knowledge", {})
        for k in ("total", "acquired", "learned"):
            assert k in kn
        health = d.get("health", {})
        for c in ("questionnaire", "steps", "forges", "vault", "evaluation_room", "deployment", "git"):
            assert health.get(c) is True, f"{c} health should be true, got {health}"


# ── Governance regression ────────────────────────────────────────────────────
class TestGovernance:
    def test_boardroom_submit_clean_accept_and_vaulted(self, sess):
        payload = {
            "game_name": "TEST_iter137",
            "filename": f"TEST_gov_{int(time.time())}.md",
            "content": "A wholesome cozy fantasy adventure about brave adventurers exploring beautiful forests.",
            "kind": "artifact",
        }
        r = sess.post(f"{S}/boardroom/submit", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("verdict") == "accept", d
        assert d.get("vaulted") is True
        assert d.get("file_id")


# ── Regression ───────────────────────────────────────────────────────────────
class TestRegression:
    def test_activate_44(self, sess):
        r = sess.post(f"{BASE_URL}/api/gameforge/activate", json={}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Look for "4/4 live" hint - shape unknown, so check flexibly
        summary = d.get("summary") or d
        # Convert to string and check
        as_str = str(d).lower()
        assert "4/4" in as_str or d.get("live") == 4 or d.get("total") == 4, f"activate: {d}"

    def test_map_systems_19(self, sess):
        r = sess.get(f"{BASE_URL}/api/gameforge/map/systems", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total") == 19, d
        assert d.get("live") == 19, d

    def test_knowledge_apis_39(self, sess):
        r = sess.get(f"{BASE_URL}/api/gameforge/knowledge/apis", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total") == 39, d
