"""Private deterministic reference library for Skeleton's offline AI workspace.

This implements *searchable evidence retrieval*, not a claim that arbitrary
generated model text is grounded. It deliberately never downloads, crawls,
executes, follows stored file paths or interprets stored text as instructions.
Explicit operator-selected files use safe, no-follow regular-file admission.
"""
from __future__ import annotations

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


# Legacy symbolic names remain importable. None means no public-service quota.
MAX_DOCUMENT_BYTES = None
MAX_TITLE_BYTES = 200
MAX_DOCUMENTS_PER_MODEL = None
MAX_CHUNKS_PER_MODEL = None
MAX_SEARCH_TOKENS = 24
MAX_QUERY_BYTES = 1_024
_CHUNK_CHARS = 600
_CHUNK_OVERLAP = 80
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
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            parts: list[str] = []
            byte_count = 0
            try:
                while data := source.read(256 * 1024):
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


class OfflineKnowledgeLibrary:
    """Model-scoped documents stored in the existing local SQLite DB."""

    def __init__(self, store: OfflineChatStore, model_digest: str,
                 tokenizer_digest: str) -> None:
        if not isinstance(store, OfflineChatStore):
            raise RuntimeContractError("a canonical local SQLite store is required")
        self.store = store
        self.model_digest = _identity(model_digest, "model digest")
        self.tokenizer_digest = _identity(tokenizer_digest, "tokenizer digest")
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
    def _chunks(content: str) -> list[tuple[int, int, str]]:
        rows: list[tuple[int, int, str]] = []
        start = 0
        while start < len(content):
            end = min(len(content), start + _CHUNK_CHARS)
            if end < len(content):
                boundary = content.rfind(" ", start + _CHUNK_CHARS // 2, end)
                if boundary > start:
                    end = boundary
            if end <= start:
                raise RuntimeContractError("invalid reference chunk boundary")
            rows.append((start, end, content[start:end]))
            if end == len(content):
                break
            start = max(start + 1, end - _CHUNK_OVERLAP)
        return rows

    def add_text(self, title: str, content: str) -> dict[str, Any]:
        import secrets
        import time

        payload = self._validate(title, content)
        digest = sha256(payload).hexdigest()
        pieces = self._chunks(content)
        if not any(_terms(piece[2]) for piece in pieces):
            raise RuntimeContractError("reference document has no searchable terms")
        with self.store._transaction():
            # Duplicate admissions must not launder a corrupted stored source
            # into an apparently verified result. Validate all existing
            # source/offset/hash records before changing or reusing the index.
            self._verified_snapshot()
            row = self.store._db.execute(
                "SELECT document_id, title FROM offline_documents "
                "WHERE model_digest=? AND tokenizer_digest=? AND content_digest=?",
                (self.model_digest, self.tokenizer_digest, digest),
            ).fetchone()
            if row is not None:
                return {
                    "document_id": row[0], "title": row[1], "sha256": digest,
                    "chunk_count": len(pieces), "reused": True,
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
                [(doc_id, index, start, end, piece)
                 for index, (start, end, piece) in enumerate(pieces)],
            )
            return {
                "document_id": doc_id, "title": title.strip(), "sha256": digest,
                "chunk_count": len(pieces), "reused": False,
            }

    def _verified_snapshot(self) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        """Verify documents AND source chunks from one SQLite read snapshot.

        Never advertise a citation unless the indexed text is provably an
        exact slice of the stored document whose SHA-256 matches the source.
        """
        with self.store._lock:
            own_snapshot = not self.store._db.in_transaction
            if own_snapshot:
                self.store._db.execute("BEGIN")
            try:
                documents = self.store._db.execute(
                    "SELECT document_id, title, content_digest, content_text, "
                    "created_ns FROM offline_documents "
                    "WHERE model_digest=? AND tokenizer_digest=? "
                    "ORDER BY created_ns DESC, document_id",
                    (self.model_digest, self.tokenizer_digest),
                ).fetchall()
                chunks = self.store._db.execute(
                    "SELECT c.document_id, d.title, d.content_digest, "
                    "c.ordinal, c.char_start, c.char_end, c.content "
                    "FROM offline_documents d JOIN offline_document_chunks c "
                    "ON d.document_id=c.document_id "
                    "WHERE d.model_digest=? AND d.tokenizer_digest=? "
                    "ORDER BY d.document_id, c.ordinal",
                    (self.model_digest, self.tokenizer_digest),
                ).fetchall()
            finally:
                if own_snapshot:
                    self.store._db.execute("ROLLBACK")
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
        documents, _ = self._verified_snapshot()
        return [
            {"document_id": row[0], "title": row[1], "sha256": row[2],
             "character_count": len(row[3]), "created_ns": row[4]}
            for row in documents
        ]

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

    def get_document(self, document_id: str) -> dict[str, Any]:
        """Return the exact verified source for inspection or private export."""
        if not isinstance(document_id, str) or len(document_id) > 100:
            raise RuntimeContractError("invalid reference document id")
        documents, _ = self._verified_snapshot()
        for row in documents:
            if row[0] == document_id:
                return {
                    "document_id": row[0], "title": row[1], "sha256": row[2],
                    "text": row[3], "created_ns": str(row[4]),
                    "size_bytes": len(row[3].encode("utf-8")),
                }
        raise RuntimeContractError("unknown local reference document")

    def search(self, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        if (not isinstance(query, str) or not query.strip()
                or len(query.encode("utf-8")) > MAX_QUERY_BYTES):
            raise RuntimeContractError("invalid local reference query")
        if type(limit) is not int or not 1 <= limit <= 12:
            raise RuntimeContractError("invalid reference search limit")
        terms = _terms(query)
        if not terms:
            return []
        _, records = self._verified_snapshot()
        corpus: list[tuple[tuple[Any, ...], set[str], dict[str, int]]] = []
        df = {term: 0 for term in terms}
        for row in records:
            words = _TERMS.findall(unicodedata.normalize("NFKC", row[6]).casefold())
            freqs: dict[str, int] = {}
            for term in words:
                if term in df:
                    freqs[term] = freqs.get(term, 0) + 1
            for token in freqs:
                df[token] += 1
            corpus.append((row, set(freqs), freqs))
        n = len(corpus)
        scored: list[LocalKnowledgeHit] = []
        query_lower = unicodedata.normalize("NFKC", query.strip()).casefold()
        for row, present, freqs in corpus:
            if not present:
                continue
            score = sum(
                (1.0 + math.log1p(freqs[token]))
                * math.log1p((n + 1) / (df[token] + 0.5))
                for token in present
            )
            if query_lower in unicodedata.normalize("NFKC", row[6]).casefold():
                score += 2.0
            scored.append(LocalKnowledgeHit(
                document_id=row[0], title=row[1], sha256=row[2],
                chunk_index=row[3], char_start=row[4], char_end=row[5],
                passage=row[6], score=score,
            ))
        scored.sort(key=lambda hit: (-hit.score, hit.document_id, hit.chunk_index))
        return [hit.to_dict() for hit in scored[:limit]]


__all__ = [
    "OfflineKnowledgeLibrary", "LocalKnowledgeHit", "read_reference_file",
    "MAX_DOCUMENT_BYTES", "MAX_DOCUMENTS_PER_MODEL", "MAX_CHUNKS_PER_MODEL",
]
