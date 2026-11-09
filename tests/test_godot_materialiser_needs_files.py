"""A Godot materialisation does not invent a project."""

import json

import pytest

from skeleton.forge.materialisers import MaterialisationRegistry
from skeleton.kernel.errors import MaterialisationError


def test_an_empty_godot_target_is_refused() -> None:
    registry = MaterialisationRegistry()
    with pytest.raises(MaterialisationError):
        registry.get("godot").encode({})
    with pytest.raises(MaterialisationError):
        registry.get("godot").encode({"name": "FORGE", "pack": {}})
    encoded = registry.get("godot").encode({"files": {"player.gd": "extends Node\n"}})
    payload = json.loads(encoded)
    assert payload["count"] == 1
    assert payload["files"]["player.gd"] == "extends Node\n"
