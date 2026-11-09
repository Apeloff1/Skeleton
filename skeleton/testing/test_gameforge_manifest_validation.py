"""Keep Godot path validation and manifest truth identical across transports."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from skeleton.context.pipeline import GameForgeRun, _stage_emit
from skeleton.forge.source_manifest import source_manifest


def _files():
    return {"project.godot": "[application]\n", "data/rooms.json": "{}"}


@pytest.mark.parametrize("invalid", [
    "../escape.gd", "/absolute/escape.gd", "sub/../../escape.gd",
    "CON.txt", "build_report.md", "sub\\escape.gd",
])
def test_in_memory_manifest_rejects_projector_unsafe_paths(invalid):
    with pytest.raises((ValueError, TypeError)):
        source_manifest({**_files(), invalid: "contents"})


def test_casefold_alias_is_invalid_in_memory_as_on_disk():
    with pytest.raises(ValueError):
        source_manifest({**_files(), "Data/a.gd": "x", "data/A.gd": "y"})


def test_in_memory_source_attestation_needs_godot_entrypoint():
    with pytest.raises(ValueError, match="project.godot"):
        source_manifest({"data/rooms.json": "{}"})


def test_emit_blocks_bad_source_before_gdscript_verification():
    with patch("skeleton.forge.gdscript_check.check_ok") as checked:
        with pytest.raises(ValueError):
            _stage_emit({"files": {**_files(), "../bad.gd": "x"}})
        checked.assert_not_called()


def test_failed_gameforge_run_never_reports_verified_source_manifest():
    with patch("skeleton.context.pipeline._stage_emit",
               side_effect=RuntimeError("intended emit failure")):
        output = GameForgeRun().execute("a quiet village", era="cozy_wholesome")
    assert not output["succeeded"]
    assert output["source_manifest"] is None
    assert output["files"]  # partial source exists but must not be attested as sealed


def test_successful_godot_source_receipt_is_portable():
    result = source_manifest(_files())
    assert result["file_count"] == 2
    assert len(result["sha256"]) == 64
    assert result == source_manifest(dict(reversed(list(_files().items()))))
