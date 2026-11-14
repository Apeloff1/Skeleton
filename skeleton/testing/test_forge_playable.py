"""Questionnaire -> GameForge -> playable Godot project, end to end.

Static tests always run. The headless tests boot the emitted project in a
real Godot 4 binary (resolved like the playtest gate: artifact plane,
``SKELETON_GODOT_BIN``/``GODOT_BINARY``, or PATH) and let the generated
Autopilot *play the core loop to a win*; they skip when no binary exists.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.forge.eras import list_eras
from skeleton.forge.playable import (
    ERA_LOOPS,
    LOOPS,
    PlayableExportError,
    build_config,
    choose_loop,
    emit_playable,
    export_game,
    forge_playable,
    generate_level,
    main,
    parse_smoke,
    smoke_run,
    validate_level,
    validate_project,
)
from skeleton.forge.playtest import playtest, resolve_binary
from skeleton.forge.projector import ProjectExistsError

ANSWERS = {
    "extraction": {"genre": "extraction", "theme": "sci-fi", "perspective": "top-down"},
    "arena": {"genre": "shooter", "theme": "retro", "combat": "fast"},
    "soulslike": {"genre": "soulslike", "theme": "dark-fantasy", "combat": "melee"},
    "cozy": {"genre": "cozy", "theme": "cozy", "combat": "none"},
    "horror": {"genre": "horror", "theme": "horror", "perspective": "top-down"},
}

_GODOT, _SOURCE, _ = resolve_binary()
needs_godot = pytest.mark.skipif(_GODOT is None, reason=f"no Godot binary ({_SOURCE})")


def test_every_canonical_era_has_a_playable_loop() -> None:
    assert set(list_eras()) <= set(ERA_LOOPS)
    assert set(ERA_LOOPS.values()) == set(LOOPS)


@pytest.mark.parametrize("loop", LOOPS)
def test_questionnaire_answers_select_each_archetype(loop: str) -> None:
    chosen, reason = choose_loop("extraction_now", ANSWERS[loop])
    assert chosen == loop, reason


def test_explicit_loop_and_combat_none_win_over_genre() -> None:
    assert choose_loop("soulslike", {"genre": "shooter", "loop": "cozy"})[0] == "cozy"
    assert choose_loop("soulslike", {"genre": "shooter", "combat": "none"})[0] == "cozy"
    assert choose_loop("horror_survival", {})[0] == "horror"
    assert choose_loop("not_an_era", {})[0] == "extraction"


@pytest.mark.parametrize("loop", LOOPS)
@pytest.mark.parametrize("seed_int", [1, 7, 12345, 2**31 - 1])
def test_generated_levels_are_closed_connected_and_complete(loop: str, seed_int: int) -> None:
    rows = generate_level(loop, seed_int, {"cores_total": 4})
    assert validate_level(rows, loop) == []
    assert rows == generate_level(loop, seed_int, {"cores_total": 4})  # deterministic


def test_level_validator_rejects_unreachable_and_missing_goals() -> None:
    rows = ["#######", "#P.#X.#", "#######"]
    problems = validate_level(rows, "horror")
    assert any("unreachable" in p for p in problems)
    assert any("'K'" in p for p in problems)


@pytest.mark.parametrize("loop", LOOPS)
def test_forged_project_is_statically_playable(loop: str) -> None:
    config, files, provenance = forge_playable(ANSWERS[loop])
    assert config["loop"] == loop
    assert validate_project(files) == []
    # a real scene, a real controller, a real loop with win + lose states
    assert 'run/main_scene="res://scenes/main.tscn"' in files["project.godot"]
    assert f'path="res://scripts/loops/{loop}.gd"' in files["scenes/main.tscn"]
    assert "move_and_slide" in files["scripts/player.gd"]
    assert 'Game.finish("win")' in files[f"scripts/loops/{loop}.gd"]
    # provenance ties the build to the forge run
    assert provenance["blueprint_id"] and provenance["spec_id"]
    assert json.loads(files["data/forge_provenance.json"])["loop"] == loop


@pytest.mark.parametrize("loop", LOOPS)
def test_placeholders_are_clearly_labelled(loop: str) -> None:
    _, files, _ = forge_playable(ANSWERS[loop])
    manifest = json.loads(files["data/asset_manifest.json"])
    assert manifest["all_placeholder"] is True
    assert {e["status"] for e in manifest["entries"]} == {"placeholder"}
    svgs = [p for p in files if p.startswith("assets/placeholders/") and p.endswith(".svg")]
    assert svgs and all("PLACEHOLDER" in files[p] for p in svgs)
    assert "PLACEHOLDER ART" in files["scripts/hud.gd"]
    assert "placeholder" in files["README.md"].lower()


def test_rules_are_derived_from_the_era_pack() -> None:
    pack = {
        "player": {"speed": 175.0, "max_health": 140.0, "i_frame_ms": 250.0},
        "heat": {"max_heat": 90.0, "passive_cool": 20.0, "sprint_heat_per_sec": 10.0},
        "ttk": {"trash": 1.0, "elite": 4.0, "boss": 60.0},
        "session": {"collapse_max": 400.0},
        "recipes": [{"id": "kinetic_basic", "damage": 20, "heat": 5.0, "rpm": 300}],
        "hardware": {"key": "snes", "viewport": [512, 448], "pixel_snap": True, "palette": ["#112233", "#445566"]},
    }
    cfg = build_config(pack, loop="extraction", title="T", era="extraction_now", seed="abcdef0123")
    assert cfg["player"]["speed"] == 175.0 and cfg["player"]["max_hp"] == 140.0
    assert cfg["player"]["iframe_seconds"] == 0.25
    assert cfg["weapon"]["damage"] == 20 and cfg["weapon"]["cooldown"] == 0.2
    assert cfg["player_dps"] == 100.0
    assert cfg["enemies"]["trash"]["hp"] == 100.0  # dps * ttk(trash)
    assert cfg["heat"]["enabled"] and cfg["heat"]["max"] == 90.0
    assert cfg["rules"]["collapse_seconds"] == 240.0
    assert cfg["viewport"] == [512, 448] and cfg["pixel_snap"] is True
    files = emit_playable(cfg)
    assert "textures/canvas_textures/default_texture_filter=0" in files["project.godot"]
    souls = build_config(pack, loop="soulslike", title="T", era="soulslike", seed="abcdef0123")
    assert souls["weapon"]["mode"] == "melee" and "boss" in souls["enemies"]
    cozy = build_config(pack, loop="cozy", title="T", era="cozy_wholesome", seed="abcdef0123")
    assert cozy["weapon"]["mode"] == "none" and cozy["enemies"] == {}


def test_different_answers_forge_different_games() -> None:
    a, _, _ = forge_playable(ANSWERS["arena"])
    b, _, _ = forge_playable(ANSWERS["horror"])
    assert (a["loop"], a["era"]) != (b["loop"], b["era"])
    assert a["level"]["rows"] != b["level"]["rows"]
    again, _, _ = forge_playable(ANSWERS["arena"])
    assert again == a  # same answers -> same game


def test_export_writes_project_and_refuses_to_clobber(tmp_path: Path) -> None:
    out = tmp_path / "game"
    result = export_game(ANSWERS["cozy"], out)
    assert result.ok and result.loop == "cozy"
    assert (out / "project.godot").is_file() and (out / "FORGE_MANIFEST.json").is_file()
    assert (out / "data" / "level.txt").read_text().count("F") == 8
    with pytest.raises(ProjectExistsError):
        export_game(ANSWERS["cozy"], out)
    assert export_game(ANSWERS["cozy"], out, overwrite=True).ok


def test_export_rejects_bad_inputs(tmp_path: Path) -> None:
    with pytest.raises(PlayableExportError):
        export_game(ANSWERS["cozy"], tmp_path / "x", smoke="sometimes")
    with pytest.raises(PlayableExportError):
        export_game(ANSWERS["cozy"], tmp_path / "y", loop="racing")
    with pytest.raises(PlayableExportError):
        export_game(ANSWERS["cozy"], tmp_path / "z", seed="NOT-HEX")


def test_cli_entrypoint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "cli"
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps(ANSWERS["soulslike"]))
    assert main(["--answers", str(answers), "--out", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["loop"] == "soulslike" and report["ok"] is True
    assert (out / "scripts" / "loops" / "soulslike.gd").is_file()


def test_smoke_report_parser() -> None:
    log = 'noise\nFORGE_SMOKE {"outcome": "win", "loop": "arena"}\nmore'
    assert parse_smoke(log) == {"outcome": "win", "loop": "arena"}
    assert parse_smoke("FORGE_SMOKE {broken") is None
    assert parse_smoke("nothing here") is None


def test_smoke_run_reports_unavailable_without_binary(tmp_path: Path) -> None:
    export_game(ANSWERS["cozy"], tmp_path / "g")
    res = smoke_run(tmp_path / "g", binary=str(tmp_path / "no-such-godot"))
    assert res["status"] == "unavailable" and res["passed"] is False


@needs_godot
def test_playable_project_passes_the_boot_playtest_gate() -> None:
    _, files, _ = forge_playable(ANSWERS["extraction"])
    result = playtest(files, frames=240)
    assert result["status"] == "passed", result["errors"]


@needs_godot
@pytest.mark.parametrize("loop", LOOPS)
def test_e2e_questionnaire_forge_export_autoplay_wins(loop: str, tmp_path: Path) -> None:
    """questionnaire -> GameForge -> export -> headless Godot: the bot beats the loop."""
    result = export_game(ANSWERS[loop], tmp_path / loop, smoke="require", smoke_seconds=420)
    smoke = result.smoke or {}
    assert smoke.get("errors") == [], smoke.get("errors")
    report = smoke.get("report") or {}
    assert report.get("loop") == loop
    assert report.get("outcome") == "win", json.dumps(report)[:2000]
    stats = report["stats"]
    if loop == "cozy":
        assert stats["interactions"] > 0 and stats["pickups"] > 0
    else:
        assert stats["damage_dealt"] > 0
    if loop in {"arena", "soulslike"}:
        assert stats["kills"] > 0
