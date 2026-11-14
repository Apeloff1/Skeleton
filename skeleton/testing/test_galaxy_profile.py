"""Full Galaxy -> GameForge source-only validation, receipts and emission."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

import pytest

from skeleton.context.galaxy_profile import (
    ARTIFACT_PATH, MATRIX_FIELDS, SCHEMA,
    attach_galaxy_profile, canonical_profile_bytes, galaxy_profile_receipt,
    normalise_galaxy_profile,
)
from skeleton.forge.source_manifest import source_manifest


def sample():
    cfg = {
        "title": "North Star",
        "genre": "racing",
        "game_vision": "An original game with tight controls",
        "game_pace": "breakneck",
        "extra_params": {"music_variety": 8, "dialog_tree_depth": 7},
        "style_params": {"graphic_style": "pixel_art"},
        "narrative_phases": {"prelude": {"count": 5, "secrets": 8}},
    }
    for key in MATRIX_FIELDS:
        cfg[key] = {"kickoff": {"count": 9, "complexity": 5}}
    return {"schema": SCHEMA, "config": cfg}


def test_complete_profile_has_stable_receipt_and_project_artifact():
    profile = normalise_galaxy_profile(sample())
    a = galaxy_profile_receipt(profile)
    assert a["matrices"] == 14
    assert a["source"] == "galaxy_studio"
    assert a["artifact"] == ARTIFACT_PATH
    assert a["sha256"] == hashlib.sha256(canonical_profile_bytes(profile)).hexdigest()
    reordered = sample()
    reordered["config"] = dict(reversed(list(reordered["config"].items())))
    assert galaxy_profile_receipt(normalise_galaxy_profile(reordered)) == a
    files = attach_galaxy_profile({"project.godot": "[application]\n"}, profile)
    assert json.loads(files[ARTIFACT_PATH]) == profile
    manifest = source_manifest(files)
    assert ARTIFACT_PATH in manifest["files"]
    assert manifest["file_count"] == 2


def test_missing_or_invalid_source_profile_never_corrupts_project_files():
    assert attach_galaxy_profile({"project.godot": "hello"}, None) == {"project.godot": "hello"}
    profile = normalise_galaxy_profile(sample())
    with pytest.raises(ValueError, match="collision"):
        attach_galaxy_profile({"project.godot": "hello", ARTIFACT_PATH: "wrong"}, profile)


@pytest.mark.parametrize("bad", [
    None, float("nan"), float("inf"), True, {"bad": object()},
])
def test_fails_closed_for_non_json_values(bad):
    profile = sample()
    profile["config"]["extra_params"]["music_variety"] = bad
    if bad is None:  # nullable numeric extras are legal JSON, not active controls.
        assert normalise_galaxy_profile(profile)
    else:
        with pytest.raises(ValueError):
            normalise_galaxy_profile(profile)


def test_requires_exact_schema_and_all_fourteen_matrices():
    profile = sample()
    profile["schema"] = "unknown"
    with pytest.raises(ValueError, match="schema"):
        normalise_galaxy_profile(profile)
    profile = sample()
    del profile["config"]["unique_flair_matrix"]
    with pytest.raises(ValueError, match="matrix"):
        normalise_galaxy_profile(profile)


def test_nonfinite_nested_values_and_prototype_pollution_rejected():
    profile = sample()
    profile["config"]["mechanics_matrix"]["kickoff"]["count"] = math.inf
    with pytest.raises(ValueError):
        normalise_galaxy_profile(profile)
    profile = sample()
    profile["config"]["__proto__"] = {"admin": True}
    with pytest.raises(ValueError):
        normalise_galaxy_profile(profile)


def test_oversized_text_and_deep_or_dense_profiles_refused():
    profile = sample()
    profile["config"]["game_vision"] = "x" * 12_001
    with pytest.raises(ValueError):
        normalise_galaxy_profile(profile)
    profile = sample()
    profile["config"]["mechanics_matrix"]["kickoff"] = {
        str(i) if i else "axis": i for i in range(5000)
    }
    with pytest.raises(ValueError):
        normalise_galaxy_profile(profile)


def test_no_mutable_alias_is_returned():
    raw = sample()
    result = normalise_galaxy_profile(raw)
    raw["config"]["mechanics_matrix"]["kickoff"]["count"] = 123
    assert result["config"]["mechanics_matrix"]["kickoff"]["count"] == 9


def test_axes_must_be_in_range_and_phase_shapes_must_be_real():
    p = sample()
    p["config"]["art_matrix"]["kickoff"]["count"] = -1
    with pytest.raises(ValueError, match="axis"):
        normalise_galaxy_profile(p)
    p = sample()
    p["config"]["art_matrix"]["kickoff"]["count"] = 1001
    with pytest.raises(ValueError, match="axis"):
        normalise_galaxy_profile(p)
    p = sample()
    p["config"]["art_matrix"]["kickoff"] = []
    with pytest.raises(ValueError, match="axis"):
        normalise_galaxy_profile(p)


def test_live_emit_stage_carries_canonical_design_profile_without_code_change(monkeypatch):
    from skeleton.context import pipeline
    import skeleton.forge.gdscript_check as check
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr(check, "check_ok", lambda files: (True, []))
    original = {"project.godot": "config_version=5\n"}
    p = normalise_galaxy_profile(sample())
    ctx = {"era": "extraction_now", "target": "godot",
           "files": dict(original), "galaxy_profile": p,
           "playtest_mode": "off", "project_root": None}
    result = pipeline._stage_emit(ctx)
    assert result["emitted"] is True
    assert ctx["file_count"] == 2
    assert ctx["files"]["project.godot"] == original["project.godot"]
    assert json.loads(ctx["files"][ARTIFACT_PATH]) == p
    assert source_manifest(ctx["files"])["file_count"] == 2


def test_run_route_forwards_full_galaxy_profile_as_one_isolated_build_input(monkeypatch):
    from backend.routes.skeleton_gameforge import RunRequest, run
    from skeleton.context.pipeline import GameForgeRun
    seen = {}
    class Stub:
        def execute(self, vision, **options):
            seen["vision"] = vision
            seen["options"] = options
            return {"files": {"project.godot": "config_version=5\n"}, "succeeded": True}
    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    out = run(RunRequest(vision="A new original racing game", galaxy_profile=sample()))
    assert seen["vision"] == "A new original racing game"
    assert seen["options"]["galaxy_profile"] == sample()
    assert out["file_names"] == ["project.godot"]
    assert "files" not in out


def test_explicit_ranged_and_gunplay_matrix_changes_real_build_plan():
    from dataclasses import dataclass
    from skeleton.context.galaxy_profile import apply_galaxy_mechanics

    @dataclass(frozen=True)
    class Plan:
        spawn_weapon: bool
        notes: list[str]

    profile = sample()
    # 0 is the historical matrix default: no implicit weapon override.
    profile["config"]["mechanics_matrix"]["ranged"] = {"count": 0}
    baseline = normalise_galaxy_profile(profile)
    unchanged, receipt = apply_galaxy_mechanics(Plan(False, []), baseline)
    assert not unchanged.spawn_weapon
    assert receipt["supported_inputs"] == []
    assert receipt["applied"] == []

    profile["config"]["mechanics_matrix"]["ranged"]["count"] = 7
    profile["config"]["mechanics_matrix"]["gunplay"] = {"count": 3}
    explicit = normalise_galaxy_profile(profile)
    armed, receipt = apply_galaxy_mechanics(Plan(False, []), explicit)
    assert armed.spawn_weapon
    assert len(armed.notes) == 1
    assert receipt["supported_inputs"] == [
        "mechanics_matrix.gunplay.count", "mechanics_matrix.ranged.count",
    ]
    assert receipt["applied"] == [{
        "target": "build_plan.spawn_weapon", "value": True,
        "changed": True, "source": receipt["supported_inputs"],
    }]
    assert receipt["unmapped_matrix_dials"] == receipt["active_matrix_dials"] - 2
    already, seen = apply_galaxy_mechanics(Plan(True, ["kept"]), explicit)
    assert already.notes == ["kept"]
    assert not seen["applied"][0]["changed"]


def test_unsupported_matrix_dials_remain_preserved_without_fake_mechanics():
    from dataclasses import dataclass
    from skeleton.context.galaxy_profile import apply_galaxy_mechanics

    @dataclass(frozen=True)
    class Plan:
        spawn_weapon: bool = False
        notes: tuple[str, ...] = ()

    raw = sample()
    raw["config"]["world_matrix"]["forest"] = {"count": 100}
    profile = normalise_galaxy_profile(raw)
    plan, receipt = apply_galaxy_mechanics(Plan(), profile)
    assert not plan.spawn_weapon
    assert receipt["active_matrix_dials"] > 0
    assert receipt["unmapped_matrix_dials"] == receipt["active_matrix_dials"]
    assert receipt["applied"] == []



def test_historical_room_dials_reach_real_godot_room_distribution():
    from dataclasses import dataclass
    from skeleton.context.galaxy_profile import apply_galaxy_mechanics
    from skeleton.forge.eras import compile_era
    from skeleton.forge.godot_emit import emit_godot

    @dataclass(frozen=True)
    class Plan:
        spawn_weapon: bool = False
        room_bias: str = "balanced"
        notes: tuple[str, ...] = ()

    pack = compile_era("extraction_now")
    for matrix, feature, expected in (
        ("mechanics_matrix", "melee", "combat"),
        ("mechanics_matrix", "crafting", "loot"),
        ("world_matrix", "volcanic", "heat"),
    ):
        raw = sample()
        raw["config"][matrix][feature] = {"count": 7}
        plan, receipt = apply_galaxy_mechanics(Plan(), normalise_galaxy_profile(raw))
        assert plan.room_bias == expected
        assert receipt["applied"] == [{
            "target": "build_plan.room_bias", "value": expected,
            "changed": True, "source": [f"{matrix}.{feature}.count"],
        }]
        assert receipt["unmapped_matrix_dials"] == receipt["active_matrix_dials"] - 1
        emitted = emit_godot(pack, build_plan={
            "seed": "galaxy-historical-deterministic", "room_bias": plan.room_bias,
        })
        actual_plan = json.loads(emitted["data/build_plan.json"])
        assert actual_plan["room_bias"] == expected
        rooms = json.loads(emitted["data/rooms.json"])["rooms"]
        assert rooms[0]["kind"] == "spawn"
        assert rooms[-1]["kind"] == "extract"
        assert len(rooms) >= 3


def test_room_votes_choose_strongest_and_ties_use_stable_explicit_order():
    from dataclasses import dataclass
    from skeleton.context.galaxy_profile import apply_galaxy_mechanics

    @dataclass(frozen=True)
    class Plan:
        spawn_weapon: bool = False
        room_bias: str = "balanced"
        notes: tuple[str, ...] = ()

    raw = sample()
    raw["config"]["mechanics_matrix"]["melee"] = {"count": 2}
    raw["config"]["mechanics_matrix"]["forging"] = {"count": 8}
    raw["config"]["world_matrix"]["volcanic"] = {"count": 4}
    plan, receipt = apply_galaxy_mechanics(Plan(), normalise_galaxy_profile(raw))
    assert plan.room_bias == "loot"
    assert receipt["room_votes"] == {"combat": 2, "loot": 8, "heat": 4}
    assert receipt["unmapped_matrix_dials"] == receipt["active_matrix_dials"] - 3
    raw["config"]["mechanics_matrix"]["melee"]["count"] = 8
    plan, receipt = apply_galaxy_mechanics(Plan(), normalise_galaxy_profile(raw))
    assert plan.room_bias == "combat"
    assert receipt["room_votes"] == {"combat": 8, "loot": 8, "heat": 4}


def test_room_distribution_keeps_existing_build_when_creator_did_not_choose_it():
    from dataclasses import dataclass
    from skeleton.context.galaxy_profile import apply_galaxy_mechanics

    @dataclass(frozen=True)
    class Plan:
        spawn_weapon: bool = False
        room_bias: str = "heat"
        notes: tuple[str, ...] = ()

    raw = sample()
    raw["config"]["mechanics_matrix"]["tactical"] = {"count": 0}
    plan, receipt = apply_galaxy_mechanics(Plan(), normalise_galaxy_profile(raw))
    assert plan.room_bias == "heat"
    assert "room_votes" not in receipt
    assert receipt["applied"] == []
