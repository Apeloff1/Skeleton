"""Regression: Galaxy design survives the recovered GameForge source pipeline."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.context.galaxy_profile import (
    ARTIFACT_PATH, MATRIX_FIELDS, SCHEMA, canonical_profile_bytes, normalise_galaxy_profile,
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
