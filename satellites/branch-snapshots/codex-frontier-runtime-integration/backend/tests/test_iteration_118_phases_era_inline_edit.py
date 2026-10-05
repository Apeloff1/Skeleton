"""Iteration 118 — era file_count_standard, /snowball/{pid}/phases crosswire,
era scaling on the 100-phase build, /stages inline edit + build."""
from __future__ import annotations

import os
import uuid
import requests

BASE = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or os.environ.get("EXPO_BACKEND_URL")
        or "https://player-retention.preview.emergentagent.com").rstrip("/")
PID = "8999ecfb0f9b4ca599f3cf83c1178879"


# ── era catalog: every era has file_count_standard and values match spec ──
class TestEras:
    EXPECTED = {
        "8bit": 200, "16bit": 1200, "early3d": 3500, "64bit": 12000,
        "earlyhd": 45000, "modern": 250000, "nextgen": 600000,
    }

    def test_eras_have_file_count_standard(self):
        r = requests.get(f"{BASE}/api/galaxy-studio/eras", timeout=30)
        assert r.status_code == 200, r.text
        eras = r.json()
        # Could be list or dict; normalize to a dict by key
        if isinstance(eras, dict) and "eras" in eras:
            eras = eras["eras"]
        if isinstance(eras, list):
            by_key = {e["key"]: e for e in eras}
        else:
            by_key = eras
        for key, val in self.EXPECTED.items():
            assert key in by_key, f"era {key} missing from catalog"
            assert by_key[key].get("file_count_standard") == val, (
                f"era {key}: expected file_count_standard={val}, "
                f"got {by_key[key].get('file_count_standard')}")

    def test_eras_ascending_file_counts(self):
        r = requests.get(f"{BASE}/api/galaxy-studio/eras", timeout=30)
        eras = r.json()
        if isinstance(eras, dict) and "eras" in eras:
            eras = eras["eras"]
        if isinstance(eras, list):
            ordered = sorted(eras, key=lambda e: e.get("order", 0))
        else:
            ordered = sorted(eras.values(), key=lambda e: e.get("order", 0))
        counts = [e["file_count_standard"] for e in ordered]
        assert counts == sorted(counts), f"counts not monotonic: {counts}"


# ── /api/snowball/{pid}/phases crosswire endpoint ──
class TestSnowballPhases:
    def test_modern_phases(self):
        r = requests.get(f"{BASE}/api/snowball/{PID}/phases",
                         params={"era": "modern"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "error" not in d, d
        assert d["phases_total"] == 100
        assert d["bands_total"] == 8
        fp = d.get("file_plan")
        assert fp and fp["file_target"] == 250000
        # sum of band file_targets ≈ era target (rounding tolerated)
        band_sum = sum(b["file_target"] for b in fp["bands"])
        assert abs(band_sum - fp["file_target"]) <= 8, (
            f"band sum {band_sum} vs target {fp['file_target']}")
        # produced_pct consistent
        produced = fp["files_produced"]
        passed_bands = [b for b in d["bands"] if b["passed"]]
        produced_check = sum(b["file_target"] for b in passed_bands)
        assert produced == produced_check
        assert "eras" in d and isinstance(d["eras"], list) and len(d["eras"]) == 7

    def test_era_scaling_8bit(self):
        r = requests.get(f"{BASE}/api/snowball/{PID}/phases",
                         params={"era": "8bit"}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["file_plan"]["file_target"] == 200

    def test_era_scaling_nextgen(self):
        r = requests.get(f"{BASE}/api/snowball/{PID}/phases",
                         params={"era": "nextgen"}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["file_plan"]["file_target"] == 600000


# ── /stages inline edit backend ──
class TestStageInlineEdit:
    def test_add_update_build_delete(self):
        bid = f"TEST_inline_{uuid.uuid4().hex[:10]}"
        # add a boss stage
        r = requests.post(f"{BASE}/api/galaxy-studio/stages/{bid}/add",
                          json={"type": "boss"}, timeout=30)
        assert r.status_code == 200, r.text
        stg = r.json()
        assert "id" in stg, stg
        sid = stg["id"]
        # update title + note
        upd = requests.put(
            f"{BASE}/api/galaxy-studio/stages/{bid}/{sid}",
            json={"title": "The Drowned Cathedral",
                  "note": "flooded gothic boss arena with rising tide phases"},
            timeout=30)
        assert upd.status_code == 200, upd.text
        ud = upd.json()
        assert ud.get("title") == "The Drowned Cathedral"
        assert "flooded gothic" in ud.get("note", "")
        # build
        bld = requests.post(
            f"{BASE}/api/galaxy-studio/stages/{bid}/{sid}/build",
            json={"enrich": False}, timeout=60)
        assert bld.status_code == 200, bld.text
        bd = bld.json()
        assert bd.get("ok") is True
        assert bd.get("gamefile_count") == 4, bd
        # cleanup
        d = requests.delete(f"{BASE}/api/galaxy-studio/stages/{bid}/{sid}",
                            timeout=30)
        assert d.status_code == 200
        assert d.json().get("deleted") is True
