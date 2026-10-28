"""TF-IDF inverted index for the retrieval package.

The retrieval stack fuses results from back-ends; the index is the
back-end that lives in-process. Tokenise → sublinear TF → BM25-style
IDF → ScoredResult with plane="index". Slots straight into Fuser/Ranker.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any, Dict, List, Mapping, Tuple

from skeleton.retrieval.freshness import PlaneFreshness
from skeleton.retrieval.fusion import ScoredResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_INDEX_STATE_VERSION = 1


class InvertedIndex:
    """In-process inverted index with BM25-lite scoring."""

    def __init__(self, *, b: float = 0.75, k1: float = 1.5) -> None:
        if isinstance(b, bool) or not isinstance(b, (int, float)) or not 0.0 <= float(b) <= 1.0:
            raise ValueError("b must be between 0 and 1")
        if isinstance(k1, bool) or not isinstance(k1, (int, float)) or float(k1) < 0.0:
            raise ValueError("k1 must be non-negative")
        self._docs: Dict[str, List[str]] = {}
        self._content: Dict[str, str] = {}
        self._df: Counter[str] = Counter()
        self._doc_length: Dict[str, int] = {}
        self._postings: Dict[str, Dict[str, int]] = {}
        self._total_doc_length = 0
        self._revision = 0
        self.k1 = float(k1)
        self.b = float(b)

    def add(self, doc_id: str, text: str) -> None:
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("doc_id must be a non-empty string")
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        tokens = self._tokenise(text)
        if not tokens:
            raise ValueError("text must contain a token")
        term_counts = Counter(tokens)
        new_terms = set(term_counts)

        old_tokens = self._docs.get(doc_id)
        old_terms = set(old_tokens) if old_tokens is not None else set()
        if old_tokens is not None:
            self._total_doc_length -= self._doc_length[doc_id]

        for term in old_terms - new_terms:
            self._df[term] -= 1
            if self._df[term] <= 0:
                del self._df[term]
            posting = self._postings.get(term)
            if posting is not None:
                posting.pop(doc_id, None)
                if not posting:
                    del self._postings[term]

        for term in old_terms & new_terms:
            self._postings[term][doc_id] = term_counts[term]

        for term in new_terms - old_terms:
            self._df[term] += 1
            self._postings.setdefault(term, {})[doc_id] = term_counts[term]

        self._docs[doc_id] = tokens
        self._content[doc_id] = text
        self._doc_length[doc_id] = len(tokens)
        self._total_doc_length += len(tokens)
        self._revision += 1

    def remove(self, doc_id: str) -> bool:
        tokens = self._docs.get(doc_id)
        if tokens is None:
            return False

        for term in set(tokens):
            self._df[term] -= 1
            if self._df[term] <= 0:
                del self._df[term]
            posting = self._postings.get(term)
            if posting is not None:
                posting.pop(doc_id, None)
                if not posting:
                    del self._postings[term]

        self._total_doc_length -= self._doc_length[doc_id]
        del self._docs[doc_id]
        del self._content[doc_id]
        del self._doc_length[doc_id]
        self._revision += 1
        return True

    @property
    def revision(self) -> int:
        return self._revision

    def content_digest(self) -> str:
        """Digest exact indexed content, independent of insertion order."""
        encoded = json.dumps(
            [
                {"doc_id": doc_id, "text": self._content[doc_id]}
                for doc_id in sorted(self._content)
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(encoded, digest_size=16).hexdigest()

    def snapshot(self) -> Dict[str, Any]:
        """Return a versioned deterministic checkpoint for restart/migration."""
        return {
            "version": _INDEX_STATE_VERSION,
            "revision": self._revision,
            "b": self.b,
            "k1": self.k1,
            "content_digest": self.content_digest(),
            "documents": [
                {"doc_id": doc_id, "text": self._content[doc_id]}
                for doc_id in sorted(self._content)
            ],
        }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "InvertedIndex":
        """Restore an index checkpoint, rejecting incompatible/corrupt state."""
        if not isinstance(payload, Mapping):
            raise ValueError("index snapshot must be a mapping")
        if payload.get("version") != _INDEX_STATE_VERSION:
            raise ValueError("unsupported index snapshot version")
        revision = payload.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("index revision must be a non-negative integer")
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise ValueError("index snapshot documents must be a list")
        index = cls(
            b=payload.get("b"),
            k1=payload.get("k1"),
        )
        seen = set()
        for row in documents:
            if not isinstance(row, Mapping):
                raise ValueError("index snapshot document must be a mapping")
            doc_id = row.get("doc_id")
            text = row.get("text")
            if not isinstance(doc_id, str) or not doc_id:
                raise ValueError("snapshot doc_id must be a non-empty string")
            if doc_id in seen:
                raise ValueError("duplicate doc_id in index snapshot")
            if not isinstance(text, str):
                raise ValueError("snapshot text must be a string")
            seen.add(doc_id)
            index.add(doc_id, text)
        if revision < len(documents):
            raise ValueError("index revision cannot trail document count")
        expected_digest = payload.get("content_digest")
        if not isinstance(expected_digest, str) or expected_digest != index.content_digest():
            raise ValueError("index snapshot content digest mismatch")
        index._revision = revision
        return index

    def freshness_state(
        self,
        *,
        source_revision: str,
        indexed_at: float,
        stale_after_s: float,
    ) -> PlaneFreshness:
        """Bind freshness to this exact index corpus digest."""
        return PlaneFreshness(
            plane="index",
            index_version=self.content_digest(),
            source_revision=source_revision,
            indexed_at=indexed_at,
            stale_after_s=stale_after_s,
        )

    def search(
        self, query: str, *, top_k: int = 10
    ) -> Tuple[ScoredResult, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
        query_counts = Counter(self._tokenise(query))
        if not query_counts:
            raise ValueError("query must contain a token")
        if not self._docs:
            return tuple()

        n_docs = len(self._docs)
        avgdl = self._total_doc_length / n_docs
        if avgdl <= 0:
            raise ValueError("index has no tokens")
        scores: Dict[str, float] = {}
        for token, query_tf in query_counts.items():
            postings = self._postings.get(token)
            if not postings:
                continue
            df = self._df.get(token, 0)
            if df <= 0:
                continue
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            for doc_id, tf_raw in postings.items():
                dl = self._doc_length[doc_id]
                if dl <= 0:
                    raise ValueError("document has no tokens")
                norm = 1 - self.b + self.b * (dl / avgdl)
                tf = tf_raw / (tf_raw + self.k1 * norm)
                scores[doc_id] = (
                    scores.get(doc_id, 0.0) + query_tf * idf * tf
                )

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        return tuple(
            ScoredResult(
                fragment_id=doc_id,
                content=self._content[doc_id],
                score=round(score, 6),
                plane="index",
            )
            for doc_id, score in ranked
        )

    def size(self) -> int:
        return len(self._docs)

    @staticmethod
    def _tokenise(text: str) -> List[str]:
        return _TOKEN_PATTERN.findall(text.lower())
