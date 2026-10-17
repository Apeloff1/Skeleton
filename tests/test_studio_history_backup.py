"""Offline qualification backup checks with synthetic game-run receipts only."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.studio_campaign_lock import campaign_lock
from skeleton.ai.game_builder.studio_history_segments import seal_full_heads
from skeleton.ai.game_builder.studio_history_backup import (
    StudioHistoryBackupError, restore_studio_history, snapshot_studio_history,
    verify_studio_history_snapshot,
)
from skeleton.ai.game_builder.studio_execution_history import ENTRY_SCHEMA
from tests.test_studio_execution_history_segments import IDENTITY, chain, head


def test_snapshot_revalidates_segment_and_current_head(tmp_path):
    source = tmp_path / "campaign"
    source.mkdir()
    target = tmp_path / "backups"
    target.mkdir(mode=0o700)
    runs = chain(1, 65, None)
    with campaign_lock(source):
        segments, current = seal_full_heads(
            source, IDENTITY, [], runs, entry_schema=ENTRY_SCHEMA)
        head(source, current, segments)
    saved = snapshot_studio_history(source, target, name="checkpoint-001",
                                   identity=IDENTITY)
    assert saved["verified"]
    assert saved["historical_runs"] == 65
    assert saved["sealed_segments"] == 1
    assert saved["native_runtime_replayed"] is False
    assert verify_studio_history_snapshot(
        target, name="checkpoint-001", identity=IDENTITY) == saved
    with pytest.raises(StudioHistoryBackupError):
        snapshot_studio_history(source, target, name="checkpoint-001",
                                identity=IDENTITY)


def test_missing_segment_and_mutated_source_fail_closed(tmp_path):
    source = tmp_path / "campaign"
    source.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir(mode=0o700)
    head(source, chain(1, 3, None))
    snapshot_studio_history(source, backup, name="safe", identity=IDENTITY)
    journal = backup / "safe" / "qualification_history.json"
    journal.write_bytes(journal.read_bytes() + b" ")
    with pytest.raises(StudioHistoryBackupError):
        verify_studio_history_snapshot(backup, name="safe", identity=IDENTITY)
    with pytest.raises(StudioHistoryBackupError):
        verify_studio_history_snapshot(backup, name="../bad", identity=IDENTITY)


def test_snapshot_does_not_invent_empty_history(tmp_path):
    source = tmp_path / "campaign"
    source.mkdir()
    target = tmp_path / "backup"
    target.mkdir(mode=0o700)
    with pytest.raises(StudioHistoryBackupError):
        snapshot_studio_history(source, target, name="empty", identity=IDENTITY)

def test_symlinked_archive_segment_directory_is_not_a_valid_backup(tmp_path):
    source = tmp_path / "campaign"
    source.mkdir()
    backup = tmp_path / "private"
    backup.mkdir(mode=0o700)
    runs = chain(1, 65, None)
    with campaign_lock(source):
        segments, tail = seal_full_heads(
            source, IDENTITY, [], runs, entry_schema=ENTRY_SCHEMA,
        )
        head(source, tail, segments)
    snapshot_studio_history(source, backup, name="record", identity=IDENTITY)
    image = backup / "record"
    archive = image / "qualification_history_segments"
    real = image / "segments_relocated"
    archive.rename(real)
    archive.symlink_to(real, target_is_directory=True)
    with pytest.raises(StudioHistoryBackupError):
        verify_studio_history_snapshot(
            backup, name="record", identity=IDENTITY,
        )

def test_recovery_uses_new_directory_and_preserves_archive_chain(tmp_path):
    source = tmp_path / "production"
    source.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir(mode=0o700)
    runs = chain(1, 130, None)
    with campaign_lock(source):
        segments, tip = seal_full_heads(
            source, IDENTITY, [], runs, entry_schema=ENTRY_SCHEMA,
        )
        head(source, tip, segments)
    evidence = snapshot_studio_history(
        source, backup, name="month-1", identity=IDENTITY,
    )
    assert evidence["historical_runs"] == 130
    recovered = tmp_path / "recovered"
    report = restore_studio_history(
        backup, recovered, name="month-1", identity=IDENTITY,
    )
    assert report["backup_restored"] is True
    assert report["historical_runs"] == 130
    assert report["operator_reauthorization_required"] is True
    assert report["campaign_started_or_resumed"] is False
    from skeleton.ai.game_builder.studio_execution_history import _read_history
    assert _read_history(recovered, IDENTITY)["_archive_stats"]["archive_entry_count"] == 128
    assert (recovered / "qualification_history.json").is_file()
    assert sorted((recovered / "qualification_history_segments").glob("*.json"))
    with pytest.raises(StudioHistoryBackupError, match="replace"):
        restore_studio_history(
            backup, recovered, name="month-1", identity=IDENTITY,
        )
    # Source and immutable snapshot remain intact after restoration.
    assert verify_studio_history_snapshot(
        backup, name="month-1", identity=IDENTITY,
    ) == evidence


def test_recovery_rejects_tamper_and_preserves_absent_target(tmp_path):
    source = tmp_path / "production"
    source.mkdir()
    head(source, chain(1, 3, None))
    private = tmp_path / "backups"
    private.mkdir(mode=0o700)
    snapshot_studio_history(source, private, name="copy", identity=IDENTITY)
    target = tmp_path / "should-not-exist"
    journal = private / "copy" / "qualification_history.json"
    journal.write_bytes(journal.read_bytes() + b" ")
    with pytest.raises(StudioHistoryBackupError):
        restore_studio_history(
            private, target, name="copy", identity=IDENTITY,
        )
    assert not target.exists()


def test_recovery_never_replaces_symlink_or_existing_campaign(tmp_path):
    source = tmp_path / "production"
    source.mkdir()
    head(source, chain(1, 3, None))
    private = tmp_path / "backups"
    private.mkdir(mode=0o700)
    snapshot_studio_history(source, private, name="copy", identity=IDENTITY)
    claimed = tmp_path / "existing"
    claimed.mkdir()
    with pytest.raises(StudioHistoryBackupError, match="replace"):
        restore_studio_history(
            private, claimed, name="copy", identity=IDENTITY,
        )
    existing = tmp_path / "other"
    existing.mkdir()
    link = tmp_path / "link"
    link.symlink_to(existing, target_is_directory=True)
    with pytest.raises(StudioHistoryBackupError, match="replace"):
        restore_studio_history(
            private, link, name="copy", identity=IDENTITY,
        )

