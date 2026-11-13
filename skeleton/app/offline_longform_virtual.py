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
from .offline_longform_merkle import (
    EMPTY_ROOT, MerkleIntegrityError, install_merkle_schema,
    build_merkle_tree, verify_merkle_page,
)
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
            install_merkle_schema(self._db)
            self._db.execute("""CREATE TABLE IF NOT EXISTS longform_work (
                work_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                source_terminal_chain TEXT NOT NULL,
                next_page INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                last_request_id TEXT,
                last_start_page INTEGER,
                last_page_count INTEGER,
                last_receipt_digest TEXT,
                receipt_chain TEXT NOT NULL,
                updated_ns INTEGER NOT NULL
            )""")
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

    def ingest(
        self, root: str | Path, relative: str,
        *, request_id: str | None = None,
    ) -> dict[str, object]:
        """Atomically spool once; caller can recover by a stable request id.

        A retried import never duplicates a previous committed archive and
        never represents a new source version as the old source snapshot.
        """
        if request_id is not None:
            self._identity(request_id, "import request identity")
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
                source_id = request_id or secrets.token_hex(24)
                count = 0
                stored = 0
                ordinal = 0
                pending = ""
                previous = ROOT_CHAIN
                last_disk_probe = time.monotonic()
                with self._lock:
                    previous_import = self._db.execute(
                        "SELECT source_label, source_sha256, bytes, pages, "
                        "terminal_chain, stored_bytes FROM longform_sources "
                        "WHERE source_id=?", (source_id,),
                    ).fetchone()
                    if previous_import is not None:
                        if previous_import[0] != rel.as_posix():
                            raise LongformMemoryError(
                                "import request identity already belongs to another source"
                            )
                        manifest = self._read_verified(source_id)[0]
                        return {
                            "source_id": source_id,
                            "source_sha256": manifest["source_sha256"],
                            "source_bytes": manifest["source_bytes"],
                            "page_count": manifest["page_count"],
                            "terminal_chain": manifest["terminal_chain"],
                            "stored_payload_bytes": previous_import[5],
                            "storage": "sqlite_wal_adaptive_zlib_pages",
                            "verified": True, "replayed": True,
                        }
                    self._db.execute("BEGIN IMMEDIATE")
                    try:
                        next_fts_rowid = int(self._db.execute(
                            "SELECT COALESCE(MAX(rowid),0)+1 FROM longform_fts"
                        ).fetchone()[0])
                        def publish(page: str) -> None:
                            nonlocal previous, ordinal, stored, last_disk_probe
                            nonlocal next_fts_rowid
                            raw = page.encode("utf-8")
                            digest = sha256(raw).hexdigest()
                            compressed = (
                                zlib.compress(raw, 3)
                                if snapshot.cpu_load_ratio < 0.75 else raw
                            )
                            use_zlib = len(compressed) < len(raw) * 0.92
                            encoded = compressed if use_zlib else raw
                            previous = _chain(previous, ordinal, raw)
                            # Re-sample live disk pressure periodically, not
                            # once per 1-KiB page. SQLITE_FULL and the write
                            # transaction still fail closed between probes.
                            now = time.monotonic()
                            if ordinal % 128 == 0 or now - last_disk_probe >= 1.0:
                                try:
                                    admit_disk_document(
                                        probe_local_resources(self.path),
                                        max(len(encoded) * 3, 4096),
                                    )
                                except LocalResourcePressure as exc:
                                    raise LongformMemoryError(str(exc)) from exc
                                last_disk_probe = now
                            self._db.execute(
                                "INSERT INTO longform_pages "
                                "(source_id,ordinal,encoded,plain_bytes,"
                                "digest,chain,encoding,fts_rowid) "
                                "VALUES (?,?,?,?,?,?,?,?)",
                                (source_id, ordinal, encoded, len(raw), digest,
                                 previous.hex(), "zlib" if use_zlib else "raw",
                                 next_fts_rowid),
                            )
                            self._db.execute(
                                "INSERT INTO longform_fts"
                                "(rowid,source_id,ordinal,text) "
                                "VALUES (?,?,?,?)",
                                (next_fts_rowid, source_id, ordinal, page),
                            )
                            next_fts_rowid += 1
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
                        root = build_merkle_tree(
                            self._db, source_id, ordinal,
                        )
                        self._db.execute(
                            "INSERT INTO longform_sources "
                            "(source_id,source_label,source_sha256,bytes,pages,"
                            "terminal_chain,stored_bytes,created_ns,merkle_root) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (source_id, rel.as_posix(), hasher.hexdigest(),
                             count, ordinal, previous.hex(), stored,
                             time.time_ns(), root),
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
            "replayed": False,
        }

    def inspect_source(self, source_id: str) -> dict[str, object]:
        """Retrieve a previously committed source after a lost HTTP response."""
        self._identity(source_id, "source identity")
        with self._lock:
            data = self._db.execute(
                "SELECT source_label, stored_bytes FROM longform_sources "
                "WHERE source_id=?", (source_id,),
            ).fetchone()
            if data is None:
                raise LongformMemoryError("unknown committed longform source")
            manifest = self._read_verified(source_id)[0]
            return {
                **manifest,
                "source_label": data[0],
                "stored_payload_bytes": data[1],
                "storage": "sqlite_wal_adaptive_zlib_pages",
            }

    def _read_verified(
        self, source_id: str, *, selected: set[int] | None = None,
        max_selected_bytes: int = 0,
    ) -> tuple[dict[str, object], dict[int, str]]:
        """Stream-verifies the *entire* archive using bounded memory.

        Decoded pages are retained only if explicitly selected. The full
        document hash, ordered chain and searchable projection are checked
        before returning any selected text to a model or API caller.
        """
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
        count = 0
        captured: dict[int, str] = {}
        captured_bytes = 0
        cursor = self._db.execute(
            "SELECT ordinal,encoded,plain_bytes,digest,chain,encoding,fts_rowid "
            "FROM longform_pages WHERE source_id=? ORDER BY ordinal",
            (source_id,),
        )
        resources = probe_local_resources(self.path)
        sampled_at = time.monotonic()
        for index, encoded, length, expected_digest, expected_chain, encoding, fts_rowid in cursor:
            if index != count or encoding not in ("raw", "zlib"):
                raise LongformMemoryError("longform page ordering or encoding corrupted")
            # Page length must be reasonable relative to *current* RAM.
            # A malicious SQLite row must not force unlimited decompression.
            now = time.monotonic()
            if count % 128 == 0 or now - sampled_at >= 1.0:
                resources = probe_local_resources(self.path)
                sampled_at = now
            page_limit = max(
                1024, min(
                    resources.read_chunk_bytes * 4,
                    resources.resident_document_budget // 2,
                ),
            )
            if type(length) is not int or length < 0 or length > page_limit:
                raise LongformMemoryError("invalid longform page allocation")
            try:
                if encoding == "zlib":
                    decoder = zlib.decompressobj()
                    raw = decoder.decompress(encoded, length + 1)
                    if (len(raw) > length or not decoder.eof
                            or decoder.unconsumed_tail or decoder.unused_data):
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
            if fts_rowid is not None:
                projection = self._db.execute(
                    "SELECT source_id, ordinal, text FROM longform_fts "
                    "WHERE rowid=?", (fts_rowid,),
                ).fetchone()
                if projection != (source_id, index, text):
                    raise LongformMemoryError("longform search projection corrupted")
            else:
                projection = self._db.execute(
                    "SELECT text FROM longform_fts "
                    "WHERE source_id=? AND ordinal=?", (source_id, index),
                ).fetchone()
                if projection != (text,):
                    raise LongformMemoryError("longform search projection corrupted")
            digest.update(raw)
            actual_bytes += length
            if selected is not None and index in selected:
                captured_bytes += length
                if captured_bytes > max_selected_bytes:
                    raise LongformMemoryError(
                        "page window exceeds current RAM headroom"
                    )
                captured[index] = text
            count += 1
        actual_fts_count = self._db.execute(
            "SELECT COUNT(*) FROM longform_fts WHERE source_id=?",
            (source_id,),
        ).fetchone()[0]
        if (count != expected_pages or actual_bytes != expected_bytes
                or actual_fts_count != expected_pages
                or digest.hexdigest() != expected_sha
                or chain.hex() != terminal_chain):
            raise LongformMemoryError("longform snapshot integrity mismatch")
        return {
            "source_id": source_id, "source_sha256": expected_sha,
            "source_bytes": expected_bytes, "page_count": expected_pages,
            "terminal_chain": terminal_chain, "verified": True,
        }, captured

    def _read_selected_merkle(
        self, source_id: str, selection: set[int],
        *, max_selected_bytes: int,
    ) -> tuple[dict[str, object], dict[int, str]] | None:
        """Verify selected immutable page membership without full archive scan.

        Legacy archives with no Merkle root continue to use the existing
        complete file/hash-chain verification path. A modern root MUST be
        supported by a valid path for each page before returning any text.
        """
        row = self._db.execute(
            "SELECT source_sha256,bytes,pages,terminal_chain,merkle_root "
            "FROM longform_sources WHERE source_id=?", (source_id,),
        ).fetchone()
        if row is None:
            raise LongformMemoryError("unknown longform source")
        digest, source_bytes, total, terminal, root = row
        if root is None:
            return None
        if (type(total) is not int or total < 0
                or type(source_bytes) is not int or source_bytes < 0
                or type(root) is not str or len(root) != 64):
            raise LongformMemoryError("invalid Merkle source manifest")
        manifest: dict[str, object] = {
            "source_id": source_id, "source_sha256": digest,
            "source_bytes": source_bytes, "page_count": total,
            "terminal_chain": terminal, "merkle_root": root,
            "verified": True, "verification_scope": "selected_merkle_pages",
        }
        if total == 0:
            if (root != EMPTY_ROOT or source_bytes != 0
                    or digest != sha256(b"").hexdigest()
                    or terminal != ROOT_CHAIN.hex()):
                raise LongformMemoryError("empty Merkle manifest corrupted")
            if selection:
                raise LongformMemoryError("selected page outside empty archive")
            return manifest, {}
        if selection and (min(selection) < 0 or max(selection) >= total):
            raise LongformMemoryError("selected longform page out of bounds")
        captured: dict[int, str] = {}
        used = 0
        resources = probe_local_resources(self.path)
        page_limit = max(
            1024, min(
                resources.read_chunk_bytes * 4,
                resources.resident_document_budget // 2,
            ),
        )
        for index in sorted(selection):
            record = self._db.execute(
                "SELECT encoded,plain_bytes,digest,encoding,fts_rowid "
                "FROM longform_pages WHERE source_id=? AND ordinal=?",
                (source_id, index),
            ).fetchone()
            if record is None:
                raise LongformMemoryError("selected longform page is missing")
            encoded, length, page_digest, encoding, fts_rowid = record
            if fts_rowid is None:
                # Old archive or partial migration: refuse a fast proof and
                # use full-source/FTS verification instead.
                return None
            if type(fts_rowid) is not int or fts_rowid <= 0:
                raise LongformMemoryError("invalid page FTS identity")
            if (type(length) is not int or not 0 <= length <= page_limit
                    or type(encoded) is not bytes
                    or encoding not in ("zlib", "raw")):
                raise LongformMemoryError("invalid selected page allocation")
            if used + length > max_selected_bytes:
                raise LongformMemoryError("selected pages exceed live RAM headroom")
            try:
                if encoding == "zlib":
                    decoder = zlib.decompressobj()
                    raw = decoder.decompress(encoded, length + 1)
                    if (len(raw) != length or not decoder.eof
                            or decoder.unused_data or decoder.unconsumed_tail):
                        raise ValueError("invalid selected compressed page")
                else:
                    raw = encoded
                page = raw.decode("utf-8", errors="strict")
            except (ValueError, UnicodeError, zlib.error) as exc:
                raise LongformMemoryError("corrupted selected longform page") from exc
            if len(raw) != length or sha256(raw).hexdigest() != page_digest:
                raise LongformMemoryError("selected longform page digest mismatch")
            try:
                verify_merkle_page(
                    self._db, source_id, ordinal=index, page_count=total,
                    byte_length=length, page_digest=page_digest, root=root,
                )
            except MerkleIntegrityError as exc:
                raise LongformMemoryError("selected Merkle page proof failed") from exc
            projection = self._db.execute(
                "SELECT source_id,ordinal,text FROM longform_fts "
                "WHERE rowid=?", (fts_rowid,),
            ).fetchone()
            if projection != (source_id, index, page):
                raise LongformMemoryError("selected source search text changed")
            captured[index] = page
            used += length
        return manifest, captured

    def read_window(
        self, source_id: str, *, start_page: int = 0, pages: int = 1
    ) -> dict[str, object]:
        if (type(start_page) is not int or start_page < 0
                or type(pages) is not int or pages < 1):
            raise LongformMemoryError("invalid page window")
        # This caps one HTTP-sized materialization, not file size or archive.
        # The model's verified context window remains a separate constraint.
        safe = min(
            8 * 1024 * 1024,
            probe_local_resources(self.path).resident_document_budget // 4,
        )
        if safe < 2048:
            raise LongformMemoryError("insufficient memory for longform page reading")
        if pages > max(1, safe // 1024):
            raise LongformMemoryError("requested window exceeds live page budget")
        with self._lock:
            count_row = self._db.execute(
                "SELECT pages FROM longform_sources WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if count_row is None:
                raise LongformMemoryError("unknown longform source")
            if type(count_row[0]) is not int or count_row[0] < 0:
                raise LongformMemoryError("invalid longform page count")
            selection = set(range(
                min(start_page, count_row[0]),
                min(start_page + pages, count_row[0]),
            ))
            merkle = self._read_selected_merkle(
                source_id, selection, max_selected_bytes=safe,
            )
            if merkle is None:
                manifest, captured = self._read_verified(
                    source_id, selected=selection,
                    max_selected_bytes=safe,
                )
            else:
                manifest, captured = merkle
            return {
                **manifest, "start_page": start_page,
                "returned_pages": len(captured),
                "text": "".join(captured[i] for i in sorted(captured)),
                "model_context_applied": False,
            }

    def verify(self, source_id: str) -> dict[str, object]:
        with self._lock:
            return self._read_verified(source_id)[0]

    def search(
        self, source_id: str, query: str, *, limit: int = 5
    ) -> dict[str, object]:
        """Retrieve a small provenance-verified subset, not entire corpus."""
        import re
        if type(query) is not str or not query.strip() or len(query) > 512:
            raise LongformMemoryError("invalid longform search query")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise LongformMemoryError("invalid longform search return count")
        terms = tuple(dict.fromkeys(re.findall(
            r"(?u)\w{2,32}", query.casefold(),
        )))[:12]
        if not terms:
            raise LongformMemoryError("longform search needs text terms")
        expression = " OR ".join('"' + term + '"' for term in terms)
        with self._lock:
            rows = self._db.execute(
                "SELECT ordinal FROM longform_fts "
                "WHERE longform_fts MATCH ? AND source_id=? "
                "ORDER BY bm25(longform_fts), ordinal LIMIT ?",
                (expression, source_id, limit),
            ).fetchall()
            positions = [int(row[0]) for row in rows]
            safe = min(
                8 * 1024 * 1024,
                probe_local_resources(self.path).resident_document_budget // 4,
            )
            merkle = self._read_selected_merkle(
                source_id, set(positions), max_selected_bytes=safe,
            )
            if merkle is None:
                manifest, captured = self._read_verified(
                    source_id, selected=set(positions),
                    max_selected_bytes=safe,
                )
            else:
                manifest, captured = merkle
        return {
            **manifest,
            "hits": [
                {"page": position, "text": captured[position],
                 "source_sha256": manifest["source_sha256"]}
                for position in positions
            ],
            "model_context_applied": False,
            "search_completeness_proven": False,
        }


    @staticmethod
    def _identity(value: str, label: str) -> str:
        if type(value) is not str or len(value) != 48 or any(
            ch not in "0123456789abcdef" for ch in value
        ):
            raise LongformMemoryError("invalid " + label)
        return value

    def start_work(self, source_id: str) -> dict[str, object]:
        """Create a durable chapter/page cursor only after archive verification."""
        source_id = self._identity(source_id, "source identity")
        with self._lock:
            manifest = self._read_verified(source_id)[0]
            work_id = secrets.token_hex(24)
            root = sha256(
                b"skeleton.longform.work.v1:" +
                bytes.fromhex(work_id) +
                bytes.fromhex(manifest["source_sha256"])
            ).hexdigest()
            self._db.execute(
                "INSERT INTO longform_work VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    work_id, source_id, manifest["source_sha256"],
                    manifest["terminal_chain"], 0, 0,
                    None, None, None, None, root, time.time_ns(),
                ),
            )
            return {
                "work_id": work_id, "source_id": source_id,
                "source_sha256": manifest["source_sha256"],
                "next_page": 0, "revision": 0,
                "total_pages": manifest["page_count"],
                "receipt_chain": root,
                "progress_committed": True,
            }

    def inspect_work(self, work_id: str) -> dict[str, object]:
        work_id = self._identity(work_id, "work identity")
        with self._lock:
            record = self._db.execute(
                "SELECT w.source_id, w.source_sha256, w.next_page, "
                "w.revision, w.receipt_chain, s.pages, "
                "w.source_terminal_chain, s.terminal_chain, s.source_sha256 "
                "FROM longform_work AS w JOIN longform_sources AS s "
                "ON s.source_id=w.source_id WHERE w.work_id=?",
                (work_id,),
            ).fetchone()
            if record is None:
                raise LongformMemoryError("unknown longform work cursor")
            source, digest, page, revision, chain, total, pinned, current, current_digest = record
            if current != pinned or current_digest != digest:
                raise LongformMemoryError("longform cursor source changed")
            return {
                "work_id": work_id, "source_id": source,
                "source_sha256": digest, "next_page": page,
                "revision": revision, "total_pages": total,
                "receipt_chain": chain,
                "complete": page >= total,
            }

    def advance_work(
        self, work_id: str, *, expected_revision: int,
        request_id: str, pages: int = 1,
    ) -> dict[str, object]:
        """Exactly-once cursor movement with replayable completed page receipts.

        The client must reuse request_id on transport retries. The same
        request has its previous verified page content reconstructed, while
        a conflicting revision or changed source fails closed.
        """
        work_id = self._identity(work_id, "work identity")
        self._identity(request_id, "work request identity")
        if type(expected_revision) is not int or expected_revision < 0:
            raise LongformMemoryError("invalid expected work revision")
        if type(pages) is not int or pages < 1:
            raise LongformMemoryError("invalid requested page batch")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                state = self._db.execute(
                    "SELECT source_id, source_sha256, source_terminal_chain, "
                    "next_page, revision, last_request_id, last_start_page, "
                    "last_page_count, last_receipt_digest, receipt_chain "
                    "FROM longform_work WHERE work_id=?",
                    (work_id,),
                ).fetchone()
                if state is None:
                    raise LongformMemoryError("unknown longform work cursor")
                (
                    source_id, source_sha, terminal, next_page, revision,
                    last_request, last_start, last_pages, last_digest,
                    receipt_chain,
                ) = state
                replay = (
                    last_request == request_id
                    and expected_revision == revision - 1
                    and pages == last_pages
                )
                if not replay and expected_revision != revision:
                    raise LongformMemoryError("stale longform revision")
                if not replay and last_request == request_id:
                    raise LongformMemoryError("work request identity already consumed")
                if replay:
                    start = last_start
                    target = last_pages
                else:
                    start = next_page
                    target = pages
                # read_window fully verifies the source and retains only the
                # selected small window. Never advance an unverified source.
                window = self.read_window(
                    source_id, start_page=start, pages=target,
                )
                if window["terminal_chain"] != terminal or (
                    window["source_sha256"] != source_sha
                ):
                    raise LongformMemoryError("work cursor lost source identity")
                count = window["returned_pages"]
                if not replay and count == 0:
                    raise LongformMemoryError("longform work already at end")
                payload = window["text"]
                digest = sha256(
                    b"skeleton.longform.delivery.v1:" + payload.encode("utf-8")
                    + str(start).encode("ascii")
                    + str(count).encode("ascii")
                    + bytes.fromhex(source_sha)
                ).hexdigest()
                if replay:
                    if digest != last_digest:
                        raise LongformMemoryError("replayed work receipt changed")
                    self._db.execute("COMMIT")
                    return {
                        **window, "work_id": work_id, "request_id": request_id,
                        "revision": revision, "next_page": next_page,
                        "receipt_digest": digest,
                        "receipt_chain": receipt_chain,
                        "replayed": True, "progress_committed": True,
                    }
                new_chain = sha256(
                    bytes.fromhex(receipt_chain) +
                    bytes.fromhex(request_id) +
                    bytes.fromhex(digest)
                ).hexdigest()
                updated = self._db.execute(
                    "UPDATE longform_work SET next_page=?, revision=?, "
                    "last_request_id=?, last_start_page=?, last_page_count=?, "
                    "last_receipt_digest=?, receipt_chain=?, updated_ns=? "
                    "WHERE work_id=? AND revision=? AND receipt_chain=?",
                    (
                        start + count, revision + 1, request_id, start, pages,
                        digest, new_chain, time.time_ns(), work_id, revision,
                        receipt_chain,
                    ),
                )
                if updated.rowcount != 1:
                    raise LongformMemoryError("work cursor CAS failed")
                self._db.execute("COMMIT")
                return {
                    **window, "work_id": work_id, "request_id": request_id,
                    "revision": revision + 1, "next_page": start + count,
                    "receipt_digest": digest, "receipt_chain": new_chain,
                    "replayed": False, "progress_committed": True,
                }
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise


__all__ = ["LongformVirtualMemory", "LongformMemoryError"]
