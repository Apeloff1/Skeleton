"""TF-IDF inverted index for the retrieval package.

The retrieval stack fuses results from back-ends; the index is the
back-end that lives in-process. Tokenise → sublinear TF → BM25-style
IDF → ScoredResult with plane="index". Slots straight into Fuser/Ranker.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

from skeleton.retrieval.fusion import ScoredResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


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
        self.k1 = k1
        self.b = b

    def add(self, doc_id: str, text: str) -> None:
        tokens = self._tokenise(text)
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
        return True

    def search(
        self, query: str, *, top_k: int = 10
    ) -> Tuple[ScoredResult, ...]:
        query_counts = Counter(self._tokenise(query))
        if not query_counts:
            return tuple()

        n_docs = max(len(self._docs), 1)
        avgdl = (self._total_doc_length / n_docs) or 1.0
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
                dl = self._doc_length.get(doc_id, 1) or 1
                norm = 1 - self.b + self.b * (dl / avgdl)
                tf = tf_raw / (tf_raw + self.k1 * norm)
                scores[doc_id] = (
                    scores.get(doc_id, 0.0) + query_tf * idf * tf
                )

        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
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
