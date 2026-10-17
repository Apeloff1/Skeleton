"""Offline qualification backup checks with synthetic game-run receipts only."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.studio_campaign_lock import campaign_lock
from skeleton.ai.game_builder.studio_history_segments import seal_full_heads
from skeleton.ai.game_builder.studio_history_backup import (
    StudioHistoryBackupError, snapshot_studio_history,
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
