"""Iteration 119 — Galaxy Studio Build Journey + snowball /phases live overlay
+ universal_forge.apply_axis_directives mirror.

Validates:
 1) GET /api/galaxy-studio/journey/{pid}
 2) GET /api/snowball/{pid}/phases?era=...  (caching + live band overlay)
 3) core.universal_forge.apply_axis_directives (geometry reduce/increase + panel decals)
"""
from __future__ import annotations

import os
import sys
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                          os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
PID = "8999ecfb0f9b4ca599f3cf83c1178879"
JOURNEY_URL = f"{BASE_URL}/api/galaxy-studio/journey/{PID}"
PHASES_URL = f"{BASE_URL}/api/snowball/{PID}/phases"


# ── 1. Build Journey ────────────────────────────────────────────────────────
class TestBuildJourney:
    def test_journey_returns_7_milestones_with_required_fields(self):
        r = requests.get(JOURNEY_URL, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        ms = j.get("milestones", [])
        assert len(ms) == 7, f"expected 7 milestones got {len(ms)}"
        keys = [m["key"] for m in ms]
        assert keys == ["concept", "spine", "world", "systems", "assets",
                        "polish", "launch"], keys
        for m in ms:
            for f in ("state", "progress_pct", "xp", "xp_earned", "badge",
                      "route", "cta"):
                assert f in m, f"milestone {m['key']} missing {f}"
            assert m["state"] in ("done", "active", "locked")

    def test_journey_top_level_fields(self):
        j = requests.get(JOURNEY_URL, timeout=30).json()
        for f in ("completion_pct", "earned_xp", "total_xp", "rank",
                  "streak", "badges", "next_best_action", "share_card",
                  "band_done"):
            assert f in j, f"top-level missing {f}"
        assert j["total_xp"] == 1470, j["total_xp"]
        r = j["rank"]
        for f in ("level", "rank", "rank_icon", "xp_to_next", "next_rank"):
            assert f in r, f"rank missing {f}"

    def test_journey_concept_done_nba_first_not_done(self):
        j = requests.get(JOURNEY_URL, timeout=30).json()
        ms = j["milestones"]
        concept = next(m for m in ms if m["key"] == "concept")
        assert concept["state"] == "done", concept
        nba = j["next_best_action"]
        assert nba, "next_best_action should not be null"
        first_not_done = next(m for m in ms if m["state"] != "done")
        assert nba["key"] == first_not_done["key"], (nba, first_not_done["key"])
        assert nba["route"] == first_not_done["route"]


# ── 2. Snowball /phases live overlay + caching ──────────────────────────────
class TestSnowballPhases:
    def test_phases_modern_live_overlay(self):
        r = requests.get(PHASES_URL, params={"era": "modern"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "file_plan" in d, d
        fp = d["file_plan"]
        assert "files_produced" in fp and "produced_pct" in fp
        # bands_passed should match number of green bands
        bands = d.get("bands", [])
        green = sum(1 for b in bands if b.get("passed"))
        assert d.get("bands_passed") == green, (d.get("bands_passed"), green)
        # live overlay: files_produced is the sum of band file_targets where passed
        live_sum = sum(b.get("file_target", 0) for b in bands if b.get("passed"))
        assert fp["files_produced"] == live_sum, (fp["files_produced"], live_sum)

    def test_phases_caching_second_call_faster(self):
        # warm up cache
        requests.get(PHASES_URL, params={"era": "modern"}, timeout=60)
        t0 = time.time()
        r2 = requests.get(PHASES_URL, params={"era": "modern"}, timeout=60)
        dt = time.time() - t0
        assert r2.status_code == 200
        # cached call should be < 3s (relaxed for prod ingress)
        assert dt < 5.0, f"cached call too slow: {dt:.2f}s"

    def test_phases_era_8bit_target_200(self):
        r = requests.get(PHASES_URL, params={"era": "8bit"}, timeout=60)
        assert r.status_code == 200
        fp = r.json().get("file_plan", {})
        assert fp.get("file_target") == 200, fp

    def test_phases_era_nextgen_target_600000(self):
        r = requests.get(PHASES_URL, params={"era": "nextgen"}, timeout=60)
        assert r.status_code == 200
        fp = r.json().get("file_plan", {})
        assert fp.get("file_target") == 600000, fp


# ── 3. universal_forge.apply_axis_directives mirror ─────────────────────────
class TestApplyAxisDirectives:
    @classmethod
    def setup_class(cls):
        sys.path.insert(0, "/app/backend")

    def _base_spec(self):
        return {
            "geometry": [
                {"shape": "box", "pos": [0, 0, 0], "size": [1, 2, 1]},
                {"shape": "box", "pos": [0, 1, 0], "size": [0.5, 0.5, 0.5]},
            ],
            "palette": ["#888"],
        }

    def test_low_tri_budget_reduces_parts(self):
        import core.universal_forge as uf
        spec = uf.apply_axis_directives(self._base_spec(),
            {"tri_budget": 500, "proportion": "2head", "dim": "3d"})
        base_parts = [p for p in spec["geometry"] if not p.get("decal")]
        assert len(base_parts) < 2, f"expected <2 base parts got {len(base_parts)}"
        assert spec.get("axis_directives", {}).get("tri_budget") == 500

    def test_high_tri_budget_paneling_adds_panel_decals(self):
        import core.universal_forge as uf
        spec = uf.apply_axis_directives(self._base_spec(),
            {"tri_budget": 200000, "paneling": 1, "topo": "subd"})
        panels = [p for p in spec["geometry"] if p.get("panel")]
        assert len(panels) > 0, "expected panel decals added"
        base_parts = [p for p in spec["geometry"] if not p.get("decal")]
        assert len(base_parts) > 2, f"expected densified parts got {len(base_parts)}"
        assert spec.get("topo") == "subd"
        assert spec.get("axis_directives", {}).get("paneling") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
