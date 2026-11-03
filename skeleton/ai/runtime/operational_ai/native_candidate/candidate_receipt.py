"""Attested candidate receipts, not independent model-quality approval."""
from __future__ import annotations
from dataclasses import dataclass

from .strict import digest, sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class CandidateReceipt:
    run_id: str
    checkpoint_sha256: str
    candidate_model_sha256: str
    manifest_sha256: str
    rights_sha256: str
    corpus_sha256: str
    partition_sha256: str
    optimizer_steps: int
    candidate_only: bool = True

    def __post_init__(self) -> None:
        from .strict import identity, number
        identity(self.run_id, "run")
        for key in ("checkpoint_sha256", "candidate_model_sha256", "manifest_sha256",
                    "rights_sha256", "corpus_sha256", "partition_sha256"):
            sha(getattr(self, key), key)
        number(self.optimizer_steps, "steps", 1, 1000000)
        if self.candidate_only is not True:
            deny("candidate-only")

    def record(self) -> dict:
        return {
            **{k: getattr(self, k) for k in self.__dataclass_fields__},
            "production_authorized": False,
            "training_quality_certified": False,
            "real_device_qualified": False,
        }

    @property
    def digest(self) -> str:
        return digest(self.record())
