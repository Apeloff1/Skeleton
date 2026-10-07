"""
Iteration 50 — Studio Pipeline orchestrator + Central Game KB forges
Validates:
  - GET /api/playable/{pid}/pipeline   (9-stage tracker shape)
  - GET /api/pipeline/{pid}/kb         (4-artifact catalogue)
  - POST /api/pipeline/{pid}/forge/mechanics/async (LLM forge end-to-end)
  - POST /api/pipeline/{pid}/forge/badstage/async  (error path)
  - Regression: leaderboard, apply-assets, genesis/styles, health/registry
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
PID = "d02790d6d8174ff59bf7005221cd7609"

VALID_STATUSES = {"done", "partial", "todo"}
EXPECTED_KEYS = ["mode", "spec", "world", "narrative", "mechanics", "assets", "implementation", "qa", "build"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Pipeline tracker ──────────────────────────────────────────────────
class TestPipelineTracker:
    def test_pipeline_shape(self, s):
        r = s.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "stages" in d and isinstance(d["stages"], list)
        assert len(d["stages"]) == 9
        assert d["total"] == 9
        assert isinstance(d["done"], int)
        assert isinstance(d["percent"], int)
        assert "next_label" in d
        # each stage has the right shape
        for st in d["stages"]:
            assert set(["key", "label", "icon", "status", "detail", "route"]).issubset(st.keys())
            assert st["status"] in VALID_STATUSES
        keys = [st["key"] for st in d["stages"]]
        assert keys == EXPECTED_KEYS, f"unexpected stage keys: {keys}"

    def test_forge_field_on_spec_and_mechanics(self, s):
        d = s.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=20).json()
        by_key = {st["key"]: st for st in d["stages"]}
        assert by_key["spec"].get("forge") == "spec"
        assert by_key["mechanics"].get("forge") == "mechanics"

    def test_core_spec_done(self, s):
        # core_specs already forged per problem statement
        d = s.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=20).json()
        by_key = {st["key"]: st for st in d["stages"]}
        assert by_key["spec"]["status"] == "done", f"spec stage not done: {by_key['spec']}"


# ── Central Knowledge Base ────────────────────────────────────────────
class TestKnowledgeBase:
    def test_kb_shape(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 4
        names = [a["name"] for a in d["artifacts"]]
        assert names == ["core_specs", "lore_graph", "mechanics_config", "asset_manifest"]
        for a in d["artifacts"]:
            assert "present" in a and isinstance(a["present"], bool)
            assert "summary" in a
        assert "present_count" in d
        # core_specs should already exist & be non-null
        assert d["core_specs"] is not None
        # core_specs artifact entry should be present
        cs = next(a for a in d["artifacts"] if a["name"] == "core_specs")
        assert cs["present"] is True


# ── Forge error path ──────────────────────────────────────────────────
class TestForgeErrors:
    def test_unknown_stage_returns_error(self, s):
        r = s.post(f"{BASE_URL}/api/pipeline/{PID}/forge/badstage/async", json={}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "error" in d
        assert "forgeable" in d
        assert set(d["forgeable"]) == {"spec", "mechanics"}


# ── Live LLM forge end-to-end ─────────────────────────────────────────
class TestMechanicsForge:
    def test_forge_mechanics_async_and_kb_flip(self, s):
        # 1. fire forge
        r = s.post(f"{BASE_URL}/api/pipeline/{PID}/forge/mechanics/async", json={}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "job_id" in d, d
        job_id = d["job_id"]
        assert d.get("stage") == "mechanics"

        # 2. poll job (LLM ~10-25s, allow up to 90s)
        # _run_job flattens the coroutine's return dict into the job doc itself,
        # so {ok, artifact, summary, keys, model} sit at the top level alongside job_status.
        final = None
        for _ in range(45):
            time.sleep(2)
            jr = s.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=10)
            assert jr.status_code == 200, jr.text
            jd = jr.json()
            if jd.get("job_status") == "done":
                final = jd
                break
            if jd.get("job_status") == "error":
                pytest.fail(f"job errored: {jd}")
        assert final is not None, "forge job did not complete within 90s"
        assert final.get("ok") is True, f"forge result not ok: {final}"
        assert final.get("artifact") == "mechanics_config"

        # 3. KB should now have mechanics_config present
        kb = s.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=15).json()
        mech = next(a for a in kb["artifacts"] if a["name"] == "mechanics_config")
        assert mech["present"] is True, f"mechanics_config not present in kb: {kb}"
        assert kb.get("mechanics_config") is not None

        # 4. Pipeline tracker should now mark mechanics stage as done
        pl = s.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=15).json()
        by_key = {st["key"]: st for st in pl["stages"]}
        assert by_key["mechanics"]["status"] == "done", f"mechanics stage not done: {by_key['mechanics']}"


# ── Regressions ───────────────────────────────────────────────────────
class TestRegressions:
    def test_leaderboard_assets_complete(self, s):
        r = s.get(f"{BASE_URL}/api/playable/leaderboard?assets=complete", timeout=15)
        assert r.status_code == 200

    def test_apply_assets_async(self, s):
        r = s.post(f"{BASE_URL}/api/playable/{PID}/apply-assets/async", json={}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # accept job_id OR known error (rate_limited / no generated assets)
        assert ("job_id" in d) or ("error" in d), d

    def test_assets_genesis_styles(self, s):
        r = s.get(f"{BASE_URL}/api/assets/genesis/styles", timeout=15)
        assert r.status_code == 200

    def test_health_registry(self, s):
        r = s.get(f"{BASE_URL}/api/health/registry", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok", 0) >= 141, f"registry ok count too low: {d.get('ok')}"
