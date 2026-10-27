"""Transactional, encrypted memento publication under the SQLite conversation owner.

This is a conformance adapter, not a second conversation authority. It uses the
existing SQLiteConversationRepository connection and RLock so ciphertext and
the trusted CAS head commit or roll back together. Production Mongo needs an
equivalent owner-scoped majority-durable transaction/outbox.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import TYPE_CHECKING

from skeleton.context.sealed_memento import (
    ARCHIVE_WINDOW_MESSAGES,
    MementoCatalogHead,
    MementoRecord,
    SealedMementoArchive,
    decode_catalog_head,
    encode_catalog_head,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextLimitError,
    SealedContextReplayError,
)

if TYPE_CHECKING:
    from skeleton.persistence.conversation_repository import SQLiteConversationRepository

_MAX_READ_BYTES = 16 * 1024 * 1024


class MementoAuthorityConflict(SealedContextReplayError):
    """Stale version, missing evidence, or incompatible trusted head."""


@dataclass(frozen=True, slots=True)
class MementoReadPage:
    records: tuple[MementoRecord, ...]
    starting_head: MementoCatalogHead
    verified_head: MementoCatalogHead
    authoritative_head: MementoCatalogHead
    source_thread_version: int

    @property
    def has_more(self) -> bool:
        return self.verified_head.serial < self.authoritative_head.serial


def _fingerprint(archive: SealedMementoArchive) -> str:
    b = archive.binding
    raw = json.dumps(
        [b.tenant_id, b.owner_id, b.conversation_id, b.model_id, b.policy_id],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"skeleton.memento.binding.v1\x00" + raw).hexdigest()


class SQLiteMementoAuthority:
    """Append-only head/frame CAS embedded in the existing conversation database."""

    def __init__(self, conversation: SQLiteConversationRepository) -> None:
        if not all(hasattr(conversation, name) for name in (
            "_connection", "_lock", "namespace", "get_thread"
        )):
            raise TypeError("canonical SQLite conversation authority required")
        self.conversation = conversation
        with conversation._lock:
            conversation._connection.executescript("""
                CREATE TABLE IF NOT EXISTS conversation_memento_head (
                    namespace TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    binding_digest TEXT NOT NULL,
                    source_thread_version INTEGER NOT NULL,
                    head_blob BLOB NOT NULL,
                    PRIMARY KEY(namespace, thread_id),
                    FOREIGN KEY(namespace, thread_id)
                        REFERENCES conversation_thread(namespace, thread_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS conversation_memento_frame (
                    namespace TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    global_serial INTEGER NOT NULL CHECK(global_serial > 0),
                    stream TEXT NOT NULL CHECK(stream IN ('user', 'llm', 'work')),
                    ciphertext BLOB NOT NULL,
                    head_blob BLOB NOT NULL,
                    PRIMARY KEY(namespace, thread_id, global_serial),
                    FOREIGN KEY(namespace, thread_id)
                        REFERENCES conversation_thread(namespace, thread_id)
                        ON DELETE CASCADE
                );
            """)

    def _authorize(self, archive: SealedMementoArchive):
        b = archive.binding
        return self.conversation.get_thread(
            b.conversation_id, tenant_id=b.tenant_id, owner_id=b.owner_id
        )

    def _current(self, archive: SealedMementoArchive) -> MementoCatalogHead:
        b = archive.binding
        row = self.conversation._connection.execute(
            """SELECT binding_digest, head_blob FROM conversation_memento_head
               WHERE namespace=? AND thread_id=?""",
            (self.conversation.namespace, b.conversation_id),
        ).fetchone()
        if row is None:
            return MementoCatalogHead()
        if row["binding_digest"] != _fingerprint(archive):
            raise SealedContextBoundaryError("archive model/policy/owner binding drift")
        return decode_catalog_head(bytes(row["head_blob"]))

    def trusted_head(self, *, archive: SealedMementoArchive) -> MementoCatalogHead:
        """Fetch the trusted head from the authenticated repository, not a client."""
        with self.conversation._lock:
            self._authorize(archive)
            return self._current(archive)

    def publish(
        self, *, archive: SealedMementoArchive, expected_head: MementoCatalogHead,
        expected_thread_version: int, stream: str, ciphertext: bytes,
    ) -> MementoCatalogHead:
        """Atomically publish one verified frame and one advancing head.

        Every failure restores the previous DB state. Thread version drift
        rejects replay of a valid but stale context snapshot.
        """
        if not isinstance(archive, SealedMementoArchive) or not isinstance(
            expected_head, MementoCatalogHead
        ):
            raise SealedContextError("verified archive and trusted CAS head required")
        if type(expected_thread_version) is not int or expected_thread_version < 1:
            raise SealedContextError("positive canonical version required")
        if not isinstance(ciphertext, bytes) or len(ciphertext) > 4 * 1024 * 1024:
            raise SealedContextLimitError("bounded ciphertext frame required")
        b = archive.binding
        con = self.conversation._connection
        with self.conversation._lock:
            con.execute("BEGIN IMMEDIATE")
            try:
                thread = self._authorize(archive)
                if thread.version != expected_thread_version:
                    raise MementoAuthorityConflict("canonical thread version changed")
                if not thread.writable:
                    raise SealedContextBoundaryError("conversation is not writable")
                previous = self._current(archive)
                if previous != expected_head:
                    raise MementoAuthorityConflict("stale or conflicting memento head")
                record, next_head = archive.verify_append(
                    stream, ciphertext, previous=previous
                )
                if record.causal_serial is not None:
                    causal = con.execute(
                        """SELECT 1 FROM conversation_memento_frame
                           WHERE namespace=? AND thread_id=? AND global_serial=?""",
                        (self.conversation.namespace, b.conversation_id, record.causal_serial),
                    ).fetchone()
                    if causal is None:
                        raise MementoAuthorityConflict("unverified or missing causal predecessor")
                con.execute(
                    """INSERT INTO conversation_memento_frame
                       (namespace, thread_id, global_serial, stream, ciphertext, head_blob)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (self.conversation.namespace, b.conversation_id, record.serial,
                     stream, ciphertext, encode_catalog_head(next_head)),
                )
                if previous.serial == 0:
                    con.execute(
                        """INSERT INTO conversation_memento_head
                           (namespace, thread_id, binding_digest, source_thread_version, head_blob)
                           VALUES (?, ?, ?, ?, ?)""",
                        (self.conversation.namespace, b.conversation_id,
                         _fingerprint(archive), expected_thread_version,
                         encode_catalog_head(next_head)),
                    )
                else:
                    changed = con.execute(
                        """UPDATE conversation_memento_head
                           SET head_blob=?, source_thread_version=?
                           WHERE namespace=? AND thread_id=? AND head_blob=?
                           AND binding_digest=?""",
                        (encode_catalog_head(next_head), expected_thread_version,
                         self.conversation.namespace, b.conversation_id,
                         encode_catalog_head(previous), _fingerprint(archive)),
                    )
                    if changed.rowcount != 1:
                        raise MementoAuthorityConflict("memento compare-and-swap failed")
                con.execute("COMMIT")
                return next_head
            except BaseException:
                con.execute("ROLLBACK")
                raise

    def read_window(
        self, *, archive: SealedMementoArchive, after_serial: int = 0,
        limit: int = ARCHIVE_WINDOW_MESSAGES,
    ) -> MementoReadPage:
        """Reconstruct a contiguous, authenticated 2000-record archive page."""
        if type(after_serial) is not int or after_serial < 0:
            raise SealedContextLimitError("invalid read cursor")
        if type(limit) is not int or not 1 <= limit <= ARCHIVE_WINDOW_MESSAGES:
            raise SealedContextLimitError("archive read is capped at 2000 records")
        b = archive.binding
        con = self.conversation._connection
        with self.conversation._lock:
            con.execute("BEGIN")
            try:
                thread = self._authorize(archive)
                trusted = self._current(archive)
                if after_serial > trusted.serial:
                    raise MementoAuthorityConflict("read cursor exceeds trusted catalog")
                if after_serial:
                    checkpoint = con.execute(
                        """SELECT head_blob FROM conversation_memento_frame
                           WHERE namespace=? AND thread_id=? AND global_serial=?""",
                        (self.conversation.namespace, b.conversation_id, after_serial),
                    ).fetchone()
                    if checkpoint is None:
                        raise MementoAuthorityConflict("trusted resume checkpoint missing")
                    start = decode_catalog_head(bytes(checkpoint["head_blob"]))
                    if start.serial != after_serial:
                        raise MementoAuthorityConflict("resume checkpoint is inconsistent")
                else:
                    start = MementoCatalogHead()
                rows = con.execute(
                    """SELECT global_serial, stream, ciphertext, head_blob
                       FROM conversation_memento_frame
                       WHERE namespace=? AND thread_id=? AND global_serial>?
                       ORDER BY global_serial ASC LIMIT ?""",
                    (self.conversation.namespace, b.conversation_id, after_serial, limit),
                ).fetchall()
                if sum(len(row["ciphertext"]) for row in rows) > _MAX_READ_BYTES:
                    raise SealedContextLimitError("archive page exceeds 16 MiB budget")
                for serial, row in enumerate(rows, start=after_serial + 1):
                    if row["global_serial"] != serial:
                        raise MementoAuthorityConflict("archive contains a missing serial")
                finish = decode_catalog_head(bytes(rows[-1]["head_blob"])) if rows else start
                if not rows and start != trusted:
                    raise MementoAuthorityConflict("archive tail is missing")
                result = archive.replay(
                    ((row["stream"], bytes(row["ciphertext"])) for row in rows),
                    trusted_head=finish, starting_head=start, max_messages=limit,
                ) if rows else ()
                if finish.serial > trusted.serial:
                    raise MementoAuthorityConflict("archive checkpoint beyond trusted catalog")
                if finish.serial == trusted.serial and finish != trusted:
                    raise MementoAuthorityConflict("archive tail disagrees with trusted head")
                con.execute("COMMIT")
                return MementoReadPage(result, start, finish, trusted, thread.version)
            except BaseException:
                con.execute("ROLLBACK")
                raise
