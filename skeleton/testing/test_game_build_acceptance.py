"""Three real game outputs must actually execute; no empty release receipts."""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from scripts.game import accept_game_builds as acceptance


def test_all_implemented_game_outputs_are_executed_not_just_generated():
    if not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
        pytest.fail("P2 build-closure gate requires a real C89 compiler")
    one = acceptance.execute_all_available_game_acceptance()
    assert one["schema_version"] == "skeleton.game.executed_acceptance.v1"
    assert len(one["accepted_execution_targets"]) == 3
    assert one["portable_c89"]["compiled_and_actually_won"] is True
    assert len(one["portable_c89"]["compiled_binary_sha256"]) == 64
    assert one["chip8_original_rom"]["win_state_reached"] is True
    assert one["chip8_original_rom"]["machine_interpreter_used"] is True
    assert one["chip8_original_rom"]["rom_bytes"] > 64
    assert one["native_preview"]["terminal_won"] is True
    assert one["native_preview"]["frames_verified"] >= 16
    assert one["all_implemented_gameplay_outputs_executed"] is True
    assert one["full_166_platform_release_completion"] is False
    assert one["full_legal_publication_signoff"] is False
    assert one["training_examples_added"] == 0
    assert one["portable_c89"]["proprietary_sdk_used"] is False
    assert one["chip8_original_rom"]["legal_publication_approved"] is False
    assert one["native_preview"]["installed_windows_binary_verified"] is False
    # Compiler-generated binary identity can vary by compiler/site.
    # The game source/ROM and native-replay identities must be repeatable.
    second = acceptance.execute_all_available_game_acceptance()
    assert (
        one["portable_c89"]["source_sha256"]
        == second["portable_c89"]["source_sha256"]
    )
    assert (
        one["chip8_original_rom"]["rom_sha256"]
        == second["chip8_original_rom"]["rom_sha256"]
    )
    assert (
        one["native_preview"]["replay_sha256"]
        == second["native_preview"]["replay_sha256"]
    )


def test_gate_refuses_missing_compiler_instead_of_signing_a_fake_success(monkeypatch):
    monkeypatch.setattr(acceptance.shutil, "which", lambda cmd: None)
    with pytest.raises(acceptance.GameAcceptanceError, match="compiler"):
        acceptance.execute_all_available_game_acceptance()


def test_aggregate_game_acceptance_cli_emits_only_passed_receipts(capsys):
    assert acceptance.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["portable_c89"]["compiled_and_actually_won"] is True
    assert report["chip8_original_rom"]["win_state_reached"] is True
    assert report["native_preview"]["terminal_won"] is True
    assert report["full_166_platform_release_completion"] is False


def test_acceptance_does_not_load_licenses_roms_or_training_data():
    import inspect
    body = inspect.getsource(acceptance)
    assert "urllib" not in body
    assert "requests." not in body
    assert "pirated_rom" not in body
    assert "openai" not in body.lower()
    assert "skeleton.ai.training.datasets" not in body
