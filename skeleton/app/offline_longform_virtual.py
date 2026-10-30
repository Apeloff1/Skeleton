"""Private adaptive virtual memory for Apple Silicon and other local machines.

Long-form UTF-8 sources are spooled into small, optionally compressed SQLite
pages with hash-chained provenance. This is application-managed disk-backed
memory, NOT a change to kernel swap, the model's trained context window, or
Metal driver coherency. Only verified, bounded windows can reach model input.
"""
from __future__ import annotations

import codecs
from hashlib import sha256
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import threading
import time
import zlib

from .offline_resource_fabric import _open_source_at
from .offline_resources import (
    LocalResourcePressure, admit_disk_document, probe_local_resources,
)
from .offline_sqlite_safety import (
    UnsafeOfflineSqlitePath, check_sqlite_companion_paths,
)


class LongformMemoryError(RuntimeError):
    """Long-form virtual-memory operation could not be verified safely."""


ROOT_CHAIN = sha256(b"skeleton.local.longform.virtual.v1").digest()


def _chain(previous: bytes, ordinal: int, data: bytes) -> bytes:
    return sha256(
        previous + ordinal.to_bytes(8, "big") + len(data).to_bytes(8, "big")
        + sha256(data).digest()
    ).digest()


def _source(root: str | Path, relative: str) -> tuple[Path, Path]:
    base = Path(root).expanduser()
    if base.is_symlink() or not base.is_dir():
        raise LongformMemoryError("selected root must be a regular directory")
    base = base.resolve(strict=True)
    if type(relative) is not str or not relative or "\x00" in relative:
        raise LongformMemoryError("invalid selected relative path")
    rel = Path(relative)
    if rel.is_absolute() or any(part in {".", ".."} for part in rel.parts):
        raise LongformMemoryError("source escapes selected root")
    path = base / rel
    if path.resolve(strict=True).is_relative_to(base) is False:
        raise LongformMemoryError("source escapes selected root")
    # On Windows the parent path must not be a junction/symlink.
    if os.name != "posix" and path.resolve(strict=True) != path:
        raise LongformMemoryError("redirected source is forbidden")
    return base, rel


class LongformVirtualMemory:
    """Separate local SQLite authority with source-bound provenance and pages."""

    def __init__(self, path: str | Path) -> None:
        selected = Path(path).expanduser()
        if selected.is_symlink() or not selected.parent.is_dir() or (
            selected.exists() and not selected.is_file()
        ):
            raise LongformMemoryError("invalid private longform database path")
        try:
            check_sqlite_companion_paths(selected)
        except UnsafeOfflineSqlitePath as exc:
            raise LongformMemoryError(str(exc)) from exc
        self.path = Path(os.path.abspath(selected))
        self._lock = threading.RLock()
        created = not self.path.exists()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False,
            timeout=10,
        )
        try:
            if created and os.name == "posix":
                os.chmod(self.path, 0o600)
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("""CREATE TABLE IF NOT EXISTS longform_sources (
                source_id TEXT PRIMARY KEY,
                source_label TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                pages INTEGER NOT NULL,
                terminal_chain TEXT NOT NULL,
                stored_bytes INTEGER NOT NULL,
                created_ns INTEGER NOT NULL
            )""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS longform_pages (
                source_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                encoded BLOB NOT NULL,
                plain_bytes INTEGER NOT NULL,
                digest TEXT NOT NULL,
                chain TEXT NOT NULL,
                encoding TEXT NOT NULL,
                PRIMARY KEY(source_id, ordinal)
            ) WITHOUT ROWID""")
            self._db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS longform_fts
                USING fts5(source_id UNINDEXED, ordinal UNINDEXED, text,
                           tokenize='unicode61')""")
        except BaseException:
            self._db.close()
            raise

    def __enter__(self) -> "LongformVirtualMemory":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def ingest(self, root: str | Path, relative: str) -> dict[str, object]:
        """Atomically spool a selected UTF-8 source; no full-file text buffer."""
        base, rel = _source(root, relative)
        try:
            fd = _open_source_at(base, rel)
        except OSError as exc:
            raise LongformMemoryError("selected source cannot be opened safely") from exc
        try:
            with os.fdopen(fd, "rb") as handle:
                start = os.fstat(handle.fileno())
                if not stat.S_ISREG(start.st_mode):
                    raise LongformMemoryError("source must be a regular file")
                snapshot = probe_local_resources(self.path)
                admit_disk_document(snapshot, start.st_size)
                page_chars = max(
                    1024, min(snapshot.read_chunk_bytes // 4,
                              max(1024, snapshot.resident_document_budget // 8)),
                )
                decoder = codecs.getincrementaldecoder("utf-8")("strict")
                hasher = sha256()
                source_id = secrets.token_hex(24)
                count = 0
                length = 0
                stored = 0
                ordinal = 0
                pending = ""
                previous = ROOT_CHAIN
                with self._lock:
                    self._db.execute("BEGIN IMMEDIATE")
                    try:
                        def publish(page: str) -> None:
                            nonlocal previous, ordinal, stored
                            raw = page.encode("utf-8")
                            digest = sha256(raw).hexdigest()
                            compressed = (
                                zlib.compress(raw, 3)
                                if snapshot.cpu_load_ratio < 0.75 else raw
                            )
                            use_zlib = len(compressed) < len(raw) * 0.92
                            encoded = compressed if use_zlib else raw
                            previous = _chain(previous, ordinal, raw)
                            # Disk headroom can change during long imports.
                            try:
                                admit_disk_document(
                                    probe_local_resources(self.path),
                                    len(encoded) * 3,
                                )
                            except LocalResourcePressure as exc:
                                raise LongformMemoryError(str(exc)) from exc
                            self._db.execute(
                                "INSERT INTO longform_pages VALUES (?,?,?,?,?,?,?)",
                                (source_id, ordinal, encoded, len(raw), digest,
                                 previous.hex(), "zlib" if use_zlib else "raw"),
                            )
                            self._db.execute(
                                "INSERT INTO longform_fts(source_id,ordinal,text) "
                                "VALUES (?,?,?)", (source_id, ordinal, page),
                            )
                            ordinal += 1
                            stored += len(encoded)

                        for chunk in iter(
                            lambda: handle.read(snapshot.read_chunk_bytes), b"",
                        ):
                            if b"\x00" in chunk:
                                raise LongformMemoryError("binary source is unsupported")
                            hasher.update(chunk)
                            count += len(chunk)
                            pending += decoder.decode(chunk)
                            while len(pending) >= page_chars:
                                publish(pending[:page_chars])
                                pending = pending[page_chars:]
                        pending += decoder.decode(b"", final=True)
                        if pending:
                            publish(pending)
                        end = os.fstat(handle.fileno())
                        if (
                            (start.st_dev, start.st_ino, start.st_size, start.st_mtime_ns)
                            != (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns)
                            or count != start.st_size or
                            not (base / rel).resolve(strict=True).is_relative_to(base)
                        ):
                            raise LongformMemoryError("source changed during ingestion")
                        self._db.execute(
                            "INSERT INTO longform_sources VALUES (?,?,?,?,?,?,?,?)",
                            (source_id, rel.as_posix(), hasher.hexdigest(),
                             count, ordinal, previous.hex(), stored, time.time_ns()),
                        )
                        self._db.execute("COMMIT")
                    except BaseException:
                        self._db.execute("ROLLBACK")
                        raise
        except UnicodeError as exc:
            raise LongformMemoryError("selected source is not UTF-8") from exc
        return {
            "source_id": source_id, "source_sha256": hasher.hexdigest(),
            "source_bytes": count, "page_count": ordinal,
            "stored_payload_bytes": stored, "terminal_chain": previous.hex(),
            "storage": "sqlite_wal_adaptive_zlib_pages", "verified": True,
        }

    def _read_verified(self, source_id: str) -> tuple[dict[str, object], list[str]]:
        if type(source_id) is not str or len(source_id) != 48 or (
            any(ch not in "0123456789abcdef" for ch in source_id)
        ):
            raise LongformMemoryError("invalid longform source identity")
        row = self._db.execute(
            "SELECT source_sha256, bytes, pages, terminal_chain "
            "FROM longform_sources WHERE source_id=?", (source_id,),
        ).fetchone()
        if row is None:
            raise LongformMemoryError("unknown longform source")
        expected_sha, expected_bytes, expected_pages, terminal_chain = row
        digest = sha256()
        chain = ROOT_CHAIN
        actual_bytes = 0
        pages: list[str] = []
        cursor = self._db.execute(
            "SELECT ordinal,encoded,plain_bytes,digest,chain,encoding "
            "FROM longform_pages WHERE source_id=? ORDER BY ordinal",
            (source_id,),
        )
        for index, encoded, length, expected_digest, expected_chain, encoding in cursor:
            if index != len(pages) or encoding not in ("raw", "zlib"):
                raise LongformMemoryError("longform page ordering or encoding corrupted")
            try:
                # zlib.decompress may expand malicious modified content;
                # enforce original chunk length using an exact-size streaming cap.
                if encoding == "zlib":
                    z = zlib.decompressobj()
                    raw = z.decompress(encoded, length + 1)
                    if len(raw) > length or not z.eof or z.unconsumed_tail:
                        raise ValueError("invalid compressed longform page")
                else:
                    raw = encoded
                text = raw.decode("utf-8", errors="strict")
            except (ValueError, UnicodeError, zlib.error) as exc:
                raise LongformMemoryError("corrupt longform compressed page") from exc
            if len(raw) != length or sha256(raw).hexdigest() != expected_digest:
                raise LongformMemoryError("longform page digest mismatch")
            chain = _chain(chain, index, raw)
            if chain.hex() != expected_chain:
                raise LongformMemoryError("longform page chain mismatch")
            projection = self._db.execute(
                "SELECT text FROM longform_fts WHERE source_id=? AND ordinal=?",
                (source_id, index),
            ).fetchone()
            if projection != (text,):
                raise LongformMemoryError("longform search projection corrupted")
            digest.update(raw)
            actual_bytes += length
            pages.append(text)
        if (len(pages) != expected_pages or actual_bytes != expected_bytes
                or digest.hexdigest() != expected_sha
                or chain.hex() != terminal_chain):
            raise LongformMemoryError("longform snapshot integrity mismatch")
        return {
            "source_id": source_id, "source_sha256": expected_sha,
            "source_bytes": expected_bytes, "page_count": expected_pages,
            "terminal_chain": terminal_chain, "verified": True,
        }, pages

    def read_window(
        self, source_id: str, *, start_page: int = 0, pages: int = 1
    ) -> dict[str, object]:
        if (type(start_page) is not int or start_page < 0
                or type(pages) is not int or pages < 1):
            raise LongformMemoryError("invalid page window")
        # Hard RAM/transport guard on this single read, never on corpus size.
        safe = probe_local_resources(self.path).resident_document_budget // 4
        if safe < 2048:
            raise LongformMemoryError("insufficient memory for longform page reading")
        with self._lock:
            manifest, text_pages = self._read_verified(source_id)
            selected = text_pages[start_page:start_page + pages]
            total = sum(len(text.encode("utf-8")) for text in selected)
            if total > safe:
                raise LongformMemoryError("page window exceeds current RAM headroom")
            return {
                **manifest, "start_page": start_page,
                "returned_pages": len(selected),
                "text": "".join(selected),
                "model_context_applied": False,
            }

    def verify(self, source_id: str) -> dict[str, object]:
        with self._lock:
            return self._read_verified(source_id)[0]


__all__ = ["LongformVirtualMemory", "LongformMemoryError"]
