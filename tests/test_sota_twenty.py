from __future__ import annotations

import json

import pytest

from skeleton.game.doctor import doctor
from skeleton.game.emit_pack import EmitPackError, default_tree, validate_emit
from skeleton.game.flake import FlakeError, advance, ledger, open_flake
from skeleton.game.release_graph import graph
from skeleton.game.spec import SpecError, compile_spec
from skeleton.game.token_clock import TokenClockError, tick


def test_spec_lists_conflicts_and_no_prose() -> None:
    card = compile_spec("NEXUS-EXTRACT heat godot unity #807")
    assert card["stored_prose"] == 0
    assert "loop" in card["fields"]
    assert "emit-engine" in card["conflicts"]
    with pytest.raises(SpecError):
        compile_spec("  ")


def test_emit_pack_requires_tree_and_bans_godot_binary() -> None:
    ok = validate_emit(default_tree())
    assert ok["valid"] == 1
    assert ok["godot_binary"] == 0
    missing = validate_emit(["world.json"])
    assert missing["valid"] == 0
    assert "project.godot" in missing["missing"]
    with pytest.raises(EmitPackError, match="forbidden"):
        validate_emit(["backend/godot"])


def test_doctor_bumps_weakest_without_retune() -> None:
    card = doctor({"fun": 0.2, "clarity": 0.8, "feasibility": 0.7, "originality": 0.6}, seed=7)
    assert card["axis"] == "fun"
    assert card["retune"] is False
    assert card["live_knobs"] is False
    assert card["after"]["axes"]["fun"] > card["before"]["axes"]["fun"]
    assert card["stored_prose"] == 0


def test_flake_lifecycle_and_release_graph() -> None:
    digest = "a" * 64
    opened = open_flake(test_id="tests/test_game_replay.py", digest=digest)
    quarantined = advance(opened, "quarantine")
    closed = advance(quarantined, "close")
    assert closed["state"] == "closed"
    book = ledger([opened, closed])
    assert book["n"] == 2
    with pytest.raises(FlakeError):
        advance(opened, "expire")
    tree = graph(
        [
            {"name": "pack", "body": {"max_level": 20}},
            {"name": "catalog", "body": {"n": 2}},
        ]
    )
    assert tree["reproducible"] is True
    assert len(tree["root"]) == 64
    assert graph(
        [
            {"name": "pack", "body": {"max_level": 20}},
            {"name": "catalog", "body": {"n": 2}},
        ]
    )["root"] == tree["root"]


def test_token_clock_not_every_frame() -> None:
    card = tick(frames=20, warps=1)
    assert card["every_frame"] is False
    assert card["tokens"] == 5
    assert card["extract_count"] == card["warp_count"] == 1
    with pytest.raises(TokenClockError):
        tick(frames=0)


def test_cli_spec_emit_doctor(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["spec", "NEXUS-EXTRACT", "heat", "#807"]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["ok"] is True
    assert spec["stored_prose"] == 0
    assert main(["emit"]) == 0
    emit = json.loads(capsys.readouterr().out)
    assert emit["valid"] == 1
    assert emit["godot_binary"] == 0
    assert main(["doctor", "--seed", "3"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["retune"] is False
    assert doc["axis"] == "fun"
