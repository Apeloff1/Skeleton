"""Reference-backed game knowledge retrieval for generation pipelines.

The acquired gaming corpus intentionally stores metadata and provenance rather
than copied game prose.  This module turns that reference index into a small,
deterministic retrieval surface that pipelines can use for genre-aware design
grounding without silently importing external text.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(value.lower().replace("_", " ")))


@dataclass(frozen=True)
class GameReference:
    """One provenance-preserving game reference from the acquired index."""

    appid: int
    title: str
    era: str
    dialect: str
    source: str
    citation: str
    license: str
    url: str
    wiki: str = ""
    wiki_citation: str = ""
    wiki_license: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GameReference":
        if not isinstance(raw, Mapping):
            raise ValueError("game reference entries must be objects")
        if raw.get("stored_prose", 0) != 0:
            raise ValueError("game knowledge references must remain metadata-only")

        required = ("title", "era", "dialect", "source", "citation", "license", "url")
        invalid = [
            key
            for key in required
            if not isinstance(raw.get(key), str) or not str(raw[key]).strip()
        ]
        if invalid:
            raise ValueError(f"game reference missing required text fields: {', '.join(invalid)}")

        appid = raw.get("appid")
        if isinstance(appid, bool) or not isinstance(appid, int) or appid <= 0:
            raise ValueError("game reference appid must be a positive integer")

        optional_text = ("wiki", "wiki_citation", "wiki_license")
        invalid_optional = [
            key
            for key in optional_text
            if key in raw and not isinstance(raw[key], str)
        ]
        if invalid_optional:
            raise ValueError(f"game reference optional fields must be text: {', '.join(invalid_optional)}")

        return cls(
            appid=appid,
            title=raw["title"].strip(),
            era=raw["era"].strip(),
            dialect=raw["dialect"].strip(),
            source=raw["source"].strip(),
            citation=raw["citation"].strip(),
            license=raw["license"].strip(),
            url=raw["url"].strip(),
            wiki=raw.get("wiki", "").strip(),
            wiki_citation=raw.get("wiki_citation", "").strip(),
            wiki_license=raw.get("wiki_license", "").strip(),
        )

    def to_context(self) -> dict[str, Any]:
        """Return compact grounding metadata safe to place in generation context."""
        return {
            "appid": self.appid,
            "title": self.title,
            "era": self.era,
            "source": self.source,
            "citation": self.citation,
            "license": self.license,
            "url": self.url,
            "wiki": self.wiki,
            "wiki_citation": self.wiki_citation,
            "wiki_license": self.wiki_license,
        }


@dataclass(frozen=True)
class ScoredGameReference:
    reference: GameReference
    score: int
    matched_terms: tuple[str, ...]

    def to_context(self) -> dict[str, Any]:
        context = self.reference.to_context()
        context["score"] = self.score
        context["matched_terms"] = list(self.matched_terms)
        return context


class GameKnowledgeBase:
    """Load and retrieve deterministic, citation-preserving game references."""

    def __init__(self, references: Sequence[GameReference], *, source: str = "packaged") -> None:
        if not references:
            raise ValueError("game knowledge requires at least one reference")
        appids = [reference.appid for reference in references]
        if len(appids) != len(set(appids)):
            raise ValueError("game knowledge contains duplicate appids")
        self._references = tuple(references)
        self._source = source

    @classmethod
    def packaged(cls) -> "GameKnowledgeBase":
        return cls.from_path(Path(__file__).with_name("references.json"))

    @classmethod
    def from_path(cls, path: str | Path) -> "GameKnowledgeBase":
        source_path = Path(path)
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("game knowledge file must contain an object")
        if raw.get("kind") != "reference-index":
            raise ValueError("game knowledge file must be a reference-index")
        items = raw.get("games")
        if not isinstance(items, list) or not items:
            raise ValueError("game knowledge reference-index has no games")
        if not all(isinstance(item, Mapping) for item in items):
            raise ValueError("game knowledge reference entries must be objects")

        declared_count = raw.get("n")
        if declared_count is not None:
            if isinstance(declared_count, bool) or not isinstance(declared_count, int):
                raise ValueError("game knowledge reference count must be an integer")
            if declared_count != len(items):
                raise ValueError("game knowledge reference count does not match index metadata")

        references = [GameReference.from_mapping(item) for item in items]
        return cls(references, source=str(source_path))

    @property
    def references(self) -> tuple[GameReference, ...]:
        return self._references

    def eras(self) -> dict[str, int]:
        return dict(sorted(Counter(reference.era for reference in self._references).items()))

    def search(self, query: str = "", *, era: str | None = None, limit: int = 4) -> list[ScoredGameReference]:
        """Rank references by explicit title/dialect overlap plus an optional era boost."""
        if limit < 1:
            raise ValueError("limit must be positive")
        normalized_era = (era or "").strip().lower()
        query_terms = set(_tokens(query))
        scored: list[ScoredGameReference] = []

        for reference in self._references:
            title_terms = set(_tokens(reference.title))
            dialect_terms = set(_tokens(reference.dialect))
            era_terms = set(_tokens(reference.era))
            title_hits = query_terms & title_terms
            dialect_hits = query_terms & dialect_terms
            era_hits = query_terms & era_terms

            score = len(title_hits) * 8 + len(dialect_hits) * 3 + len(era_hits) * 2
            if normalized_era and reference.era.lower() == normalized_era:
                score += 12
            elif normalized_era:
                requested = set(_tokens(normalized_era))
                score += len(requested & era_terms) * 2

            if score <= 0:
                continue
            matched = tuple(sorted(title_hits | dialect_hits | era_hits))
            scored.append(ScoredGameReference(reference=reference, score=score, matched_terms=matched))

        scored.sort(key=lambda item: (-item.score, item.reference.title.lower(), item.reference.appid))
        return scored[:limit]

    def context(self, query: str = "", *, era: str | None = None, limit: int = 4) -> dict[str, Any]:
        """Build bounded knowledge context for downstream game/code generation."""
        matches = self.search(query, era=era, limit=limit)
        return {
            "kind": "game-reference-context",
            "query": query.strip(),
            "era": era,
            "reference_count": len(matches),
            "references": [match.to_context() for match in matches],
            "policy": "reference metadata only; derive original mechanics, do not copy source prose",
        }

    def stats(self) -> dict[str, Any]:
        return {
            "references": len(self._references),
            "eras": self.eras(),
            "source": self._source,
        }


def build_game_knowledge_context(
    query: str,
    *,
    era: str | None = None,
    limit: int = 4,
    references: Iterable[GameReference] | None = None,
) -> dict[str, Any]:
    """Convenience entry point for generation code that needs bounded context."""
    knowledge = GameKnowledgeBase(tuple(references)) if references is not None else GameKnowledgeBase.packaged()
    return knowledge.context(query, era=era, limit=limit)


__all__ = [
    "GameKnowledgeBase",
    "GameReference",
    "ScoredGameReference",
    "build_game_knowledge_context",
]
