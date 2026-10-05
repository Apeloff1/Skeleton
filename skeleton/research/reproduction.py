"""Reproduction package contracts for research evidence.

This module is authority-neutral and binds reproduction instructions to exact
claim, result, environment, and dependency digests.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReproductionError(ValueError):
    pass


class Availability(str, Enum):
    AVAILABLE = "available"
    RESTRICTED = "restricted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ReproductionDependency:
    dependency_id: str
    digest: str
    availability: Availability
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.dependency_id.strip() or not self.evidence_ref.strip():
            raise ReproductionError("dependency identity and evidence are required")
        if not _SHA256.fullmatch(self.digest):
            raise ReproductionError("dependency digest must be sha256")
        object.__setattr__(self, "availability", Availability(self.availability))


@dataclass(frozen=True, slots=True)
class ReproductionPackage:
    package_id: str
    claim_digest: str
    result_digest: str
    environment_digest: str
    dependencies: tuple[ReproductionDependency, ...]
    replay_steps: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.package_id.strip():
            raise ReproductionError("package_id is required")
        for value in (self.claim_digest, self.result_digest, self.environment_digest):
            if not _SHA256.fullmatch(value):
                raise ReproductionError("package digests must be sha256")
        if not self.dependencies or not self.replay_steps:
            raise ReproductionError("dependencies and replay steps are required")
        if len({d.dependency_id for d in self.dependencies}) != len(self.dependencies):
            raise ReproductionError("dependency ids must be unique")

    @property
    def runnable(self) -> bool:
        return all(d.availability is Availability.AVAILABLE for d in self.dependencies)

    @property
    def digest(self) -> str:
        payload = {
            "package_id": self.package_id,
            "claim_digest": self.claim_digest,
            "result_digest": self.result_digest,
            "environment_digest": self.environment_digest,
            "dependencies": [
                (d.dependency_id, d.digest, d.availability.value, d.evidence_ref)
                for d in sorted(self.dependencies, key=lambda item: item.dependency_id)
            ],
            "replay_steps": list(self.replay_steps),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
