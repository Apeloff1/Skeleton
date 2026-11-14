"""Actual Godot headless acceptance for the eight original playable mini-games.

This test is intentionally not satisfiable by source-only assertions.
An absent Godot binary is skipped, never reported as a native pass.
"""
from __future__ import annotations

import pytest

from skeleton.forge.archetype_content import (
    COMPLETE_MARKER, FAILED_MARKER, archetype_files, attach_archetype_content,
    content_archetypes,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.playtest import playtest, resolve_binary


@pytest.mark.parametrize("name", content_archetypes())
def test_real_godot_completes_original_game_loop_in_selected_main_scene(name):
    binary, source, verified = resolve_binary()
    if binary is None:
        pytest.skip("Native Godot binary unavailable; source-only proof is not native acceptance")

    files = emit_godot(compile_era("extraction_now"))
    files = attach_archetype_content(files, name)
    target = f'res://scenes/archetypes/{name}/main.tscn'
    previous = 'run/main_scene="res://scenes/levels/run_level.tscn"'
    assert files["project.godot"].count(previous) == 1
    files["project.godot"] = files["project.godot"].replace(
        previous, f'run/main_scene="{target}"',
    )
    result = playtest(files, binary=binary, frames=4500, timeout=100.0)
    assert result["status"] == "passed", (name, source, verified, result)
    assert result["passed"] is True
    boot = next((item for item in result["steps"] if item["step"] == "boot"), None)
    assert boot is not None, (name, result)
    assert boot["returncode"] == 0 and not boot["timed_out"], (name, boot)
    assert f"{COMPLETE_MARKER} {name} " in boot["log_tail"], (name, boot)
    assert FAILED_MARKER not in boot["log_tail"], (name, boot)
