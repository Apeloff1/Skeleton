"""Backup custody tests never require Docker and never modify a real volume."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

from scripts import chroma_backup


def _existing(*, running: bool = False, identity: str = "c" * 64):
    return [{
        "Id": identity,
        "Name": "/tutolage-chroma",
        "State": {
            "Status": "running" if running else "exited",
            "Running": running, "Restarting": False,
            "StartedAt": "2026-10-31T00:00:00Z",
            "FinishedAt": "2026-10-31T00:01:00Z",
        },
        "RestartCount": 0,
        "Config": {"Image": "chromadb/chroma:latest@sha256:reviewed"},
        "Mounts": [{"Destination": "/chroma/chroma", "Type": "volume", "Name": "skeleton_chroma_data"}],
    }]


def test_two_stopped_legacy_stores_are_backed_up_without_mutating_docker(tmp_path, monkeypatch):
    calls = []
    def fake_docker(*args):
        calls.append(args)
        if args[0] == "inspect":
            return json.dumps(_existing())
        assert args[0] == "cp"
        assert args[1] in {
            "tutolage-chroma:/data/.",
            "tutolage-chroma:/chroma/chroma/.",
        }
        name = "chroma.sqlite3" if args[1].startswith("tutolage-chroma:/data/") else "legacy.txt"
        Path(args[2], name).write_bytes(b"known-backup-byte")
        return ""

    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    dest = tmp_path / "preserved-chroma"
    manifest = chroma_backup.backup_legacy_chroma(dest)
    assert [call[0] for call in calls] == ["inspect", "cp", "cp", "inspect"]
    assert dest.is_dir()
    assert manifest["release_accepted"] is False
    assert manifest["migration_complete"] is False
    assert manifest["source_container_id"] == "c" * 64
    assert {x["path"] for x in manifest["files"]} == {
        "container-data/chroma.sqlite3", "legacy-volume/legacy.txt",
    }
    assert all(x["sha256"] == sha256(b"known-backup-byte").hexdigest() for x in manifest["files"])
    assert json.loads((dest / "manifest.json").read_text()) == manifest
    assert dest.stat().st_mode & 0o077 == 0
    verified = chroma_backup.verify_backup(dest)
    assert verified["matches_manifest"] is True
    assert verified["database_integrity_verified"] is False
    assert verified["migration_complete"] is False


def test_running_container_is_rejected_before_copy(tmp_path, monkeypatch):
    calls = []
    def fake_docker(*args):
        calls.append(args)
        return json.dumps(_existing(running=True))
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    with pytest.raises(chroma_backup.BackupRejected, match="stop"):
        chroma_backup.backup_legacy_chroma(tmp_path / "backup")
    assert calls == [("inspect", "tutolage-chroma")]
    assert not (tmp_path / "backup").exists()


def test_container_replacement_during_copy_rejects_completed_manifest(tmp_path, monkeypatch):
    inspections = 0
    def fake_docker(*args):
        nonlocal inspections
        if args[0] == "inspect":
            inspections += 1
            return json.dumps(_existing(identity=("c" if inspections == 1 else "d") * 64))
        Path(args[2], "sample.txt").write_text("preserved")
        return ""
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    with pytest.raises(chroma_backup.BackupRejected, match="changed"):
        chroma_backup.backup_legacy_chroma(tmp_path / "backup")
    assert not (tmp_path / "backup").exists()


def test_restart_between_copies_is_detected(tmp_path, monkeypatch):
    inspections = 0
    def fake_docker(*args):
        nonlocal inspections
        if args[0] == "inspect":
            inspections += 1
            info = _existing()
            if inspections == 2:
                info[0]["State"]["StartedAt"] = "2026-10-31T00:02:00Z"
                info[0]["State"]["FinishedAt"] = "2026-10-31T00:03:00Z"
            return json.dumps(info)
        Path(args[2], "sample.txt").write_text("preserved")
        return ""
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    with pytest.raises(chroma_backup.BackupRejected, match="changed"):
        chroma_backup.backup_legacy_chroma(tmp_path / "backup")
    assert not (tmp_path / "backup").exists()


@pytest.mark.parametrize("destination", ["/data", "/data/nested", "/chroma/chroma/nested"])
def test_shadow_mounts_are_rejected_before_copy(tmp_path, monkeypatch, destination):
    info = _existing()
    info[0]["Mounts"].append({"Destination": destination, "Type": "bind"})
    calls = []
    def fake_docker(*args):
        calls.append(args)
        return json.dumps(info)
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    with pytest.raises(chroma_backup.BackupRejected, match="mounts"):
        chroma_backup.backup_legacy_chroma(tmp_path / "backup")
    assert calls == [("inspect", "tutolage-chroma")]


def test_concurrent_destination_is_not_replaced(tmp_path, monkeypatch):
    destination = tmp_path / "backup"
    def fake_docker(*args):
        if args[0] == "inspect":
            return json.dumps(_existing())
        Path(args[2], "sample.txt").write_text("preserved")
        return ""
    real_manifest = chroma_backup._manifest_files
    def concurrent_destination(staging):
        result = real_manifest(staging)
        destination.mkdir()
        return result
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    monkeypatch.setattr(chroma_backup, "_manifest_files", concurrent_destination)
    with pytest.raises(chroma_backup.BackupRejected, match="already exists"):
        chroma_backup.backup_legacy_chroma(destination)
    assert destination.is_dir()
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("mutation", ["changed", "added", "removed", "symlink", "duplicate_manifest_key"])
def test_verify_rejects_changed_or_unsafe_backup(tmp_path, monkeypatch, mutation):
    def fake_docker(*args):
        if args[0] == "inspect":
            return json.dumps(_existing())
        Path(args[2], "sample.txt").write_text("preserved")
        return ""
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    backup = tmp_path / "backup"
    chroma_backup.backup_legacy_chroma(backup)
    saved = backup / "container-data" / "sample.txt"
    if mutation == "changed":
        saved.write_text("different")
    elif mutation == "added":
        (backup / "unexpected.txt").write_text("unexpected")
    elif mutation == "removed":
        saved.unlink()
    elif mutation == "symlink":
        saved.unlink()
        saved.symlink_to(tmp_path / "outside")
    else:
        manifest = backup / "manifest.json"
        manifest.write_text(manifest.read_text().replace('{', '{"schema":"duplicate",', 1))
    with pytest.raises(chroma_backup.BackupRejected):
        chroma_backup.verify_backup(backup)


def test_symlinked_backup_ancestor_is_rejected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(chroma_backup.BackupRejected, match="symlink"):
        chroma_backup.backup_legacy_chroma(alias / "backup")


def test_verify_cli_does_not_contact_docker(tmp_path, monkeypatch, capsys):
    def fake_docker(*args):
        if args[0] == "inspect":
            return json.dumps(_existing())
        Path(args[2], "sample.txt").write_text("preserved")
        return ""
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    backup = tmp_path / "backup"
    chroma_backup.backup_legacy_chroma(backup)
    def forbidden_docker(*args):
        raise AssertionError("verification must not contact Docker")
    monkeypatch.setattr(chroma_backup, "_docker", forbidden_docker)
    monkeypatch.setattr(sys, "argv", ["chroma_backup.py", "--verify", str(backup)])
    assert chroma_backup.main() == 0
    assert json.loads(capsys.readouterr().out)["matches_manifest"] is True


def test_symlink_or_existing_target_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(chroma_backup.BackupRejected, match="already exists"):
        chroma_backup.backup_legacy_chroma(target)

    def fake_docker(*args):
        if args[0] == "inspect":
            return json.dumps(_existing())
        (Path(args[2]) / "escape").symlink_to(tmp_path)
        return ""
    monkeypatch.setattr(chroma_backup, "_docker", fake_docker)
    with pytest.raises(chroma_backup.BackupRejected, match="link"):
        chroma_backup.backup_legacy_chroma(tmp_path / "backup")
    assert not (tmp_path / "backup").exists()
