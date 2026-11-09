"""Low-token repository context planning from Jeeves' canonical source atlas.

This module builds compact, deterministic source bookmarks for an AI task.
It does not read arbitrary files, evaluate code, invoke editors, run commands
or infer execution rights from file discovery. Hosts separately authorize
source materialization through their normal filesystem controls.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any

from skeleton.jeeves.repository_file_atlas import JeevesRepositoryFileAtlas

_TOKEN = re.compile(r"[a-z0-9_]{2,64}")
_CODE = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java", ".cs", ".cpp", ".h"})
MAX_QUERY_CHARS = 8192
MAX_TERMS = 16
MAX_REFERENCES = 64
MAX_CANDIDATES = 1600


class FileContextError(ValueError):
    """Objective or context budget violates the bounded plan contract."""


@dataclass(frozen=True, slots=True)
class SourceBookmark:
    path: str
    feature: str
    owner_root: str
    score: int
    bytes: int
    modified_ns: int
    source_digest: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path, "feature": self.feature,
            "owner_root": self.owner_root, "score": self.score,
            "bytes": self.bytes, "modified_ns": self.modified_ns,
            "source_digest": self.source_digest,
            "content_loaded": False,
            "execution_authority": "none",
        }


@dataclass(frozen=True, slots=True)
class SourceContextPlan:
    objective_digest: str
    atlas_index_digest: str
    bookmarks: tuple[SourceBookmark, ...]
    token_budget: int
    estimated_tokens: int
    candidate_count: int
    total_matched: int

    @property
    def digest(self) -> str:
        payload = self.to_dict()
        payload.pop("digest", None)
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "jeeves.source_context_plan.v1",
            "objective_digest": self.objective_digest,
            "atlas_index_digest": self.atlas_index_digest,
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
            "candidate_count": self.candidate_count,
            "total_matched": self.total_matched,
            "bookmarks": [ref.to_dict() for ref in self.bookmarks],
            "context_source": "metadata_only",
            "requires_host_file_grant": True,
        }


class JeevesFileContextPlanner:
    """Rank bounded context bookmarks, not the entire repository text."""

    def __init__(self, atlas: JeevesRepositoryFileAtlas) -> None:
        if not isinstance(atlas, JeevesRepositoryFileAtlas):
            raise FileContextError("host-managed source atlas required")
        self.atlas = atlas

    @staticmethod
    def _tokens(objective: str) -> tuple[str, ...]:
        if not isinstance(objective, str) or not objective.strip() or len(objective) > MAX_QUERY_CHARS:
            raise FileContextError("objective must be bounded non-empty text")
        found = tuple(dict.fromkeys(_TOKEN.findall(objective.casefold())))
        if not found:
            raise FileContextError("objective has no searchable terms")
        return found[:MAX_TERMS]

    @staticmethod
    def _score(row: dict[str, Any], terms: tuple[str, ...], *, include_tests: bool) -> int:
        path = row["path"].casefold()
        name = path.rsplit("/", 1)[-1]
        feature = row["feature"].casefold()
        parts = set(re.split(r"[/_.\-]+", path))
        score = 0
        for term in terms:
            if term in parts:
                score += 15
            if term in name:
                score += 9
            elif term in path:
                score += 4
            if term in feature:
                score += 8
        if row["suffix"] in _CODE:
            score += 3
        if path.endswith(("/__init__.py", "/index.ts", "/index.tsx", "/main.py")):
            score += 1
        is_test = (
            name.startswith("test_") or "/tests/" in path
            or "/testing/" in path or name.endswith(".test.ts")
        )
        if is_test:
            score += 2 if include_tests else -30
        if row["owner_root"] == "unresolved":
            score -= 10
        return score

    @staticmethod
    def _cost(row: dict[str, Any]) -> int:
        # Cost estimates only metadata, never falsely promise source content.
        return max(10, (len(row["path"]) + len(row["feature"]) +
                        len(row["owner_root"]) + 160) // 4)

    def compile(
        self, objective: str, *,
        max_references: int = 32,
        token_budget: int = 2048,
        include_tests: bool = False,
        preferred_feature: str | None = None,
    ) -> SourceContextPlan:
        if type(max_references) is not int or not 1 <= max_references <= MAX_REFERENCES:
            raise FileContextError("max_references outside 1..64")
        if type(token_budget) is not int or not 128 <= token_budget <= 32_768:
            raise FileContextError("token_budget outside 128..32768")
        if type(include_tests) is not bool:
            raise FileContextError("include_tests must be boolean")
        if preferred_feature is not None and (
            not isinstance(preferred_feature, str)
            or not 1 <= len(preferred_feature) <= 192
        ):
            raise FileContextError("preferred_feature must be canonical feature name")
        terms = self._tokens(objective)
        seen: dict[str, dict[str, Any]] = {}
        total_matched = 0
        atlas_digest = None
        for term in terms:
            selection = self.atlas.search(query=term, limit=100, offset=0)
            atlas_digest = selection["index_sha256"]
            total_matched += selection["total_matched"]
            for row in selection["files"]:
                if preferred_feature is not None and row["feature"] != preferred_feature:
                    continue
                seen[row["path"]] = row
                if len(seen) > MAX_CANDIDATES:
                    raise FileContextError("source context candidate budget exceeded")
        if atlas_digest is None:
            raise FileContextError("source atlas is not available")
        scored = []
        for row in seen.values():
            score = self._score(row, terms, include_tests=include_tests)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["path"]))
        chosen: list[SourceBookmark] = []
        spent = 0
        for score, row in scored:
            if len(chosen) >= max_references:
                break
            cost = self._cost(row)
            if spent + cost > token_budget:
                continue
            chosen.append(SourceBookmark(
                path=row["path"], feature=row["feature"],
                owner_root=row["owner_root"], score=score,
                bytes=row["bytes"], modified_ns=row["modified_ns"],
                source_digest=row["content_sha256"],
            ))
            spent += cost
        objective_digest = sha256(objective.encode("utf-8")).hexdigest()
        return SourceContextPlan(
            objective_digest=objective_digest,
            atlas_index_digest=atlas_digest,
            bookmarks=tuple(chosen),
            token_budget=token_budget,
            estimated_tokens=spent,
            candidate_count=len(seen),
            total_matched=total_matched,
        )


__all__ = [
    "FileContextError", "SourceBookmark", "SourceContextPlan",
    "JeevesFileContextPlanner",
]
