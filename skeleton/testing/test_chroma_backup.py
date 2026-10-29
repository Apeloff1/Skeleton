"""Backup custody tests never require Docker and never modify a real volume."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts import chroma_backup


def _existing(*, running: bool = False, identity: str = "c" * 64):
    return [{
        "Id": identity,
        "Name": "/tutolage-chroma",
        "State": {
            "Status": "running" if running else "exited",
            "Running": running, "Restarting": False,
        },
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
