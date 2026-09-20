"""Documentation coverage map for machine-owned repository subsystems."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class DocumentationLink:
    zone: str
    path: str
    score: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "path": self.path,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class DocumentationCoverage:
    zone: str
    links: tuple[DocumentationLink, ...]
    covered: bool
    confidence: int

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "links": [item.as_dict() for item in self.links],
            "covered": self.covered,
            "confidence": self.confidence,
        }


def _tokens(value: str) -> set[str]:
    return {
        item
        for item in re.split(r"[^a-z0-9]+", value.casefold())
        if len(item) >= 2
    }


def documentation_coverage(
    model: RepositoryModel,
    *,
    minimum_score: int = 25,
) -> tuple[DocumentationCoverage, ...]:
    docs = [item for item in model.files if item.kind == "docs"]
    result: list[DocumentationCoverage] = []
    for subsystem in model.subsystems:
        links: list[DocumentationLink] = []
        zone_tokens = _tokens(subsystem.name)
        for document in docs:
            score = 0
            reasons: list[str] = []
            lower = document.path.casefold()
            doc_tokens = _tokens(document.path)
            if document.zone == subsystem.name:
                score += 50
                reasons.append("documentation is inside subsystem zone")
            if subsystem.name.casefold() in lower:
                score += 35
                reasons.append("subsystem name appears in documentation path")
            overlap = zone_tokens.intersection(doc_tokens)
            if overlap:
                score += min(25, len(overlap) * 10)
                reasons.append("zone/document path tokens overlap")
            name = PurePosixPath(document.path).name.casefold()
            if name.startswith("readme"):
                score += 10
                reasons.append("README surface")
            if score >= minimum_score:
                links.append(DocumentationLink(
                    zone=subsystem.name,
                    path=document.path,
                    score=min(score, 100),
                    reasons=tuple(reasons),
                ))
        links.sort(key=lambda item: (-item.score, item.path))
        confidence = links[0].score if links else 0
        result.append(DocumentationCoverage(
            zone=subsystem.name,
            links=tuple(links[:12]),
            covered=confidence >= minimum_score,
            confidence=confidence,
        ))
    return tuple(sorted(result, key=lambda item: item.zone))


def undocumented_code_zones(model: RepositoryModel) -> tuple[str, ...]:
    coverage = {item.zone: item for item in documentation_coverage(model)}
    return tuple(sorted(
        subsystem.name
        for subsystem in model.subsystems
        if subsystem.code_files > 0
        and not coverage[subsystem.name].covered
    ))
