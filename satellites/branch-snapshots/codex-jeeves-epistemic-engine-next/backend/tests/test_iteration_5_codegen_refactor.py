"""
Iteration 5 regression — verifies the refactor that extracted ~4300 lines of
pure code-generator helpers from routes/galaxy_studio.py into
routes/galaxy_studio_codegen.py. Behaviour MUST be unchanged.

Checks:
  - Core endpoints (/api/health, /api/languages, /api/feature-flags) -> 200
  - Galaxy Studio catalogue endpoints (/genres, /manifest,
    /capabilities/catalog) -> 200
  - Agent once-over runs + history endpoint (self-contained sub-router)
  - End-to-end create -> advance -> status build generates files
    (file_count > 0) — critical regression check exercising the moved _gen_*
    generators.

Uses LOCAL backend URL per main-agent note: ingress times out on heavy build
calls; local does not.
"""
import time
import pytest
import requests

LOCAL_URL = "http://localhost:8001"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ----- Core endpoints --------------------------------------------------
class TestCoreEndpoints:
    def test_health(self, api):
        r = api.get(f"{LOCAL_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_languages(self, api):
        r = api.get(f"{LOCAL_URL}/api/languages", timeout=10)
        assert r.status_code == 200

    def test_feature_flags(self, api):
        r = api.get(f"{LOCAL_URL}/api/feature-flags", timeout=10)
        assert r.status_code == 200


# ----- Galaxy Studio catalog/manifest endpoints ------------------------
class TestGalaxyStudioCatalogs:
    def test_genres(self, api):
        r = api.get(f"{LOCAL_URL}/api/galaxy-studio/genres", timeout=15)
        assert r.status_code == 200

    def test_manifest(self, api):
        r = api.get(f"{LOCAL_URL}/api/galaxy-studio/manifest", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_capabilities_catalog(self, api):
        r = api.get(f"{LOCAL_URL}/api/galaxy-studio/capabilities/catalog", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


# ----- Agent Once-Over -------------------------------------------------
class TestAgentOnceOver:
    def test_once_over_run(self, api):
        r = api.post(f"{LOCAL_URL}/api/galaxy-studio/agents/once-over", json={}, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("total_agents", 0) > 0
        assert body.get("healthy", 0) > 0

    def test_once_over_history(self, api):
        r = api.get(f"{LOCAL_URL}/api/galaxy-studio/agents/once-over/history?limit=5", timeout=15)
        assert r.status_code == 200


# ----- End-to-end build: critical regression for codegen extraction ----
class TestE2EBuild:
    def test_create_advance_status_generates_files(self, api):
        create_payload = {
            "title": "TEST_CodegenRefactorBuild",
            "genre": "rpg",
            "subgenre": "action",
            "description": "Regression for codegen extraction",
            "complexity": 8,
            "scale": "advanced",
            "mutation_matrix": {
                "combat_mutations": {"rate": 2, "magnitude": 3},
            },
        }
        r = api.post(f"{LOCAL_URL}/api/galaxy-studio/create", json=create_payload, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        build_id = body.get("build_id") or body.get("id")
        assert build_id, f"No build_id in response: {body}"

        last_status = None
        file_count = 0
        for _ in range(60):
            adv = api.post(
                f"{LOCAL_URL}/api/galaxy-studio/advance",
                json={"build_id": build_id},
                timeout=180,
            )
            assert adv.status_code == 200, (
                f"advance failed: {adv.status_code} {adv.text[:500]}"
            )
            j = adv.json()
            last_status = j.get("status") or j.get("phase")
            file_count = j.get("file_count", file_count) or file_count
            if last_status in ("completed", "done", "complete"):
                break
            time.sleep(0.3)

        st = api.get(f"{LOCAL_URL}/api/galaxy-studio/status/{build_id}", timeout=30)
        assert st.status_code == 200, st.text
        s = st.json()
        final_files = s.get("file_count", 0) or s.get("files_generated", 0) or file_count
        assert final_files > 0, (
            f"No files generated — codegen extraction may be broken. status={s}"
        )
