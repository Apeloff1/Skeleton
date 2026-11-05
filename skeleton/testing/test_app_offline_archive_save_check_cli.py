"""CLI integration: archive/save replay without a destination or installation."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.testing.test_app_offline_progress_migration import (
    _journey, _package, _save,
)


def _args(archive, archive_pin, manifest_pin, save, save_pin):
    return [
        "studio-journey", "--check-archive-save",
        "--archive", str(archive),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest_pin,
        "--load-save", str(save),
        "--expected-save-sha256", save_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_standalone_check_replays_original_save_without_writing(tmp_path, capsys):
    source, manifest_pin = _journey(tmp_path, capsys)
    save, save_pin, replay_digest = _save(tmp_path, capsys, source, manifest_pin)
    archive, archive_pin = _package(tmp_path, capsys, source, manifest_pin)
    before = set(tmp_path.iterdir())
    archive_bytes, save_bytes = archive.read_bytes(), save.read_bytes()
    assert run_app_cli(_args(
        archive, archive_pin, manifest_pin, save, save_pin,
    )) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["replay_digest"] == replay_digest
    assert result["action_count"] == 3
    assert result["save_world_binding_verified"] is True
    assert result["private_save_replayed"] is True
    assert result["read_only"] is True
    assert result["destination_reserved"] is False
    assert result["native_device_qualified"] is False
    assert result["package_signed"] is False
    assert result["release_certified"] is False
    assert set(tmp_path.iterdir()) == before
    assert archive.read_bytes() == archive_bytes
    assert save.read_bytes() == save_bytes


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_standalone_check_rejects_foreign_save(tmp_path, capsys):
    source, manifest_pin = _journey(tmp_path, capsys)
    archive, archive_pin = _package(tmp_path, capsys, source, manifest_pin)
    foreign, foreign_manifest = _journey(tmp_path, capsys, "foreign", 912)
    save, save_pin, _ = _save(tmp_path, capsys, foreign, foreign_manifest)
    assert run_app_cli(_args(
        archive, archive_pin, manifest_pin, save, save_pin,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
@pytest.mark.parametrize("extra", [
    ["--output", "unwanted"], ["--onboard"],
    ["--preflight-migration"], ["--migrate-progress"],
    ["--moves", "up"], ["--save", "new-save.json"],
])
def test_standalone_check_rejects_mode_mixing(tmp_path, capsys, extra):
    source, manifest_pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, manifest_pin)
    archive, archive_pin = _package(tmp_path, capsys, source, manifest_pin)
    assert run_app_cli(_args(
        archive, archive_pin, manifest_pin, save, save_pin,
    ) + extra) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_standalone_check_rejects_missing_operator_ack(tmp_path, capsys):
    source, manifest_pin = _journey(tmp_path, capsys)
    save, save_pin, _ = _save(tmp_path, capsys, source, manifest_pin)
    archive, archive_pin = _package(tmp_path, capsys, source, manifest_pin)
    args = _args(archive, archive_pin, manifest_pin, save, save_pin)
    args.remove("--trusted-local-operator")
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
