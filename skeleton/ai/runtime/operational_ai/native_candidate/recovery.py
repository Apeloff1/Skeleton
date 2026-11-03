"""Recovery classifies post-gradient or post-publication uncertainty as held."""
from __future__ import annotations
from dataclasses import dataclass

from .state_rules import RunState
from .strict import sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    state: str
    action: str
    retry_authorized: bool
    model_activation_allowed: bool = False

    def record(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def decide(state: RunState, *, checkpoint_sha256: str | None = None,
           stored_artifact_verified: bool = False) -> RecoveryDecision:
    if type(state) is not RunState or type(stored_artifact_verified) is not bool:
        deny("recovery-types")
    if checkpoint_sha256 is not None:
        sha(checkpoint_sha256, "checkpoint")
    if state.state == "uncertain":
        return RecoveryDecision("held", "independent-review-of-partial-candidate", False)
    if state.state in ("training", "candidate"):
        if checkpoint_sha256 and stored_artifact_verified:
            return RecoveryDecision("held", "verify-receipts-before-new-run", False)
        return RecoveryDecision("held", "missing-publication-or-incomplete-gradient", False)
    if state.state == "held":
        return RecoveryDecision("held", "operator-review-required", False)
    return RecoveryDecision("held", "manual-replan-new-run-id", False)
