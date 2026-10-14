"""Differential comparison for two evidence bundles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import EvidenceBundle, ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class DifferentialFinding:
    probe_id: str
    comparable_observations: int
    matching_observations: int
    changed_shapes: bool
    changed_features: bool
    agreement_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "comparable_observations": self.comparable_observations,
            "matching_observations": self.matching_observations,
            "changed_shapes": self.changed_shapes,
            "changed_features": self.changed_features,
            "agreement_ratio": self.agreement_ratio,
            "digest": self.digest,
        }


def compare_bundles(
    left: EvidenceBundle,
    right: EvidenceBundle,
) -> tuple[DifferentialFinding, ...]:
    if left.target_id == right.target_id and left.digest == right.digest:
        return ()

    left_by_probe: dict[str, list] = {}
    right_by_probe: dict[str, list] = {}
    for obs in left.observations:
        left_by_probe.setdefault(obs.probe_id, []).append(obs)
    for obs in right.observations:
        right_by_probe.setdefault(obs.probe_id, []).append(obs)

    shared = sorted(set(left_by_probe) & set(right_by_probe))
    if not shared:
        raise ReverseEngineeringError("differential comparison requires shared probe_ids")

    findings: list[DifferentialFinding] = []
    for probe_id in shared:
        lhs = sorted(left_by_probe[probe_id], key=lambda item: item.ordinal)
        rhs = sorted(right_by_probe[probe_id], key=lambda item: item.ordinal)
        n = min(len(lhs), len(rhs))
        matches = sum(lhs[i].output_digest == rhs[i].output_digest for i in range(n))
        changed_shapes = {o.output_shape for o in lhs} != {o.output_shape for o in rhs}
        changed_features = {
            flag for o in lhs for flag in o.feature_flags
        } != {
            flag for o in rhs for flag in o.feature_flags
        }
        agreement = matches / n if n else 0.0
        payload = {
            "probe_id": probe_id,
            "left_target": left.target_id,
            "right_target": right.target_id,
            "n": n,
            "matches": matches,
            "changed_shapes": changed_shapes,
            "changed_features": changed_features,
        }
        findings.append(
            DifferentialFinding(
                probe_id=probe_id,
                comparable_observations=n,
                matching_observations=matches,
                changed_shapes=changed_shapes,
                changed_features=changed_features,
                agreement_ratio=round(agreement, 12),
                digest=stable_digest(payload),
            )
        )
    return tuple(findings)
