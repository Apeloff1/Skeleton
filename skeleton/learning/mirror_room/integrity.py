"""Deterministic split-contamination controls for Mirror Room."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from .contracts import (
    MirrorRoomError,
    MirrorScenario,
    ScenarioSplit,
    _canonical_json,
    _digest,
    _finite,
    _positive_int,
)

_TOKEN = re.compile(r"[A-Za-z0-9_./:-]+")


@dataclass(frozen=True, slots=True)
class SplitIntegrityPolicy:
    exact_payload_reuse_forbidden: bool = True
    near_duplicate_threshold: float = 0.995
    minimum_tokens_for_similarity: int = 6
    shingle_size: int = 3
    max_reported_pairs: int = 64

    def __post_init__(self) -> None:
        if not isinstance(self.exact_payload_reuse_forbidden, bool):
            raise MirrorRoomError("exact_payload_reuse_forbidden must be boolean")
        threshold = _finite(
            "near_duplicate_threshold",
            self.near_duplicate_threshold,
            minimum=0.0,
        )
        if threshold <= 0.0 or threshold > 1.0:
            raise MirrorRoomError("near_duplicate_threshold must be within (0, 1]")
        object.__setattr__(self, "near_duplicate_threshold", threshold)
        object.__setattr__(
            self,
            "minimum_tokens_for_similarity",
            _positive_int("minimum_tokens_for_similarity", self.minimum_tokens_for_similarity),
        )
        object.__setattr__(self, "shingle_size", _positive_int("shingle_size", self.shingle_size))
        object.__setattr__(
            self,
            "max_reported_pairs",
            _positive_int("max_reported_pairs", self.max_reported_pairs),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "exact_payload_reuse_forbidden": self.exact_payload_reuse_forbidden,
                "near_duplicate_threshold": self.near_duplicate_threshold,
                "minimum_tokens_for_similarity": self.minimum_tokens_for_similarity,
                "shingle_size": self.shingle_size,
                "max_reported_pairs": self.max_reported_pairs,
            }
        )


@dataclass(frozen=True, slots=True)
class CrossSplitSimilarity:
    left_scenario_id: str
    left_split: ScenarioSplit
    right_scenario_id: str
    right_split: ScenarioSplit
    exact_payload_match: bool
    similarity: float

    @property
    def digest(self) -> str:
        return _digest(
            {
                "left_scenario_id": self.left_scenario_id,
                "left_split": self.left_split.value,
                "right_scenario_id": self.right_scenario_id,
                "right_split": self.right_split.value,
                "exact_payload_match": self.exact_payload_match,
                "similarity": self.similarity,
            }
        )


@dataclass(frozen=True, slots=True)
class SplitIntegrityReport:
    policy_digest: str
    scenario_count: int
    split_counts: tuple[tuple[str, int], ...]
    suspicious_pairs: tuple[CrossSplitSimilarity, ...]
    maximum_cross_split_similarity: float
    passed: bool

    @property
    def digest(self) -> str:
        return _digest(
            {
                "policy_digest": self.policy_digest,
                "scenario_count": self.scenario_count,
                "split_counts": list(self.split_counts),
                "suspicious_pairs": [item.digest for item in self.suspicious_pairs],
                "maximum_cross_split_similarity": self.maximum_cross_split_similarity,
                "passed": self.passed,
            }
        )


def _tokens(scenario: MirrorScenario) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(_canonical_json(scenario.payload).lower()))


def _shingles(tokens: Sequence[str], size: int) -> frozenset[tuple[str, ...]]:
    if not tokens:
        return frozenset()
    if len(tokens) < size:
        return frozenset((token,) for token in tokens)
    return frozenset(
        tuple(tokens[index : index + size])
        for index in range(len(tokens) - size + 1)
    )


def _jaccard(left: frozenset[tuple[str, ...]], right: frozenset[tuple[str, ...]]) -> float:
    union = left | right
    if not union:
        return 1.0 if not left and not right else 0.0
    return len(left & right) / len(union)


def inspect_split_integrity(
    scenarios: Iterable[MirrorScenario],
    *,
    policy: SplitIntegrityPolicy | None = None,
) -> SplitIntegrityReport:
    actual = policy or SplitIntegrityPolicy()
    items = tuple(scenarios)
    if not items:
        raise MirrorRoomError("split integrity inspection requires scenarios")
    if any(not isinstance(item, MirrorScenario) for item in items):
        raise MirrorRoomError("split integrity inspection requires MirrorScenario")
    ids = [item.scenario_id for item in items]
    if len(ids) != len(set(ids)):
        raise MirrorRoomError("split integrity requires globally unique scenario IDs")

    prepared = {
        item.scenario_id: (
            item,
            _tokens(item),
        )
        for item in items
    }
    suspicious: list[CrossSplitSimilarity] = []
    maximum = 0.0
    ordered = sorted(items, key=lambda item: (item.split.value, item.scenario_id))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if left.split is right.split:
                continue
            left_item, left_tokens = prepared[left.scenario_id]
            right_item, right_tokens = prepared[right.scenario_id]
            exact = left_item.payload_digest == right_item.payload_digest
            if (
                len(left_tokens) >= actual.minimum_tokens_for_similarity
                and len(right_tokens) >= actual.minimum_tokens_for_similarity
            ):
                similarity = _jaccard(
                    _shingles(left_tokens, actual.shingle_size),
                    _shingles(right_tokens, actual.shingle_size),
                )
            else:
                similarity = 1.0 if exact else 0.0
            maximum = max(maximum, similarity)
            reject = (
                (actual.exact_payload_reuse_forbidden and exact)
                or (not exact and similarity >= actual.near_duplicate_threshold)
            )
            if reject:
                suspicious.append(
                    CrossSplitSimilarity(
                        left_scenario_id=left.scenario_id,
                        left_split=left.split,
                        right_scenario_id=right.scenario_id,
                        right_split=right.split,
                        exact_payload_match=exact,
                        similarity=similarity,
                    )
                )

    suspicious = sorted(
        suspicious,
        key=lambda item: (
            -int(item.exact_payload_match),
            -item.similarity,
            item.left_scenario_id,
            item.right_scenario_id,
        ),
    )[: actual.max_reported_pairs]
    counts = tuple(
        (split.value, sum(1 for item in items if item.split is split))
        for split in ScenarioSplit
    )
    return SplitIntegrityReport(
        policy_digest=actual.digest,
        scenario_count=len(items),
        split_counts=counts,
        suspicious_pairs=tuple(suspicious),
        maximum_cross_split_similarity=maximum,
        passed=not suspicious,
    )


def validate_split_integrity(
    scenarios: Iterable[MirrorScenario],
    *,
    policy: SplitIntegrityPolicy | None = None,
) -> SplitIntegrityReport:
    report = inspect_split_integrity(scenarios, policy=policy)
    if report.passed:
        return report
    first = report.suspicious_pairs[0]
    relation = "exact duplicate" if first.exact_payload_match else "near duplicate"
    raise MirrorRoomError(
        "Mirror Room split contamination detected: "
        f"{relation} {first.left_scenario_id}({first.left_split.value}) "
        f"<-> {first.right_scenario_id}({first.right_split.value}) "
        f"similarity={first.similarity:.6f}"
    )


__all__ = [
    "CrossSplitSimilarity",
    "SplitIntegrityPolicy",
    "SplitIntegrityReport",
    "inspect_split_integrity",
    "validate_split_integrity",
]
