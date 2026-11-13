"""Read-only migrated game recovery with separately pinned source and save."""
from __future__ import annotations

import json
import pytest

from skeleton.app.cli import run_app_cli


def _prepare(tmp_path, capsys):
    source = tmp_path / "original-game"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "migration-recovery",
        "--title", "Original Compass", "--seed", "217",
        "--output", str(source), "--trusted-local-operator",
    ]) == 0
    pin = json.loads(capsys.readouterr().out)["trusted_in_process_manifest_sha256"]
    old_save = tmp_path / "old-save.json"
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(source),
        "--expected-manifest-sha256", pin, "--moves", "up,right",
        "--save", str(old_save), "--trusted-local-operator",
    ]) == 0
    save_pin = json.loads(capsys.readouterr().out)["independent_save_sha256"]
    archive = tmp_path / "original.zip"
    assert run_app_cli([
        "studio-journey", "--package-existing", "--output", str(source),
        "--expected-manifest-sha256", pin, "--archive", str(archive),
        "--trusted-local-operator",
    ]) == 0
    archive_pin = json.loads(capsys.readouterr().out)["independent_archive_sha256"]
    installed = tmp_path / "installed"
    migrated = tmp_path / "migrated-save.json"
    assert run_app_cli([
        "studio-journey", "--migrate-progress", "--output", str(installed),
        "--archive", str(archive), "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", pin, "--load-save", str(old_save),
        "--expected-save-sha256", save_pin, "--save", str(migrated),
        "--trusted-local-operator",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    return installed, migrated, pin, receipt["independent_migrated_save_sha256"], archive, archive_pin


def _recover(installed, migrated, pin, save_pin, *extra):
    return [
        "studio-journey", "--reconcile-migration", "--output", str(installed),
        "--load-save", str(migrated), "--expected-manifest-sha256", pin,
        "--expected-save-sha256", save_pin, "--trusted-local-operator", *extra,
    ]


def test_recovery_reexecutes_and_preserves_source_and_private_save(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    source_bytes = (installed / "release.json").read_bytes()
    save_bytes = save.read_bytes()
    assert run_app_cli(_recover(
        installed, save, pin, save_pin, "--archive", str(archive),
        "--expected-archive-sha256", archive_pin,
    )) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["action_count"] == 2
    assert result["read_only"] is True
    assert result["private_save_replayed"] is True
    assert result["original_archive_integrity_verified"] is True
    assert result["migration_atomicity_proven"] is False
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert save.read_bytes() == save_bytes
    assert (installed / "release.json").read_bytes() == source_bytes


def test_recovery_without_original_archive_does_not_claim_archive_proof(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    assert run_app_cli(_recover(installed, save, pin, save_pin)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["original_archive_integrity_verified"] is False
    assert result["archive_sha256"] is None


@pytest.mark.parametrize("bad", ["manifest", "save", "archive"])
def test_wrong_independent_pin_fails_closed(tmp_path, capsys, bad):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    if bad == "manifest":
        pin = "0" * 64
    if bad == "save":
        save_pin = "0" * 64
    if bad == "archive":
        archive_pin = "0" * 64
    assert run_app_cli(_recover(
        installed, save, pin, save_pin, "--archive", str(archive),
        "--expected-archive-sha256", archive_pin,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_and_pin_must_be_supplied_together(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    assert run_app_cli(_recover(
        installed, save, pin, save_pin, "--archive", str(archive),
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(_recover(
        installed, save, pin, save_pin,
        "--expected-archive-sha256", archive_pin,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_tampered_installed_game_or_save_is_rejected(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    original_save = save.read_bytes()
    save.write_bytes(original_save + b" ")
    assert run_app_cli(_recover(installed, save, pin, save_pin)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    # Restore the independently pinned private save before separately testing
    # source tampering; otherwise this test would never reach source custody.
    save.write_bytes(original_save)
    (installed / "index.html").write_text("tampered")
    assert run_app_cli(_recover(installed, save, pin, save_pin)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_recovery_rejects_mutating_gameplay_options(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    assert run_app_cli(_recover(
        installed, save, pin, save_pin, "--moves", "up",
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_reconciliation_rejects_alias_of_private_save(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    alias = tmp_path / "save-alias.json"
    alias.symlink_to(save)
    assert run_app_cli(_recover(installed, alias, pin, save_pin)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_reconciliation_rejects_save_publication_or_gameplay_flags(tmp_path, capsys):
    installed, save, pin, save_pin, archive, archive_pin = _prepare(tmp_path, capsys)
    assert run_app_cli(_recover(
        installed, save, pin, save_pin, "--save", str(tmp_path / "new.json"),
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not (tmp_path / "new.json").exists()
