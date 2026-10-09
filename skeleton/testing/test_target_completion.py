"""Completion gates and real frozen-console usage for original CHIP-8 games."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.game.verify_target_completion import (
    GATES, completion_overview, main as completion_cli, target_status,
)
from skeleton.ai.runtime.game_platform_catalog import TARGETS
from skeleton.app.offline_cli import main as offline_console
from skeleton.app.cli import run_app_cli


def test_full_era_catalog_completion_accounting_cannot_mark_stub_as_complete(capsys):
    status = completion_overview()
    assert status["counts"]["design_profiles"] == len(TARGETS)
    assert status["counts"]["design_profiles"] >= 166
    assert status["counts"]["source_or_bytecode_exporters_implemented"] == 1
    assert status["counts"]["platforms_fully_release_verified"] == 0
    assert status["counts"]["platforms_needing_release_proofs"] == len(TARGETS)
    assert status["counts"]["local_rom_execution_evidenced_in_this_run"] == 0
    assert status["completed_percent"] == 0
    assert status["scope_is_target_releases_not_internal_coding_tasks"]
    assert len(status["target_gate_sha256"]) == 64
    assert completion_cli([]) == 0
    assert json.loads(capsys.readouterr().out) == status


def test_completed_homebrew_compiler_still_needs_release_and_hardware_proofs():
    proof = target_status("chip8-vip", prove_local=True)
    assert proof["target"] == "chip8-vip"
    assert proof["native_exporter_code_present"] is True
    assert proof["local_proof"]["machine_interpreter_win_verified"] is True
    assert len(proof["local_proof"]["rom_sha256"]) == 64
    assert proof["gates"]["real_binary_or_source_emitter"] is True
    assert proof["gates"]["repeatable_deterministic_build"] is True
    assert proof["gates"]["in_repo_execution_verified"] is True
    assert proof["gates"]["human_release_signoff"] is False
    assert proof["gates"]["asset_rights_independently_verified"] is False
    assert proof["gates"]["release_ci_exact_head_success"] is False
    assert proof["full_target_release_completed"] is False
    assert proof["publish_or_license_approval"] is False
    assert proof["gate_count"] == len(GATES)
    assert set(proof["gates"]) == set(GATES)


def test_legacy_and_proprietary_targets_cannot_forge_exporter_support():
    for target in (
        "nes-famicom", "game-boy", "super-nintendo-snes",
        "sega-genesis-mega-drive", "playstation-1", "playstation-2",
        "original-xbox", "nintendo-switch", "playstation-5",
        "xbox-series-x", "nintendo-switch-2",
    ):
        proof = target_status(target, prove_local=True)
        assert proof["native_exporter_code_present"] is False
        assert proof["operationally_usable_homebrew_rom"] is False
        assert proof["full_target_release_completed"] is False
        assert proof["passed_gates"] == []
        assert proof["local_proof"] is None


def test_advertised_portability_evidence_requires_actual_codegen_and_vm_proof():
    overview = completion_overview(prove_chip8=True)
    assert overview["counts"]["local_rom_execution_evidenced_in_this_run"] == 1
    assert overview["counts"]["platforms_fully_release_verified"] == 0
    assert overview["completed_percent"] == 0


def test_original_chip8_rom_can_be_exported_with_frozen_and_unified_cli(
    tmp_path: Path, capsys,
):
    frozen = tmp_path / "frozen-original.ch8"
    unified = tmp_path / "unified-original.ch8"
    assert offline_console(["--chip8-demo-output", str(frozen)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["acceptance"]["win_state_reached"]
    assert receipt["licensed_sdk_embedded"] is False
    assert receipt["boot_rom_embedded"] is False
    assert frozen.exists()
    assert len(frozen.read_bytes()) == receipt["rom_bytes"]
    assert run_app_cli([
        "local-ai", "--chip8-demo-output", str(unified),
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["rom_sha256"] == receipt["rom_sha256"]
    assert unified.read_bytes() == frozen.read_bytes()
    assert second["training_examples_added"] == 0
    assert receipt["rom_sha256"] == hashlib.sha256(frozen.read_bytes()).hexdigest()


def test_chip8_export_rejects_conflicting_inference_and_state_changes(
    tmp_path: Path, capsys,
):
    out = str(tmp_path / "new.ch8")
    assert offline_console([
        "--chip8-demo-output", out, "--model", "some.gguf",
    ]) == 2
    import pytest
    with pytest.raises(SystemExit) as exited:
        offline_console([
            "--chip8-demo-output", out, "--game-preview-check",
        ])
    assert exited.value.code == 2  # argparse rejects mutually exclusive modes
    assert offline_console([
        "--chip8-demo-output", out, "--queue-status",
    ]) == 2
    assert offline_console([
        "--chip8-export-capsule", "x.json",
    ]) == 2
    assert offline_console([
        "--chip8-rom-output", out,
    ]) == 2
    assert not (tmp_path / "new.ch8").exists()
    assert capsys.readouterr().out == ""


def test_chip8_source_map_data_not_training_dataset(tmp_path: Path):
    data_bank = Path(__file__).resolve().parents[2] / (
        "skeleton/ai/training/datasets/offline_foundations_v1"
    )
    before = sorted(
        (path.name, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in data_bank.iterdir() if path.is_file()
    )
    assert offline_console(["--chip8-demo-output", str(tmp_path / "game.ch8")]) == 0
    after = sorted(
        (path.name, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in data_bank.iterdir() if path.is_file()
    )
    assert before == after
