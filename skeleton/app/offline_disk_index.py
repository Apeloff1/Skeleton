"""SQLite-backed, bounded-RAM local text indexing for low-memory machines.

Sources are streamed from no-follow file handles by the existing library.
Chunks are stored durably in SQLite and searchable through a separate FTS5
projection. Source digest, byte length, ordering, chunk bytes, and projected
search text are verified before any hit can become model context.
"""
from __future__ import annotations

from hashlib import sha256
import sqlite3


OVERLAP_CHARS = 128  # Retrieval seam overlap, not a document size quota.


def create_chunk_tables(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS offline_document_chunks (
        id INTEGER PRIMARY KEY,
        document_id INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        char_start INTEGER NOT NULL,
        body TEXT NOT NULL,
        body_sha256 TEXT NOT NULL,
        UNIQUE(document_id, ordinal)
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS offline_chunk_doc
        ON offline_document_chunks(document_id, ordinal)""")
    db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS offline_document_chunk_fts
        USING fts5(body, tokenize='unicode61')""")


def clear_chunks(db: sqlite3.Connection, document_id: int) -> None:
    db.execute(
        "DELETE FROM offline_document_chunk_fts WHERE rowid IN "
        "(SELECT id FROM offline_document_chunks WHERE document_id=?)",
        (document_id,),
    )
    db.execute(
        "DELETE FROM offline_document_chunks WHERE document_id=?", (document_id,)
    )


class DiskChunkWriter:
    """Ingest untrusted source pieces without a full-document Python string."""

    def __init__(self, db: sqlite3.Connection, document_id: int, chars: int):
        if chars < 256:
            raise ValueError("disk chunk buffer must fit valid UTF-8 text")
        self.db = db
        self.document_id = document_id
        self.chunk_chars = chars
        self.pending = ""
        self.tail = ""
        self.ordinal = 0
        self.char_start = 0

    def _emit(self, value: str) -> None:
        if not value:
            return
        cursor = self.db.execute(
            "INSERT INTO offline_document_chunks "
            "(document_id, ordinal, char_start, body, body_sha256) "
            "VALUES (?,?,?,?,?)",
            (
                self.document_id, self.ordinal, self.char_start, value,
                sha256(value.encode("utf-8")).hexdigest(),
            ),
        )
        # Retain only 128 characters of overlap at each seam for FTS recall.
        indexed = self.tail + value
        self.db.execute(
            "INSERT INTO offline_document_chunk_fts(rowid, body) VALUES (?,?)",
            (cursor.lastrowid, indexed),
        )
        self.tail = indexed[-OVERLAP_CHARS:]
        self.char_start += len(value)
        self.ordinal += 1

    def feed(self, value: str) -> None:
        self.pending += value
        while len(self.pending) >= self.chunk_chars:
            cut = self.pending.rfind(
                " ", max(1, self.chunk_chars // 2), self.chunk_chars
            )
            cut = cut + 1 if cut >= self.chunk_chars // 2 else self.chunk_chars
            self._emit(self.pending[:cut])
            self.pending = self.pending[cut:]

    def finish(self) -> int:
        self._emit(self.pending)
        self.pending = ""
        return self.ordinal


def verify_chunks(
    db: sqlite3.Connection, document_id: int, digest: str, size_bytes: int
) -> bool:
    """Verify *all* persisted segments, not just the FTS hit being returned.

    Cursor iteration stays O(single chunk) memory. This also checks a
    duplicated/corrupt/removed chunk and the derived FTS projection.
    """
    sha = sha256()
    ordinal = 0
    char_start = 0
    total_bytes = 0
    tail = ""
    rows = db.execute(
        "SELECT id, ordinal, char_start, body, body_sha256 "
        "FROM offline_document_chunks WHERE document_id=? ORDER BY ordinal",
        (document_id,),
    )
    for rowid, number, start, body, chunk_digest in rows:
        if (
            not isinstance(body, str)
            or number != ordinal or start != char_start
        ):
            return False
        encoded = body.encode("utf-8")
        if sha256(encoded).hexdigest() != chunk_digest:
            return False
        indexed = tail + body
        projection = db.execute(
            "SELECT body FROM offline_document_chunk_fts WHERE rowid=?", (rowid,)
        ).fetchone()
        if projection != (indexed,):
            return False
        sha.update(encoded)
        total_bytes += len(encoded)
        char_start += len(body)
        tail = indexed[-OVERLAP_CHARS:]
        ordinal += 1
    return ordinal > 0 and total_bytes == size_bytes and sha.hexdigest() == digest


def search_chunks(
    db: sqlite3.Connection, expression: str, limit: int
) -> list[tuple[str, str, str, str, float, int]]:
    return db.execute(
        "SELECT d.root, d.relative_path, d.sha256, "
        "offline_document_chunk_fts.body, "
        "bm25(offline_document_chunk_fts) AS rank, d.id "
        "FROM offline_document_chunk_fts "
        "JOIN offline_document_chunks AS c "
        "ON c.id=offline_document_chunk_fts.rowid "
        "JOIN offline_documents AS d ON d.id=c.document_id "
        "WHERE offline_document_chunk_fts MATCH ? "
        "ORDER BY rank ASC, d.root ASC, d.relative_path ASC, c.ordinal ASC "
        "LIMIT ?",
        (expression, limit),
    ).fetchall()


__all__ = [
    "DiskChunkWriter", "create_chunk_tables", "clear_chunks",
    "verify_chunks", "search_chunks",
]
