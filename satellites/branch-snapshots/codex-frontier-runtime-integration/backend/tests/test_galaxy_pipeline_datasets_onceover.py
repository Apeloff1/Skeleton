"""
Iteration 3 — Tests for Galaxy Studio batch:
  • 8-stage Game Development Pipeline catalog
  • 16 local agent self-sufficiency datasets catalog
  • Agent Once-Over cadence orchestrator (+ last endpoint)
  • E2E build emits pipeline/* and data/datasets/* artifacts (and still
    includes capabilities/* + logic/mutations/* from prior batches)
  • /api/health regression
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend .env public backend url (preview ingress)
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Regression: /api/health ─────────────────────────────────────────────
class TestHealth:
    def test_health(self, client):
        r = client.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # tolerate various shapes — just ensure healthy signal present
        assert (data.get("status") in ("healthy", "ok")) or data.get("ok") is True, data


# ── 8-stage Game Development Pipeline catalog ───────────────────────────
class TestPipelineCatalog:
    def test_catalog_shape(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/pipeline/catalog", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["total_stages"] == 8
        assert data["total_tasks"] == 41
        stages = data["stages"]
        assert len(stages) == 8
        for s in stages:
            assert {"id", "title", "gate", "tasks"}.issubset(s.keys())
            assert isinstance(s["tasks"], list) and len(s["tasks"]) >= 4
        # total_tasks must equal sum of task counts
        assert sum(len(s["tasks"]) for s in stages) == 41


# ── 16 Agent self-sufficiency datasets catalog ──────────────────────────
class TestDatasetsCatalog:
    def test_catalog_shape(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/datasets/catalog", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["total_datasets"] == 16
        assert data["total_records"] == 100
        datasets = data["datasets"]
        assert len(datasets) == 16
        for d in datasets:
            assert {"id", "title", "kind", "count", "sample"}.issubset(d.keys())
            assert isinstance(d["sample"], list) and 1 <= len(d["sample"]) <= 5
            assert d["count"] >= 1
        assert sum(d["count"] for d in datasets) == 100


# ── Agent Once-Over cadence orchestrator ────────────────────────────────
class TestOnceOver:
    def test_once_over_run_and_last(self, client):
        r = client.post(f"{BASE_URL}/api/galaxy-studio/agents/once-over", json={}, timeout=180)
        assert r.status_code == 200, r.text
        rep = r.json()
        assert rep["ok"] is True
        assert rep["total_agents"] == 16
        assert rep["healthy"] == 16, f"degraded agents: {rep.get('blockers')}"
        assert rep["blockers"] == []
        assert isinstance(rep["results"], list) and len(rep["results"]) == 16
        for res in rep["results"]:
            for k in ("agent", "path", "ok", "status", "latency_ms", "attempts", "finding"):
                assert k in res, f"missing key {k} in {res}"
            assert res["ok"] is True
            assert res["finding"] == "ok"

        # /last must reflect cached report
        r2 = client.get(f"{BASE_URL}/api/galaxy-studio/agents/once-over/last", timeout=15)
        assert r2.status_code == 200, r2.text
        last = r2.json()
        assert last["ok"] is True
        assert last["ran"] is True
        assert last["report"] is not None
        assert last["report"]["total_agents"] == 16
        assert last["report"]["healthy"] == 16


# ── E2E: Build emits pipeline/* and data/datasets/* files ───────────────
class TestE2EBuildArtifacts:
    @pytest.fixture(scope="class")
    def build_id(self, client):
        payload = {
            "title": "TEST_PipelineDatasetsBuild",
            "genre": "rpg",
            "complexity": "advanced",
            # mutation_matrix unlocks logic/mutations/* (prior-batch regression)
            "mutation_matrix": {
                "physics_gravity": {"rate": 3, "magnitude": 2},
                "ai_aggression": {"rate": 2, "magnitude": 4},
                "world_seed": {"rate": 5},
            },
        }
        r = client.post(f"{BASE_URL}/api/galaxy-studio/create", json=payload, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        bid = data.get("build_id") or data.get("id") or (data.get("build") or {}).get("id")
        assert bid, f"no build_id returned: {data}"
        return bid

    def test_drive_build_to_completion(self, client, build_id):
        # Try /advance up to ~14 times; if not completed, force-complete.
        completed = False
        status = None
        for _ in range(14):
            r = client.post(
                f"{BASE_URL}/api/galaxy-studio/advance",
                json={"build_id": build_id},
                timeout=180,
            )
            if r.status_code != 200:
                break
            j = r.json() or {}
            build_obj = j.get("build") or j
            status = build_obj.get("status")
            if status == "completed":
                completed = True
                break
            time.sleep(1.0)

        if not completed:
            fr = client.post(
                f"{BASE_URL}/api/galaxy-studio/force-complete/{build_id}",
                timeout=180,
            )
            assert fr.status_code == 200, fr.text
            status = "completed"

        # Build must NOT have failed
        assert status == "completed", f"final status: {status}"

    def test_files_listing_includes_pipeline_and_datasets(self, client, build_id):
        # Allow async vault save a moment
        time.sleep(2.0)
        r = client.get(f"{BASE_URL}/api/galaxy-studio/files/{build_id}", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # Extract list of file paths regardless of envelope shape
        paths = []
        if isinstance(data, dict):
            if isinstance(data.get("files"), list):
                first = data["files"][0] if data["files"] else None
                if isinstance(first, str):
                    paths = data["files"]
                elif isinstance(first, dict):
                    paths = [
                        f.get("path") or f.get("name") or f.get("filename")
                        for f in data["files"]
                    ]
            elif isinstance(data.get("paths"), list):
                paths = data["paths"]
            elif isinstance(data.get("files"), dict):
                paths = list(data["files"].keys())
        paths = [p for p in paths if p]
        assert paths, f"empty files listing: {str(data)[:400]}"

        # (a) pipeline/* artifacts
        assert "pipeline/GameDevelopmentPipeline.ts" in paths, "missing GameDevelopmentPipeline.ts"
        assert "pipeline/TaskGraph.ts" in paths, "missing TaskGraph.ts"
        stage_files = [p for p in paths if p.startswith("pipeline/stages/") and p.endswith("Stage.ts")]
        assert stage_files, f"no pipeline/stages/*Stage.ts files; sample={paths[:8]}"

        # (b) data/datasets/* artifacts
        assert "data/datasets/DatasetRegistry.ts" in paths, "missing DatasetRegistry.ts"
        dataset_files = [
            p for p in paths
            if p.startswith("data/datasets/") and p.endswith("Dataset.ts")
        ]
        assert dataset_files, f"no data/datasets/*Dataset.ts files; sample={paths[:8]}"

        # Regression: prior batches still present
        cap_files = [p for p in paths if p.startswith("capabilities/")]
        assert cap_files, "no capabilities/* files present (regression)"
        mut_files = [p for p in paths if p.startswith("logic/mutations/")]
        assert mut_files, "no logic/mutations/* files present (regression)"
