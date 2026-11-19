"""Regression: Galaxy design survives the recovered GameForge source pipeline."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.context.galaxy_profile import (
    ARTIFACT_PATH, MATRIX_FIELDS, SCHEMA, attach_galaxy_profile, canonical_profile_bytes, normalise_galaxy_profile,
)
from skeleton.context.pipeline import GameForgeRun


def profile():
    config = {
        "title": "Custody test", "genre": "racing", "narrative_phases": {"prelude": {"count": 4}},
        "extra_params": {"music_variety": 9}, "style_params": {"graphic_style": "pixel_art"},
    }
    config.update({field: {"kickoff": {"count": 5}} for field in MATRIX_FIELDS})
    config["mechanics_matrix"]["gunplay"] = {"count": 1}
    return {"schema": SCHEMA, "config": config}


def test_full_profile_is_sealed_and_applies_supported_mechanics():
    full = profile()
    before = copy.deepcopy(full)
    result = GameForgeRun().execute("An original extraction game", era="extraction_now",
                                    archetype="extraction", galaxy_profile=full)
    assert result["succeeded"], result.get("run")
    assert full == before
    assert json.loads(result["files"][ARTIFACT_PATH]) == before
    receipt = result["galaxy_profile"]
    assert receipt["emitted"] is True and receipt["matrices"] == 14
    assert receipt["sha256"] == hashlib.sha256(canonical_profile_bytes(before)).hexdigest()
    assert result["source_manifest"] is not None
    assert ARTIFACT_PATH in result["source_manifest"]["files"]
    assert result["build_plan"]["spawn_weapon"] is True
    assert "mechanics_matrix.gunplay.count" in result["galaxy_mechanics"]["supported_inputs"]


def test_invalid_profile_rejected_before_pipeline():
    for key in ("narrative_phases", "extra_params", "style_params", "world_matrix"):
        full = profile()
        full["config"].pop(key)
        with pytest.raises(ValueError):
            normalise_galaxy_profile(full)
        with pytest.raises(ValueError):
            GameForgeRun().execute("An original game", galaxy_profile=full)


def test_absent_profile_does_not_create_implicit_authoring_artifact():
    result = GameForgeRun().execute("An original extraction game", era="extraction_now",
                                    archetype="extraction")
    assert result["succeeded"]
    assert ARTIFACT_PATH not in result["files"]
    assert "galaxy_profile" not in result


def test_profile_rejects_aggregate_escaped_budget_and_invalid_unicode():
    full = profile()
    full["config"]["large"] = ["界" * 12_000] * 10
    with pytest.raises(ValueError, match="600KB"):
        normalise_galaxy_profile(full)
    full = profile()
    full["config"]["bad"] = "\ud800"
    with pytest.raises(ValueError, match="Unicode"):
        normalise_galaxy_profile(full)


def test_profile_rejects_shared_wide_graph_before_semantic_validation():
    full = profile()
    full["config"]["wide"] = [[0] * 4096] * 7
    with pytest.raises(ValueError, match="complexity"):
        normalise_galaxy_profile(full)


def test_profile_artifact_rejects_case_insensitive_path_collision():
    from skeleton.context.galaxy_profile import attach_galaxy_profile
    with pytest.raises(ValueError, match="collision"):
        attach_galaxy_profile({ARTIFACT_PATH.upper(): "existing"}, profile())


def test_profile_preserves_extra_nested_controls_and_canonical_digest():
    full = profile()
    full["config"]["extra_params"].update({
        "production": {"physics": 5},
        "platforms": ["linux", "windows"],
        "languages": ["norwegian"],
    })
    detached = normalise_galaxy_profile(full)
    original = canonical_profile_bytes(detached)
    full["config"]["extra_params"]["production"]["physics"] = 99
    assert canonical_profile_bytes(detached) == original


@pytest.mark.parametrize("value", [float(2**53), -float(2**53), 1e100, -1e100])
def test_profile_rejects_float_outside_client_safe_numeric_range(value):
    full = profile()
    full["config"]["extra_params"]["numeric"] = value
    with pytest.raises(ValueError, match="unsafe Galaxy number"):
        normalise_galaxy_profile(full)
    from skeleton.ai.runtime.context.galaxy_profile import normalise_galaxy_profile as mirrored
    with pytest.raises(ValueError, match="unsafe Galaxy number"):
        mirrored(full)


def test_profile_accepts_safe_fractional_and_boundary_numbers():
    full = profile()
    full["config"]["extra_params"].update({"fractional": 0.125, "boundary": float(2**53 - 1)})
    assert normalise_galaxy_profile(full) == full


@pytest.mark.parametrize("mode,matrix,phase,dial,axis", [
    ("extraction", "world_matrix", "volcanic", "complexity", "risk"),
    ("combat_loop", "mechanics_matrix", "melee", "complexity", "lethality"),
    ("pipeline", "mechanics_matrix", "building", "count", "grind"),
    ("puzzle", "mechanics_matrix", "puzzle", "complexity", "opacity"),
    ("racing", "mechanics_matrix", "driving", "count", "grind"),
    ("survival", "world_matrix", "desert", "complexity", "scarcity"),
    ("stealth", "mechanics_matrix", "stealth", "complexity", "risk"),
    ("crafting", "mechanics_matrix", "parkour", "complexity", "tempo"),
])
def test_galaxy_controls_change_real_native_source(mode, matrix, phase, dial, axis):
    from skeleton.context.galaxy_profile import compile_galaxy_playable_axes, seal_galaxy_playable_controls
    from skeleton.forge.archetype_content import archetype_files, verify_archetype_content
    raw = profile()
    raw["config"][matrix][phase] = {dial: 1000}
    admitted = normalise_galaxy_profile(raw)
    baseline = archetype_files(mode)
    effective, receipt = compile_galaxy_playable_axes(admitted, mode, {})
    assert effective[axis] == 1.0
    generated = archetype_files(mode, operator_axes=effective)
    assert generated != baseline
    assert verify_archetype_content(generated, mode, operator_axes=effective)
    sealed, doc = seal_galaxy_playable_controls(attach_galaxy_profile(generated, admitted), receipt)
    assert doc["axes"][0]["authority"] == "galaxy_matrix"
    assert doc["native_execution_qualified"] is False
    for path, digest in doc["native_sources"].items():
        assert digest == hashlib.sha256(sealed[path].encode()).hexdigest()


def test_galaxy_control_precedence_and_max_vote_are_deterministic():
    from skeleton.context.galaxy_profile import compile_galaxy_playable_axes
    from skeleton.ai.runtime.context.galaxy_profile import compile_galaxy_playable_axes as mirrored
    raw = profile()
    raw["config"]["world_matrix"].update(volcanic={"complexity": 900}, wasteland={"complexity": 600})
    original = copy.deepcopy(raw)
    effective, receipt = compile_galaxy_playable_axes(raw, "extraction", {"risk": 0.0, "tempo": 0.42})
    assert effective == {"risk": 0.0, "tempo": 0.42}
    assert receipt["axes"] == [{
        "axis": "risk", "requested": 0.9, "effective": 0.0, "authority": "forge_override",
        "sources": [{"path": "world_matrix.volcanic.complexity", "value": 900},
                    {"path": "world_matrix.wasteland.complexity", "value": 600}],
    }]
    assert mirrored(raw, "extraction", {"risk": 0.0, "tempo": 0.42}) == (effective, receipt)
    assert raw == original


def test_galaxy_controls_zero_and_unmapped_data_do_not_change_playable_axes():
    from skeleton.context.galaxy_profile import compile_galaxy_playable_axes
    raw = profile()
    raw["config"]["mechanics_matrix"]["parkour"] = {"complexity": 0}
    raw["config"]["audio_matrix"]["music"] = {"depth": 100}
    axes, receipt = compile_galaxy_playable_axes(raw, "crafting", {})
    assert axes == {} and receipt["axes"] == []
    assert receipt["unmapped_matrix_dials"] == receipt["active_matrix_dials"]
    assert compile_galaxy_playable_axes(None, "crafting", {"tempo": 0.5}) == ({"tempo": 0.5}, None)


def test_galaxy_playable_receipt_is_in_final_source_manifest():
    from skeleton.context.galaxy_profile import PLAYABLE_RECEIPT_PATH
    raw = profile()
    raw["config"]["mechanics_matrix"]["driving"] = {"count": 1000, "complexity": 800}
    result = GameForgeRun().execute(
        "An original extraction world with a racing scene", era="extraction_now",
        archetype="extraction", playable_content=True, playable_archetype="racing",
        galaxy_profile=raw, operator_axes={"risk": 0.0},
    )
    assert result["succeeded"], result.get("run")
    doc = result["galaxy_playable_controls"]
    assert json.loads(result["files"][PLAYABLE_RECEIPT_PATH]) == doc
    assert PLAYABLE_RECEIPT_PATH in result["source_manifest"]["files"]
    assert doc["effective_axes"] == {"grind": 1.0, "risk": 0.0}
    assert result["playable_mechanics"]["applied_axes"] == {"grind": 1.0, "risk": 0.0}
    assert "const GOAL_LAPS := 4" in result["files"]["scripts/archetypes/racing/core_loop.gd"]
    for path, digest in doc["native_sources"].items():
        assert digest == hashlib.sha256(result["files"][path].encode()).hexdigest()


def test_galaxy_playable_receipt_refuses_collision_or_missing_native_source():
    from skeleton.context.galaxy_profile import (
        PLAYABLE_RECEIPT_PATH, compile_galaxy_playable_axes, seal_galaxy_playable_controls,
    )
    from skeleton.forge.archetype_content import archetype_files
    axes, receipt = compile_galaxy_playable_axes(profile(), "racing", {})
    files = archetype_files("racing", operator_axes=axes)
    with pytest.raises(ValueError, match="collision"):
        seal_galaxy_playable_controls({**files, PLAYABLE_RECEIPT_PATH.upper(): "existing"}, receipt)
    files.pop("scripts/archetypes/racing/core_loop.gd")
    with pytest.raises(ValueError, match="missing"):
        seal_galaxy_playable_controls(files, receipt)


@pytest.mark.parametrize("mode,constant,original", [
    ("puzzle", "USE_RADIUS", 18.0), ("racing", "LAP_RADIUS", 24.0),
    ("survival", "PICKUP_RADIUS", 19.0), ("stealth", "USE_RADIUS", 18.0),
    ("crafting", "USE_RADIUS", 19.0),
])
def test_expanded_prototype_interaction_range_is_effective(mode, constant, original):
    from skeleton.forge.archetype_content import archetype_files, verify_archetype_content
    from skeleton.forge.playable_tuning import SOURCE_PATH
    baseline = archetype_files(mode)
    for value, scale in ((0.0, 0.75), (1.0, 1.25)):
        axes = {"agency": value}
        result = archetype_files(mode, operator_axes=axes)
        loop = result[f"scripts/archetypes/{mode}/core_loop.gd"]
        assert f"const {constant} := {original * scale:.2f}" in loop
        assert json.loads(result[SOURCE_PATH])["applied"][f"{mode}.interaction_radius"] == round(original * scale, 2)
        assert verify_archetype_content(result, mode, operator_axes=axes)
        assert result != baseline


@pytest.mark.parametrize("mode,name", [("puzzle", "switches"), ("survival", "supplies"), ("crafting", "materials")])
@pytest.mark.parametrize("value,count", [(0.0, 2), (0.5, 4), (1.0, 6)])
def test_expanded_objective_routes_have_exact_bounded_cardinality(mode, name, value, count):
    import re
    from skeleton.forge.archetype_content import archetype_files
    from skeleton.forge.playable_tuning import SOURCE_PATH
    result = archetype_files(mode, operator_axes={"grind": value})
    loop = result[f"scripts/archetypes/{mode}/core_loop.gd"]
    points = re.search(r"var " + name + r": Array\[Vector2\] = \[(.*?)\]", loop, re.S).group(1)
    assert points.count("Vector2(") == count
    assert json.loads(result[SOURCE_PATH])["applied"][f"{mode}.{name}_required"] == count
    if mode == "crafting":
        assert f"crafted = collected == {count}" in loop
        assert f"Materials %d/{count}" in loop
    elif mode == "survival":
        assert f"Supplies %d/{count}" in loop


def test_crafting_galaxy_material_budget_is_real_not_metadata():
    from skeleton.context.galaxy_profile import compile_galaxy_playable_axes
    from skeleton.forge.archetype_content import archetype_files
    raw = profile()
    raw["config"]["mechanics_matrix"]["crafting"] = {"count": 1000, "intricacy": 800}
    axes, receipt = compile_galaxy_playable_axes(raw, "crafting", {})
    assert axes == {"agency": 0.8, "grind": 1.0}
    files = archetype_files("crafting", operator_axes=axes)
    assert "crafted = collected == 6" in files["scripts/archetypes/crafting/core_loop.gd"]
    assert receipt["mapped_matrix_dials"] == 2


@pytest.mark.parametrize("damage", ["digest", "counts", "vote", "authority", "operator", "extra", "profile", "noncanonical", "missing"])
def test_galaxy_seal_rejects_unbound_authored_control_receipts(damage):
    from skeleton.context.galaxy_profile import compile_galaxy_playable_axes, seal_galaxy_playable_controls
    from skeleton.forge.archetype_content import archetype_files
    raw = profile()
    raw["config"]["mechanics_matrix"]["driving"] = {"count": 1000}
    admitted = normalise_galaxy_profile(raw)
    overrides = {"grind": 0.0}
    axes, receipt = compile_galaxy_playable_axes(admitted, "racing", overrides)
    files = attach_galaxy_profile(archetype_files("racing", operator_axes=axes), admitted)
    if damage == "digest":
        receipt["profile_sha256"] = "f" * 64
    elif damage == "counts":
        receipt["active_matrix_dials"] += 1
    elif damage == "vote":
        row = next(row for row in receipt["axes"] if row["axis"] == "grind")
        row["sources"][0]["value"] = 500
    elif damage == "authority":
        row = next(row for row in receipt["axes"] if row["axis"] == "grind")
        row["authority"] = "galaxy_matrix"
    elif damage == "operator":
        overrides = {"grind": 1.0}
    elif damage == "extra":
        receipt["source_verified"] = True
    elif damage == "profile":
        alternate = copy.deepcopy(admitted)
        alternate["config"]["title"] = "Different project"
        files = attach_galaxy_profile({key: value for key, value in files.items() if key != ARTIFACT_PATH}, alternate)
    elif damage == "noncanonical":
        files[ARTIFACT_PATH] = " " + files[ARTIFACT_PATH]
    elif damage == "missing":
        del files[ARTIFACT_PATH]
    with pytest.raises(ValueError, match="profile|receipt"):
        seal_galaxy_playable_controls(files, receipt, operator_axes=overrides)


def test_galaxy_seal_reconstructs_consistent_offline_override_receipt():
    from skeleton.context.galaxy_profile import compile_galaxy_playable_axes, seal_galaxy_playable_controls
    from skeleton.forge.archetype_content import archetype_files
    raw = profile()
    raw["config"]["mechanics_matrix"]["driving"] = {"count": 900}
    admitted = normalise_galaxy_profile(raw)
    overrides = {"grind": 0.0, "tempo": 0.37}
    axes, receipt = compile_galaxy_playable_axes(admitted, "racing", overrides)
    files = attach_galaxy_profile(archetype_files("racing", operator_axes=axes), admitted)
    assert seal_galaxy_playable_controls(files, receipt, operator_axes=overrides) == seal_galaxy_playable_controls(files, receipt)
