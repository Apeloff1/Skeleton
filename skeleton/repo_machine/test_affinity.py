"""Heuristic source-to-test affinity mapping from machine repository metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from .model import FileRecord, RepositoryModel

_STOP = {"test", "tests", "spec", "specs", "src", "source", "lib", "app", "main", "index"}


def _stem_tokens(path: str) -> set[str]:
    stem = PurePosixPath(path).stem.casefold()
    stem = re.sub(r"^(test_|spec_)", "", stem)
    stem = re.sub(r"(_test|_spec)$", "", stem)
    pieces = re.split(r"[^a-z0-9]+", stem)
    return {item for item in pieces if len(item) >= 2 and item not in _STOP}


@dataclass(frozen=True, slots=True)
class TestAffinity:
    source_path: str
    test_path: str
    score: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "test_path": self.test_path,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def score_test_affinity(source: FileRecord, test: FileRecord) -> TestAffinity:
    if source.kind != "source":
        raise ValueError("source record must be kind=source")
    if test.kind != "test":
        raise ValueError("test record must be kind=test")

    score = 0
    reasons: list[str] = []
    source_tokens = _stem_tokens(source.path)
    test_tokens = _stem_tokens(test.path)
    overlap = source_tokens.intersection(test_tokens)
    if overlap:
        score += 20 + min(30, len(overlap) * 10)
        reasons.append("filename token overlap")

    source_stem = PurePosixPath(source.path).stem.casefold()
    test_stem = PurePosixPath(test.path).stem.casefold()
    if source_stem in test_stem:
        score += 35
        reasons.append("source basename appears in test basename")

    if source.zone == test.zone:
        score += 20
        reasons.append("same machine zone")
    elif test.zone == "tests":
        score += 8
        reasons.append("shared tests zone")

    source_parent = PurePosixPath(source.path).parent.name.casefold()
    test_parent = PurePosixPath(test.path).parent.name.casefold()
    if source_parent and source_parent == test_parent:
        score += 10
        reasons.append("matching parent directory")

    if source.language == test.language:
        score += 5
        reasons.append("same language")

    imported_tokens = {
        part.casefold()
        for imported in test.imports
        for part in re.split(r"[./:_-]+", imported)
        if len(part) >= 2
    }
    if source_tokens.intersection(imported_tokens):
        score += 20
        reasons.append("test imports source-like module token")

    return TestAffinity(
        source_path=source.path,
        test_path=test.path,
        score=min(score, 100),
        reasons=tuple(reasons),
    )


def build_test_affinity(
    model: RepositoryModel,
    *,
    minimum_score: int = 20,
    max_tests_per_source: int = 12,
) -> dict[str, tuple[TestAffinity, ...]]:
    if not 0 <= minimum_score <= 100:
        raise ValueError("minimum_score must be in [0,100]")
    sources = [item for item in model.files if item.kind == "source"]
    tests = [item for item in model.files if item.kind == "test"]
    result: dict[str, tuple[TestAffinity, ...]] = {}
    for source in sources:
        candidates: list[TestAffinity] = []
        for test in tests:
            affinity = score_test_affinity(source, test)
            if affinity.score >= minimum_score:
                candidates.append(affinity)
        candidates.sort(key=lambda item: (-item.score, item.test_path))
        result[source.path] = tuple(candidates[:max_tests_per_source])
    return result


def uncovered_sources(
    model: RepositoryModel,
    *,
    minimum_score: int = 20,
) -> tuple[str, ...]:
    affinity = build_test_affinity(model, minimum_score=minimum_score)
    return tuple(sorted(
        path
        for path, matches in affinity.items()
        if not matches
    ))
