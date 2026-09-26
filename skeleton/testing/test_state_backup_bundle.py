from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from pathlib import Path

import pytest

from scripts import state_backup_bundle as backup


def _create_db(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS authority "
            "(id TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO authority(id, value) VALUES (?, ?)",
            ("record-1", value),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_required_bundle(source: Path) -> None:
    policy = backup._load_policy(backup.DEFAULT_POLICY)
    for index, store in enumerate(policy["stores"]):
        if store["required"]:
            _create_db(
                source / store["file"],
                f"value-{index}",
            )


def test_backup_and_verify_required_sqlite_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "backup"
    _seed_required_bundle(source)

    manifest = backup.create_backup(
        source,
        destination,
        created_at=datetime(
            2026,
            9,
            26,
            3,
            0,
            tzinfo=timezone.utc,
        ),
    )
    verified = backup.verify_backup(destination)

    assert manifest["format"] == "state-backup-manifest.v1"
    assert manifest["bundle_digest"] == verified["bundle_digest"]
    assert verified["status"] == "verified"
    assert verified["store_count"] == 7
    assert {
        entry["id"]
        for entry in verified["stores"]
    } == {
        "operation-state",
        "engine-execution",
        "engine-submissions",
        "engine-tool-receipts",
        "engine-quota",
        "engine-pressure",
        "governance-lifecycle",
    }
    assert all(
        entry["sqlite_integrity"] == "ok"
        for entry in verified["stores"]
    )


def test_backup_includes_optional_operation_stream_when_present(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "backup"
    _seed_required_bundle(source)
    _create_db(source / "operation_stream.sqlite", "stream")

    manifest = backup.create_backup(source, destination)

    assert any(
        entry["id"] == "operation-stream"
        for entry in manifest["stores"]
    )
    assert backup.verify_backup(destination)["store_count"] == 8


def test_backup_fails_closed_when_required_store_is_missing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "backup"
    _seed_required_bundle(source)
    (source / "engine_quota.sqlite").unlink()

    with pytest.raises(
        backup.StateBackupError,
        match="required state store is missing",
    ):
        backup.create_backup(source, destination)


def test_verify_detects_backup_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "backup"
    _seed_required_bundle(source)
    backup.create_backup(source, destination)

    target = destination / "engine_execution.sqlite"
    conn = sqlite3.connect(target)
    try:
        conn.execute(
            "UPDATE authority SET value = 'tampered' WHERE id = 'record-1'"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(
        backup.StateBackupError,
        match="verification mismatch",
    ):
        backup.verify_backup(destination)


def test_policy_declares_restore_order_and_retention_floor() -> None:
    policy = backup._load_policy(backup.DEFAULT_POLICY)

    stores = sorted(
        policy["stores"],
        key=lambda item: item["restore_order"],
    )
    assert stores[0]["id"] == "operation-state"
    assert stores[-1]["id"] == "operation-stream"
    assert policy["retention"]["minimum_verified_snapshots"] >= 2
    assert policy["retention"]["prune_requires_newer_verified_snapshot"] is True
