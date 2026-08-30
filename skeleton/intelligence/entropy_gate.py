"""Uncertainty gate — semantic-entropy abstention for generated answers.

Wave-3 SOTA (semantic entropy / abstention line of work): an answer should
be *refused*, not smoothed over, when the model's sample distribution
splits across incompatible meanings. This module implements the in-process
version with no model dependency:

1. **Cluster** N sampled answers by meaning (normalized token-overlap
   clustering — the pure-Python stand-in for embedding entailment).
2. **Semantic entropy** = entropy over the cluster-size distribution.
   One dominant cluster → low entropy → answer. Many rival clusters →
   high entropy → the model is guessing.
3. **Abstention policy** — three bands: ANSWER / HEDGE / ABSTAIN, with
   the hedge band carrying the sample disagreement into the response.

Pure domain, deterministic, CI-safe.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TOKEN = re.compile(r"[a-z0-9]+")


class Decision(str, Enum):
    ANSWER = "answer"
    HEDGE = "hedge"
    ABSTAIN = "abstain"


def _norm_tokens(text: str) -> frozenset:
    return frozenset(_TOKEN.findall((text or "").lower()))


def _similar(a: frozenset, b: frozenset, threshold: float) -> bool:
    if not a or not b:
        return a == b
    inter = len(a & b)
    union = len(a | b)
    return union > 0 and (inter / union) >= threshold


def cluster_answers(samples: Sequence[str], *, threshold: float = 0.5) -> List[List[str]]:
    """Greedy meaning-clustering by token-overlap Jaccard."""
    clusters: List[Tuple[frozenset, List[str]]] = []
    for sample in samples:
        toks = _norm_tokens(sample)
        placed = False
        for rep, members in clusters:
            if _similar(toks, rep, threshold):
                members.append(sample)
                placed = True
                break
        if not placed:
            clusters.append((toks, [sample]))
    return [members for _, members in clusters]


def semantic_entropy(samples: Sequence[str], *, threshold: float = 0.5) -> float:
    """Entropy over meaning-cluster sizes; 0 when every sample agrees."""
    if len(samples) < 2:
        return 0.0
    clusters = cluster_answers(samples, threshold=threshold)
    total = len(samples)
    h = 0.0
    for members in clusters:
        p = len(members) / total
        h -= p * math.log(p)
    return h


@dataclass(frozen=True)
class GateVerdict:
    decision: Decision
    entropy: float
    clusters: int
    dominant_share: float
    representative: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "entropy": round(self.entropy, 4),
            "clusters": self.clusters,
            "dominant_share": round(self.dominant_share, 4),
            "representative": self.representative[:200],
        }


class UncertaintyGate:
    """Semantic-entropy abstention policy over sampled answers."""

    def __init__(self, *, abstain_above: float = 1.0, hedge_above: float = 0.35,
                 cluster_threshold: float = 0.5) -> None:
        if not 0.0 <= hedge_above <= abstain_above:
            raise ValueError("bands must satisfy 0 <= hedge_above <= abstain_above")
        self.abstain_above = abstain_above
        self.hedge_above = hedge_above
        self.cluster_threshold = cluster_threshold
        self.evaluations = 0
        self.abstentions = 0

    def evaluate(self, samples: Sequence[str]) -> GateVerdict:
        self.evaluations += 1
        if not samples:
            self.abstentions += 1
            return GateVerdict(Decision.ABSTAIN, float("inf"), 0, 0.0, "")
        clusters = cluster_answers(samples, threshold=self.cluster_threshold)
        counts = Counter(len(m) for m in clusters)
        dominant = max(counts) / len(samples)
        h = semantic_entropy(samples, threshold=self.cluster_threshold)
        # representative = first member of the largest cluster
        largest = max(clusters, key=len)
        rep = largest[0]
        if h > self.abstain_above:
            decision = Decision.ABSTAIN
            self.abstentions += 1
        elif h > self.hedge_above:
            decision = Decision.HEDGE
        else:
            decision = Decision.ANSWER
        return GateVerdict(decision, h, len(clusters), dominant, rep)

    def stats(self) -> Dict[str, Any]:
        return {
            "evaluations": self.evaluations,
            "abstentions": self.abstentions,
            "abstention_rate": round(
                self.abstentions / self.evaluations, 4) if self.evaluations else 0.0,
        }
