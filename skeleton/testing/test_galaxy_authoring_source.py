"""Exact source and fail-closed transport of the original Galaxy matrices."""
from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.forge.galaxy_authoring import (
    GalaxyAuthoringError, MATRIX_FIELDS, PROFILE_PATH, PROFILE_SCHEMA,
    RECEIPT_SCHEMA, authored_source, normalise_galaxy_authoring,
)


def _profile():
    source = {
        "title": "A user's original frontier game",
        "genre": "racing",
        "game_vision": "A story with 100 chapters and several endings",
        "narrative_phases": {"prelude": {"count": 2, "secrets": 5}},
        "extra_params": {"quest_variety": 42},
        "style_params": {"graphic_style": "painted"},
        "game_pace": "action_packed",
    }
    for name in MATRIX_FIELDS:
        source[name] = {"kickoff": {"count": 12, "complexity": 4}}
    return {"schema": PROFILE_SCHEMA, "config": source}


def test_full_original_source_survives_without_implicit_design_loss():
    authored = _profile()
    stable, receipt = authored_source(authored)
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["matrix_count"] == 14
    assert receipt["path"] == PROFILE_PATH
    assert receipt["native_gameplay_qualified"] is False
    assert receipt["full_original_authoring_preserved"] is True
    assert receipt["sha256"] == hashlib.sha256(stable.encode()).hexdigest()
    assert receipt["byte_count"] == len(stable.encode())
    restored = json.loads(stable)
    assert restored == authored
    assert stable == authored_source(restored)[0]


def test_rejected_profile_never_mutates_caller_data():
    source = _profile()
    original = json.dumps(source, sort_keys=True)
    copy = normalise_galaxy_authoring(source)
    copy["config"]["title"] = "changed"
    assert json.dumps(source, sort_keys=True) == original
    assert source["config"]["title"] != "changed"


@pytest.mark.parametrize("damage", [
    lambda p: p.pop("config"),
    lambda p: p.update(schema="different"),
    lambda p: p.update(extra=True),
    lambda p: p["config"].pop("art_matrix"),
    lambda p: p["config"].update(title=""),
    lambda p: p["config"].update(genre=""),
    lambda p: p["config"].update(extra_params=[]),
    lambda p: p["config"].update(style_params=None),
    lambda p: p["config"]["mechanics_matrix"].update(kickoff={"count": float("nan")}),
    lambda p: p["config"]["narrative_phases"].update(prologue={"count": -1}),
    lambda p: p["config"]["art_matrix"].update(kickoff={"huge": 1001}),
    lambda p: p["config"].update(prototype={"constructor": True}),
    lambda p: p["config"].update(game_vision="x" * 12001),
    lambda p: p["config"].update(game_vision="z" * 450001),
])
def test_untrusted_unknown_incomplete_or_oversized_matrix_fails_closed(damage):
    profile = _profile()
    damage(profile)
    with pytest.raises(GalaxyAuthoringError):
        normalise_galaxy_authoring(profile)


def test_explicit_infinite_or_non_json_matrix_values_are_denied():
    for bad in [float("inf"), float("-inf"), object(), set(), 2 ** 60]:
        profile = _profile()
        profile["config"]["extra_params"]["broken"] = bad
        with pytest.raises(GalaxyAuthoringError):
            authored_source(profile)


def test_success_receipt_does_not_make_unverified_gameplay_ready():
    _, receipt = authored_source(_profile())
    assert receipt["full_original_authoring_preserved"] is True
    assert receipt["native_gameplay_qualified"] is False
    assert "model_quality_certified" not in receipt
    assert "release_qualified" not in receipt
