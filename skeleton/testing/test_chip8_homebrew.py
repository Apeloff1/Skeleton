"""End-to-end original CHIP-8 ROM generation, real bytecode execution and rights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.game.export_chip8 import (
    Chip8ExportError, _original_capsule, compile_chip8_homebrew,
    main as chip8_export, verify_chip8_executable,
)
from skeleton.ai.runtime.chip8_machine import Chip8Error, Chip8Machine
from skeleton.ai.runtime.game_project_capsule import GameCapsuleError
from skeleton.ai.runtime.game_platform_catalog import (
    TARGETS, catalog_summary, plan_game_targets,
)


def test_first_executable_vintage_adapter_is_real_and_not_fake_console_readiness():
    profile = TARGETS["chip8-vip"].as_dict()
    assert profile["era"] == "1970s"
    assert profile["native_export_implemented"] is True
    assert profile["emulator_integrated"] is True
    assert profile["real_hardware_validated"] is False
    assert profile["rights_clearance_certified"] is False
    assert profile["published_binary_ready"] is False
    report = catalog_summary()
    assert report["original_homebrew_vm_rom_exporter_count"] == 1
    assert report["native_console_exporter_count"] == 0
    assert report["target_count"] == len(TARGETS) == 159
    requested = plan_game_targets(
        target_ids=["chip8-vip", "game-boy", "playstation-5"],
        required_features=["tile2d", "input"],
    )
    assert requested["targets"][0]["native_export_implemented"] is True
    assert requested["targets"][0]["unimplemented_native_export_is_blocker"] is False
    assert requested["targets"][1]["native_export_implemented"] is False
    assert requested["targets"][2]["sdk_independent_authorization_verified"] is False
    assert requested["native_binaries_ready"] == 0


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 1729, 65535, 2**31 - 1])
def test_original_chip8_rom_executes_to_win_with_no_original_console_firmware(seed):
    capsule = _original_capsule(seed)
    program = compile_chip8_homebrew(capsule)
    assert program["rom_bytes"] == len(program["rom"])
    assert 64 < len(program["rom"]) <= 3584
    assert program["rom_sha256"] == hashlib.sha256(program["rom"]).hexdigest()
    assert program["target"] == "chip8-vip"
    assert program["shortest_path_keys"]
    assert program["shortest_path_steps"] == len(program["shortest_path_keys"])
    assert set(program["shortest_path_keys"]) <= {2, 4, 6, 8}
    assert program["boot_rom_embedded"] is False
    assert program["licensed_sdk_embedded"] is False
    assert program["original_game_assets_only"] is True
    assert program["training_examples_added"] == 0
    assert program["real_1970s_hardware_tested"] is False
    accepted = verify_chip8_executable(program)
    assert accepted["win_state_reached"] is True
    assert accepted["rom_sha256"] == program["rom_sha256"]
    assert accepted["vm_program_counter"] == program["win_loop_address"]
    assert accepted["copyright_or_firmware_bytes_copied"] is False
    assert accepted["real_hardware_tested"] is False
    assert accepted["input_events_used"] == len(program["shortest_path_keys"])
    assert len(accepted["display_sha256"]) == 64
    assert compile_chip8_homebrew(capsule) == program
    assert verify_chip8_executable(program) == accepted


def test_vm_game_really_stops_against_wall_and_waits_for_controller_input():
    project = compile_chip8_homebrew(_original_capsule(42))
    vm = Chip8Machine(project["rom"])
    before = vm.run_until_wait()
    assert before["waiting_for_key"] is True
    assert before["registers"][3] == project["initial_state"]
    initial_screen = before["display_sha256"]
    # The spawn is (1, 1), so moving left runs into the border wall.
    rejected_move = vm.run_until_wait(key=4)
    assert rejected_move["registers"][3] == project["initial_state"]
    assert rejected_move["waiting_for_key"] is True
    assert rejected_move["rom_sha256"] == project["rom_sha256"]
    assert rejected_move["display_sha256"] == initial_screen


def test_original_game_rom_changes_with_seed_and_remains_independently_replayable():
    games = [
        compile_chip8_homebrew(_original_capsule(seed))
        for seed in range(8)
    ]
    assert len({game["rom_sha256"] for game in games}) >= 7
    for game in games:
        assert verify_chip8_executable(game)["win_state_reached"]


@pytest.mark.parametrize("seed", [True, -1, 2**31, "7", 1.2])
def test_seed_input_is_not_silently_coerced_or_overextended(seed):
    with pytest.raises(Chip8ExportError):
        _original_capsule(seed)


def test_chip8_is_fail_closed_for_invalid_opcode_and_bad_keyboard_event():
    vm = Chip8Machine(b"\x00\x00")
    with pytest.raises(Chip8Error, match="unsupported"):
        vm.step()
    vm = Chip8Machine(b"\xF2\x0A")
    with pytest.raises(Chip8Error):
        vm.step(key=16)
    with pytest.raises(Chip8Error):
        vm.run_until_wait(max_instructions=0)
    assert vm.step()["waiting_for_key"] is True
    assert vm.step(key=4)["registers"][2] == 4


def test_chip8_rom_output_is_a_real_bounded_executable_file_and_idempotent(
    tmp_path: Path, capsys,
):
    first = tmp_path / "first.ch8"
    second = tmp_path / "second.ch8"
    assert chip8_export([
        "--demo-rom", "--seed", "42", "--output", str(first),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["target"] == "chip8-vip"
    assert receipt["acceptance"]["win_state_reached"] is True
    assert receipt["boot_rom_embedded"] is False
    assert receipt["licensed_sdk_embedded"] is False
    assert receipt["legal_publication_approved"] is False
    assert receipt["copyright_compliance_certified"] is False
    assert receipt["training_examples_added"] == 0
    rom = first.read_bytes()
    assert len(rom) <= 3584
    assert receipt["rom_sha256"] == hashlib.sha256(rom).hexdigest()
    assert chip8_export([
        "--demo-rom", "--seed", "42", "--output", str(second),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["rom_sha256"] == receipt["rom_sha256"]
    assert first.read_bytes() == second.read_bytes()
    assert chip8_export(["--demo-rom", "--output", str(first)]) == 1
    assert "new file" in capsys.readouterr().err


def test_original_rights_bound_capsule_can_be_exported_from_private_source(
    tmp_path: Path, capsys,
):
    source = tmp_path / "authored.json"
    source.write_text(json.dumps(_original_capsule(47)), encoding="utf-8")
    output = tmp_path / "authored.ch8"
    assert chip8_export([
        "--capsule", str(source), "--output", str(output),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["acceptance"]["win_state_reached"]
    assert result["source_capsule_sha256"]
    assert result["rom_bytes"] == len(output.read_bytes())


def test_modified_false_permission_cannot_be_converted_to_a_rom():
    project = _original_capsule(12)
    project["rights_receipt"]["source_kind_summary"] = ["licensed"]
    with pytest.raises(GameCapsuleError):
        compile_chip8_homebrew(project)
    project = _original_capsule(12)
    project["legal_release_authorized"] = True
    with pytest.raises(GameCapsuleError):
        compile_chip8_homebrew(project)


def test_chip8_compiler_rejects_unsupported_hardware_map_dimensions():
    from scripts.game.game_project import _demo
    with pytest.raises(Chip8ExportError, match="5-8"):
        compile_chip8_homebrew(_demo(1, ["chip8-vip"], "NO"))


def test_chip8_export_never_creates_or_modifies_training_data(tmp_path):
    bank = Path(__file__).resolve().parents[2] / (
        "skeleton/ai/training/datasets/offline_foundations_v1"
    )
    before = {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in bank.iterdir() if file.is_file()
    }
    chip8_export([
        "--demo-rom", "--output", str(tmp_path / "original.ch8"),
    ])
    assert before == {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in bank.iterdir() if file.is_file()
    }
