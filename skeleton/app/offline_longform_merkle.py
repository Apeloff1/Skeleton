"""Tamper-evident, page-granular Merkle proofs for long-form virtual memory.

Immutable archive pages are committed with a binary Merkle tree in the same
SQLite transaction. Selective reads require O(log N) sibling hashes rather
than rescanning a multi-gigabyte source. The complete original file digest
and rolling chain remain available for explicit full verification.

The index is not a signature or remote attestation; its root is pinned by the
local archive manifest. An attacker permitted to rewrite the entire trusted
database can also rewrite that root.
"""
from __future__ import annotations

from hashlib import sha256
import sqlite3


class MerkleIntegrityError(RuntimeError):
    """A selected long-form page cannot be proven against its archive root."""


def _hex64(value: str) -> bytes:
    if (type(value) is not str or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise MerkleIntegrityError("invalid page proof hash")
    return bytes.fromhex(value)


def _leaf(index: int, length: int, page_digest: str) -> bytes:
    if (type(index) is not int or index < 0
            or type(length) is not int or length < 0):
        raise MerkleIntegrityError("invalid page proof geometry")
    return sha256(
        b"skeleton.longform.merkle.leaf.v1\0"
        + index.to_bytes(8, "big")
        + length.to_bytes(8, "big")
        + _hex64(page_digest)
    ).digest()


def _parent(left: bytes, right: bytes) -> bytes:
    if len(left) != 32 or len(right) != 32:
        raise MerkleIntegrityError("invalid Merkle parent")
    return sha256(b"skeleton.longform.merkle.node.v1\0" + left + right).digest()


EMPTY_ROOT = sha256(b"skeleton.longform.merkle.empty.v1").hexdigest()


def install_merkle_schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS longform_merkle (
        source_id TEXT NOT NULL,
        level INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        digest TEXT NOT NULL,
        PRIMARY KEY(source_id, level, ordinal)
    ) WITHOUT ROWID""")
    # Migration of historical private archives. NULL means legacy full-scan
    # verification, never an invented Merkle guarantee.
    columns = {
        row[1] for row in db.execute("PRAGMA table_info(longform_sources)")
    }
    if "merkle_root" not in columns:
        db.execute("ALTER TABLE longform_sources ADD COLUMN merkle_root TEXT")


def build_merkle_tree(
    db: sqlite3.Connection, source_id: str, page_count: int,
) -> str:
    """Build binary levels using streaming SQLite cursors and constant RAM.

    Leaves bind ordered page index, UTF-8 length and the full byte digest.
    Odd-sized levels duplicate their final node, canonically.
    This function MUST be called inside the same ingest transaction that
    inserts the source pages, FTS projection and archive manifest.
    """
    if type(page_count) is not int or page_count < 0:
        raise MerkleIntegrityError("invalid longform page count")
    db.execute("DELETE FROM longform_merkle WHERE source_id=?", (source_id,))
    if page_count == 0:
        return EMPTY_ROOT
    previous_index = -1
    for index, length, digest in db.execute(
        "SELECT ordinal, plain_bytes, digest FROM longform_pages "
        "WHERE source_id=? ORDER BY ordinal", (source_id,),
    ):
        if index != previous_index + 1:
            raise MerkleIntegrityError("missing or out-of-order longform leaf")
        db.execute(
            "INSERT INTO longform_merkle VALUES (?,?,?,?)",
            (source_id, 0, index, _leaf(index, length, digest).hex()),
        )
        previous_index = index
    if previous_index + 1 != page_count:
        raise MerkleIntegrityError("incomplete longform Merkle leaves")
    level = 0
    size = page_count
    while size > 1:
        cursor = db.execute(
            "SELECT ordinal,digest FROM longform_merkle "
            "WHERE source_id=? AND level=? ORDER BY ordinal",
            (source_id, level),
        )
        pending: bytes | None = None
        next_index = 0
        observed = 0
        for index, digest in cursor:
            if index != observed:
                raise MerkleIntegrityError("missing intermediate Merkle node")
            observed += 1
            child = _hex64(digest)
            if pending is None:
                pending = child
                continue
            db.execute(
                "INSERT INTO longform_merkle VALUES (?,?,?,?)",
                (source_id, level + 1, next_index,
                 _parent(pending, child).hex()),
            )
            next_index += 1
            pending = None
        if observed != size:
            raise MerkleIntegrityError("invalid Merkle level width")
        if pending is not None:
            db.execute(
                "INSERT INTO longform_merkle VALUES (?,?,?,?)",
                (source_id, level + 1, next_index,
                 _parent(pending, pending).hex()),
            )
            next_index += 1
        size = (size + 1) // 2
        level += 1
        if next_index != size:
            raise MerkleIntegrityError("invalid Merkle parent count")
    row = db.execute(
        "SELECT digest FROM longform_merkle WHERE "
        "source_id=? AND level=? AND ordinal=0",
        (source_id, level),
    ).fetchone()
    if row is None:
        raise MerkleIntegrityError("longform Merkle root missing")
    return _hex64(row[0]).hex()


def verify_merkle_page(
    db: sqlite3.Connection, source_id: str,
    *, ordinal: int, page_count: int, byte_length: int,
    page_digest: str, root: str,
) -> None:
    """Prove one selected page against the immutable archive root."""
    if (type(page_count) is not int or page_count < 1
            or type(ordinal) is not int or not 0 <= ordinal < page_count):
        raise MerkleIntegrityError("selected page is outside archive")
    expected = _hex64(root)
    current = _leaf(ordinal, byte_length, page_digest)
    pos = ordinal
    size = page_count
    level = 0
    while size > 1:
        sibling = pos ^ 1
        if sibling >= size:
            partner = current
        else:
            row = db.execute(
                "SELECT digest FROM longform_merkle "
                "WHERE source_id=? AND level=? AND ordinal=?",
                (source_id, level, sibling),
            ).fetchone()
            if row is None:
                raise MerkleIntegrityError("missing Merkle sibling")
            partner = _hex64(row[0])
        current = _parent(
            current, partner,
        ) if pos % 2 == 0 else _parent(partner, current)
        pos //= 2
        size = (size + 1) // 2
        level += 1
    if current != expected:
        raise MerkleIntegrityError("selected page Merkle proof mismatch")


__all__ = [
    "EMPTY_ROOT", "MerkleIntegrityError", "install_merkle_schema",
    "build_merkle_tree", "verify_merkle_page",
]
