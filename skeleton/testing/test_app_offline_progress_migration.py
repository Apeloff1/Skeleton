"""Full first-playable -> save -> archive -> fresh install -> replay migration."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.app.cli import run_app_cli


def _journey(tmp_path, capsys, project="migrate-original", seed=431):
    source = tmp_path / (project + "-source")
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", project,
        "--title", "Original Starlight", "--seed", str(seed),
        "--output", str(source), "--trusted-local-operator",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    return source, receipt["trusted_in_process_manifest_sha256"]


def _package(tmp_path, capsys, source, pin):
    archive = tmp_path / "portable-game.zip"
    assert run_app_cli([
        "studio-journey", "--package-existing", "--output", str(source),
        "--archive", str(archive), "--expected-manifest-sha256", pin,
        "--trusted-local-operator",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    return archive, receipt["independent_archive_sha256"]


def _save(tmp_path, capsys, source, pin):
    save = tmp_path / "original-progress.json"
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(source),
        "--expected-manifest-sha256", pin, "--moves", "up,right,down",
        "--save", str(save), "--trusted-local-operator",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    return save, receipt["independent_save_sha256"], receipt["replay_digest"]


def _migrate(archive, archive_pin, pin, save, save_pin, destination, migrated):
    return [
        "studio-journey", "--migrate-progress",
        "--archive", str(archive),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", pin,
        "--load-save", str(save),
        "--expected-save-sha256", save_pin,
        "--output", str(destination), "--save", str(migrated),
        "--trusted-local-operator",
    ]


def test_original_game_migration_reexecutes_private_history(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, replay_digest = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    before = save.read_bytes()
    destination = tmp_path / "fresh-installed-game"
    migrated = tmp_path / "fresh-progress.json"
    assert run_app_cli(_migrate(
        archive, archive_pin, pin, save, save_pin, destination, migrated,
    )) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["replay_digest"] == replay_digest
    assert result["action_count"] == 3
    assert result["private_save_replayed"] is True
    assert result["migration_atomic_across_destinations"] is False
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert migrated.read_bytes() == before
    assert save.read_bytes() == before
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(destination),
        "--expected-manifest-sha256", pin,
        "--load-save", str(migrated),
        "--expected-save-sha256", result["independent_migrated_save_sha256"],
        "--moves", "left", "--trusted-local-operator",
    ]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["action_count"] == 4


@pytest.mark.parametrize("invalid", ["archive_pin", "manifest_pin", "save_pin"])
def test_invalid_independent_pins_fail_before_install(tmp_path, capsys, invalid):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    pins = {"archive_pin": archive_pin, "manifest_pin": pin, "save_pin": save_pin}
    pins[invalid] = "0" * 64
    destination = tmp_path / "should-not-exist"
    migrated = tmp_path / "should-not-exist.json"
    assert run_app_cli(_migrate(
        archive, pins["archive_pin"], pins["manifest_pin"],
        save, pins["save_pin"], destination, migrated,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not destination.exists()
    assert not migrated.exists()


def test_existing_install_and_save_collision_never_overwritten(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    destination = tmp_path / "occupied"
    destination.mkdir()
    (destination / "owner.txt").write_text("preserve")
    migrated = tmp_path / "migrated.json"
    assert run_app_cli(_migrate(
        archive, archive_pin, pin, save, save_pin, destination, migrated,
    )) == 2
    assert (destination / "owner.txt").read_text() == "preserve"
    assert not migrated.exists()
    clean = tmp_path / "clean-install"
    migrated.write_text("preserve")
    assert run_app_cli(_migrate(
        archive, archive_pin, pin, save, save_pin, clean, migrated,
    )) == 2
    assert migrated.read_text() == "preserve"
    assert not clean.exists()


def test_foreign_game_progress_rejected_without_new_save(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    foreign, foreign_pin = _journey(tmp_path, capsys, "different-original", 999)
    save, save_pin, _ = _save(tmp_path, capsys, foreign, foreign_pin)
    destination = tmp_path / "foreign-attempt"
    migrated = tmp_path / "foreign-progress.json"
    assert run_app_cli(_migrate(
        archive, archive_pin, pin, save, save_pin, destination, migrated,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not migrated.exists()
    # A foreign save is rejected by archive-bound preflight before mkdir.
    assert not destination.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_symlinked_progress_rejected_before_install(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    alias = tmp_path / "aliased-save.json"
    alias.symlink_to(save)
    destination = tmp_path / "not-created"
    assert run_app_cli(_migrate(
        archive, archive_pin, pin, alias, save_pin,
        destination, tmp_path / "new-progress.json",
    )) == 2
    assert not destination.exists()


def test_migration_options_rejected_in_unrelated_modes(tmp_path, capsys):
    assert run_app_cli([
        "studio-journey", "--migrate-progress", "--onboard",
        "--project-id", "x", "--title", "x", "--seed", "1",
        "--output", str(tmp_path / "x"), "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_migration_rejects_save_inside_installation_source(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    destination = tmp_path / "new-game"
    assert run_app_cli(_migrate(
        archive, archive_pin, pin, save, save_pin, destination,
        destination / "save.json",
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not destination.exists()


def test_migration_requires_explicit_operator_acknowledgement(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    destination = tmp_path / "not-authorized"
    args = _migrate(
        archive, archive_pin, pin, save, save_pin,
        destination, tmp_path / "not-authorized.json",
    )
    args.remove("--trusted-local-operator")
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not destination.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_migration_rejects_symlinked_archive_before_install(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    alias = tmp_path / "aliased-archive.zip"
    alias.symlink_to(archive)
    destination = tmp_path / "unpublished"
    assert run_app_cli(_migrate(
        alias, archive_pin, pin, save, save_pin,
        destination, tmp_path / "unpublished.json",
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not destination.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX inode custody")
@pytest.mark.parametrize("input_name", ["original_save", "archive"])
def test_same_bytes_inode_replacement_after_install_fails_closed(
    tmp_path, capsys, monkeypatch, input_name,
):
    from skeleton.app import offline_progress_migration as module

    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    destination = tmp_path / "new-install"
    migrated = tmp_path / "new-save.json"
    target = save if input_name == "original_save" else archive
    original = module.install_offline_game_source

    def replace_after_install(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / ("replacement-save.json" if input_name == "original_save"
                                  else "replacement-archive.zip")
        replacement.write_bytes(target.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, target)
        return receipt

    monkeypatch.setattr(module, "install_offline_game_source",
                        replace_after_install)
    with pytest.raises(module.OfflineProgressMigrationError):
        module.migrate_offline_game_progress(
            archive, destination,
            expected_archive_sha256=archive_pin,
            expected_manifest_sha256=pin,
            original_save=save, expected_save_sha256=save_pin,
            migrated_save=migrated, authorized=True,
        )
    # The already-published install is retained for quarantine; no second
    # publication should occur after an input inode replacement.
    assert destination.is_dir()
    assert not migrated.exists()
