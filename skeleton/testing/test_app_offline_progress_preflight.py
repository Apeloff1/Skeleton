"""Preflight is read-only, and never claims to replay a save or reserve a path."""
from __future__ import annotations

import json
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.testing.test_app_offline_progress_migration import (
    _journey, _save, _package, _migrate,
)


def _preflight(archive, archive_pin, pin, save, save_pin, destination, migrated):
    args = _migrate(archive, archive_pin, pin, save, save_pin, destination, migrated)
    args[args.index("--migrate-progress")] = "--preflight-migration"
    return args


def test_pinned_preflight_does_not_create_installation_or_save(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    destination, migrated = tmp_path / "new-install", tmp_path / "new-save.json"
    assert run_app_cli(_preflight(
        archive, archive_pin, pin, save, save_pin, destination, migrated,
    )) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["archive_integrity_verified"] is True
    assert receipt["private_save_integrity_verified"] is True
    assert receipt["save_world_binding_verified"] is True
    assert receipt["destination_reserved"] is False
    assert receipt["private_save_replayed"] is True
    assert receipt["source_gameplay_reexecuted_from_archive"] is False
    assert receipt["release_certified"] is False
    assert not destination.exists()
    assert not migrated.exists()


@pytest.mark.parametrize("bad", ["archive", "manifest", "save"])
def test_bad_pin_fails_preflight_without_publication(tmp_path, capsys, bad):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    pins = {"archive": archive_pin, "manifest": pin, "save": save_pin}
    pins[bad] = "0" * 64
    destination, migrated = tmp_path / "new-install", tmp_path / "new-save.json"
    assert run_app_cli(_preflight(
        archive, pins["archive"], pins["manifest"],
        save, pins["save"], destination, migrated,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not destination.exists()
    assert not migrated.exists()


def test_preflight_rejects_existing_destination_and_mode_mix(tmp_path, capsys):
    source, pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, pin)
    archive, archive_pin = _package(tmp_path, capsys, source, pin)
    destination, migrated = tmp_path / "new-install", tmp_path / "new-save.json"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("preserve")
    args = _preflight(
        archive, archive_pin, pin, save, save_pin, destination, migrated,
    )
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert sentinel.read_text() == "preserve"
    assert not migrated.exists()
    assert run_app_cli(args + ["--play-existing"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
