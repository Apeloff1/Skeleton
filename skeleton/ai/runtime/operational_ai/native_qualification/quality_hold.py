"""Explicit independent qualification holds; no self-reported CI or device proof."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import deny

REQUIRED = (
    "native_model", "tokenizer", "checkpoint_rights", "checkpoint_digest",
    "source_corpus", "real_generation", "durable_chat", "process_fence",
    "report_integrity", "device", "installer", "privacy_review",
    "merge_readiness", "backend_quality", "app_e2e", "workflow_input_security",
    "sealed_context_guard", "artifact_policy", "malware_gate",
    "repository_hygiene", "secret_scanning", "dependency_review",
)


@dataclass(frozen=True, slots=True)
class Hold:
    gate: str
    complete: bool
    sha256: str | None = None

    def __post_init__(self) -> None:
        if self.gate not in REQUIRED:
            deny("hold-gate")
        if type(self.complete) is not bool:
            deny("hold-status")
        if self.sha256 is None:
            if self.complete:
                deny("hold-unproven")
        else:
            from .canonical import hex64
            hex64(self.sha256, "hold-proof")


def assess(holds: tuple[Hold, ...]) -> dict:
    if type(holds) is not tuple or len({h.gate for h in holds}) != len(holds):
        deny("hold-inventory")
    indexed = {h.gate: h for h in holds}
    missing = [gate for gate in REQUIRED if gate not in indexed]
    pending = [gate for gate in REQUIRED if gate in indexed and not indexed[gate].complete]
    return {
        "schema": "skeleton.native-qualification.holds.v1",
        "required": len(REQUIRED), "proven": len(REQUIRED) - len(missing) - len(pending),
        "missing": missing, "pending": pending,
        "evidence_inventory_complete": not missing and not pending,
        "release_qualified": False,
        "source": "independent-exact-head-gate-evidence-required",
    }
