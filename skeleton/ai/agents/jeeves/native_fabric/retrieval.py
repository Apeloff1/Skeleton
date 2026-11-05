"""Pure bounded lexical search over already-approved source snippets.

This is only a relevance/indexing layer. A source still requires the existing
signed manifest, descriptor-anchored read and live principal check before
it may be presented to the model. Indexing a document never grants source
read authority, copyright rights, model instruction precedence or tool use.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import math
import re
from typing import Iterable, Mapping, Sequence

from .contracts import (
    ContractHold, canonical_bytes, digest, exact_integer, fingerprint,
    identifier, text,
)


_WORD = re.compile(r"[^\W_]+(?:[_'-][^\W_]+)*", re.UNICODE)


def tokenize(raw: str, *, maximum: int = 8192) -> tuple[str, ...]:
    text(raw, maximum_bytes=262144, may_be_empty=True)
    exact_integer(maximum, minimum=1, maximum=100000)
    return tuple(m.group(0).casefold() for m in _WORD.finditer(raw))[:maximum]


@dataclass(frozen=True, slots=True)
class SourceChunk:
    chunk_id: str
    parent_sha256: str
    scope_sha256: str
    content: str
    offset_bytes: int
    complete_source: bool

    def __post_init__(self):
        identifier(self.chunk_id, "chunk")
        digest(self.parent_sha256)
        digest(self.scope_sha256)
        text(self.content, maximum_bytes=65536)
        exact_integer(self.offset_bytes, maximum=2**40)
        if type(self.complete_source) is not bool:
            raise ContractHold("chunk completeness must be explicit")

    @property
    def fingerprint(self) -> str:
        return fingerprint({
            "chunk": self.chunk_id, "parent": self.parent_sha256,
            "scope": self.scope_sha256, "offset": self.offset_bytes,
            "text_sha256": sha256(self.content.encode("utf-8")).hexdigest(),
            "complete": self.complete_source,
        })


def split_source(
    content: str, *, source_id: str, scope_sha256: str,
    chunk_bytes: int = 2048, overlap_bytes: int = 128,
    maximum_chunks: int = 512,
) -> tuple[SourceChunk, ...]:
    identifier(source_id, "source")
    digest(scope_sha256)
    text(content, maximum_bytes=1048576)
    exact_integer(chunk_bytes, minimum=128, maximum=65536)
    exact_integer(overlap_bytes, maximum=32768)
    exact_integer(maximum_chunks, minimum=1, maximum=4096)
    if overlap_bytes >= chunk_bytes:
        raise ContractHold("overlap must be smaller than source chunk")
    raw = content.encode("utf-8", "strict")
    parent = sha256(raw).hexdigest()
    # Split UTF-8 by character boundaries; positions remain exact byte
    # offsets into the attested original rather than decoded character indexes.
    chunks: list[SourceChunk] = []
    start = 0
    while start < len(raw):
        end = min(start + chunk_bytes, len(raw))
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        if end <= start:
            raise ContractHold("source has a codepoint longer than chunk ceiling")
        piece = raw[start:end].decode("utf-8", "strict")
        chunks.append(SourceChunk(
            chunk_id=f"{source_id}:c{len(chunks):04d}",
            parent_sha256=parent,
            scope_sha256=scope_sha256,
            content=piece,
            offset_bytes=start,
            complete_source=end == len(raw),
        ))
        if len(chunks) > maximum_chunks:
            raise ContractHold("source would exceed bounded chunk inventory")
        if end == len(raw):
            break
        next_start = max(start + 1, end - overlap_bytes)
        while next_start < end and (raw[next_start] & 0xC0) == 0x80:
            next_start += 1
        if next_start >= end:
            next_start = end
        start = next_start
    if not chunks:
        raise ContractHold("source cannot produce zero chunks")
    return tuple(chunks)


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: SourceChunk
    score: float
    matched_terms: tuple[str, ...]
    rank: int

    def __post_init__(self):
        if not isinstance(self.chunk, SourceChunk):
            raise ContractHold("typed source chunk required")
        if type(self.score) is not float or not math.isfinite(self.score) or self.score < 0:
            raise ContractHold("nonnegative finite retrieval score required")
        exact_integer(self.rank, minimum=1)
        if len(self.matched_terms) > 256:
            raise ContractHold("unbounded matched terms")


class BoundedLexicalIndex:
    """Deterministic BM25 without network, embeddings or private file reads."""

    def __init__(
        self, chunks: Sequence[SourceChunk], *,
        scope_sha256: str,
        maximum_chunks: int = 4096,
        k1: float = 1.2, b: float = 0.75,
    ):
        digest(scope_sha256)
        exact_integer(maximum_chunks, minimum=1, maximum=100000)
        if type(chunks) not in (tuple, list) or not 1 <= len(chunks) <= maximum_chunks:
            raise ContractHold("bounded index corpus required")
        if type(k1) not in (float, int) or type(b) not in (float, int):
            raise ContractHold("finite BM25 settings required")
        if not math.isfinite(k1) or not 0.1 <= k1 <= 5.0:
            raise ContractHold("invalid BM25 saturation")
        if not math.isfinite(b) or not 0.0 <= b <= 1.0:
            raise ContractHold("invalid BM25 length normalization")
        self.scope_sha256 = scope_sha256
        self.k1, self.b = float(k1), float(b)
        self.chunks = tuple(chunks)
        self._terms: dict[str, Counter[str]] = {}
        self._df: Counter[str] = Counter()
        lengths = []
        for chunk in chunks:
            if not isinstance(chunk, SourceChunk) or chunk.scope_sha256 != scope_sha256:
                raise ContractHold("cross-scope source index forbidden")
            if chunk.chunk_id in self._terms:
                raise ContractHold("duplicate source chunk ID")
            terms = Counter(tokenize(chunk.content))
            self._terms[chunk.chunk_id] = terms
            self._df.update(terms.keys())
            lengths.append(sum(terms.values()))
        self._mean_length = max(1, sum(lengths) / len(lengths))

    def _score(self, terms: Counter[str], query: tuple[str, ...]) -> float:
        length = sum(terms.values())
        normalization = self.k1 * (1 - self.b + self.b * length / self._mean_length)
        total = 0.0
        N = len(self.chunks)
        for term in set(query):
            freq = terms.get(term, 0)
            if freq == 0:
                continue
            df = self._df[term]
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            total += idf * freq * (self.k1 + 1) / (freq + normalization)
        return total

    def search(
        self, query: str, *,
        maximum_results: int = 16,
        minimum_match: int = 1,
    ) -> tuple[SearchHit, ...]:
        text(query, maximum_bytes=32768)
        exact_integer(maximum_results, minimum=1, maximum=256)
        exact_integer(minimum_match, minimum=1, maximum=256)
        q = tokenize(query, maximum=256)
        if not q:
            raise ContractHold("query lacks searchable words")
        candidates = []
        for chunk in self.chunks:
            tf = self._terms[chunk.chunk_id]
            matched = tuple(sorted(term for term in set(q) if tf.get(term, 0)))
            if len(matched) < minimum_match:
                continue
            score = self._score(tf, q)
            if score <= 0:
                continue
            candidates.append((chunk, score, matched))
        candidates.sort(key=lambda t: (-t[1], t[0].chunk_id))
        return tuple(
            SearchHit(chunk, float(score), matched, rank)
            for rank, (chunk, score, matched) in enumerate(
                candidates[:maximum_results], start=1,
            )
        )

    def source_coverage(self, query: str) -> dict[str, object]:
        q = set(tokenize(query, maximum=256))
        if not q:
            raise ContractHold("query has no searchable terms")
        observed = set(self._df)
        missing = tuple(sorted(q - observed))
        return {
            "schema": "jeeves.fabric.source_coverage.v1",
            "scope_sha256": self.scope_sha256,
            "query_sha256": sha256(query.encode("utf-8")).hexdigest(),
            "matched_terms": len(q) - len(missing),
            "total_terms": len(q),
            "missing_terms": missing,
            "source_rights_qualified": False,
        }


__all__ = [
    "tokenize", "SourceChunk", "split_source", "SearchHit",
    "BoundedLexicalIndex",
]
