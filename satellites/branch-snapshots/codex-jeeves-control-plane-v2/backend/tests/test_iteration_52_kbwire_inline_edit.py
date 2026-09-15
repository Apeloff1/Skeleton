"""
Iteration 52 — KB inline edit (PUT /api/pipeline/{pid}/kb/{artifact}) +
                Apply KB to game (POST /api/playable/{pid}/apply-kb/async)
                + regressions.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/') or \
           'https://gemini-game-craft.preview.emergentagent.com'
PID = "d02790d6d8174ff59bf7005221cd7609"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── PUT /api/pipeline/{pid}/kb/{artifact} ────────────────────────────────────
class TestInlineEdit:
    def test_edit_core_specs_ok(self, s):
        # snapshot original first so we can restore
        prev = s.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=15).json()
        orig_core = (prev.get("data") or {}).get("core_specs") or {}

        payload = {"data": {"title": "UnitTest", "logline": "y",
                            "pillars": ["a"], "core_loop": ["z"]}}
        r = s.put(f"{BASE_URL}/api/pipeline/{PID}/kb/core_specs",
                  json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("artifact") == "core_specs"
        assert set(d.get("keys") or []) == {"title", "logline", "pillars", "core_loop"}

        # GET verifies persistence
        g = s.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=15).json()
        cs = (g.get("data") or {}).get("core_specs") or {}
        assert cs.get("title") == "UnitTest", cs
        assert cs.get("logline") == "y"

        # restore if we had a real one
        if orig_core and "core_loop" in orig_core:
            s.put(f"{BASE_URL}/api/pipeline/{PID}/kb/core_specs",
                  json={"data": orig_core}, timeout=15)

    def test_edit_unknown_artifact_returns_editable(self, s):
        r = s.put(f"{BASE_URL}/api/pipeline/{PID}/kb/notreal",
                  json={"data": {"a": 1}}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "error" in d, d
        ed = d.get("editable")
        assert isinstance(ed, list) and len(ed) == 5, ed
        assert set(ed) == {"core_specs", "lore_graph", "quest_db",
                           "mechanics_config", "build_manifest"}

    def test_edit_empty_object_rejected(self, s):
        r = s.put(f"{BASE_URL}/api/pipeline/{PID}/kb/core_specs",
                  json={"data": {}}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "error" in d, d


# ── POST /api/playable/{pid}/apply-kb/async ──────────────────────────────────
class TestApplyKBAsync:
    def test_apply_kb_async_end_to_end(self, s):
        # snapshot version-before from pipeline (cheap, no HTML)
        pp0 = s.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=15).json()
        impl0 = next((st for st in pp0.get("stages", []) if st.get("key") == "implementation"), {})
        import re
        m = re.search(r"v(\d+)", impl0.get("detail") or "")
        v_before = int(m.group(1)) if m else 1

        r = s.post(f"{BASE_URL}/api/playable/{PID}/apply-kb/async",
                   json={}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("error") == "rate_limited":
            pytest.skip("rate_limited – previous test run too recent")
        assert d.get("job_id"), d
        assert d.get("job_status") == "running"
        jid = d["job_id"]

        # poll up to 240s (LLM game rewrite can be slow)
        final = None
        for _ in range(80):
            time.sleep(3)
            jr = s.get(f"{BASE_URL}/api/playable/job/{jid}", timeout=15).json()
            if jr.get("job_status") in ("done", "error"):
                final = jr
                break
        assert final is not None, "job did not finish within 240s"
        assert final.get("job_status") == "done", final
        # _run_job flattens the dict — read top-level keys
        assert final.get("applied") is True, final
        synced = final.get("synced") or []
        assert isinstance(synced, list)
        assert "core_specs" in synced
        assert "mechanics_config" in synced
        assert int(final.get("version") or 0) > v_before

        # pipeline.Implementation stage detail starts with 'KB-synced'
        pp = s.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=15).json()
        impl = next((st for st in pp.get("stages", []) if st.get("key") == "implementation"), None)
        assert impl is not None
        assert (impl.get("detail") or "").startswith("KB-synced"), impl


# ── Regressions ──────────────────────────────────────────────────────────────
class TestRegressions:
    def test_forge_build_still_ok(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{PID}/forge/build/async",
                   json={}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("job_id"), d
        assert d.get("stage") == "build"

    def test_kb_has_6_artifacts(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total") == 6
        names = [a["name"] for a in d.get("artifacts", [])]
        assert names == ["core_specs", "lore_graph", "quest_db",
                         "mechanics_config", "asset_manifest", "build_manifest"]

    def test_apply_assets_async_returns_job(self, s):
        r = s.post(f"{BASE_URL}/api/playable/{PID}/apply-assets/async",
                   json={}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        if d.get("error") == "rate_limited":
            pytest.skip("rate_limited")
        assert d.get("job_id"), d

    def test_health_registry(self, s):
        r = s.get(f"{BASE_URL}/api/health/registry", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") == 143, d
