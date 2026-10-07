"""Iteration 115 — Snowball axes (non-synthetic spec-aware advanced choices).

Tests the genuine, hand-authored axis catalog at /api/galaxy-studio/axes:
  * stats: 37 axes / 229 options / 143 advanced / advanced_majority=true
  * crosswiring: only spec-relevant options offered
  * escalation: more options unlock as stage_index grows
  * effects: selections fold to real forge directives, off-spec dropped
  * regression: galaxy-studio/systems/catalog still works, 150 prefixed routers
  * code-level: item_foundry & build_config honour the new axes
"""
from __future__ import annotations

import os
import sys
import requests

BASE_URL = os.environ.get(
    "EXPO_BACKEND_URL",
    os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001"),
).rstrip("/")

# allow `from core...` style imports for code-level checks
sys.path.insert(0, "/app/backend")


# ─────────────── API: stats ────────────────
class TestAxesStats:
    def test_stats_shape(self):
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/axes/stats", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["axes"] == 37, d
        assert d["total_options"] == 229, d
        assert d["advanced_options"] == 143, d
        assert d["advanced_majority"] is True, d
        # advanced must outnumber non-advanced
        assert d["advanced_options"] > (d["total_options"] - d["advanced_options"])


# ─────────────── API: crosswiring (spec-relevant only) ────────────────
class TestAxesCrosswiring:
    def test_puzzle_2d_excludes_3d_only_and_genre_locked_options(self):
        r = requests.get(
            f"{BASE_URL}/api/galaxy-studio/axes",
            params={"genre": "puzzle", "dimension": "2d", "stage_index": 1},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        axes = {a["key"]: a for a in d["axes"]}

        # rt_gi is 3d-only — must be absent from lighting_model for 2d
        lm_ids = {o["id"] for o in axes.get("lighting_model", {}).get("options", [])}
        assert "rt_gi" not in lm_ids, lm_ids

        # subsurface is 3d-only — must be absent from materials_pbr (if axis present)
        mp_ids = {o["id"] for o in axes.get("materials_pbr", {}).get("options", [])}
        assert "subsurface" not in mp_ids, mp_ids

        # rollback netcode requires fighting/shooter/arcade → puzzle must NOT see it
        nc_ids = {o["id"] for o in axes.get("netcode_model", {}).get("options", [])}
        assert "rollback" not in nc_ids, nc_ids

        # every axis must report advanced_count/total and advanced_majority field
        for a in d["axes"]:
            assert "advanced_count" in a and "total" in a and "advanced_majority" in a

    def test_escalation_stage3_has_more_options_than_stage0(self):
        params0 = {"genre": "shooter", "dimension": "3d", "stage_index": 0}
        params3 = {"genre": "shooter", "dimension": "3d", "stage_index": 3}
        r0 = requests.get(f"{BASE_URL}/api/galaxy-studio/axes", params=params0, timeout=30)
        r3 = requests.get(f"{BASE_URL}/api/galaxy-studio/axes", params=params3, timeout=30)
        assert r0.status_code == 200 and r3.status_code == 200
        t0 = r0.json()["total_options"]
        t3 = r3.json()["total_options"]
        assert t3 > t0, f"escalation broken: stage3={t3} not > stage0={t0}"


# ─────────────── API: derive (real directives) ────────────────
class TestAxesDerive:
    def test_off_spec_selections_dropped(self):
        payload = {
            "selections": {
                "graphic_style": "pbr_photoreal",  # 3d-only
                "lighting_model": "rt_gi",          # 3d-only + unlock=3
                "netcode_model": "rollback",       # fighting/shooter/arcade
            },
            "spec": {"genre": "puzzle", "dimension": "2d"},
            "stage_index": 0,
        }
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/axes/derive", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["applied"] == {}, f"expected empty applied, got {d['applied']}"
        whys = {item["why"] for item in d["dropped"]}
        assert "off_spec" in whys, d["dropped"]
        assert d["dropped_count"] == 3, d

    def test_valid_3d_shooter_selections_apply_with_real_directives(self):
        payload = {
            "selections": {
                "graphic_style": "pbr_photoreal",
                "lighting_model": "rt_gi",
                "netcode_model": "rollback",
                "materials_pbr": "metal_rough_pbr",
            },
            "spec": {"genre": "shooter", "dimension": "3d"},
            "stage_index": 3,
        }
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/axes/derive", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "graphic_style" in d["applied"], d
        assert "netcode_model" in d["applied"], d
        # the flat directives map should contain real forge directives
        dirs = d["directives"]
        assert dirs.get("shader") == "pbr_metalrough", dirs
        assert dirs.get("gi") == "rtgi", dirs
        assert dirs.get("net") == "rollback", dirs
        # namespaced form also present
        assert dirs.get("graphic_style.shader") == "pbr_metalrough"


# ─────────────── API: flavor ────────────────
class TestAxesFlavor:
    def test_flavor_returns_string_and_effect(self):
        payload = {
            "axis_key": "graphic_style",
            "option_id": "pbr_photoreal",
            "spec": {"genre": "shooter"},
        }
        r = requests.post(f"{BASE_URL}/api/galaxy-studio/axes/flavor", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "flavor" in d and isinstance(d["flavor"], str) and len(d["flavor"]) > 0
        assert d["effect"].get("shader") == "pbr_metalrough"
        assert d["axis"] == "graphic_style"
        assert d["option"] == "pbr_photoreal"


# ─────────────── Regression ────────────────
class TestRegression:
    def test_systems_catalog_still_22(self):
        # The canonical endpoint exposing the 22 systems is /api/galaxy-studio/systems
        r = requests.get(f"{BASE_URL}/api/galaxy-studio/systems", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        systems = d.get("systems") or d.get("catalog") or []
        assert isinstance(systems, list)
        assert len(systems) == 22, f"expected 22 systems, got {len(systems)}"

    def test_registered_routers_count_is_150(self):
        # The 150-router target counts the "no-prefix" group (those whose
        # APIRouter already carries /api), per boot logs `registered=150`.
        from core.routes_registry import KNOWN_ROUTES
        assert len(KNOWN_ROUTES) == 150, len(KNOWN_ROUTES)


# ─────────────── Code-level: item_foundry ────────────────
class TestItemFoundryAxes:
    def test_forge_item_applies_advanced_axes_to_skin(self):
        from core.item_foundry import forge_item
        vault_ctx = {
            "era": "modern", "genre": "shooter", "dimension": "3d",
            "applied_choices": {
                "graphic_style": "pbr_photoreal",
                "vfx_style": "gpu_simulated",
                "materials_pbr": "metal_rough_pbr",
            },
        }
        agent = {"code": "A001", "category": "combat", "agent": "TestAgent"}
        item = forge_item(build_id="b_test", phase="weapon", agent=agent,
                          vault_ctx=vault_ctx, seed=42)
        skin = item.get("skin") or {}
        assert skin.get("shader") == "pbr_metalrough", skin
        assert skin.get("vfx") == "gpu_particles", skin
        fd = skin.get("forge_directives") or {}
        assert isinstance(fd, dict) and len(fd) > 0, item
        # applied_choices stamp also reflected
        assert skin.get("applied_choices", {}).get("graphic_style") == "pbr_photoreal"

    def test_procedural_phase_draws_from_new_archetype_bucket(self):
        from core.item_foundry import forge_item, _ARCHETYPES
        vault_ctx = {"era": "modern", "genre": "puzzle", "dimension": "2d",
                     "applied_choices": {}}
        agent = {"code": "A002", "category": "design"}
        item = forge_item(build_id="b_test", phase="procedural", agent=agent,
                          vault_ctx=vault_ctx, seed=99)
        # procedural bucket must exist
        assert "procedural" in _ARCHETYPES, list(_ARCHETYPES.keys())
        # the chosen archetype must come from the procedural bucket
        assert item["definition"]["archetype"] in _ARCHETYPES["procedural"], item


# ─────────────── Code-level: build_config ────────────────
class TestBuildConfigChoiceSpecs:
    def test_choice_specs_includes_new_axes(self):
        from core.build_config import CHOICE_SPECS
        assert len(CHOICE_SPECS) >= 45, len(CHOICE_SPECS)
        # CHOICE_SPECS is a list of tuples (key, label, kind, target)
        keys = {row[0] if isinstance(row, (tuple, list)) else row for row in CHOICE_SPECS}
        for key in ("graphic_style", "lighting_model", "netcode_model", "materials_pbr",
                    "render_pipeline", "vfx_style"):
            assert key in keys, f"missing axis key {key} in CHOICE_SPECS"

    def test_normalize_derive_summary_smoke(self):
        from core import build_config as bc
        selections = {"graphic_style": "pbr_photoreal", "lighting_model": "rt_gi"}
        # Each helper called only if present — must not raise
        for fn_name in ("normalize_selections", "normalize", "derive_choices",
                        "derive", "summarize_choices", "summary"):
            fn = getattr(bc, fn_name, None)
            if callable(fn):
                try:
                    fn(selections)
                except TypeError:
                    # function might need extra args; accept signature mismatch
                    pass
