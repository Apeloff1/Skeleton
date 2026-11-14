"""Private memory database qualification (POSIX source tests, not device proof)."""
import asyncio
import os

import pytest

from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteUnavailable
from skeleton.frontier.runtime.memory_adapters import SQLiteCollection

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="private POSIX directory custody required",
)


def directory(tmp_path):
    path = tmp_path / "private"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


@pytest.mark.asyncio
async def test_private_collection_cross_thread_and_reopen(tmp_path):
    path = directory(tmp_path)
    with SQLiteCollection.from_private_database(path, create=True) as store:
        await asyncio.to_thread(store.add, ids=["one"], documents=["hello"], metadatas=[{}])
        assert await asyncio.to_thread(store.count) == 1
        assert (path / "frontier-memory.db").stat().st_mode & 0o777 == 0o600
    with SQLiteCollection.from_private_database(path) as reopened:
        assert reopened.get()["documents"] == ["hello"]
        reopened.delete(ids=["one"])
        assert reopened.count() == 0


def test_replaced_private_path_fences_reads_and_writes(tmp_path):
    path = directory(tmp_path)
    with SQLiteCollection.from_private_database(path, create=True) as store:
        old = path / "frontier-memory.db"
        old.rename(path / "displaced.db")
        old.touch(mode=0o600)
        with pytest.raises(PrivateSQLiteUnavailable):
            store.get()
        with pytest.raises(PrivateSQLiteUnavailable):
            store.add(ids=["one"], documents=["hello"], metadatas=[{}])


def test_private_collection_refuses_shared_directory_and_implicit_creation(tmp_path):
    path = directory(tmp_path)
    with pytest.raises(OSError):
        SQLiteCollection.from_private_database(path)
    assert not (path / "frontier-memory.db").exists()
    path.chmod(0o755)
    with pytest.raises(PrivateSQLiteUnavailable):
        SQLiteCollection.from_private_database(path, create=True)


def test_private_memory_rejects_relaxed_durability_and_page_policy(tmp_path):
    path = directory(tmp_path)
    with SQLiteCollection.from_private_database(path, create=True, max_database_bytes=1 << 20) as store:
        store._connection.execute("PRAGMA synchronous = OFF")
        with pytest.raises(PrivateSQLiteUnavailable, match="policy"):
            store.count()
        store._connection.execute("PRAGMA synchronous = FULL")
        assert store.count() == 0
        store._connection.execute("PRAGMA max_page_count = 100000")
        with pytest.raises(PrivateSQLiteUnavailable, match="policy"):
            store.add(ids=["a"], documents=["hello"], metadatas=[{}])


def test_inherited_collection_is_denied_before_lock_or_database_use(tmp_path, monkeypatch):
    path = directory(tmp_path)
    with SQLiteCollection.from_private_database(path, create=True) as store:
        original = os.getpid()
        with monkeypatch.context() as patch:
            patch.setattr(os, "getpid", lambda: original + 1)
            with pytest.raises(PrivateSQLiteUnavailable, match="inherited"):
                store.count()
            with pytest.raises(PrivateSQLiteUnavailable, match="inherited"):
                store._private_handle.assert_current()
            with pytest.raises(PrivateSQLiteUnavailable, match="inherited"):
                store.close()
        assert store.count() == 0
