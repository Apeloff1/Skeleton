"""Pairwise contradiction matrix for evidence-backed propositions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class PropositionEvidence:
    proposition_id: str
    evidence_digest: str
    supports: tuple[str, ...]
    contradicts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.proposition_id:
            raise ReverseEngineeringError("proposition evidence requires identity")
        if not is_sha256_digest(self.evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be a sha256 hex digest")
        if len(self.supports) != len(set(self.supports)):
            raise ReverseEngineeringError("supports entries must be unique")
        if len(self.contradicts) != len(set(self.contradicts)):
            raise ReverseEngineeringError("contradicts entries must be unique")
        if set(self.supports) & set(self.contradicts):
            raise ReverseEngineeringError("an evidence item cannot both support and contradict a proposition")


@dataclass(frozen=True)
class ContradictionPair:
    left_proposition: str
    right_proposition: str
    directed_contradiction_count: int
    mutual: bool


@dataclass(frozen=True)
class ContradictionMatrixReport:
    proposition_count: int
    contradiction_pair_count: int
    mutual_pair_count: int
    pairs: tuple[ContradictionPair, ...]
    isolated_proposition_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposition_count": self.proposition_count,
            "contradiction_pair_count": self.contradiction_pair_count,
            "mutual_pair_count": self.mutual_pair_count,
            "pairs": [
                {
                    "left_proposition": pair.left_proposition,
                    "right_proposition": pair.right_proposition,
                    "directed_contradiction_count": pair.directed_contradiction_count,
                    "mutual": pair.mutual,
                }
                for pair in self.pairs
            ],
            "isolated_proposition_count": self.isolated_proposition_count,
            "digest": self.digest,
        }


def build_contradiction_matrix(
    evidence: Sequence[PropositionEvidence],
) -> ContradictionMatrixReport:
    if not evidence:
        raise ReverseEngineeringError("contradiction matrix requires evidence")
    propositions = sorted(
        {item.proposition_id for item in evidence}
        | {name for item in evidence for name in item.supports}
        | {name for item in evidence for name in item.contradicts}
    )
    directed: dict[tuple[str, str], int] = {}
    touched: set[str] = set()
    for item in evidence:
        for target in item.contradicts:
            if item.proposition_id == target:
                raise ReverseEngineeringError("proposition cannot contradict itself")
            directed[(item.proposition_id, target)] = directed.get((item.proposition_id, target), 0) + 1
            touched.add(item.proposition_id)
            touched.add(target)

    pairs: list[ContradictionPair] = []
    for left_index, left in enumerate(propositions):
        for right in propositions[left_index + 1:]:
            lr = directed.get((left, right), 0)
            rl = directed.get((right, left), 0)
            if lr or rl:
                pairs.append(
                    ContradictionPair(
                        left_proposition=left,
                        right_proposition=right,
                        directed_contradiction_count=lr + rl,
                        mutual=lr > 0 and rl > 0,
                    )
                )
    payload = {
        "evidence": [
            {
                "proposition_id": item.proposition_id,
                "evidence_digest": item.evidence_digest,
                "supports": list(item.supports),
                "contradicts": list(item.contradicts),
            }
            for item in sorted(evidence, key=lambda value: (value.proposition_id, value.evidence_digest))
        ]
    }
    return ContradictionMatrixReport(
        proposition_count=len(propositions),
        contradiction_pair_count=len(pairs),
        mutual_pair_count=sum(pair.mutual for pair in pairs),
        pairs=tuple(pairs),
        isolated_proposition_count=len(set(propositions) - touched),
        digest=stable_digest(payload),
    )
