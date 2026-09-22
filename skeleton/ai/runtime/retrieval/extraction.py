"""
Skeleton Retrieval — Triple extraction from free text

Provides:
- TripleExtractor: Rule-based subject-predicate-object extraction

Runs during document ingestion so the KAG plane self-populates
from RAG documents. Deliberately simple pattern rules — no NLP
dependency — but the interface accepts a custom extractor callable
for anything smarter (LLM-based extraction, spaCy, etc.).
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple


# Patterns ordered by confidence: first match wins per sentence.
_PATTERNS: List[Tuple[re.Pattern, Callable[[re.Match], Optional[Tuple[str, str, str]]]]] = [
    # "X is a Y" / "X is an Y" / "X are Y"
    (re.compile(r"\b([A-Z][\w -]{1,40}?)\s+(?:is|are|was|were)\s+(?:a|an|the)?\s*([\w -]{2,40})", re.IGNORECASE),
     lambda m: (m.group(1).strip(), "is_a", m.group(2).strip())),
    # "X has Y" / "X have Y"
    (re.compile(r"\b([A-Z][\w -]{1,40}?)\s+(?:has|have|had)\s+(?:a|an|the)?\s*([\w -]{2,40})", re.IGNORECASE),
     lambda m: (m.group(1).strip(), "has", m.group(2).strip())),
    # "X produces Y" / "X creates Y" / "X builds Y" / "X generates Y"
    (re.compile(r"\b([A-Z][\w -]{1,40}?)\s+(produces?|creates?|builds?|generates?|makes?)\s+(?:a|an|the)?\s*([\w -]{2,40})", re.IGNORECASE),
     lambda m: (m.group(1).strip(), m.group(2).rstrip("s").lower() + "s", m.group(3).strip())),
    # "X uses Y" / "X requires Y" / "X needs Y"
    (re.compile(r"\b([A-Z][\w -]{1,40}?)\s+(uses?|requires?|needs?)\s+(?:a|an|the)?\s*([\w -]{2,40})", re.IGNORECASE),
     lambda m: (m.group(1).strip(), m.group(2).rstrip("s").lower() + "s", m.group(3).strip())),
    # "X can Y" — capability
    (re.compile(r"\b([A-Z][\w -]{1,40}?)\s+can\s+([a-z][\w-]{1,25})", re.IGNORECASE),
     lambda m: (m.group(1).strip(), "can", m.group(2).strip())),
]

_STOP = {"the", "a", "an", "this", "that", "it", "they", "we", "you", "he", "she"}


class TripleExtractor:
    """Extract knowledge triples from sentences via pattern rules."""

    def __init__(self, custom: Optional[Callable[[str], List[Tuple[str, str, str]]]] = None):
        self._custom = custom
        self._stats = {"sentences": 0, "extracted": 0}

    def extract(self, text: str) -> List[Tuple[str, str, str]]:
        """Extract (subject, predicate, object) triples from text."""
        if self._custom is not None:
            return self._custom(text)

        triples: List[Tuple[str, str, str]] = []
        sentences = re.split(r"[.!?\n]+", text)
        self._stats["sentences"] += len(sentences)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            for pattern, builder in _PATTERNS:
                m = pattern.search(sentence)
                if m:
                    triple = builder(m)
                    if triple and self._valid(triple):
                        triples.append(triple)
                    break

        self._stats["extracted"] += len(triples)
        return triples

    @staticmethod
    def _valid(triple: Tuple[str, str, str]) -> bool:
        subject, _, obj = triple
        if subject.lower().split()[0] in _STOP:
            return False
        if len(subject) < 2 or len(obj) < 2:
            return False
        if subject.lower() == obj.lower():
            return False
        return True

    def stats(self) -> dict:
        return dict(self._stats)
