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
            if self.store._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='offline_semantic_vectors'").fetchone():
                scope=sha256(("offline-knowledge-v1:"+self.model_digest+":"+self.tokenizer_digest).encode()).hexdigest()
                self.store._db.execute("DELETE FROM offline_semantic_vectors WHERE scope=?",(scope,))

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

    def search(self, query: str, *, limit: int = 6,
               document_ids: tuple[str, ...] | list[str] | None = None,
               evidence_excerpt: bool = False
               ) -> list[dict[str, Any]]:
        if (not isinstance(query, str) or not query.strip()
                or len(query.encode("utf-8")) > MAX_QUERY_BYTES):
            raise RuntimeContractError("invalid local reference query")
        if type(evidence_excerpt) is not bool:
            raise RuntimeContractError("explicit semantic evidence excerpt mode required")
        if type(limit) is not int or not 1 <= limit <= 12:
            raise RuntimeContractError("invalid reference search limit")
        # Do not fall back to the entire library if an explicitly selected
        # source was withdrawn, deleted or belongs to another model identity.
        from .offline_grounding import normalized_document_scope
        selected = normalized_document_scope(document_ids)
        terms = _terms(query)
        if not terms and selected is None and self._semantic_ranker is None:
            return []
        if self._semantic_ann is not None:
            return self._ann_search(query,limit=limit,selected=selected,evidence_excerpt=evidence_excerpt)
        documents, records = self._verified_snapshot(selected)
        if selected is not None:
            known = {row[0] for row in documents}
            if not set(selected).issubset(known):
                raise RuntimeContractError("selected local grounding source is unavailable")
            selected_set = set(selected)
            records = [row for row in records if row[0] in selected_set]
            documents = [row for row in documents if row[0] in selected_set]
        if self._semantic_ranker is not None:
            return self._semantic_search(query,documents,records,limit=limit,selected=selected,evidence_excerpt=evidence_excerpt)
        if not terms:
            return []
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
