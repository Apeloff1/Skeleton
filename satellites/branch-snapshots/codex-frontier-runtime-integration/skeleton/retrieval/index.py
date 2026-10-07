"""TF-IDF inverted index for the retrieval package.

The retrieval stack fuses results from back-ends; the index is the
back-end that lives in-process. Tokenise → sublinear TF → BM25-style
IDF → ScoredResult with source="index". Slots straight into Fuser/Ranker.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Set, Tuple

from skeleton.retrieval.fusion import ScoredResult

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class InvertedIndex:
    """In-process inverted index with BM25-lite scoring."""

    def __init__(self, *, b: float = 0.75, k1: float = 1.5) -> None:
        self._docs: Dict[str, List[str]] = {}
        self._df: Counter = Counter()
        self._doc_length: Dict[str, int] = {}
        self.k1 = k1
        self.b = b

    def add(self, doc_id: str, text: str) -> None:
        tokens = self._tokenise(text)
        if doc_id in self._docs:
            old_terms = set(self._docs[doc_id])
            for term in old_terms:
                self._df[term] -= 1
        self._docs[doc_id] = tokens
        self._doc_length[doc_id] = len(tokens)
        for term in set(tokens):
            self._df[term] += 1

    def remove(self, doc_id: str) -> bool:
        if doc_id not in self._docs:
            return False
        for term in set(self._docs[doc_id]):
            self._df[term] -= 1
        del self._docs[doc_id]
        del self._doc_length[doc_id]
        return True

    def search(
        self, query: str, *, top_k: int = 10
    ) -> Tuple[ScoredResult, ...]:
        q_tokens = self._tokenise(query)
        if not q_tokens:
            return tuple()
        n_docs = max(len(self._docs), 1)
        avgdl = (
            sum(self._doc_length.values()) / n_docs if n_docs else 1.0
        ) or 1.0
        scores: Dict[str, float] = {}
        for token in q_tokens:
            df = self._df.get(token, 0)
            if df <= 0:
                continue
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            for doc_id, tokens in self._docs.items():
                tf_raw = tokens.count(token)
                if tf_raw == 0:
                    continue
                dl = self._doc_length.get(doc_id, 1) or 1
                norm = 1 - self.b + self.b * (dl / avgdl)
                tf = tf_raw / (tf_raw + self.k1 * norm)
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * tf
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
        return tuple(
            ScoredResult(item_id=doc_id, score=round(score, 6), source="index")
            for doc_id, score in ranked
        )

    def size(self) -> int:
        return len(self._docs)

    @staticmethod
    def _tokenise(text: str) -> List[str]:
        return _TOKEN_PATTERN.findall(text.lower())
