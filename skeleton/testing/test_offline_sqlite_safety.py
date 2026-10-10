"""SQLite sidecar redirection must fail closed before opening a database."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from skeleton.app.offline_audit import OfflineAuditError, audit_database
from skeleton.app.offline_library import OfflineDocumentLibrary, OfflineLibraryError
from skeleton.app.offline_workspace import OfflineWorkspace, OfflineWorkspaceError
from skeleton.app.offline_index_queue import OfflineIndexQueue, OfflineQueueError
from skeleton.app.offline_snapshot import OfflineSnapshotError, create_snapshot
from skeleton.app.offline_sqlite_safety import (
    SIDECARS, UnsafeOfflineSqlitePath, check_sqlite_companion_paths,
)


@pytest.mark.parametrize("suffix", SIDECARS)
def test_database_clients_reject_symlinked_sqlite_sidecars(
    tmp_path: Path, suffix: str,
) -> None:
    victim = tmp_path / "unrelated-private-data.txt"
    victim.write_bytes(b"SECRET MUST REMAIN UNCHANGED")
    target = tmp_path / "local.sqlite"
    link = Path(str(target) + suffix)
    try:
        link.symlink_to(victim)
    except OSError:
        pytest.skip("host disallows symlink creation")
    for client, error in (
        (OfflineWorkspace, OfflineWorkspaceError),
        (OfflineDocumentLibrary, OfflineLibraryError),
        (OfflineIndexQueue, OfflineQueueError),
    ):
        with pytest.raises(error, match="companion"):
            client(target)
        assert not target.exists()
        assert victim.read_bytes() == b"SECRET MUST REMAIN UNCHANGED"


def test_snapshot_and_auditor_reject_symlinked_wal_input(
    tmp_path: Path,
) -> None:
    target = tmp_path / "chat.sqlite"
    with OfflineWorkspace(target) as db:
        db.open("default", "a" * 64)
    victim = tmp_path / "outside.txt"
    victim.write_bytes(b"DO NOT ALTER")
    sidecar = Path(str(target) + "-wal")
    sidecar.unlink(missing_ok=True)
    try:
        sidecar.symlink_to(victim)
    except OSError:
        pytest.skip("host disallows symlinks")
    with pytest.raises(OfflineAuditError, match="companion"):
        audit_database(target, "workspace")
    with pytest.raises(OfflineSnapshotError, match="companion"):
        create_snapshot(tmp_path / "portable", workspace=target)
    assert victim.read_bytes() == b"DO NOT ALTER"


def test_special_file_sidecar_is_not_admitted(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO not available")
    database = tmp_path / "database.sqlite"
    fifo = Path(str(database) + "-journal")
    os.mkfifo(fifo)
    with pytest.raises(UnsafeOfflineSqlitePath, match="companion"):
        check_sqlite_companion_paths(database)
    with pytest.raises(OfflineWorkspaceError, match="companion"):
        OfflineWorkspace(database)
