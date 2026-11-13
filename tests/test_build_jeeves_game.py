"""Operator proposal admission and create-only project publication boundaries."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_jeeves_game import admit_proposal, publish_create_only
from skeleton.forge.game_builder import _apply_planner
from skeleton.forge.game_design_spec import compile_brief


def proposal() -> dict:
    return {
        "title": "Lantern Run", "fantasy": "Carry a lantern through flooded ruins.",
        "core_loop": "Jump between ledges and reach the far gate.",
        "gameplay": {"difficulty": "normal", "theme": "moss",
            "objective_label": "Reach the far gate", "player_speed": 220,
            "encounter_style": "patrol"},
    }


def test_complete_design_reaches_actual_builder_guard_without_changing_locked_fields():
    compiled = compile_brief("A small platformer. Fantasy: flooded ruins.")
    admitted, violations = admit_proposal(compiled, json.dumps(proposal()))
    assert not violations
    applied = _apply_planner(compiled, lambda _spec: admitted)
    assert applied["title"] == "Lantern Run"
    assert applied["gameplay"]["player_speed"] == 220
    for key in ("genre", "engine", "scope", "brief"):
        assert applied[key] == compiled[key]


@pytest.mark.parametrize("change", [
    {"genre": "rpg_roguelike"}, {"engine": "host-shell"},
    {"path": "/tmp/generated.gd"}, {"code": "OS.execute('sh')"},
    {"tools": ["shell"]}, {"provider": "hosted"},
])
def test_untrusted_design_never_grants_source_path_or_execution_authority(change):
    compiled = compile_brief("A small platformer.")
    admitted, violations = admit_proposal(compiled, proposal() | change)
    assert violations and admitted == compiled


@pytest.mark.parametrize("raw", [
    {"title": "Only prose"}, "```json\n{}\n```", "```garbage\n{}\n```",
    '{"title":"first","title":"second"}', '{"gameplay":NaN}',
    {"title": "Bad", "fantasy": "", "core_loop": "jump", "gameplay": {}},
])
def test_incomplete_or_noncanonical_operator_designs_are_explicitly_rejected(raw):
    compiled = compile_brief("A small platformer.")
    admitted, violations = admit_proposal(compiled, raw)
    assert violations and admitted == compiled


def test_explicit_user_gameplay_survives_both_model_guards():
    compiled = compile_brief("A small platformer. Difficulty: easy. Theme: frost. Player speed: 120.")
    forged = proposal()
    forged["gameplay"].update(difficulty="hard", theme="ember", player_speed=360)
    admitted, violations = admit_proposal(compiled, forged)
    assert violations and admitted == compiled
    # The direct hook boundary is independently guarded as well.
    applied = _apply_planner(compiled, lambda base: {**base, **forged})
    assert applied == compiled


def test_atomic_publication_preserves_a_destination_created_during_planning(tmp_path: Path):
    source = tmp_path / "private-staged-project"
    source.mkdir()
    (source / "project.godot").write_text("config_version=5\n")
    destination = tmp_path / "operator-project"
    destination.mkdir()
    (destination / "keep.txt").write_text("Operator's newer project")
    with pytest.raises(OSError):
        publish_create_only(source, destination)
    assert (destination / "keep.txt").read_text() == "Operator's newer project"
    assert not (destination / "project.godot").exists()
    assert source.is_dir()


def test_atomic_publication_moves_a_complete_directory_once(tmp_path: Path):
    source = tmp_path / "staged"
    source.mkdir()
    (source / "project.godot").write_text("config_version=5\n")
    destination = tmp_path / "published"
    publish_create_only(source, destination)
    assert not source.exists()
    assert (destination / "project.godot").read_text() == "config_version=5\n"
