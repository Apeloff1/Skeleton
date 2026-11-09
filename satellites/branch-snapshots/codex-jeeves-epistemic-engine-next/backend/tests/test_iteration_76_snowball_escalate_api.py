"""Iteration 76 — Public-URL integration tests for the escalating snowball build.

Covers the new Galaxy Studio endpoints:
- POST /api/galaxy-studio/vault-gdd/escalate (escalating, parity-locked, quality-gated)
- GET  /api/galaxy-studio/vault-gdd/parity/{build_id}
- POST /api/galaxy-studio/assets/forge (10× asset pack per gamefile)
- GET  /api/galaxy-studio/assets/{build_id}
- GET  /api/galaxy-studio/vault-gdd/{build_id}/gamefiles.zip (downloadable bundle)
"""
import io
import json
import os
import uuid
import zipfile

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://player-retention.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def fresh_build_id():
    return f"TEST_it76_{uuid.uuid4().hex[:10]}"


# ── 1. POST /vault-gdd/escalate ────────────────────────────────────────────
class TestEscalate:
    def test_escalate_returns_ladder_and_parity_lock(self, api, fresh_build_id):
        payload = {"build_id": fresh_build_id, "genre": "rpg", "seed": 7,
                   "platoon_size": 4, "persist": True}
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()

        # 6 stages → 6 ladder rows + 6 GDD sections
        assert len(data["ladder"]) == 6
        assert data["gdd_sections"] == 6
        # parity locked + 100%
        assert data["parity_locked"] is True
        assert data["parity_pct"] == 100
        # grade escalating
        assert data["grade_escalating"] is True
        # totals
        assert data["totals"]["gamefiles"] > 0
        assert data["totals"]["assets"] == data["totals"]["gamefiles"] * 10
        assert data["totals"]["assets_per_item"] == 10

        # Per-ladder-row required keys
        required = {"grade_floor", "max_grade", "accepted", "forged",
                    "assets", "parity_ok", "quality", "level", "stage"}
        for row in data["ladder"]:
            assert required.issubset(row.keys()), f"missing keys in {row}"
            assert row["parity_ok"] is True
            assert row["assets"] == row["accepted"] * 10

        # grade floor strictly escalates across stages
        floors = [r["grade_floor"] for r in data["ladder"]]
        assert floors == sorted(floors)
        assert floors[0] < floors[-1]


# ── 2. GET /vault-gdd/parity/{build_id} ────────────────────────────────────
class TestParity:
    def test_parity_after_escalate(self, api, fresh_build_id):
        # depends on TestEscalate persist=True for same build_id
        r = api.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/parity/{fresh_build_id}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["build_id"] == fresh_build_id
        assert data["parity_locked"] is True
        assert data["parity_pct"] == 100
        assert data["grade_escalating"] is True
        assert isinstance(data["ladder"], list)
        assert len(data["ladder"]) == 6

    def test_parity_404_for_unknown_build(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/parity/TEST_it76_nope_{uuid.uuid4().hex[:6]}",
                    timeout=15)
        assert r.status_code == 404


# ── 3. POST /assets/forge ──────────────────────────────────────────────────
class TestAssetForge:
    def test_forge_assets_10x(self, api, fresh_build_id):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/assets/forge",
                     json={"build_id": fresh_build_id, "seed": 1, "persist": True},
                     timeout=45)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["assets_per_item"] == 10
        items = data.get("items") or data.get("gamefiles") or data.get("item_count")
        # accept any of the keys the summary may use to report N
        n_items = data.get("items") if isinstance(data.get("items"), int) else None
        if n_items is None:
            # try other shapes
            n_items = data.get("gamefiles") or data.get("item_count")
        assert n_items is not None, f"summary missing item count: {data}"
        assert data["total_assets"] == n_items * 10
        # by_type must cover the 10 asset types (list of {type, count} or dict)
        by_type = data["by_type"]
        if isinstance(by_type, list):
            types = {x["type"] for x in by_type}
        else:
            types = set(by_type.keys())
        assert len(types) == 10, f"expected 10 asset types, got {types}"


# ── 4. GET /assets/{build_id} ──────────────────────────────────────────────
class TestAssetList:
    def test_list_persisted_assets(self, api, fresh_build_id):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/assets/{fresh_build_id}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["build_id"] == fresh_build_id
        assert isinstance(data["assets"], list)
        assert len(data["assets"]) > 0
        # spot check schema
        a0 = data["assets"][0]
        assert "type" in a0
        # no mongo _id leakage
        assert "_id" not in a0


# ── 5. GET /vault-gdd/{build_id}/gamefiles.zip ─────────────────────────────
class TestGamefilesZip:
    def test_zip_download_after_escalate(self, api, fresh_build_id):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/{fresh_build_id}/gamefiles.zip",
                    timeout=60)
        assert r.status_code == 200, r.text[:300] if r.text else r.status_code
        ctype = r.headers.get("content-type", "")
        assert "application/zip" in ctype, f"unexpected content-type: {ctype}"
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert ".zip" in cd.lower()

        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "GDD.md" in names
            assert "manifest.json" in names
            assert any(n.startswith("gamefiles/") for n in names), f"no gamefiles/ entries: {names[:5]}"
            # GDD.md non-empty
            with zf.open("GDD.md") as f:
                gdd_bytes = f.read()
            assert len(gdd_bytes) > 50
            # manifest.json parses & has build_id
            with zf.open("manifest.json") as f:
                man = json.loads(f.read())
            assert man["build_id"] == fresh_build_id
            assert man["items"] > 0
            assert man["assets"] > 0
            # at least one .js and one .json under gamefiles/
            assert any(n.endswith(".js") and n.startswith("gamefiles/") for n in names)
            assert any(n.endswith(".json") and n.startswith("gamefiles/") for n in names)

    def test_zip_404_when_no_gamefiles(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/TEST_it76_empty_{uuid.uuid4().hex[:6]}/gamefiles.zip",
                    timeout=15)
        assert r.status_code == 404
