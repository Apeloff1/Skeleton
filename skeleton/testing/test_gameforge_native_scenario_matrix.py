"""Reviewed native scenario inventory, source-bound tuning, and marker admission."""
from scripts.qualify_gameforge_godot_native import exact_completion, reviewed_scenarios
from skeleton.context.pipeline import GameForgeRun
from skeleton.forge.archetype_content import content_archetypes
import pytest


def test_reviewed_inventory_has_exactly_one_baseline_and_tuned_case_per_mode():
    matrix = reviewed_scenarios()
    assert len(matrix) == 16
    assert tuple(sorted({name for name, _ in matrix})) == content_archetypes()
    for name in content_archetypes():
        pair = [axes for key, axes in matrix if key == name]
        assert len(pair) == 2 and pair[0] == {} and pair[1]


@pytest.mark.parametrize(("name", "axes"), reviewed_scenarios())
def test_native_matrix_source_receipts_are_exact(name, axes):
    result = GameForgeRun().execute(
        "Original qualification " + name, archetype=name, playable_content=True,
        operator_axes=axes,
    )
    assert result["succeeded"] is True
    assert result["playable_mechanics"]["applied_axes"] == axes
    assert result["playable_mechanics"]["source_verified"] is True
    assert result["source_manifest"]["file_count"] == len(result["files"])


@pytest.mark.parametrize("text", [
    "ARCHETYPE_LOOP_COMPLETE puzzle_extra",
    "ARCHETYPE_LOOP_COMPLETE puzzle\nARCHETYPE_LOOP_COMPLETE puzzle",
    "ARCHETYPE_LOOP_COMPLETE puzzle\nARCHETYPE_LOOP_FAILED racing",
    "ARCHETYPE_LOOP_COMPLETE puzzle\nARCHETYPE_LOOP_COMPLETE racing",
    "prefixed ARCHETYPE_LOOP_COMPLETE puzzle",
])
def test_foreign_duplicate_and_failed_markers_cannot_qualify(text):
    assert not exact_completion(text, "puzzle")


def test_one_exact_marker_with_optional_reason():
    assert exact_completion("ARCHETYPE_LOOP_COMPLETE puzzle solved switches", "puzzle")
    assert exact_completion("ARCHETYPE_LOOP_COMPLETE puzzle", "puzzle")
