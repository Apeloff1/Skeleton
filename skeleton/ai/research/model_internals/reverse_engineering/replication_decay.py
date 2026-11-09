"""Replication-quality decay as evidence ages across campaign epochs."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class AgedReplication:
    replication_id: str
    claim_digest: str
    quality: float
    produced_epoch: int
    current_epoch: int

    def __post_init__(self) -> None:
        if not self.replication_id:
            raise ReverseEngineeringError("aged replication requires identity")
        if not is_sha256_digest(self.claim_digest):
            raise ReverseEngineeringError("claim_digest must be sha256 hex")
        if not isfinite(self.quality) or not 0.0 <= self.quality <= 1.0:
            raise ReverseEngineeringError("quality must be within [0, 1]")
        if self.produced_epoch < 0 or self.current_epoch < self.produced_epoch:
            raise ReverseEngineeringError("replication epochs are invalid")

    @property
    def age(self) -> int:
        return self.current_epoch - self.produced_epoch


@dataclass(frozen=True)
class ReplicationDecayReport:
    replication_count: int
    mean_raw_quality: float
    mean_age: float
    mean_decayed_quality: float
    minimum_decayed_quality: float
    half_life_epochs: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "replication_count": self.replication_count,
            "mean_raw_quality": self.mean_raw_quality,
            "mean_age": self.mean_age,
            "mean_decayed_quality": self.mean_decayed_quality,
            "minimum_decayed_quality": self.minimum_decayed_quality,
            "half_life_epochs": self.half_life_epochs,
            "digest": self.digest,
        }


def analyze_replication_decay(
    replications: Sequence[AgedReplication],
    *,
    half_life_epochs: float = 100.0,
) -> ReplicationDecayReport:
    if not replications:
        raise ReverseEngineeringError("replication decay requires replications")
    if not isfinite(half_life_epochs) or half_life_epochs <= 0.0:
        raise ReverseEngineeringError("half_life_epochs must be finite and positive")
    digests = {item.claim_digest for item in replications}
    if len(digests) != 1:
        raise ReverseEngineeringError("aged replications must share claim_digest")
    decay_constant = 0.6931471805599453 / half_life_epochs
    decayed = [
        item.quality * exp(-decay_constant * item.age)
        for item in replications
    ]
    payload = {
        "claim_digest": next(iter(digests)),
        "half_life_epochs": half_life_epochs,
        "replications": [
            {
                "replication_id": item.replication_id,
                "quality": item.quality,
                "produced_epoch": item.produced_epoch,
                "current_epoch": item.current_epoch,
            }
            for item in sorted(replications, key=lambda value: value.replication_id)
        ],
    }
    return ReplicationDecayReport(
        replication_count=len(replications),
        mean_raw_quality=sum(item.quality for item in replications) / len(replications),
        mean_age=sum(item.age for item in replications) / len(replications),
        mean_decayed_quality=sum(decayed) / len(decayed),
        minimum_decayed_quality=min(decayed),
        half_life_epochs=half_life_epochs,
        digest=stable_digest(payload),
    )
