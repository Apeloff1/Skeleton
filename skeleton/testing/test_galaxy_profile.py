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
