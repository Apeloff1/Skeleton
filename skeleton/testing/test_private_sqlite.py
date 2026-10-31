"""POSIX-only private SQLite opener security regressions.

These tests do not claim resistance to malicious processes sharing the app UID,
nor qualify encrypted disks, macOS/Windows devices or external CAS durability.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from skeleton.ai.model_runtime.private_sqlite import (
    PrivateSQLiteUnavailable, open_private_sqlite,
)
from skeleton.app.offline_dispatch_bridge import OfflineAdaptiveDispatchService

C, E, SESSION = b"c" * 32, b"e" * 32, "a" * 32


class SimulatedAnchor:
    def __init__(self):
        self.state = None

    def initialize(self, *, generation, digest):
        if self.state is not None:
            raise ValueError("anchor exists")
        self.state = (generation, digest)

    def read(self):
        if self.state is None:
            raise ValueError("missing anchor")
        return self.state

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.state != (expected_generation, expected_digest):
            raise ValueError("stale anchor")
        self.state = (generation, digest)


class UnusedOwner:
    def execute_and_commit(self, permit, state):
        raise AssertionError("no backend execution in opener tests")


@pytest.fixture
def private_dir(tmp_path):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("POSIX O_NOFOLLOW required")
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def test_create_then_restart_is_explicit_and_persistent(private_dir):
    with open_private_sqlite(private_dir, create=True) as opened:
        opened.connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        opened.connection.execute("INSERT INTO t VALUES (1, 'persisted')")
        assert opened.connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert opened.connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert opened.connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
    with open_private_sqlite(private_dir) as restarted:
        assert restarted.connection.execute("SELECT v FROM t").fetchone() == ("persisted",)


def test_reopen_missing_never_creates_a_database(private_dir):
    with pytest.raises(FileNotFoundError):
        open_private_sqlite(private_dir)
    assert list(private_dir.iterdir()) == []


def test_create_existing_refuses_overwrite(private_dir):
    with open_private_sqlite(private_dir, create=True):
        pass
    with pytest.raises(FileExistsError):
        open_private_sqlite(private_dir, create=True)


def test_private_directory_rejects_world_or_group_access(private_dir):
    private_dir.chmod(0o750)
    with pytest.raises(PrivateSQLiteUnavailable, match="private directory"):
        open_private_sqlite(private_dir, create=True)
    private_dir.chmod(0o700)


def test_parent_symlink_refused(private_dir, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(private_dir, target_is_directory=True)
    with pytest.raises(OSError):
        open_private_sqlite(alias, create=True)


def test_database_symlink_refused(private_dir, tmp_path):
    target = tmp_path / "victim"
    target.write_bytes(b"secret")
    (private_dir / "fair-stream.db").symlink_to(target)
    with pytest.raises(OSError):
        open_private_sqlite(private_dir)
    assert target.read_bytes() == b"secret"


def test_hardlinked_database_refused(private_dir, tmp_path):
    target = tmp_path / "original"
    target.write_bytes(b"anything")
    target.chmod(0o600)
    os.link(target, private_dir / "fair-stream.db")
    with pytest.raises(PrivateSQLiteUnavailable, match="inode"):
        open_private_sqlite(private_dir)
    assert target.read_bytes() == b"anything"


def test_unsafe_existing_permissions_refused(private_dir):
    path = private_dir / "fair-stream.db"
    path.write_bytes(b"")
    path.chmod(0o644)
    with pytest.raises(PrivateSQLiteUnavailable, match="inode"):
        open_private_sqlite(private_dir)


@pytest.mark.parametrize("filename", [
    "../escape.db", ".hidden.db", "nested/name.db", "a.db?mode=memory",
    "bad\x00.db", "no-extension", "x" * 90 + ".db",
])
def test_filename_boundary(private_dir, filename):
    with pytest.raises(ValueError, match="filename"):
        open_private_sqlite(private_dir, filename=filename, create=True)


@pytest.mark.parametrize("budget", [0, 100, 1 << 31, True, 1.5])
def test_byte_budget_rejected(private_dir, budget):
    with pytest.raises(ValueError, match="byte budget"):
        open_private_sqlite(private_dir, create=True, max_database_bytes=budget)


def test_no_relative_directory_traversal(private_dir):
    with pytest.raises(ValueError, match="relative"):
        open_private_sqlite(str(private_dir) + "/../private", create=True)


def test_closed_handle_is_idempotent(private_dir):
    handle = open_private_sqlite(private_dir, create=True)
    handle.close()
    handle.close()
    with pytest.raises(sqlite3.ProgrammingError):
        handle.connection.execute("SELECT 1")
    with pytest.raises(PrivateSQLiteUnavailable, match="closed"):
        handle.__enter__()


def test_app_bootstrap_wires_private_database_and_requires_anchor(private_dir):
    anchor = SimulatedAnchor()
    service, handle = OfflineAdaptiveDispatchService.from_private_database(
        directory=private_dir, custody_key=C, execution_key=E,
        session_id=SESSION, watermark=anchor, owner=UnusedOwner(),
        storage_path=str(private_dir), bootstrap=True,
    )
    try:
        assert service.status().generation == 0
        assert not service.status().quarantined
    finally:
        handle.close()
    resumed, handle = OfflineAdaptiveDispatchService.from_private_database(
        directory=private_dir, custody_key=C, execution_key=E,
        session_id=SESSION, watermark=anchor, owner=UnusedOwner(),
        storage_path=str(private_dir), bootstrap=False,
    )
    try:
        assert resumed.status().generation == 0
    finally:
        handle.close()


def test_failed_app_bootstrap_closes_owned_connection(private_dir):
    anchor = SimulatedAnchor()
    _, first = OfflineAdaptiveDispatchService.from_private_database(
        directory=private_dir, custody_key=C, execution_key=E,
        session_id=SESSION, watermark=anchor, owner=UnusedOwner(),
        storage_path=str(private_dir), bootstrap=True,
    )
    first.close()
    with pytest.raises(FileExistsError):
        OfflineAdaptiveDispatchService.from_private_database(
            directory=private_dir, custody_key=C, execution_key=E,
            session_id=SESSION, watermark=anchor, owner=UnusedOwner(),
            storage_path=str(private_dir), bootstrap=True,
        )
    # A failed create must not destroy or reset the prior durable row.
    with open_private_sqlite(private_dir) as opened:
        assert opened.connection.execute(
            "SELECT COUNT(*) FROM local_fair_stream_custody"
        ).fetchone() == (1,)


def test_live_handle_rejects_renamed_and_replaced_inode(private_dir):
    path = private_dir / "fair-stream.db"
    with open_private_sqlite(private_dir, create=True) as handle:
        handle.assert_current()
        path.rename(private_dir / "old.db")
        path.write_bytes(b"replacement")
        path.chmod(0o600)
        with pytest.raises(PrivateSQLiteUnavailable, match="inode replaced"):
            handle.assert_current()


def test_live_handle_rejects_permission_drift(private_dir):
    path = private_dir / "fair-stream.db"
    with open_private_sqlite(private_dir, create=True) as handle:
        path.chmod(0o640)
        with pytest.raises(PrivateSQLiteUnavailable, match="inode"):
            handle.assert_current()
        path.chmod(0o600)
        handle.assert_current()


def test_live_handle_rejects_hardlink_added_after_open(private_dir):
    path = private_dir / "fair-stream.db"
    with open_private_sqlite(private_dir, create=True) as handle:
        os.link(path, private_dir / "alias.db")
        with pytest.raises(PrivateSQLiteUnavailable, match="inode"):
            handle.assert_current()


def test_live_handle_rejects_directory_permission_drift(private_dir):
    with open_private_sqlite(private_dir, create=True) as handle:
        private_dir.chmod(0o750)
        with pytest.raises(PrivateSQLiteUnavailable, match="directory custody"):
            handle.assert_current()
        private_dir.chmod(0o700)
        handle.assert_current()
