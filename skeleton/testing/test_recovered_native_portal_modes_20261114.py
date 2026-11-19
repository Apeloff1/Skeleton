"""Five recovered native loops must coexist with the three current portal slices."""
from __future__ import annotations

import pytest

from skeleton.forge.archetype_content import (
    archetype_files, content_archetypes, verify_archetype_content,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.playable_portal import attach_playable_portal, verify_playable_portal


@pytest.mark.parametrize("mode", ["puzzle", "racing", "survival", "stealth", "crafting"])
def test_recovered_loop_source_and_portal(mode):
    assert len(content_archetypes()) == 8
    source = archetype_files(mode, operator_axes={"tempo": .7, "risk": .4})
    assert verify_archetype_content(source, mode, operator_axes={"tempo": .7, "risk": .4})
    assert not verify_archetype_content(source, mode, operator_axes={"tempo": .2})
    for standalone in (False, True):
        files = {**emit_godot(compile_era("extraction_now")), **source}
        result, receipt = attach_playable_portal(files, mode, start_in_prototype=standalone)
        assert verify_playable_portal(result, mode, start_in_prototype=standalone)
        assert not verify_playable_portal(result, mode, start_in_prototype=not standalone)
        assert receipt["return_supported"]
        assert "func _on_scene_changed() -> void:" in result[receipt["script"]]
        assert f"scenes/archetypes/{mode}/main.tscn" in result
