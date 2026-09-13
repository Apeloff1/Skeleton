"""Provenance-aware world and lore primitives.

Narrative systems may enrich these records, but the kernel keeps identity,
source, confidence, and tags explicit so downstream agents can audit facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from skeleton.frontier.contracts import ProvenanceRecord


@dataclass(frozen=True, slots=True)
class LoreEntry:
    key: str
    text: str
    tags: tuple[str, ...] = ()
    confidence: float = 1.0
    provenance: ProvenanceRecord | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.text.strip():
            raise ValueError("key and text must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def matches(self, query: str) -> bool:
        needle = query.strip().lower()
        if not needle:
            return True
        haystack = " ".join((self.key, self.text, *self.tags)).lower()
        return needle in haystack


@dataclass(slots=True)
class LoreIndex:
    entries: dict[str, LoreEntry] = field(default_factory=dict)

    def upsert(self, entry: LoreEntry) -> None:
        self.entries[entry.key] = entry

    def search(self, query: str = "", *, minimum_confidence: float = 0.0) -> list[LoreEntry]:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        return [
            entry
            for entry in self.entries.values()
            if entry.confidence >= minimum_confidence and entry.matches(query)
        ]

    def remove(self, key: str) -> LoreEntry | None:
        return self.entries.pop(key, None)
