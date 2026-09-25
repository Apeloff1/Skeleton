"""Forge repair does not invent a script, and a JSON scalar is not an artefact."""

import pytest

from skeleton.forge.repair import attempt_repair
from skeleton.forge.structured_verify import _parse_ok, verify_structured


def test_repair_does_not_write_a_stub_or_a_main_scene() -> None:
    files = {"project.godot": "[section]\n", "player.gd": "eval(1)\n"}
    repaired = attempt_repair(files, request="player movement")
    assert repaired["ok"] == 0
    assert repaired["changed"] == 0
    assert repaired["files"] == files
    assert "_repair_stub" not in str(repaired["files"])
    assert "event_bus" not in str(repaired["files"])
    assert all(action["applied"] == 0 for action in repaired["actions"])


def test_a_json_scalar_is_not_a_structured_artefact() -> None:
    assert _parse_ok("true", "json") == (False, "json root must be an object or array")
    assert _parse_ok("{", "json")[0] is False
    assert _parse_ok('{"ok": true}', "json")[0] is True
    with pytest.raises(ValueError):
        verify_structured({"note.json": '{"ok": true}'}, target="json", accept_threshold=0)
