"""Query suggestions — autocomplete from corpus and lexicon."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from skeleton.retrieval.lexicon import Lexicon


class Suggester:
    """Prefix-based suggestions over common terms."""

    def __init__(self, terms: Sequence[str], *, lexicon: Optional[Lexicon] = None) -> None:
        self._terms = sorted(set(terms))
        self._lexicon = lexicon

    def suggest(self, prefix: str, *, limit: int = 5) -> Tuple[str, ...]:
        if not prefix:
            return tuple()
        lowered = prefix.lower()
        matches = [t for t in self._terms if t.lower().startswith(lowered)]
        return tuple(matches[:limit])

    def add(self, term: str) -> None:
        if term not in self._terms:
            self._terms.append(term)
            self._terms.sort()

    def expand_synonyms(self, suggestion: str) -> Tuple[str, ...]:
        if self._lexicon is None:
            return (suggestion,)
        return self._lexicon.expand(suggestion)
