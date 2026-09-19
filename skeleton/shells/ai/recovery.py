"""Recovery diagnostics for interrupted AI shell sessions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.journal import AIDecisionJournal


class RecoveryAction(str, Enum):
    NONE = "none"
    RESUME_REVIEW = "resume_review"
    REQUIRE_REPLAN = "require_replan"
    REQUIRE_VERIFICATION = "require_verification"
    MARK_FAILED = "mark_failed"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class AIRecoveryReport:
    action: RecoveryAction
    reasons: tuple[str, ...]
    checkpoint_digest: str
    journal_valid: bool
    receipt_root_matches: bool

    @property
    def safe_to_resume(self) -> bool:
        return self.action in {RecoveryAction.NONE, RecoveryAction.RESUME_REVIEW}

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "reasons": list(self.reasons),
            "checkpoint_digest": self.checkpoint_digest,
            "journal_valid": self.journal_valid,
            "receipt_root_matches": self.receipt_root_matches,
            "safe_to_resume": self.safe_to_resume,
        }


class AIRecoveryManager:
    def inspect(
        self,
        checkpoint: AISessionCheckpoint,
        journal: AIDecisionJournal,
        *,
        current_receipt_root: str,
        current_policy_fingerprint: str,
        current_tool_catalog_digest: str,
        current_effect_digest: str,
    ) -> AIRecoveryReport:
        reasons = []
        journal_valid = journal.verify()
        receipt_matches = checkpoint.receipt_root == current_receipt_root
        if not journal_valid:
            reasons.append("AI decision journal integrity failure")
            action = RecoveryAction.MANUAL_REVIEW
        elif checkpoint.policy_fingerprint != current_policy_fingerprint:
            reasons.append("AI policy changed since checkpoint")
            action = RecoveryAction.REQUIRE_REPLAN
        elif checkpoint.tool_catalog_digest != current_tool_catalog_digest:
            reasons.append("model-visible tool catalog changed since checkpoint")
            action = RecoveryAction.REQUIRE_REPLAN
        elif checkpoint.effect_digest != current_effect_digest:
            reasons.append("effect contracts changed since checkpoint")
            action = RecoveryAction.REQUIRE_REPLAN
        elif not receipt_matches and checkpoint.phase in {"executing", "verifying"}:
            reasons.append("receipt chain advanced during interrupted execution")
            action = RecoveryAction.REQUIRE_VERIFICATION
        elif checkpoint.phase in {"new", "planning", "proposed"}:
            reasons.append("planning was interrupted before deterministic review")
            action = RecoveryAction.REQUIRE_REPLAN
        elif checkpoint.phase == "review":
            action = RecoveryAction.RESUME_REVIEW
        elif checkpoint.phase in {"executing", "verifying"}:
            action = RecoveryAction.REQUIRE_VERIFICATION
        elif checkpoint.phase in {"failed", "denied", "cancelled"}:
            action = RecoveryAction.MARK_FAILED
        else:
            action = RecoveryAction.NONE
        return AIRecoveryReport(
            action,
            tuple(reasons),
            checkpoint.digest,
            journal_valid,
            receipt_matches,
        )
