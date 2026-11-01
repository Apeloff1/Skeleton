"""End-to-end offline source game play, save, resume and fail-closed custody."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli


def _build(tmp_path, capsys, project="offline-game", seed=1729):
    root = tmp_path / (project + "-source")
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", project,
        "--title", "Original Lantern", "--seed", str(seed),
        "--output", str(root), "--trusted-local-operator",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    return root, receipt["trusted_in_process_manifest_sha256"]


def _play(root, pin, *options):
    return [
        "studio-journey", "--play-existing", "--output", str(root),
        "--expected-manifest-sha256", pin, "--trusted-local-operator",
        *options,
    ]


def test_actual_gameplay_save_restore_and_continue_without_source_mutation(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys)
    before = (root / "release.json").read_bytes()
    save = tmp_path / "game-save.json"
    assert run_app_cli(_play(root, pin, "--moves", "up,right", "--save", str(save))) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["action_count"] == 2
    assert first["final_state"]["steps"] == 2
    assert first["independent_save_sha256"]
    assert first["release_certified"] is False
    assert save.is_file()
    assert run_app_cli(_play(
        root, pin, "--load-save", str(save),
        "--expected-save-sha256", first["independent_save_sha256"],
        "--moves", "left,down",
    )) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["action_count"] == 4
    assert second["final_state"]["steps"] == 4
    assert second["replay_digest"] != first["replay_digest"]
    assert (root / "release.json").read_bytes() == before


def test_save_destination_collision_never_overwrites_owner_file(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys)
    target = tmp_path / "existing.json"
    target.write_text("preserve", encoding="utf-8")
    assert run_app_cli(_play(root, pin, "--moves", "up", "--save", str(target))) == 2
    assert target.read_text(encoding="utf-8") == "preserve"
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_save_tamper_and_independent_pin_mismatch_fail_closed(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys)
    save = tmp_path / "save.json"
    assert run_app_cli(_play(root, pin, "--moves", "right", "--save", str(save))) == 0
    result = json.loads(capsys.readouterr().out)
    assert run_app_cli(_play(
        root, pin, "--load-save", str(save),
        "--expected-save-sha256", "0" * 64,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    save.write_bytes(save.read_bytes() + b" ")
    assert run_app_cli(_play(
        root, pin, "--load-save", str(save),
        "--expected-save-sha256", result["independent_save_sha256"],
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_foreign_game_save_rejected_even_with_valid_independent_save_pin(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys, "alpha", 1729)
    foreign, foreign_pin = _build(tmp_path, capsys, "beta", 1729)
    save = tmp_path / "foreign.json"
    assert run_app_cli(_play(foreign, foreign_pin, "--moves", "up", "--save", str(save))) == 0
    foreign_receipt = json.loads(capsys.readouterr().out)
    assert run_app_cli(_play(
        root, pin, "--load-save", str(save),
        "--expected-save-sha256", foreign_receipt["independent_save_sha256"],
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("moves", ["up,fly", ",up", "up,", "UP", "up,,right", "right "])
def test_unsupported_moves_never_start_gameplay(tmp_path, capsys, moves):
    assert run_app_cli(_play(tmp_path / "missing", "a" * 64, "--moves", moves)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_save_symlink_and_source_tamper_are_rejected(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys)
    save = tmp_path / "save.json"
    assert run_app_cli(_play(root, pin, "--moves", "up", "--save", str(save))) == 0
    result = json.loads(capsys.readouterr().out)
    alias = tmp_path / "alias.json"
    alias.symlink_to(save)
    assert run_app_cli(_play(
        root, pin, "--load-save", str(alias),
        "--expected-save-sha256", result["independent_save_sha256"],
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    (root / "index.html").write_text("tampered", encoding="utf-8")
    assert run_app_cli(_play(root, pin, "--moves", "up")) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_gameplay_flags_are_not_accepted_by_other_journey_modes(tmp_path, capsys):
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "game",
        "--title", "Original", "--seed", "1", "--output", str(tmp_path / "new"),
        "--moves", "up", "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_fork_replay_preserves_original_save_and_supports_alternate_actions(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys)
    save = tmp_path / "original-save.json"
    forked_save = tmp_path / "forked-save.json"
    assert run_app_cli(_play(root, pin, "--moves", "up,right,down", "--save", str(save))) == 0
    first = json.loads(capsys.readouterr().out)
    original_bytes = save.read_bytes()
    assert run_app_cli(_play(
        root, pin, "--load-save", str(save),
        "--expected-save-sha256", first["independent_save_sha256"],
        "--fork-at", "1", "--moves", "left",
        "--save", str(forked_save),
    )) == 0
    alternative = json.loads(capsys.readouterr().out)
    assert alternative["action_count"] == 2
    assert alternative["final_state"]["steps"] == 2
    assert alternative["replay_digest"] != first["replay_digest"]
    assert save.read_bytes() == original_bytes
    assert forked_save.is_file()
    assert run_app_cli(_play(
        root, pin, "--load-save", str(forked_save),
        "--expected-save-sha256", alternative["independent_save_sha256"],
    )) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["replay_digest"] == alternative["replay_digest"]


@pytest.mark.parametrize("step", ["-1", "4", "9999"])
def test_invalid_replay_fork_rejected_without_overwriting_save(tmp_path, capsys, step):
    root, pin = _build(tmp_path, capsys)
    save = tmp_path / "original-save.json"
    assert run_app_cli(_play(root, pin, "--moves", "up", "--save", str(save))) == 0
    receipt = json.loads(capsys.readouterr().out)
    before = save.read_bytes()
    assert run_app_cli(_play(
        root, pin, "--load-save", str(save),
        "--expected-save-sha256", receipt["independent_save_sha256"],
        "--fork-at", step, "--moves", "down",
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert save.read_bytes() == before


@pytest.mark.parametrize("attack", ["group_readable", "hardlink", "symlink"])
def test_private_save_rejects_nonprivate_or_aliased_files(tmp_path, capsys, attack):
    root, pin = _build(tmp_path, capsys)
    save = tmp_path / "save.json"
    assert run_app_cli(_play(root, pin, "--moves", "up", "--save", str(save))) == 0
    result = json.loads(capsys.readouterr().out)
    target = save
    if attack == "group_readable":
        save.chmod(0o640)
    elif attack == "hardlink":
        target = tmp_path / "linked.json"
        target.hardlink_to(save)
    else:
        target = tmp_path / "symlinked.json"
        target.symlink_to(save)
    assert run_app_cli(_play(
        root, pin, "--load-save", str(target),
        "--expected-save-sha256", result["independent_save_sha256"],
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"



@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "mkfifo"),
                    reason="POSIX FIFO rejection contract")
def test_offline_save_restore_rejects_fifo_without_blocking(tmp_path, capsys):
    root, pin = _build(tmp_path, capsys)
    fifo = tmp_path / "not-a-regular-save.json"
    os.mkfifo(fifo, 0o600)
    assert run_app_cli(_play(
        root, pin, "--load-save", str(fifo),
        "--expected-save-sha256", "a" * 64,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
