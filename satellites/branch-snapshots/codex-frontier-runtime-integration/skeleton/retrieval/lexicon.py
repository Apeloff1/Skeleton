"""Query lexicon — stopword filter and synonym expansion."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


_STOPWORDS: frozenset = frozenset(
    {"the", "a", "an", "of", "to", "in", "on", "at", "is", "it"}
)


class Lexicon:
    """Term-level helpers shared by the query planner."""

    def __init__(self, synonyms: Optional[Dict[str, List[str]]] = None) -> None:
        self._synonyms = synonyms or {}

    def expand(self, term: str) -> Tuple[str, ...]:
        if term in self._synonyms:
            return (term,) + tuple(self._synonyms[term])
        return (term,)

    def filter_stopwords(self, query: str) -> str:
        return " ".join(
            token for token in query.split() if token.lower() not in _STOPWORDS
        )

    def define(self, term: str, synonyms: List[str]) -> None:
        self._synonyms[term] = synonyms


def default_lexicon() -> Lexicon:
    return Lexicon()
