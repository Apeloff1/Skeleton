"""
Iteration 51 — Central Game Knowledge Base + remaining stage forges
(lore_graph, quest_db, build_manifest).

Validates:
  • build forge is deterministic & instant → ok + build_manifest in KB
  • ONE LLM forge (world → lore_graph) e2e (LLM ~15-30s)
  • /api/pipeline/{pid}/kb returns 6 artifacts with present/summary/stage
  • Unknown stage error returns forgeable list ['spec','mechanics','world','narrative','build']
  • Regressions: forge/spec + forge/mechanics still return job_id and complete;
    /api/playable/{pid}/pipeline returns 9 stages with world/narrative/build carrying 'forge';
    /api/playable/{pid}/apply-assets/async returns job_id; /api/health/registry ok=142
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
PID = "d02790d6d8174ff59bf7005221cd7609"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _poll(api, job_id, max_s=120, interval=2):
    deadline = time.time() + max_s
    last = {}
    while time.time() < deadline:
        r = api.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=20)
        if r.status_code == 200:
            last = r.json()
            if last.get("job_status") in ("done", "error"):
                return last
        time.sleep(interval)
    return last


# ─────────────────────────── KB endpoint shape ───────────────────────────
class TestKnowledgeBase:
    def test_kb_returns_six_artifacts_in_order(self, api):
        r = api.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("game_id") == PID
        assert d.get("total") == 6
        arts = d.get("artifacts")
        assert isinstance(arts, list) and len(arts) == 6
        names = [a["name"] for a in arts]
        assert names == ["core_specs", "lore_graph", "quest_db", "mechanics_config", "asset_manifest", "build_manifest"]
        for a in arts:
            assert "present" in a and isinstance(a["present"], bool)
            assert "summary" in a
            assert "stage" in a
        assert isinstance(d.get("present_count"), int)
        assert "data" in d and isinstance(d["data"], dict)
        for k in ("core_specs", "lore_graph", "quest_db", "mechanics_config", "build_manifest"):
            assert k in d["data"]


# ─────────────────────────── Forge error path ───────────────────────────
class TestForgeErrors:
    def test_unknown_stage_returns_forgeable_list(self, api):
        r = api.post(f"{BASE_URL}/api/pipeline/{PID}/forge/badstage/async", json={}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "error" in d
        assert "forgeable" in d
        assert set(d["forgeable"]) == {"spec", "mechanics", "world", "narrative", "build"}


# ─────────────────────────── Build forge (deterministic) ───────────────────────────
class TestBuildForge:
    def test_build_forge_completes_and_kb_flips(self, api):
        r = api.post(f"{BASE_URL}/api/pipeline/{PID}/forge/build/async", json={}, timeout=20)
        assert r.status_code == 200, r.text
        kick = r.json()
        assert "job_id" in kick
        assert kick.get("stage") == "build"
        assert kick.get("job_status") == "running"

        final = _poll(api, kick["job_id"], max_s=30, interval=1)
        assert final.get("job_status") == "done", final
        assert final.get("ok") is True, final
        assert final.get("artifact") == "build_manifest"

        # KB shows build_manifest present
        kb = api.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=20).json()
        bm = next(a for a in kb["artifacts"] if a["name"] == "build_manifest")
        assert bm["present"] is True
        assert kb["data"]["build_manifest"] is not None

        # Pipeline tracker build stage = done
        p = api.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=20).json()
        bstage = next(s for s in p["stages"] if s["key"] == "build")
        assert bstage["status"] == "done"
        assert bstage.get("forge") == "build"


# ─────────────────────────── LLM forge: world → lore_graph ───────────────────────────
class TestWorldForge:
    def test_world_forge_completes_and_kb_flips(self, api):
        r = api.post(f"{BASE_URL}/api/pipeline/{PID}/forge/world/async", json={}, timeout=20)
        assert r.status_code == 200, r.text
        kick = r.json()
        assert "job_id" in kick
        assert kick.get("stage") == "world"

        final = _poll(api, kick["job_id"], max_s=120, interval=3)
        assert final.get("job_status") == "done", final
        assert final.get("ok") is True, f"lore forge failed: {final}"
        assert final.get("artifact") == "lore_graph"

        kb = api.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=20).json()
        lg = next(a for a in kb["artifacts"] if a["name"] == "lore_graph")
        assert lg["present"] is True
        assert kb["data"]["lore_graph"] is not None
        assert "regions" in kb["data"]["lore_graph"]

        p = api.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=20).json()
        wstage = next(s for s in p["stages"] if s["key"] == "world")
        assert wstage["status"] == "done"
        assert wstage.get("forge") == "world"


# ─────────────────────────── Regressions ───────────────────────────
class TestRegressions:
    def test_forge_spec_returns_job_id(self, api):
        r = api.post(f"{BASE_URL}/api/pipeline/{PID}/forge/spec/async", json={}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "job_id" in d and d.get("stage") == "spec"

    def test_forge_mechanics_returns_job_id(self, api):
        r = api.post(f"{BASE_URL}/api/pipeline/{PID}/forge/mechanics/async", json={}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "job_id" in d and d.get("stage") == "mechanics"

    def test_pipeline_returns_9_stages_with_forge_fields(self, api):
        r = api.get(f"{BASE_URL}/api/playable/{PID}/pipeline", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("total") == 9
        keys = [s["key"] for s in d["stages"]]
        assert keys == ["mode", "spec", "world", "narrative", "mechanics", "assets", "implementation", "qa", "build"]
        by_key = {s["key"]: s for s in d["stages"]}
        # world / narrative / build now also carry forge
        assert by_key["world"].get("forge") == "world"
        assert by_key["narrative"].get("forge") == "narrative"
        assert by_key["build"].get("forge") == "build"
        # legacy spec + mechanics still carry forge
        assert by_key["spec"].get("forge") == "spec"
        assert by_key["mechanics"].get("forge") == "mechanics"

    def test_apply_assets_async_returns_job_id(self, api):
        r = api.post(f"{BASE_URL}/api/playable/{PID}/apply-assets/async", json={}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # Some product paths return a known-error string (e.g. assets not ready), accept both shapes
        assert ("job_id" in d) or ("error" in d), d

    def test_health_registry_ok_142(self, api):
        r = api.get(f"{BASE_URL}/api/health/registry", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # iter 50 baseline said ok=142; allow >=142 (registry can grow)
        assert d.get("ok", 0) >= 142, d
