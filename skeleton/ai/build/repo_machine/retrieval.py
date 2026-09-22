"""Deterministic lexical retrieval over machine-indexed repository metadata.

The index is intentionally small and metadata-only: paths, zones, file kinds,
languages, imports and Python symbol names already extracted by the static
scanner. Repository file contents are not copied into the retrieval index.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .model import FileRecord, RepositoryModel

_TOKEN = re.compile(r"[A-Za-z0-9_./:-]{2,}")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(value: str) -> tuple[str, ...]:
    expanded = _CAMEL.sub(" ", value.replace("\\", "/"))
    raw = _TOKEN.findall(expanded)
    tokens: set[str] = set()
    for token in raw:
        lowered = token.casefold()
        tokens.add(lowered)
        tokens.update(
            part
            for part in re.split(r"[/._:-]+", lowered)
            if len(part) >= 2
        )
    return tuple(sorted(tokens))


@dataclass(frozen=True, slots=True)
class SearchHit:
    path: str
    zone: str
    kind: str
    language: str
    score: int
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "zone": self.zone,
            "kind": self.kind,
            "language": self.language,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "reasons": list(self.reasons),
        }


class RepositoryRetrievalIndex:
    """Inverted lexical index for bounded agent navigation."""

    def __init__(self, model: RepositoryModel) -> None:
        self.model = model
        self._postings: dict[str, set[str]] = {}
        self._records = {item.path: item for item in model.files}
        self._path_tokens: dict[str, set[str]] = {}
        self._build()

    def _add(self, term: str, path: str) -> None:
        self._postings.setdefault(term, set()).add(path)

    def _build(self) -> None:
        for record in self.model.files:
            tokens: set[str] = set()
            tokens.update(_tokens(record.path))
            tokens.update(_tokens(record.zone))
            tokens.update(_tokens(record.kind))
            tokens.update(_tokens(record.language))
            for imported in record.imports:
                tokens.update(_tokens(imported))
            self._path_tokens[record.path] = tokens
            for term in tokens:
                self._add(term, record.path)

    def search(
        self,
        query: str,
        *,
        zones: Iterable[str] = (),
        kinds: Iterable[str] = (),
        languages: Iterable[str] = (),
        limit: int = 40,
    ) -> tuple[SearchHit, ...]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be in [1,500]")
        terms = set(_tokens(query))
        if not terms:
            return ()
        zone_set = {str(item).casefold() for item in zones}
        kind_set = {str(item).casefold() for item in kinds}
        language_set = {str(item).casefold() for item in languages}

        candidates: set[str] = set()
        for term in terms:
            candidates.update(self._postings.get(term, ()))
        if not candidates:
            for indexed_term, paths in self._postings.items():
                if any(term in indexed_term or indexed_term in term for term in terms):
                    candidates.update(paths)

        hits: list[SearchHit] = []
        query_lower = query.casefold()
        for path in candidates:
            record = self._records[path]
            if zone_set and record.zone.casefold() not in zone_set:
                continue
            if kind_set and record.kind.casefold() not in kind_set:
                continue
            if language_set and record.language.casefold() not in language_set:
                continue

            matched = terms.intersection(self._path_tokens[path])
            score = len(matched) * 10
            reasons: list[str] = []
            path_lower = path.casefold()
            if query_lower in path_lower:
                score += 35
                reasons.append("query substring appears in path")
            basename = path.rsplit("/", 1)[-1].casefold()
            if query_lower == basename or query_lower == basename.rsplit(".", 1)[0]:
                score += 50
                reasons.append("query exactly matches file basename")
            if record.zone in terms:
                score += 8
                reasons.append("query matches subsystem zone")
            if record.kind in terms:
                score += 5
                reasons.append("query matches file kind")
            if record.language in terms:
                score += 3
                reasons.append("query matches language")
            if record.kind in {"source", "test", "workflow"}:
                score += 2
            hits.append(SearchHit(
                path=path,
                zone=record.zone,
                kind=record.kind,
                language=record.language,
                score=score,
                matched_terms=tuple(sorted(matched)),
                reasons=tuple(reasons),
            ))

        hits.sort(key=lambda item: (-item.score, item.zone, item.path))
        return tuple(hits[:limit])
