"""One eight-mode playable library serves both recovered knob contracts.

Mass recovery landed the #5315 eight-mode tests next to the earlier
three-mode creator-axes mechanics. These checks pin the unification: one
authored source per mode, two mutually exclusive bounded knob contracts,
and one honest count on the HTTP surface.
"""
from __future__ import annotations

import json

import pytest

from skeleton.forge.archetype_content import (
    MECHANICS_AXES, archetype_files, content_archetypes, verify_archetype_content,
)
from skeleton.forge.playable_tuning import SOURCE_PATH

EIGHT = (
    "combat_loop", "crafting", "extraction", "pipeline",
    "puzzle", "racing", "stealth", "survival",
)


def test_library_and_http_surface_agree_on_eight_modes():
    from backend.routes.skeleton_gameforge import playable_archetypes
    assert content_archetypes() == EIGHT
    assert playable_archetypes()["count"] == 8
    assert set(MECHANICS_AXES) == set(EIGHT)


@pytest.mark.parametrize("mode", EIGHT)
def test_contracts_are_mutually_exclusive(mode):
    with pytest.raises(ValueError, match="not both"):
        archetype_files(mode, operator_axes={"tempo": 0.5}, tuning={"tempo": 0.5})


@pytest.mark.parametrize("mode", EIGHT)
def test_operator_axes_never_write_a_tuning_receipt(mode):
    files = archetype_files(mode, operator_axes={"tempo": 1.0})
    assert SOURCE_PATH not in files
    assert verify_archetype_content(files, mode, operator_axes={"tempo": 1.0})
    assert not verify_archetype_content(files, mode)


@pytest.mark.parametrize("mode", EIGHT)
def test_both_contracts_start_from_identical_pristine_source(mode):
    pristine = archetype_files(mode)
    assert archetype_files(mode, operator_axes={}) == pristine
    assert archetype_files(mode, tuning={}) == pristine
    tuned = archetype_files(mode, tuning={"tempo": 1.0})
    receipt = json.loads(tuned[SOURCE_PATH])
    legacy = archetype_files(mode, operator_axes={"tempo": 1.0})
    # Same tempo law in both contracts: identical controller speed.
    controller = f"scripts/archetypes/{mode}/player_controller.gd"
    speed = f"{receipt['applied']['player.speed']:.2f}"
    assert f"@export var speed: float = {speed}" in tuned[controller]
    assert f"@export var speed: float = {float(speed)}" in legacy[controller]


@pytest.mark.parametrize("mode", EIGHT)
def test_every_loop_is_input_driven_and_headless_safe(mode):
    loop = archetype_files(mode)[f"scripts/archetypes/{mode}/core_loop.gd"]
    assert "func _draw() -> void:" in loop
    assert loop.count("func _draw() -> void:") == 1
    assert "func _draw_objectives() -> void:" in loop
    assert "player.autopilot" not in loop
    # Pointer D-pad is suppressed where the controller installs a touch pad.
    assert "DisplayServer.is_touchscreen_available()" in loop
