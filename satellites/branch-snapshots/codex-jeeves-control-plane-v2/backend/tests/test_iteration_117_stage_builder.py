"""Iteration 117 — Stage Builder ("Stage Page") backend tests.

Validates:
 * /api/galaxy-studio/stages/catalog       (63 types, 100k cap, 6 groups w/ counts)
 * add → list → summary → build → crosswire to 14-gate engine → delete → reorder → update
 * Iteration-118 regression: text-gamefile generators (count==10) + quest_from_text
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "http://localhost:8001").rstrip("/")

STAGES = f"{BASE_URL}/api/galaxy-studio/stages"
GATES = f"{BASE_URL}/api/galaxy-studio/gates"
TGF = f"{BASE_URL}/api/galaxy-studio/text-gamefile"

EXPECTED_GROUP_COUNTS = {
    "core": 5, "combat": 15, "story": 13,
    "exploration": 10, "cinematic": 14, "meta": 6,
}
EXPECTED_TOTAL = sum(EXPECTED_GROUP_COUNTS.values())  # 63


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def build_id():
    return f"TEST_stage_{uuid.uuid4().hex[:10]}"


# ── Catalog ─────────────────────────────────────────────────────────────────
class TestCatalog:
    def test_catalog_shape(self, s):
        r = s.get(f"{STAGES}/catalog", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_types"] == EXPECTED_TOTAL, (
            f"expected {EXPECTED_TOTAL} types, got {d['total_types']}")
        assert d["max_stages"] == 100_000
        assert len(d["groups"]) == 6
        # Per-group counts must match exactly
        counts = {g["category"]: g["count"] for g in d["groups"]}
        assert counts == EXPECTED_GROUP_COUNTS, counts
        # Each type carries the required fields
        sample = d["groups"][0]["types"][0]
        for f in ("key", "label", "icon", "category", "difficulty",
                  "combat", "gens"):
            assert f in sample, f"missing {f} in stage type"
        assert isinstance(sample["gens"], list) and len(sample["gens"]) >= 1


# ── Add / List / Summary ────────────────────────────────────────────────────
class TestStageCRUD:
    def test_add_boss(self, s, build_id):
        r = s.post(f"{STAGES}/{build_id}/add", json={"type": "boss"}, timeout=15)
        assert r.status_code == 200, r.text
        st = r.json()
        assert "error" not in st, st
        assert st["type"] == "boss"
        assert st["seq"] == 1
        assert st["built"] is False
        assert isinstance(st["gens"], list) and len(st["gens"]) == 4
        pytest.boss_id = st["id"]

    def test_add_multiple(self, s, build_id):
        for tk in ("cutscene", "puzzle_room", "interlude"):
            r = s.post(f"{STAGES}/{build_id}/add", json={"type": tk}, timeout=15)
            assert r.status_code == 200 and "error" not in r.json(), r.text
        r = s.get(f"{STAGES}/{build_id}/list", timeout=15)
        assert r.status_code == 200
        lst = r.json()
        assert lst["count"] == 4
        seqs = [x["seq"] for x in lst["stages"]]
        assert seqs == [1, 2, 3, 4]

    def test_add_bad_type(self, s, build_id):
        r = s.post(f"{STAGES}/{build_id}/add",
                   json={"type": "nonsense_xyz"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("error") == "unknown_stage_type"

    def test_summary(self, s, build_id):
        r = s.get(f"{STAGES}/{build_id}/summary", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["stage_count"] == 4
        assert d["built_count"] == 0
        assert d["gamefile_count"] == 0
        assert d["max_stages"] == 100_000


# ── Build (creates first gamefiles) & 14-gate crosswire ─────────────────────
class TestBuildAndCrosswire:
    def test_build_boss_creates_gamefiles(self, s, build_id):
        sid = pytest.boss_id
        r = s.post(f"{STAGES}/{build_id}/{sid}/build",
                   json={"enrich": False}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["built"] is True
        assert d["gamefile_count"] == 4, d
        assert isinstance(d["gamefiles"], list) and len(d["gamefiles"]) == 4
        for gf in d["gamefiles"]:
            for f in ("id", "system", "type", "label"):
                assert f in gf
        pytest.first_gf_id = d["gamefiles"][0]["id"]

    def test_stage_flipped_built(self, s, build_id):
        r = s.get(f"{STAGES}/{build_id}/list", timeout=15)
        assert r.status_code == 200
        boss = next(x for x in r.json()["stages"] if x["id"] == pytest.boss_id)
        assert boss["built"] is True
        assert boss["gamefile_count"] == 4

    def test_summary_after_build(self, s, build_id):
        r = s.get(f"{STAGES}/{build_id}/summary", timeout=15)
        d = r.json()
        assert d["built_count"] == 1
        assert d["gamefile_count"] == 4

    def test_gate_refine_run_on_gamefile(self, s, build_id):
        """Crosswire: 14-gate engine accepts gamefile id as target."""
        payload = {"build_id": build_id, "kind": "gamefile",
                   "key": pytest.first_gf_id, "seed": 3}
        r = s.post(f"{GATES}/refine/run", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("error") is None, d
        assert d.get("passed") is True, d
        tgt = d.get("target") or {}
        assert tgt.get("kind") == "gamefile", tgt


# ── Update / Reorder / Delete ───────────────────────────────────────────────
class TestStageMutations:
    def test_update_title(self, s, build_id):
        r = s.put(f"{STAGES}/{build_id}/{pytest.boss_id}",
                  json={"title": "X"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["title"] == "X"

    def test_reorder_reverse(self, s, build_id):
        r = s.get(f"{STAGES}/{build_id}/list", timeout=15)
        ids = [x["id"] for x in r.json()["stages"]]
        reversed_ids = list(reversed(ids))
        r2 = s.post(f"{STAGES}/{build_id}/reorder",
                    json={"order": reversed_ids}, timeout=15)
        assert r2.status_code == 200 and r2.json().get("ok") is True
        r3 = s.get(f"{STAGES}/{build_id}/list", timeout=15)
        new_ids = [x["id"] for x in r3.json()["stages"]]
        new_seqs = [x["seq"] for x in r3.json()["stages"]]
        assert new_ids == reversed_ids, (new_ids, reversed_ids)
        assert new_seqs == [1, 2, 3, 4]

    def test_delete_and_resequence(self, s, build_id):
        # Delete the first stage in the (reversed) list
        r = s.get(f"{STAGES}/{build_id}/list", timeout=15)
        victim = r.json()["stages"][0]["id"]
        r2 = s.delete(f"{STAGES}/{build_id}/{victim}", timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("deleted") is True
        r3 = s.get(f"{STAGES}/{build_id}/list", timeout=15)
        rows = r3.json()["stages"]
        assert len(rows) == 3
        assert [x["seq"] for x in rows] == [1, 2, 3], "seq must be dense after delete"
        assert victim not in [x["id"] for x in rows]


# ── Iteration-118 regression: text-gamefile generators ─────────────────────
class TestIter118TextGamefile:
    def test_generators_count_10(self, s):
        r = s.get(f"{TGF}/generators", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] == 10, d
        assert len(d["generators"]) == 10

    def test_quest_from_text_no_500(self, s, build_id):
        payload = {"build_id": build_id,
                   "text": "A hero must retrieve the lost crown from the cursed crypt."}
        r = s.post(f"{TGF}/quest_from_text/generate",
                   json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("error") is None, d
        assert d.get("type") == "quest"
        # Must surface deterministic structure
        for f in ("id", "fields", "knobs", "brief"):
            assert f in d, f"missing field {f}"
        # `fields` may be dict (deterministic) or list — both are valid.
        assert d["fields"], "fields must be non-empty"
        assert d["knobs"], "knobs must be present"
        assert d["brief"], "brief must be present"
