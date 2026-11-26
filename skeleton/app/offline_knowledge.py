"""Private deterministic reference library for Skeleton's offline AI workspace.

This implements *searchable evidence retrieval*, not a claim that arbitrary
generated model text is grounded. It deliberately never downloads, crawls,
executes, follows stored file paths or interprets stored text as instructions.
Explicit operator-selected files use safe, no-follow regular-file admission.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import codecs
from hashlib import sha256
import math
import os
from pathlib import Path
import stat
import re
import unicodedata
from typing import Any

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from .offline_resources import (
    LocalResourcePressure, probe_local_resources, admit_resident_document,
)


def _require_local_headroom(
    size_bytes: int, *, write: bool = False, storage_path: str | Path = "."
) -> None:
    try:
        admit_resident_document(
            probe_local_resources(storage_path), size_bytes, write=write
        )
    except LocalResourcePressure as exc:
        raise RuntimeContractError(str(exc)) from exc


# Legacy symbolic names remain importable. None means no public-service quota.
MAX_DOCUMENT_BYTES = None
MAX_TITLE_BYTES = 200
MAX_DOCUMENTS_PER_MODEL = None
MAX_CHUNKS_PER_MODEL = None
MAX_SEARCH_TOKENS = 24
MAX_QUERY_BYTES = 1_024
_CHUNK_CHARS = 600
_CHUNK_OVERLAP = 80
# Bounded query-local scratch; not a persistent index or source authority.
_SPARSE_MATCH_COUNT = 2048
_SPARSE_MATCH_BYTES = 2 * 1024 * 1024
_MAX_DOC_CHUNKS = None
_TERMS = re.compile(r"[^\W_]{2,}", re.UNICODE)
_STOP = frozenset({
    "the", "and", "are", "for", "that", "this", "with", "from", "into",
    "you", "your", "was", "were", "have", "has", "had", "but", "not",
    "all", "can", "how", "what", "when", "where", "why", "our", "its",
    "their", "then", "than", "they", "will", "would", "should",
})



def read_reference_file(path: Path) -> str:
    """Read UTF-8 through a stable regular-file handle without a size cap.

    Inspect the path both before and after opening, bind the opened file to
    that identity, and reject any replacement or in-place change during read.
    O_NOFOLLOW also prevents symlink traversal on supporting operating systems.
    """
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeContractError(
                "reference path must be a local regular non-symlink file"
            )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) !=
                    (before.st_dev, before.st_ino)):
                raise RuntimeContractError("reference changed during file admission")
            if opened.st_size < 1:
                raise RuntimeContractError("reference file is empty")
            try:
                resources = probe_local_resources(path)
                admit_resident_document(resources, opened.st_size)
            except LocalResourcePressure as exc:
                raise RuntimeContractError(str(exc)) from exc
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            parts: list[str] = []
            byte_count = 0
            try:
                while data := source.read(resources.read_chunk_bytes):
                    if b"\x00" in data:
                        raise RuntimeContractError("binary reference content is prohibited")
                    byte_count += len(data)
                    parts.append(decoder.decode(data))
                parts.append(decoder.decode(b"", final=True))
            except UnicodeError as exc:
                raise RuntimeContractError("reference must be UTF-8 text") from exc
            after = os.fstat(source.fileno())
            current = path.lstat()
            if (not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) !=
                    (opened.st_dev, opened.st_ino)
                    or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
                    (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
                raise RuntimeContractError("reference changed during file admission")
    except (OSError, ValueError) as exc:
        if isinstance(exc, RuntimeContractError):
            raise
        raise RuntimeContractError("reference path is not a readable regular file") from exc
    if byte_count != opened.st_size:
        raise RuntimeContractError("reference changed during file admission")
    return "".join(parts)

def _identity(value: str, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise RuntimeContractError(f"invalid {label}")
    return value


def _terms(text: str, *, limit: int = MAX_SEARCH_TOKENS) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(dict.fromkeys(
        word for word in _TERMS.findall(normalized) if word not in _STOP
    ))[:limit]


@dataclass(frozen=True, slots=True)
class LocalKnowledgeHit:
    document_id: str
    title: str
    sha256: str
    chunk_index: int
    char_start: int
    char_end: int
    passage: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "document_sha256": self.sha256,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "passage": self.passage,
            "score": round(self.score, 5),
            "citation": f"local:{self.document_id}:{self.chunk_index}:{self.sha256[:16]}",
        }


def _diverse_grounding_hits(ranked: list[LocalKnowledgeHit], limit: int) -> list[LocalKnowledgeHit]:
    """Reduce only clear redundancy, preserving the best matching passage.

    Relevance-first with an explicit replacement floor. Do not classify
    similar-but-different facts as duplicates: contradictory statements may
    differ by only one word. Use exact normalized passage equivalence or
    strong overlap of verified offsets within the same source revision.
    """
    if limit <= 1 or len(ranked) <= limit:
        return ranked[:limit]
    normalized = { (hit.document_id, hit.chunk_index):
                   unicodedata.normalize("NFKC", hit.passage).casefold().strip()
                   for hit in ranked }

    def redundant(a, b):
        # Across sources do not collapse case-sensitive or Unicode-distinct
        # evidence (e.g. technical identifiers). Exact bytes only.
        if a.passage == b.passage:
            return True
        if a.document_id != b.document_id or a.sha256 != b.sha256:
            return False
        overlap = max(0, min(a.char_end,b.char_end)-max(a.char_start,b.char_start))
        shorter = min(a.char_end-a.char_start,b.char_end-b.char_start)
        return (shorter > 0 and overlap * 4 >= shorter * 3
                or normalized[(a.document_id,a.chunk_index)] == normalized[(b.document_id,b.chunk_index)])

    chosen = []
    remaining = list(ranked)
    while remaining and len(chosen) < limit:
        first = remaining[0]
        if any(redundant(first, prior) for prior in chosen):
            # Only substitute a still relevant nonredundant passage; weak
            # candidates cannot displace the original nearest result.
            alternative = next((hit for hit in remaining[1:]
                               if hit.score >= first.score * 0.70
                               and not any(redundant(hit, prior) for prior in chosen)), None)
            if alternative is not None:
                first = alternative
        chosen.append(first)
        remaining.remove(first)
    return chosen


class OfflineKnowledgeLibrary:
    """Model-scoped documents stored in the existing local SQLite DB."""

    def __init__(self, store: OfflineChatStore, model_digest: str,
                 tokenizer_digest: str, *, semantic_ranker=None) -> None:
        if not isinstance(store, OfflineChatStore):
            raise RuntimeContractError("a canonical local SQLite store is required")
        self.store = store
        # PRAGMA exposes the actual SQLite volume (including WAL placement).
        # In-memory stores intentionally use the current local working volume.
        database = store._db.execute("PRAGMA database_list").fetchone()
        self._storage_path = database[2] if database and database[2] else "."
        self.model_digest = _identity(model_digest, "model digest")
        self.tokenizer_digest = _identity(tokenizer_digest, "tokenizer digest")
        self._semantic_ranker=semantic_ranker
        self._semantic_cache=None
        self._semantic_ann=None
        if semantic_ranker is not None:
            from skeleton.retrieval.semantic_long_context import ContextualRanker
            from skeleton.retrieval.semantic_vector_cache import DerivedVectorCache
            if not isinstance(semantic_ranker,ContextualRanker):
                raise RuntimeContractError("operator-owned semantic ranker required")
            scope=sha256(("offline-knowledge-v1:"+self.model_digest+":"+self.tokenizer_digest).encode()).hexdigest()
            self._semantic_cache=DerivedVectorCache(store._db,store._lock,scope,
                dimension=semantic_ranker.encoder.policy.dimension,segments=semantic_ranker.policy.segments,
                max_bytes=semantic_ranker.policy.max_vector_bytes)
        with store._lock:
            store._db.execute("""CREATE TABLE IF NOT EXISTS offline_documents (
                document_id TEXT PRIMARY KEY,
                model_digest TEXT NOT NULL,
                tokenizer_digest TEXT NOT NULL,
                title TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                content_text TEXT NOT NULL,
                created_ns INTEGER NOT NULL,
                UNIQUE(model_digest, tokenizer_digest, content_digest)
            )""")
            store._db.execute("""CREATE TABLE IF NOT EXISTS offline_document_chunks (
                document_id TEXT NOT NULL REFERENCES offline_documents(document_id)
                    ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY (document_id, ordinal)
            )""")
            store._db.execute("""CREATE INDEX IF NOT EXISTS
                offline_doc_scoping ON offline_documents
                (model_digest, tokenizer_digest, created_ns)""")

    @staticmethod
    def _validate(title: str, content: str) -> bytes:
        if (not isinstance(title, str) or not title.strip()
                or "\x00" in title or
                len(title.encode("utf-8")) > MAX_TITLE_BYTES):
            raise RuntimeContractError("invalid reference document title")
        if not isinstance(content, str) or not content.strip() or "\x00" in content:
            raise RuntimeContractError("reference document must be nonempty text")
        payload = content.encode("utf-8")
        return payload

    @staticmethod
    def _iter_chunks(content: str):
        start = 0
        while start < len(content):
            end = min(len(content), start + _CHUNK_CHARS)
            if end < len(content):
                boundary = content.rfind(" ", start + _CHUNK_CHARS // 2, end)
                if boundary > start:
                    end = boundary
            if end <= start:
                raise RuntimeContractError("invalid reference chunk boundary")
            yield start, end, content[start:end]
            if end == len(content):
                break
            start = max(start + 1, end - _CHUNK_OVERLAP)

    @staticmethod
    def _chunks(content: str) -> list[tuple[int, int, str]]:
        return list(OfflineKnowledgeLibrary._iter_chunks(content))

    def add_text(self, title: str, content: str) -> dict[str, Any]:
        import secrets
        import time

        # The current model-scoped index materializes complete sources/chunks.
        # Admission therefore follows live RAM and free disk, not file count.
        _require_local_headroom(
            len(content), write=True, storage_path=self._storage_path
        )
        payload = self._validate(title, content)
        _require_local_headroom(
            len(payload), write=True, storage_path=self._storage_path
        )
        digest = sha256(payload).hexdigest()
        del payload
        chunk_count = 0
        searchable = False
        for _, _, piece in self._iter_chunks(content):
            chunk_count += 1
            searchable = searchable or bool(_terms(piece))
        if not searchable:
            raise RuntimeContractError("reference document has no searchable terms")
        with self.store._transaction():
            # Duplicate admissions must not launder a corrupted stored source
            # into an apparently verified result. Validate all existing
            # source/offset/hash records before changing or reusing the index.
            self._verified_search_pass(None, consume=lambda _: None)
            row = self.store._db.execute(
                "SELECT document_id, title FROM offline_documents "
                "WHERE model_digest=? AND tokenizer_digest=? AND content_digest=?",
                (self.model_digest, self.tokenizer_digest, digest),
            ).fetchone()
            if row is not None:
                return {
                    "document_id": row[0], "title": row[1], "sha256": digest,
                    "chunk_count": chunk_count, "reused": True,
                }
            # Local document and chunk counts follow available storage, not
            # hardcoded public-hosting quotas. Database errors roll back.
            doc_id = secrets.token_urlsafe(18)
            self.store._db.execute(
                "INSERT INTO offline_documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, self.model_digest, self.tokenizer_digest,
                 title.strip(), digest, content, time.time_ns()),
            )
            self.store._db.executemany(
                "INSERT INTO offline_document_chunks VALUES (?, ?, ?, ?, ?)",
                ((doc_id, index, start, end, piece)
                 for index, (start, end, piece) in enumerate(self._iter_chunks(content))),
            )
            return {
                "document_id": doc_id, "title": title.strip(), "sha256": digest,
                "chunk_count": chunk_count, "reused": False,
            }

    def _verified_snapshot(self, document_ids=None) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        """Verify documents AND source chunks from one SQLite read snapshot.

        Never advertise a citation unless the indexed text is provably an
        exact slice of the stored document whose SHA-256 matches the source.
        """
        selected=tuple(document_ids) if document_ids is not None else ()
        if document_ids is not None and (not selected or len(selected)>256 or len(set(selected))!=len(selected)):
            raise RuntimeContractError("bounded explicit source snapshot required")
        where=(" AND document_id IN ("+",".join("?" for _ in selected)+")") if selected else ""
        joined=(" AND d.document_id IN ("+",".join("?" for _ in selected)+")") if selected else ""
        params=(self.model_digest,self.tokenizer_digest,*selected)
        with self.store._lock:
            own_snapshot = not self.store._db.in_transaction
            if own_snapshot:
                self.store._db.execute("BEGIN")
            try:
                # This legacy verifier materializes the whole model corpus.
                # Check measured headroom before fetching a large snapshot.
                source_bytes = self.store._db.execute(
                    "SELECT COALESCE(SUM(LENGTH(CAST(content_text AS BLOB))),0) "
                    "FROM offline_documents "
                    "WHERE model_digest=? AND tokenizer_digest=?"+where,
                    params,
                ).fetchone()[0]
                _require_local_headroom(
                    int(source_bytes) * 2, storage_path=self._storage_path
                )
                documents = self.store._db.execute(
                    "SELECT document_id, title, content_digest, content_text, "
                    "created_ns FROM offline_documents "
                    "WHERE model_digest=? AND tokenizer_digest=?"+where+
                    " ORDER BY created_ns DESC, document_id",
                    params,
                ).fetchall()
                chunks = self.store._db.execute(
                    "SELECT c.document_id, d.title, d.content_digest, "
                    "c.ordinal, c.char_start, c.char_end, c.content "
                    "FROM offline_documents d JOIN offline_document_chunks c "
                    "ON d.document_id=c.document_id "
                    "WHERE d.model_digest=? AND d.tokenizer_digest=?"+joined+
                    " ORDER BY d.document_id, c.ordinal",
                    params,
                ).fetchall()
            finally:
                if own_snapshot:
                    self.store._db.execute("ROLLBACK")
        if selected and {row[0] for row in documents}!=set(selected):
            raise RuntimeContractError("selected local grounding source is unavailable")
        by_document: dict[str, list[tuple[Any, ...]]] = {}
        for chunk in chunks:
            by_document.setdefault(chunk[0], []).append(chunk)
        for doc in documents:
            doc_id, title, digest, source, _created = doc
            actual = self._validate(title, source)
            if sha256(actual).hexdigest() != _identity(digest, "document digest"):
                raise RuntimeContractError("reference source hash mismatch")
            expected = self._chunks(source)
            actual_chunks = by_document.pop(doc_id, [])
            if len(actual_chunks) != len(expected):
                raise RuntimeContractError("reference source index is incomplete")
            for index, (start, end, passage) in enumerate(expected):
                row = actual_chunks[index]
                if (type(row[3]) is not int or row[3] != index
                        or type(row[4]) is not int or row[4] != start
                        or type(row[5]) is not int or row[5] != end
                        or row[6] != passage):
                    raise RuntimeContractError("reference passage provenance mismatch")
        if by_document:
            raise RuntimeContractError("reference contains orphaned passages")
        return documents, chunks

    def list_documents(self) -> list[dict[str, Any]]:
        documents = []
        def metadata(row):
            documents.append({"document_id": row[0], "title": row[1], "sha256": row[2],
                              "character_count": len(row[3]), "created_ns": row[4]})
        with self._read_snapshot():
            self._verified_search_pass(None, consume=lambda _: None, on_document=metadata)
        return sorted(documents, key=lambda row: (-row["created_ns"], row["document_id"]))

    def delete(self, document_id: str) -> None:
        if (not isinstance(document_id, str) or not 8 <= len(document_id) <= 100
                or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                       for c in document_id)):
            raise RuntimeContractError("invalid reference document id")
        with self.store._transaction():
            deleted = self.store._db.execute(
                "DELETE FROM offline_documents WHERE document_id=? "
                "AND model_digest=? AND tokenizer_digest=?",
                (document_id, self.model_digest, self.tokenizer_digest),
            )
            if deleted.rowcount != 1:
                raise RuntimeContractError("unknown local reference document")
            if self.store._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='offline_semantic_vectors'").fetchone():
                scope=sha256(("offline-knowledge-v1:"+self.model_digest+":"+self.tokenizer_digest).encode()).hexdigest()
                self.store._db.execute("DELETE FROM offline_semantic_vectors WHERE scope=?",(scope,))

    def get_document(self, document_id: str) -> dict[str, Any]:
        """Return the exact verified source for inspection or private export."""
        if not isinstance(document_id, str) or len(document_id) > 100:
            raise RuntimeContractError("invalid reference document id")
        result = None
        def collect(row):
            nonlocal result
            if row[0] == document_id:
                result = {
                    "document_id": row[0], "title": row[1], "sha256": row[2],
                    "text": row[3], "created_ns": str(row[4]),
                    "size_bytes": len(row[3].encode("utf-8")),
                }
        with self._read_snapshot():
            self._verified_search_pass(None, consume=lambda _: None, on_document=collect)
        if result is None:
            raise RuntimeContractError("unknown local reference document")
        return result

    @contextmanager
    def _read_snapshot(self):
        with self.store._lock:
            own_snapshot = not self.store._db.in_transaction
            if own_snapshot:
                self.store._db.execute("BEGIN")
            try:
                yield
            finally:
                if own_snapshot:
                    self.store._db.execute("ROLLBACK")

    def _verified_search_pass(self, selected, *, consume, on_document=None):
        """Verify a complete model scope one source at a time under one snapshot.

        The caller owns the read transaction/lock. Source content and chunk
        provenance are never trusted merely because SQL matched a term.
        """
        scope = (self.model_digest, self.tokenizer_digest)
        rows = self.store._db.execute(
            "SELECT document_id, LENGTH(CAST(content_text AS BLOB)) "
            "FROM offline_documents WHERE model_digest=? AND tokenizer_digest=? "
            "ORDER BY document_id", scope,
        )
        found = set()  # only requested IDs, never one entry per corpus document
        try:
            for doc_id, size in rows:
                _require_local_headroom(int(size) * 2, storage_path=self._storage_path)
                doc = self.store._db.execute(
                    "SELECT title, content_digest, content_text, created_ns FROM offline_documents "
                    "WHERE document_id=? AND model_digest=? AND tokenizer_digest=?",
                    (doc_id, *scope),
                ).fetchone()
                if doc is None:
                    raise RuntimeContractError("reference source vanished inside snapshot")
                title, digest, source, created = doc
                payload = self._validate(title, source)
                if sha256(payload).hexdigest() != _identity(digest, "document digest"):
                    raise RuntimeContractError("reference source hash mismatch")
                del payload
                include = selected is None or doc_id in selected
                if selected is not None and include:
                    found.add(doc_id)
                indexed = self.store._db.execute(
                    "SELECT ordinal, char_start, char_end, content "
                    "FROM offline_document_chunks WHERE document_id=? ORDER BY ordinal",
                    (doc_id,),
                )
                try:
                    for n, (start, end, passage) in enumerate(self._iter_chunks(source)):
                        actual = indexed.fetchone()
                        if actual is None:
                            raise RuntimeContractError("reference source index is incomplete")
                        if (type(actual[0]) is not int or actual[0] != n
                                or type(actual[1]) is not int or actual[1] != start
                                or type(actual[2]) is not int or actual[2] != end
                                or actual[3] != passage):
                            raise RuntimeContractError("reference passage provenance mismatch")
                        if include:
                            consume((doc_id, title, digest, n, start, end, passage))
                    if indexed.fetchone() is not None:
                        raise RuntimeContractError("reference source index contains extra passages")
                finally:
                    indexed.close()
                if on_document is not None and include:
                    on_document((doc_id, title, digest, source, created))
                del source, doc
        finally:
            rows.close()
        if selected is not None and found != selected:
            raise RuntimeContractError("selected local grounding source is unavailable")

    def search(self, query: str, *, limit: int = 6,
               document_ids: tuple[str, ...] | list[str] | None = None,
               diversify: bool = False,
               ) -> list[dict[str, Any]]:
        """Exact two-pass search with bounded retained ranking state.

        Every source and indexed slice remains verified inside a single read
        snapshot. Sparse matching rows use bounded query-local scratch; dense
        queries transparently replay the verified SQL snapshot. At most 48
        scored results survive. No stale cross-transaction result cache or
        authority is introduced. Integrity verification is still linear.
        """
        if (not isinstance(query, str) or not query.strip()
                or len(query.encode("utf-8")) > MAX_QUERY_BYTES):
            raise RuntimeContractError("invalid local reference query")
        if type(evidence_excerpt) is not bool:
            raise RuntimeContractError("explicit semantic evidence excerpt mode required")
        if type(limit) is not int or not 1 <= limit <= 12:
            raise RuntimeContractError("invalid reference search limit")
        if type(diversify) is not bool:
            raise RuntimeContractError("explicit grounding diversity policy required")
        pool_limit = min(48, limit * 4) if diversify else limit
        from .offline_grounding import normalized_document_scope
        normalized = normalized_document_scope(document_ids)
        selected = None if normalized is None else set(normalized)
        terms = _terms(query)
        if not terms and selected is None and self._semantic_ranker is None:
            return []
        df = {term: 0 for term in terms}
        n = 0
        best: list[LocalKnowledgeHit] = []
        sparse = []
        sparse_bytes = 0
        sparse_available = True
        query_lower = unicodedata.normalize("NFKC", query.strip()).casefold()

        def frequencies(row):
            text = unicodedata.normalize("NFKC", row[6]).casefold()
            freqs: dict[str, int] = {}
            for token in _TERMS.findall(text):
                if token in df:
                    freqs[token] = freqs.get(token, 0) + 1
            return text, freqs

        def count(row):
            nonlocal n, sparse_bytes, sparse_available
            n += 1
            text, freqs = frequencies(row)
            for token in freqs:
                df[token] += 1
            if not freqs or not sparse_available:
                return
            # A sparse query can finish ranking immediately after the integrity
            # pass. Store only matched rows and small term-count tuples. The
            # estimate deliberately overcounts text as 4 bytes/codepoint plus
            # container, metadata and dictionary entries. A dense query falls
            # back to the original same-snapshot SQL replay with no loss.
            cost = 512 + 4 * sum(len(x) for x in (row[0], row[1], row[2], row[6]))
            cost += sum(128 + 4 * len(term) for term in freqs)
            if len(sparse) >= _SPARSE_MATCH_COUNT or sparse_bytes + cost > _SPARSE_MATCH_BYTES:
                sparse.clear()
                sparse_available = False
                sparse_bytes = 0
            else:
                sparse.append((row, freqs, query_lower in text))
                sparse_bytes += cost

        def score(row, freqs=None, phrase=None):
            if freqs is None:
                text, freqs = frequencies(row)
                phrase = query_lower in text
            if not freqs:
                return
            value = sum(
                (1.0 + math.log1p(freqs[token]))
                * math.log1p((n + 1) / (df[token] + 0.5))
                for token in sorted(freqs)
            )
            if phrase:
                value += 2.0
            hit = LocalKnowledgeHit(
                document_id=row[0], title=row[1], sha256=row[2],
                chunk_index=row[3], char_start=row[4], char_end=row[5],
                passage=row[6], score=value,
            )
            best.append(hit)
            best.sort(key=lambda x: (-x.score, x.document_id, x.chunk_index))
            if len(best) > pool_limit:
                best.pop()

        with self._read_snapshot():
            self._verified_search_pass(selected, consume=count)
            if sparse_available:
                for row, freqs, phrase in sparse:
                    score(row, freqs, phrase)
            elif terms and n:
                # The first pass verified every relevant source and every
                # indexed slice in this SAME SQLite snapshot. Re-read the
                # joined rows without rehashing documents or regenerating
                # chunk boundaries. No unverified ranking shortcut survives
                # across transactions or calls.
                records = self.store._db.execute(
                    "SELECT c.document_id, d.title, d.content_digest, "
                    "c.ordinal, c.char_start, c.char_end, c.content "
                    "FROM offline_documents d JOIN offline_document_chunks c "
                    "ON d.document_id=c.document_id WHERE d.model_digest=? "
                    "AND d.tokenizer_digest=? ORDER BY c.document_id, c.ordinal",
                    (self.model_digest, self.tokenizer_digest),
                )
                try:
                    for row in records:
                        if selected is None or row[0] in selected:
                            score(row)
                finally:
                    records.close()
        selected_hits = _diverse_grounding_hits(best, limit) if diversify else best
        return [hit.to_dict() for hit in selected_hits]

    def _semantic_search(self,query,documents,records,*,limit,selected,evidence_excerpt):
        from collections import defaultdict
        from skeleton.retrieval.semantic_long_context import document_spans
        policy=self._semantic_ranker.policy
        if len(records)>policy.max_spans or sum(len(row[3]) for row in documents)>policy.max_source_chars:
            raise RuntimeContractError("semantic source selection exceeds configured local budget")
        by_source=defaultdict(list)
        for row in records:
            by_source[row[0]].append((row[3],row[4],row[5],row[6]))
        spans=[]
        titles={doc[0]:doc[1] for doc in documents}
        with self.store._lock:
            try:
                for source_id,title,pin,body,_ in documents:
                    spans.extend(document_spans(source_id,pin,body,by_source[source_id],policy))
                ranked,proof=self._semantic_ranker.search(query,spans,limit=limit,cache=self._semantic_cache)
                results=[]
                for row,score in ranked:
                    start,end=(0,len(row.text))
                    if evidence_excerpt:
                        from .offline_grounding import MAX_EXCERPT_CHARS
                        start,end=self._semantic_ranker.evidence_excerpt(query,row,max_chars=MAX_EXCERPT_CHARS)
                    results.append(LocalKnowledgeHit(row.source_id,titles[row.source_id],row.revision,row.ordinal,
                                                     row.start+start,row.start+end,row.text[start:end],score).to_dict())
                observed,_=self._verified_snapshot(selected)
                if selected is not None:
                    observed=[row for row in observed if row[0] in set(selected)]
                if [(x[0],x[1],x[2],x[4]) for x in observed]!=[(x[0],x[1],x[2],x[4]) for x in documents]:
                    if self._semantic_cache is not None:
                        self._semantic_cache.invalidate()
                    raise RuntimeContractError("semantic source authority changed during retrieval")
            except (ValueError,MemoryError,OSError) as exc:
                raise RuntimeContractError("bounded learned semantic retrieval failed") from exc
        return results

    def semantic_source_snapshot(self):
        """Streaming, scope-bound inventory identity; source bytes verified on use."""
        import json
        h=sha256(("offline-ann-v1:"+self.model_digest+":"+self.tokenizer_digest).encode())
        db=self.store._db
        with self.store._lock:
            cursor=db.execute("""SELECT document_id,title,content_digest,created_ns,
                LENGTH(CAST(content_text AS BLOB))
                FROM offline_documents WHERE model_digest=? AND tokenizer_digest=?
                ORDER BY document_id""",(self.model_digest,self.tokenizer_digest))
            for row in cursor:
                raw=json.dumps(list(row),ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
                h.update(len(raw).to_bytes(8,"big"))
                h.update(raw)
        return h.hexdigest()

    def build_semantic_ann(self,root,name,policy,*,previous=None,interrupt=None):
        """Publish a private generation from one canonical SQLite read snapshot."""
        from skeleton.retrieval.disk_semantic_ann import build_generation,DiskANNPolicy,DiskANN
        from skeleton.retrieval.semantic_long_context import document_spans
        if self._semantic_ranker is None or not isinstance(policy,DiskANNPolicy):
            raise RuntimeContractError("explicit local learned ranker and ANN policy required")
        ranker=self._semantic_ranker
        if previous is not None and (not isinstance(previous,DiskANN) or previous.space!=ranker.identity or previous.dimension!=ranker.encoder.policy.dimension):
            raise RuntimeContractError("previous ANN feature space differs from current ranker")
        reuse={"reused_dense":0,"encoded_dense":0,"encoder_calls":0}
        def features(batch):
            cached=previous.fetch_dense(batch) if previous is not None else {}
            missing=[leaf for leaf in batch if leaf.identity not in cached]
            encoded,calls=ranker._features(missing,None,interrupt) if missing else ({},0)
            reuse["reused_dense"]+=len(cached)
            reuse["encoded_dense"]+=len(missing)
            reuse["encoder_calls"]+=calls
            for leaf in batch:
                yield leaf,cached.get(leaf.identity) or encoded[leaf.identity]
        db=self.store._db
        with self.store._lock:
            if db.in_transaction:
                raise RuntimeContractError("ANN generation requires exclusive read snapshot")
            db.execute("BEGIN")
            try:
                snapshot=self.semantic_source_snapshot()
                def rows():
                    cursor=db.execute("""SELECT document_id FROM offline_documents
                      WHERE model_digest=? AND tokenizer_digest=? ORDER BY document_id""",
                      (self.model_digest,self.tokenizer_digest))
                    for (source_id,) in cursor:
                        if interrupt:interrupt()
                        docs,chunks=self._verified_snapshot([source_id])
                        doc=docs[0]
                        pieces=((r[3],r[4],r[5],r[6]) for r in chunks)
                        batch=[]
                        for span in document_spans(doc[0],doc[2],doc[3],pieces,ranker.policy):
                            batch.append(span)
                            if len(batch)==128:
                                yield from features(batch)
                                batch.clear()
                        if batch:
                            yield from features(batch)
                receipt=build_generation(root,name,rows(),space=ranker.identity,
                    source_snapshot=snapshot,dimension=ranker.encoder.policy.dimension,
                    policy=policy,interrupt=interrupt)
            finally:
                db.execute("ROLLBACK")
            if self.semantic_source_snapshot()!=snapshot:
                # Immutable build remains historical but cannot activate.
                raise RuntimeContractError("source changed during ANN build; generation is historical only")
        receipt.update(reuse)
        receipt["previous_manifest_sha256"]=previous.manifest_sha256 if previous is not None else None
        return receipt

    def attach_semantic_ann(self,root,manifest_sha256):
        from skeleton.retrieval.disk_semantic_ann import DiskANN
        if self._semantic_ranker is None:
            raise RuntimeContractError("ANN requires an explicitly configured learned encoder")
        index=DiskANN(root,manifest_sha256,expected_space=self._semantic_ranker.identity,
                      expected_snapshot=self.semantic_source_snapshot())
        if index.dimension!=self._semantic_ranker.encoder.policy.dimension:
            raise RuntimeContractError("ANN encoder dimension mismatch")
        self._semantic_ann=index

    def _ann_search(self,query,*,limit,selected,evidence_excerpt):
        from skeleton.retrieval.semantic_long_context import document_spans
        index=self._semantic_ann
        ranker=self._semantic_ranker
        with self.store._lock:
            try:
                if self.semantic_source_snapshot()!=index.snapshot:
                    raise RuntimeContractError("semantic ANN generation stale; explicit rebuild required")
                if selected is not None:
                    chosen=set(selected)
                    placeholders=",".join("?" for _ in chosen)
                    observed={r[0] for r in self.store._db.execute(
                        "SELECT document_id FROM offline_documents WHERE model_digest=? AND tokenizer_digest=? AND document_id IN ("+placeholders+")",
                        (self.model_digest,self.tokenizer_digest,*sorted(chosen)))}
                    if observed!=chosen:
                        raise RuntimeContractError("selected local grounding source is unavailable")
                q=ranker.encoder.query(query,segments=16)
                candidates,proof=index.search(query,q.dense,allowed_source_ids=selected,
                   limit=min(index.policy.global_candidate_limit,ranker.policy.candidate_pool,256))
                if not candidates:
                    if self.semantic_source_snapshot()!=index.snapshot:
                        raise RuntimeContractError("semantic ANN generation stale")
                    return []
                by_doc={}
                for c in candidates:
                    by_doc.setdefault(c.source_id,[]).append(c)
                spans=[]
                titles={}
                for source_id,rows in by_doc.items():
                    docs,chunks=self._verified_snapshot([source_id])
                    doc=docs[0]
                    wanted={r.ordinal:r for r in rows}
                    titles[source_id]=doc[1]
                    for leaf in document_spans(doc[0],doc[2],doc[3],
                        ((r[3],r[4],r[5],r[6]) for r in chunks if r[3] in wanted),ranker.policy):
                        c=wanted.pop(leaf.ordinal)
                        if (leaf.identity!=c.span_sha256 or leaf.revision!=c.source_revision or
                            leaf.start!=c.start or leaf.end!=c.end):
                            raise RuntimeContractError("ANN candidate source custody mismatch")
                        spans.append(leaf)
                    if wanted:
                        raise RuntimeContractError("ANN candidate source was withdrawn")
                ranked,_=ranker.search(query,spans,limit=min(limit,ranker.policy.candidate_pool),cache=self._semantic_cache)
                result=[]
                for row,score in ranked:
                    start,end=0,len(row.text)
                    if evidence_excerpt:
                        from .offline_grounding import MAX_EXCERPT_CHARS
                        start,end=ranker.evidence_excerpt(query,row,max_chars=MAX_EXCERPT_CHARS)
                    result.append(LocalKnowledgeHit(row.source_id,titles[row.source_id],row.revision,row.ordinal,
                                row.start+start,row.start+end,row.text[start:end],score).to_dict())
                if self.semantic_source_snapshot()!=index.snapshot:
                    if self._semantic_cache is not None:self._semantic_cache.invalidate()
                    raise RuntimeContractError("semantic ANN authority changed during retrieval")
                return result
            except RuntimeContractError:
                raise
            except (ValueError,MemoryError,OSError) as exc:
                raise RuntimeContractError("bounded disk semantic retrieval failed") from exc


__all__ = [
    "OfflineKnowledgeLibrary", "LocalKnowledgeHit", "read_reference_file",
    "MAX_DOCUMENT_BYTES", "MAX_DOCUMENTS_PER_MODEL", "MAX_CHUNKS_PER_MODEL",
]
