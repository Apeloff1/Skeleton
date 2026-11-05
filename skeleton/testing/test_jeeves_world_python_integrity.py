"""Regression against escaped literal newlines in Python import/CLI seams."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.parametrize("path", [
    "skeleton/__main__.py",
    "skeleton/jeeves/worlds/tools.py",
    "skeleton/jeeves/worlds/events.py",
    "skeleton/jeeves/worlds/events_cli.py",
    "skeleton/jeeves/worlds/events_editor.py",
    "skeleton/jeeves/worlds/relationships.py",
    "skeleton/jeeves/worlds/relationships_cli.py",
    "skeleton/jeeves/worlds/relationships_editor.py",
    "skeleton/jeeves/worlds/route.py",
    "skeleton/jeeves/worlds/cast.py",
    "skeleton/jeeves/worlds/quest.py",
    "skeleton/jeeves/worlds/counterfactual.py",
    "skeleton/jeeves/worlds/counterfactual_cli.py",
    "skeleton/jeeves/worlds/lore.py",
    "skeleton/jeeves/worlds/lore_cli.py",
    "skeleton/jeeves/worlds/lore_editor.py",
    "skeleton/jeeves/worlds/lore_player.py",
])
def test_python_world_modules_parse(path: str):
    source = (ROOT / path).read_text(encoding="utf-8")
    ast.parse(source, filename=path)


def test_main_cli_dispatch_has_real_statements():
    source = (ROOT / "skeleton/__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    commands = {
        node.comparators[0].value for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and isinstance(node.comparators[0].value, str)
        and isinstance(node.left, ast.Name)
        and node.left.id == "cmd"
    }
    assert {
        "world-route", "world-cast", "world-quest",
        "world-counterfactual", "world-lore",
    } <= commands


def test_repaired_world_modules_import_without_syntax_error():
    from skeleton.jeeves.worlds import cast, quest, route
    from skeleton.jeeves.worlds import counterfactual, lore, lore_editor, lore_player
    assert route.SCHEMA and cast.SCHEMA and quest.SCHEMA
    assert counterfactual.SCHEMA and lore.SCHEMA and lore_editor.EDITOR_SCHEMA
    assert lore_player._LORE_JS


def test_scene_events_cli_and_typed_tool_dispatch_import():
    """A literal backslash-n in a Python import/dispatch must fail immediately."""
    from skeleton.jeeves.worlds import events, events_cli, tools
    assert callable(events.prove_events)
    assert callable(events_cli.run)
    names = {item["name"] for item in tools.manifest()["tools"]}
    assert {"world.events_preview", "world.events_propose_preview"} <= names


def test_main_cli_scene_events_dispatch_is_real_python():
    source = (ROOT / "skeleton/__main__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    branches = [node for node in ast.walk(tree)
                if isinstance(node, ast.Compare)
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == "world-events"]
    assert len(branches) == 1
    assert "world_events_cli(rest)" in source


def test_event_store_has_real_compile_and_verify_methods():
    from skeleton.jeeves.worlds.events import EventStore
    assert callable(EventStore.compile)
    assert callable(EventStore.verify)
