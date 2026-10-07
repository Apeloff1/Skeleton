"""Deterministic behavioral fingerprints from normalized observations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .contracts import EvidenceBundle, stable_digest


@dataclass(frozen=True)
class BehavioralFingerprint:
    target_id: str
    observation_count: int
    success_count: int
    kind_counts: tuple[tuple[str, int], ...]
    shape_counts: tuple[tuple[str, int], ...]
    feature_counts: tuple[tuple[str, int], ...]
    repeatability_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "observation_count": self.observation_count,
            "success_count": self.success_count,
            "kind_counts": [list(item) for item in self.kind_counts],
            "shape_counts": [list(item) for item in self.shape_counts],
            "feature_counts": [list(item) for item in self.feature_counts],
            "repeatability_ratio": self.repeatability_ratio,
            "digest": self.digest,
        }


def _repeatability_ratio(bundle: EvidenceBundle) -> float:
    by_probe: dict[str, list[str]] = {}
    for obs in bundle.observations:
        by_probe.setdefault(obs.probe_id, []).append(obs.output_digest)
    repeated = [values for values in by_probe.values() if len(values) > 1]
    if not repeated:
        return 1.0
    exact = sum(1 for values in repeated if len(set(values)) == 1)
    return exact / len(repeated)


def fingerprint_bundle(bundle: EvidenceBundle) -> BehavioralFingerprint:
    kinds = Counter(obs.kind.value for obs in bundle.observations)
    shapes = Counter(obs.output_shape for obs in bundle.observations)
    features = Counter(flag for obs in bundle.observations for flag in obs.feature_flags)
    payload = {
        "target_id": bundle.target_id,
        "bundle_digest": bundle.digest,
        "kind_counts": sorted(kinds.items()),
        "shape_counts": sorted(shapes.items()),
        "feature_counts": sorted(features.items()),
        "repeatability_ratio": round(_repeatability_ratio(bundle), 12),
    }
    return BehavioralFingerprint(
        target_id=bundle.target_id,
        observation_count=len(bundle.observations),
        success_count=sum(1 for obs in bundle.observations if obs.success),
        kind_counts=tuple(sorted(kinds.items())),
        shape_counts=tuple(sorted(shapes.items())),
        feature_counts=tuple(sorted(features.items())),
        repeatability_ratio=payload["repeatability_ratio"],
        digest=stable_digest(payload),
    )
