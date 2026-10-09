"""End-to-end C89 gameplay from an original rights-bound project capsule."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.game.export_portable_c89 import emit_portable_c89, main as export_c89
from scripts.game.game_project import _demo
from skeleton.ai.runtime.game_project_capsule import GameCapsuleError
from skeleton.ai.runtime.gameplay_capabilities import compile_level


def _original(seed: int = 42):
    return _demo(seed, ["ibm-pc-dos", "windows-11"], "NO")


def test_original_capsule_emits_self_contained_c89_game_source_without_sdk():
    project = _original()
    generated = emit_portable_c89(project)
    assert generated["language"] == "ISO C89"
    assert generated["play_semantics"] == "turn_based_integer_tile_grid"
    assert generated["source_bytes"] < 24 * 1024
    assert generated["source_sha256"] == hashlib.sha256(
        generated["source"].encode("ascii")
    ).hexdigest()
    assert generated["source_game_capsule_sha256"] == project["capsule_sha256"]
    assert generated["compiled_binary_exists"] is False
    assert generated["console_rom_created"] is False
    assert generated["licensed_platform_sdk_used"] is False
    assert generated["source_rights_independently_verified"] is False
    assert generated["publish_authorized"] is False
    assert generated["training_examples_added"] == 0
    assert "#include <stdio.h>" in generated["source"]
    assert "int main(void)" in generated["source"]
    assert "puts(\"WIN\")" in generated["source"]
    assert "system(" not in generated["source"]
    assert "socket(" not in generated["source"]
    assert "getenv(" not in generated["source"]


def test_c89_generation_is_fully_deterministic_and_seed_sensitive():
    project = _original(7)
    first = emit_portable_c89(project)
    second = emit_portable_c89(project)
    third = emit_portable_c89(_original(8))
    assert first == second
    assert first["source_sha256"] != third["source_sha256"]


def test_c89_cli_uses_exclusive_output_and_never_changes_capsule(
    tmp_path: Path, capsys,
):
    capsule = tmp_path / "original.json"
    value = _original()
    capsule.write_text(json.dumps(value), encoding="utf-8")
    original_sha = hashlib.sha256(capsule.read_bytes()).hexdigest()
    output = tmp_path / "original_game.c"
    assert export_c89(["--capsule", str(capsule), "--output", str(output)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["output_path"] == str(output)
    assert receipt["console_rom_created"] is False
    assert original_sha == hashlib.sha256(capsule.read_bytes()).hexdigest()
    assert export_c89(["--capsule", str(capsule), "--output", str(output)]) == 1
    assert original_sha == hashlib.sha256(capsule.read_bytes()).hexdigest()
    assert "unused" in capsys.readouterr().err


def test_actual_c89_binary_compiles_and_wins_from_original_generated_map(
    tmp_path: Path,
):
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("No native C compiler installed; CI gate requires one")
    original = _original(seed=42)
    c = tmp_path / "game.c"
    exe = tmp_path / "original-game"
    c.write_text(emit_portable_c89(original)["source"], encoding="ascii")
    process = subprocess.run(
        [compiler, "-std=c89", "-Wall", "-Wextra", "-Werror", "-pedantic",
         str(c), "-o", str(exe)],
        text=True, capture_output=True, timeout=40, check=False,
    )
    assert process.returncode == 0, process.stderr
    level = compile_level({"tiles": original["tilemap"]})
    moves = (
        "d" * (level["goal"]["x"] - level["spawn"]["x"])
        + "s" * (level["goal"]["y"] - level["spawn"]["y"])
        + "\n"
    )
    played = subprocess.run(
        [str(exe)], input=moves, text=True, capture_output=True,
        timeout=10, check=False,
    )
    assert played.returncode == 0
    assert "WIN" in played.stdout
    assert "BLOCKED" not in played.stdout
    assert played.stdout.count("@") >= len(moves) - 1


def test_modified_or_forged_external_rights_cannot_be_launched_as_original_c89():
    project = _original()
    project["rights_receipt"]["source_kind_summary"] = ["licensed"]
    with pytest.raises(GameCapsuleError):
        emit_portable_c89(project)
    project = _original()
    project["legal_release_authorized"] = True
    with pytest.raises(GameCapsuleError):
        emit_portable_c89(project)


def test_c89_cli_rejects_symlink_capsule(tmp_path: Path, capsys):
    data = tmp_path / "safe.json"
    data.write_text(json.dumps(_original()), "utf-8")
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(data)
    except OSError:
        pytest.skip("filesystem does not permit symlinks")
    assert export_c89([
        "--capsule", str(link), "--output", str(tmp_path / "out.c"),
    ]) == 1
    assert "regular" in capsys.readouterr().err
    assert not (tmp_path / "out.c").exists()
