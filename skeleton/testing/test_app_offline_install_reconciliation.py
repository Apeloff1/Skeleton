"""End-to-end original-game install, restart reconciliation, and gameplay."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_install_reconciliation import (
    reconcile_installed_game_archive,
)


@pytest.fixture
def installed_game(tmp_path, capsys):
    source = tmp_path / "source"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "reconcile-original",
        "--title", "Original Beacon", "--seed", "1731",
        "--output", str(source), "--trusted-local-operator",
    ]) == 0
    manifest = json.loads(capsys.readouterr().out)[
        "trusted_in_process_manifest_sha256"
    ]
    archive = tmp_path / "delivery.zip"
    assert run_app_cli([
        "studio-journey", "--package-existing", "--output", str(source),
        "--archive", str(archive), "--expected-manifest-sha256", manifest,
        "--trusted-local-operator",
    ]) == 0
    pin = json.loads(capsys.readouterr().out)["independent_archive_sha256"]
    installed = tmp_path / "installed"
    assert run_app_cli([
        "studio-journey", "--install-archive", "--archive", str(archive),
        "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest,
        "--output", str(installed), "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    return installed, archive, pin, manifest


def args(installed, archive, pin, manifest):
    return [
        "studio-journey", "--reconcile-install", "--output", str(installed),
        "--archive", str(archive), "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]


def test_reconcile_then_play_read_only(installed_game, tmp_path, capsys):
    installed, archive, pin, manifest = installed_game
    before = (installed / "release.json").read_bytes(), archive.read_bytes()
    assert run_app_cli(args(installed, archive, pin, manifest)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["matched_source_files"] > 1
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert before == ((installed / "release.json").read_bytes(), archive.read_bytes())
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(installed),
        "--expected-manifest-sha256", manifest, "--moves", "up,right",
        "--save", str(tmp_path / "progress.json"), "--trusted-local-operator",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["action_count"] == 2


@pytest.mark.parametrize("fault", [
    "wrong_archive_pin", "wrong_manifest_pin", "archive_tamper", "source_tamper",
])
def test_rejects_wrong_pins_and_tampering(installed_game, capsys, fault):
    installed, archive, pin, manifest = installed_game
    if fault == "wrong_archive_pin":
        pin = "0" * 64
    elif fault == "wrong_manifest_pin":
        manifest = "0" * 64
    elif fault == "archive_tamper":
        archive.write_bytes(archive.read_bytes() + b"tampered")
    else:
        (installed / "index.html").write_bytes(b"tampered")
    assert run_app_cli(args(installed, archive, pin, manifest)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_symlinked_installed_root_is_rejected(installed_game, tmp_path, capsys):
    installed, archive, pin, manifest = installed_game
    alias = tmp_path / "alias"
    alias.symlink_to(installed, target_is_directory=True)
    assert run_app_cli(args(alias, archive, pin, manifest)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("extra", [
    ["--install-archive"], ["--play-existing"], ["--onboard"],
    ["--migrate-progress"], ["--preflight-migration"],
    ["--check-archive-save"], ["--verify-existing"],
    ["--moves", "up"], ["--save", "new.json"],
    ["--receipt", "receipt.json"], ["--mirror-attempts", "65"],
])
def test_rejects_mode_mixing(installed_game, capsys, extra):
    installed, archive, pin, manifest = installed_game
    assert run_app_cli(args(installed, archive, pin, manifest) + extra) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_explicit_operator_acknowledgement_required(installed_game, capsys):
    installed, archive, pin, manifest = installed_game
    command = args(installed, archive, pin, manifest)
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_detects_archive_replacement_during_reconciliation(installed_game, monkeypatch):
    installed, archive, pin, manifest = installed_game
    from skeleton.app import offline_install_reconciliation as module
    original = module.inspect_offline_game_archive
    calls = 0

    def change_after_comparison(*a, **kw):
        nonlocal calls
        calls += 1
        if calls == 2:
            archive.write_bytes(archive.read_bytes() + b"replacement")
        return original(*a, **kw)

    monkeypatch.setattr(module, "inspect_offline_game_archive", change_after_comparison)
    with pytest.raises(ValueError):
        reconcile_installed_game_archive(
            installed, archive, expected_archive_sha256=pin,
            expected_manifest_sha256=manifest, authorized=True,
        )

def test_same_byte_archive_inode_swap_is_not_accepted(installed_game, monkeypatch):
    installed, archive, pin, manifest = installed_game
    from skeleton.app import offline_install_reconciliation as module
    original_read = module._read_private_archive

    def swap_with_identical_bytes(path):
        raw = original_read(path)
        replacement = archive.with_name("same-bytes.zip")
        replacement.write_bytes(raw)
        replacement.chmod(0o600)
        os.replace(replacement, archive)
        return raw

    monkeypatch.setattr(module, "_read_private_archive", swap_with_identical_bytes)
    with pytest.raises(module.OfflineInstallReconciliationError):
        module.reconcile_installed_game_archive(
            installed, archive, expected_archive_sha256=pin,
            expected_manifest_sha256=manifest, authorized=True,
        )
