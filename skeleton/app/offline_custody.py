"""Explicit local composition for the Academy and Frontier custody adapters.

No automatic data initialization, key generation, worker activation or network
access. Callers own authorization, app-account isolation and external rollback
anchors. Unsupported platforms fail closed in the canonical private opener.
"""
from __future__ import annotations

from contextlib import contextmanager
from os import PathLike

from skeleton.ai.model_runtime.private_sqlite import open_private_sqlite
from skeleton.frontier.durable_work import DurableWorkJournal
from skeleton.frontier.durable_outbox import DurableOutbox
from skeleton.frontier.worker_results import WorkerResultStore
from skeleton.learning.school.checkpoint_store import AcademyCheckpointStore


@contextmanager
def open_work_custody(directory: str | PathLike[str], *, scope: str,
                      custody_key: bytes, recovery_key: bytes, create: bool,
                      max_database_bytes: int = 96 << 20,
                      max_rows: int = 4096, max_payload_bytes: int = 64 << 20):
    """Own one authenticated journal and its outbox for the entire context."""
    if type(recovery_key) is not bytes or len(recovery_key) != 32:
        raise ValueError("independent recovery key required")
    if type(max_payload_bytes) is not int or not 4096 <= max_payload_bytes < max_database_bytes:
        raise ValueError("payload budget must leave room for SQLite overhead")
    with open_private_sqlite(directory, filename="frontier-work-orders.db",
                             create=create, max_database_bytes=max_database_bytes) as handle:
        journal = DurableWorkJournal(handle.connection, scope=scope,
                                     custody_key=custody_key, recovery_key=recovery_key,
                                     max_rows=max_rows, max_bytes=max_payload_bytes,
                                     private_handle=handle, initialize=create)
        try:
            yield journal, DurableOutbox(journal)
        finally:
            # Underlying descriptor/connection closure is guaranteed by the
            # enclosing context even if changed custody makes close fail.
            journal.close()


@contextmanager
def open_academy_custody(directory: str | PathLike[str], *, owner: str,
                         key: bytes, create: bool,
                         max_database_bytes: int = 96 << 20,
                         max_revisions: int = 256,
                         max_payload_bytes: int = 64 << 20):
    """Open an explicitly provisioned encrypted Academy checkpoint store."""
    if type(max_payload_bytes) is not int or not 4096 <= max_payload_bytes < max_database_bytes:
        raise ValueError("payload budget must leave room for SQLite overhead")
    with open_private_sqlite(directory, filename="academy-checkpoints.db",
                             create=create, max_database_bytes=max_database_bytes) as handle:
        store = AcademyCheckpointStore(handle.connection, owner=owner, key=key,
                                       max_revisions=max_revisions,
                                       max_total_bytes=max_payload_bytes,
                                       private_handle=handle, initialize=create)
        try:
            yield store
        finally:
            store.close()


@contextmanager
def open_worker_results(directory: str | PathLike[str], *, scope: str,
                        key: bytes, create: bool,
                        max_database_bytes: int = 96 << 20,
                        max_rows: int = 4096, max_payload_bytes: int = 64 << 20):
    """Separate private result database; no implicit creation on restart."""
    if type(max_payload_bytes) is not int or not 4096 <= max_payload_bytes < max_database_bytes:
        raise ValueError("result budget must leave room for SQLite overhead")
    with open_private_sqlite(directory, filename="frontier-worker-results.db",
                             create=create, max_database_bytes=max_database_bytes) as handle:
        store = WorkerResultStore(handle.connection, scope=scope, key=key, max_rows=max_rows,
                                  max_bytes=max_payload_bytes, private_handle=handle, initialize=create)
        try:
            yield store
        finally:
            store.close()
