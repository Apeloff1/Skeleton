"""
Iteration 5 — Regression for the constants relocation (AGENT_MANIFEST,
GALAXY_GENRES, BUILD_PHASES, SYNERGY_NETWORK) into
routes/galaxy_studio_constants.py + the /manifest & /genres extraction
into routes/galaxy_studio_manifest.py.

Deep-consumer focus: the BUILD PIPELINE end-to-end. POST /create exercises
GALAXY_GENRES.get(genre) + genre_info["name"] + BUILD_PHASES + SYNERGY_NETWORK
all in one call — if the moved constant is broken, this 500s.

NOTE: build watchdog freezes generation at per-build RSS soft/hard caps
(315/450MB) — that is EXPECTED. We only assert the response contract from
/create, /status, /advance, NOT that the build completes.
"""
import os
import time

import pytest
import requests


def _base_url() -> str:
    # Prefer localhost per review-request guidance (avoids Cloudflare ingress
    # flakes for slow endpoints like /once-over which take ~50-60s).
    override = os.environ.get("BACKEND_TEST_URL", "").rstrip("/")
    if override:
        return override
    return "http://localhost:8001"


BASE_URL = _base_url()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Sanity ────────────────────────────────────────────────────────────────
class TestSanity:
    def test_health(self, client):
        r = client.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") in ("healthy", "ok") or d.get("ok") is True


# ── /manifest endpoint contract (extracted into galaxy_studio_manifest.py) ─
class TestManifestExtraction:
    def test_manifest_contract(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/manifest", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_agents"] == 1444700, d
        assert d["total_phases"] == 100, d
        assert d["total_genres"] == 69, d
        assert isinstance(d["phases"], list) and len(d["phases"]) == 100
        assert "constellations" in d["synergy_network"]
        # Sample phase shape
        p0 = d["phases"][0]
        assert {"id", "name", "batch", "agents"}.issubset(p0.keys())

    def test_genres_contract(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/genres", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_genres"] == 69
        assert d["total_subgenres"] == 274
        assert len(d["genres"]) == 69
        first = d["genres"][0]
        assert {"id", "name", "subgenres", "subgenre_count"} <= set(first.keys())


# ── DEEP CONSUMER: build create exercises moved constants ────────────────
class TestBuildPipelineDeepConsumer:
    """If the constants relocation were broken, /create would 500 because it
    reads GALAXY_GENRES.get(genre) + genre_info['name'] + BUILD_PHASES +
    SYNERGY_NETWORK during the response assembly."""

    def _assert_create_ok(self, payload, client):
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/create", json=payload, timeout=60
        )
        assert r.status_code == 200, f"/create failed for {payload}: {r.status_code} {r.text[:400]}"
        d = r.json()
        # Tolerant: accept either {"build_id": ...} top-level or {"build": {...}}
        build_id = d.get("build_id") or (d.get("build") or {}).get("id") or d.get("id")
        assert build_id, f"no build_id in response: {d}"
        # Status should be 'building' (or close synonym)
        status = d.get("status") or (d.get("build") or {}).get("status")
        assert status in ("building", "queued", "started", "running"), f"unexpected status: {status} (d={d})"
        # Populated synergy_network/total_agents/total_phases — proves
        # SYNERGY_NETWORK + AGENT_MANIFEST + BUILD_PHASES still load.
        # These may live at top-level or under 'build'
        scope = d if "synergy_network" in d or "total_agents" in d else (d.get("build") or d)
        assert scope.get("total_agents", 0) > 0, f"total_agents empty: {d}"
        assert scope.get("total_phases", 0) > 0, f"total_phases empty: {d}"
        syn = scope.get("synergy_network") or {}
        assert syn, f"synergy_network missing: {d}"
        assert "constellations" in syn, f"synergy_network missing constellations: {syn}"
        return build_id

    def test_create_rpg(self, client):
        payload = {"title": "RegrA_RPG", "genre": "rpg", "complexity": 2, "age_target": "T"}
        bid = self._assert_create_ok(payload, client)
        assert isinstance(bid, str) and len(bid) > 0

    def test_create_soulslike_fusion_genre(self, client):
        payload = {"title": "RegrA_Souls", "genre": "soulslike", "complexity": 2, "age_target": "T"}
        bid = self._assert_create_ok(payload, client)
        assert isinstance(bid, str)

    def test_create_unknown_genre_falls_back_to_rpg(self, client):
        """An unknown genre key MUST gracefully fall back to GALAXY_GENRES['rpg']
        — proves the .get() fallback path still works after the relocation."""
        payload = {"title": "RegrA_Unknown", "genre": "totally_made_up_genre_xyz", "complexity": 2, "age_target": "T"}
        bid = self._assert_create_ok(payload, client)
        assert isinstance(bid, str)


# ── /status and /advance smoke (BUILD_PHASES consumed at request time) ───
class TestStatusAndAdvance:
    @pytest.fixture(scope="class")
    def build_id(self, client):
        # Tiny dedicated build for status/advance probing
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/create",
            json={"title": "RegrA_StatusAdvance", "genre": "rpg", "complexity": 1, "age_target": "T"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        bid = d.get("build_id") or (d.get("build") or {}).get("id") or d.get("id")
        assert bid, f"no build_id: {d}"
        # Give the background worker a moment to register the build before status probe
        time.sleep(0.5)
        return bid

    def test_status_endpoint(self, client, build_id):
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/status/{build_id}", timeout=20
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # Tolerant: status info may live at top-level or in 'build'
        scope = d.get("build") if isinstance(d.get("build"), dict) else d
        # Must surface some sort of progress/phase info
        progress_keys = {"status", "current_batch", "current_phase", "phase", "batch", "progress", "phases_done", "files_count"}
        assert progress_keys & set(scope.keys()), f"no progress keys in status: {list(scope.keys())[:10]}"

    def test_advance_endpoint(self, client, build_id):
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/advance",
            json={"build_id": build_id},
            timeout=180,
        )
        # 200 expected. If the build has already finished a batch automatically,
        # the endpoint may still return 200 with "no-op"; that's fine.
        assert r.status_code == 200, f"/advance failed: {r.status_code} {r.text[:400]}"
        d = r.json()
        # Response must contain a build object OR explicit status acknowledgement.
        assert isinstance(d, dict) and len(d) > 0


# ── Catalog sub-routers all return 200 ───────────────────────────────────
class TestCatalogEndpoints:
    def test_capabilities_catalog(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/capabilities/catalog", timeout=15)
        assert r.status_code == 200, r.text

    def test_pipeline_catalog(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/pipeline/catalog", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("total_stages") == 8
        assert d.get("total_tasks") == 41

    def test_datasets_catalog(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/datasets/catalog", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("total_datasets") == 16
        assert d.get("total_records") == 100


# ── Dynamic /pipeline/{build_id} counter-test (route ordering) ────────────
class TestDynamicPipelineNotShadowed:
    def test_bogus_pipeline_id_does_not_return_catalog(self, client):
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/pipeline/TEST_bogus_build_id_xyz_999",
            timeout=15,
        )
        assert r.status_code < 500, f"server err: {r.status_code} {r.text[:300]}"
        if r.status_code == 200:
            try:
                d = r.json()
            except Exception:
                d = {}
            # Must NOT be the catalog payload
            if isinstance(d, dict):
                is_cat = d.get("total_stages") == 8 and len(d.get("stages") or []) == 8
                assert not is_cat, "ROUTE-ORDERING REGRESSION: dynamic shadowed by catalog!"


# ── Once-Over orchestrator (catches galaxy_studio_agents.py sub-router) ──
class TestOnceOver:
    def test_once_over_run(self, client):
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over", json={}, timeout=240
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("total_agents") == 16

    def test_once_over_last(self, client):
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over/last", timeout=15
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("ran") is True
        assert d.get("report", {}).get("total_agents") == 16

    def test_once_over_history(self, client):
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over/history?limit=10",
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("history"), list)


# ── Vault admin sub-router ────────────────────────────────────────────────
class TestVaultAdmin:
    def test_vault_stats(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/admin/vault/stats", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        for k in ("builds", "total_files", "disk_bytes"):
            assert k in d
