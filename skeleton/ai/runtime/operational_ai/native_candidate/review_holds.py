"""Full exact-head gates remain independent from candidate training."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import identity, sha
from .errors import deny

GATES = (
    "model_rights", "training_source", "training_contamination",
    "training_runtime", "tokenizer", "validation", "holdout",
    "independent_model_qualification", "device",
    "clean_install", "rollback", "privacy", "merge_readiness",
    "backend_quality", "app_e2e", "workflow_input_security",
    "sealed_context_guard", "malware_gate", "artifact_policy",
    "repository_hygiene", "secret_scanning", "dependency_review",
)


@dataclass(frozen=True, slots=True)
class GateEvidence:
    name: str
    complete: bool
    evidence_sha256: str | None = None
    exact_head_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.name not in GATES:
            deny("gate-name")
        if type(self.complete) is not bool:
            deny("gate-status")
        if self.complete:
            if self.evidence_sha256 is None or self.exact_head_sha256 is None:
                deny("gate-missing-proof")
        for val in (self.evidence_sha256, self.exact_head_sha256):
            if val is not None:
                sha(val, "gate-digest")


def review(holds: tuple[GateEvidence, ...]) -> dict:
    if type(holds) is not tuple or len({x.name for x in holds}) != len(holds):
        deny("gate-duplicate")
    indexed = {x.name: x for x in holds}
    missing = [name for name in GATES if name not in indexed]
    pending = [name for name in GATES if name in indexed and not indexed[name].complete]
    return {
        "required": len(GATES), "missing": missing, "pending": pending,
        "fully_proven": not missing and not pending,
        "merge_authorized": False, "release_certified": False,
    }
