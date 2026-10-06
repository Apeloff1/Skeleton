"""Transparent architecture-family scoring from observable/authorized signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ArchitectureSignals:
    indexed_layer_count: int = 0
    recurrent_shape_group_count: int = 0
    attention_mode_counts: tuple[tuple[str, int], ...] = ()
    expert_tensor_count: int = 0
    state_carryover_observed: bool = False
    kv_cache_approximately_linear: bool | None = None

    def __post_init__(self) -> None:
        if self.indexed_layer_count < 0 or self.recurrent_shape_group_count < 0:
            raise ReverseEngineeringError("architecture signal counts must be non-negative")
        if self.expert_tensor_count < 0:
            raise ReverseEngineeringError("expert_tensor_count must be non-negative")
        if any(count < 0 for _, count in self.attention_mode_counts):
            raise ReverseEngineeringError("attention mode counts must be non-negative")
        modes = [mode for mode, _ in self.attention_mode_counts]
        if len(modes) != len(set(modes)):
            raise ReverseEngineeringError("attention mode counts must have unique modes")


@dataclass(frozen=True)
class ArchitectureCandidate:
    family: str
    score: float
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"family": self.family, "score": self.score, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class ArchitectureFamilyReport:
    candidates: tuple[ArchitectureCandidate, ...]
    best_family: str
    confidence_gap: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "best_family": self.best_family,
            "confidence_gap": self.confidence_gap,
            "digest": self.digest,
        }


def _attention_counts(signals: ArchitectureSignals) -> Mapping[str, int]:
    return dict(signals.attention_mode_counts)


def classify_architecture_family(signals: ArchitectureSignals) -> ArchitectureFamilyReport:
    attention = _attention_counts(signals)
    total_attention = sum(attention.values())
    scores: dict[str, float] = {
        "transformer_mha": 0.05,
        "transformer_gqa": 0.05,
        "transformer_mqa": 0.05,
        "mixture_of_experts_transformer": 0.05,
        "state_space_or_recurrent": 0.05,
        "unknown": 0.1,
    }
    evidence: dict[str, list[str]] = {key: [] for key in scores}

    transformer_families = (
        "transformer_mha",
        "transformer_gqa",
        "transformer_mqa",
        "mixture_of_experts_transformer",
    )
    if signals.indexed_layer_count > 0:
        for family in transformer_families:
            scores[family] += 0.15
            evidence[family].append("indexed_layer_structure")

    mode_map = {
        "multi_head_attention": "transformer_mha",
        "grouped_query_attention": "transformer_gqa",
        "multi_query_attention": "transformer_mqa",
    }
    for mode, family in mode_map.items():
        count = attention.get(mode, 0)
        if total_attention and count:
            fraction = count / total_attention
            scores[family] += 0.55 * fraction
            evidence[family].append(f"attention_mode:{mode}:{count}/{total_attention}")

    if signals.kv_cache_approximately_linear is True:
        for family in transformer_families:
            scores[family] += 0.1
            evidence[family].append("linear_kv_cache_scaling")

    if signals.expert_tensor_count > 0:
        scores["mixture_of_experts_transformer"] += 0.65
        evidence["mixture_of_experts_transformer"].append(
            f"expert_tensor_count:{signals.expert_tensor_count}"
        )
        if total_attention:
            scores["mixture_of_experts_transformer"] += 0.1
            evidence["mixture_of_experts_transformer"].append(
                "expert_tensors_plus_attention_structure"
            )

    if signals.state_carryover_observed:
        scores["state_space_or_recurrent"] += 0.45
        evidence["state_space_or_recurrent"].append("state_carryover_observed")
    if signals.recurrent_shape_group_count > 0:
        scores["state_space_or_recurrent"] += min(
            0.25, 0.05 * signals.recurrent_shape_group_count
        )
        evidence["state_space_or_recurrent"].append(
            f"recurrent_shape_groups:{signals.recurrent_shape_group_count}"
        )
    if total_attention == 0 and signals.state_carryover_observed:
        scores["state_space_or_recurrent"] += 0.2
        evidence["state_space_or_recurrent"].append("state_signal_without_attention_evidence")

    scores = {family: min(1.0, score) for family, score in scores.items()}
    ordered = tuple(
        ArchitectureCandidate(
            family=family,
            score=score,
            evidence=tuple(sorted(evidence[family])),
        )
        for family, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    )
    best = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None
    gap = best.score - second.score if second is not None else best.score
    payload = {
        "signals": {
            "indexed_layer_count": signals.indexed_layer_count,
            "recurrent_shape_group_count": signals.recurrent_shape_group_count,
            "attention_mode_counts": list(signals.attention_mode_counts),
            "expert_tensor_count": signals.expert_tensor_count,
            "state_carryover_observed": signals.state_carryover_observed,
            "kv_cache_approximately_linear": signals.kv_cache_approximately_linear,
        },
        "candidates": [candidate.as_dict() for candidate in ordered],
    }
    return ArchitectureFamilyReport(
        candidates=ordered,
        best_family=best.family,
        confidence_gap=gap,
        digest=stable_digest(payload),
    )
