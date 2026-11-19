"""Canonical retrieval reranker contract with deterministic stage receipts.

Legacy rerankers use different call signatures. This module gives the runtime
one typed composition point while adapters preserve those implementations.
Stages may reorder, rescore, or truncate candidates but may never inject an
unknown fragment or duplicate a fragment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Protocol, Sequence, Tuple, runtime_checkable

from skeleton.retrieval.fusion import ScoredResult


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("top_k must be an integer")
    if value < 0:
        raise ValueError("top_k must be non-negative")
    return value


def _digest(items: Sequence[ScoredResult]) -> str:
    payload = [
        {
            "fragment_id": item.fragment_id,
            "score": float(item.score),
            "plane": item.plane,
            "provenance": item.provenance,
        }
        for item in items
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=16).hexdigest()


@dataclass(frozen=True, slots=True)
class RerankReceipt:
    stage: str
    before_digest: str
    after_digest: str
    before_count: int
    after_count: int
    changed: bool
    truncated: bool


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    results: Tuple[ScoredResult, ...]
    receipts: Tuple[RerankReceipt, ...]


@runtime_checkable
class RerankStage(Protocol):
    """One canonical reranking stage."""

    name: str

    def rerank(
        self,
        query: str,
        items: Sequence[ScoredResult],
        *,
        top_k: int,
    ) -> Sequence[ScoredResult]:
        ...


class RuleRerankStage:
    name = "rule"

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def rerank(
        self,
        query: str,
        items: Sequence[ScoredResult],
        *,
        top_k: int,
    ) -> Sequence[ScoredResult]:
        return self.delegate.rerank(items, top_k=top_k)


class FeatureRerankStage:
    name = "feature"

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def rerank(
        self,
        query: str,
        items: Sequence[ScoredResult],
        *,
        top_k: int,
    ) -> Sequence[ScoredResult]:
        return self.delegate.rerank(query, list(items), top_k=top_k)


class DiversityRerankStage:
    name = "diversity"

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def rerank(
        self,
        query: str,
        items: Sequence[ScoredResult],
        *,
        top_k: int,
    ) -> Sequence[ScoredResult]:
        return self.delegate.rank(list(items), top_k=top_k)


class CanonicalReranker:
    """Compose typed reranking stages and emit deterministic receipts."""

    def __init__(self, stages: Iterable[RerankStage] = ()) -> None:
        resolved = tuple(stages)
        names = []
        for stage in resolved:
            if not isinstance(stage, RerankStage):
                raise TypeError("every rerank stage must satisfy RerankStage")
            if not isinstance(stage.name, str) or not stage.name:
                raise ValueError("rerank stage name must be a non-empty string")
            names.append(stage.name)
        if len(names) != len(set(names)):
            raise ValueError("rerank stage names must be unique")
        self._stages = resolved

    @property
    def stages(self) -> Tuple[str, ...]:
        return tuple(stage.name for stage in self._stages)

    @staticmethod
    def _validate_stage_output(
        before: Sequence[ScoredResult],
        after: Sequence[ScoredResult],
        *,
        stage: str,
        top_k: int,
    ) -> Tuple[ScoredResult, ...]:
        if len(after) > top_k:
            raise ValueError(f"rerank stage {stage!r} exceeded top_k")
        before_ids = {item.fragment_id for item in before}
        seen = set()
        output = []
        for item in after:
            if not isinstance(item, ScoredResult):
                raise TypeError(
                    f"rerank stage {stage!r} returned non-ScoredResult"
                )
            if item.fragment_id not in before_ids:
                raise ValueError(
                    f"rerank stage {stage!r} injected unknown fragment "
                    f"{item.fragment_id!r}"
                )
            if item.fragment_id in seen:
                raise ValueError(
                    f"rerank stage {stage!r} duplicated fragment "
                    f"{item.fragment_id!r}"
                )
            seen.add(item.fragment_id)
            output.append(item)
        return tuple(output)

    def run(
        self,
        query: str,
        items: Sequence[ScoredResult],
        *,
        top_k: int,
    ) -> RerankOutcome:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        limit = _limit(top_k)
        current = tuple(items)
        if any(not isinstance(item, ScoredResult) for item in current):
            raise TypeError("canonical reranker accepts ScoredResult only")
        if len({item.fragment_id for item in current}) != len(current):
            raise ValueError("input contains duplicate fragment ids")

        receipts = []
        for stage in self._stages:
            before = current
            before_digest = _digest(before)
            raw_after = stage.rerank(
                query,
                before,
                top_k=limit,
            )
            current = self._validate_stage_output(
                before,
                tuple(raw_after),
                stage=stage.name,
                top_k=limit,
            )
            after_digest = _digest(current)
            receipts.append(
                RerankReceipt(
                    stage=stage.name,
                    before_digest=before_digest,
                    after_digest=after_digest,
                    before_count=len(before),
                    after_count=len(current),
                    changed=before_digest != after_digest,
                    truncated=len(current) < len(before),
                )
            )

        if not self._stages and len(current) > limit:
            current = current[:limit]
        return RerankOutcome(
            results=current,
            receipts=tuple(receipts),
        )
