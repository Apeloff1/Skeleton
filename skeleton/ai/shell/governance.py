"""Composition of AI policy, quarantine, review, rollout, and migration controls."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.policy import AIShellPolicy
from skeleton.shells.ai.policy_migration import AIPolicyMigration, AIPolicyMigrationPlanner
from skeleton.shells.ai.policy_rollout import AIPolicyRollout, AIPolicyRolloutManager
from skeleton.shells.ai.policy_store import AIPolicyRevision, AIPolicyStore
from skeleton.shells.ai.quarantine import AIQuarantine, QuarantineTarget
from skeleton.shells.ai.review import AIReviewView
from skeleton.shells.ai.review_queue import AIReviewQueue, ReviewQueueItem


@dataclass(frozen=True)
class AIGovernanceSnapshot:
    policy_revision: int
    policy_fingerprint: str
    quarantines: tuple[dict[str, object], ...]
    review_items: int

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_revision": self.policy_revision,
            "policy_fingerprint": self.policy_fingerprint,
            "quarantines": list(self.quarantines),
            "review_items": self.review_items,
        }


class AIShellGovernance:
    def __init__(
        self,
        policy_store: AIPolicyStore | None = None,
        *,
        quarantine: AIQuarantine | None = None,
        reviews: AIReviewQueue | None = None,
    ) -> None:
        self.policy_store = policy_store or AIPolicyStore()
        self.quarantine = quarantine or AIQuarantine()
        self.reviews = reviews or AIReviewQueue()
        self.migrations = AIPolicyMigrationPlanner()
        self.rollouts = AIPolicyRolloutManager(self.policy_store)

    def current_policy(self) -> AIPolicyRevision:
        return self.policy_store.current()

    def plan_policy_change(self, target: AIShellPolicy) -> AIPolicyMigration:
        return self.migrations.compare(self.policy_store.current().policy, target)

    def prepare_policy_rollout(
        self,
        rollout_id: str,
        target: AIShellPolicy,
        *,
        canary_percent: int = 10,
        reason: str = "",
    ) -> AIPolicyRollout:
        return self.rollouts.prepare(
            rollout_id,
            target,
            canary_percent=canary_percent,
            reason=reason,
        )

    def enqueue_review(
        self,
        review: AIReviewView,
        *,
        ttl_seconds: float = 900.0,
    ) -> ReviewQueueItem:
        return self.reviews.enqueue(review, ttl_seconds=ttl_seconds)

    def require_not_quarantined(
        self,
        *,
        model_id: str,
        proposal_fingerprint: str,
        commands: tuple[str, ...],
    ) -> None:
        if self.quarantine.active(QuarantineTarget.MODEL, model_id):
            raise RuntimeError("AI model is quarantined")
        if self.quarantine.active(QuarantineTarget.PROPOSAL, proposal_fingerprint):
            raise RuntimeError("AI proposal is quarantined")
        for command in commands:
            if self.quarantine.active(QuarantineTarget.COMMAND, command):
                raise RuntimeError(f"AI command is quarantined: {command}")

    def snapshot(self) -> AIGovernanceSnapshot:
        policy = self.policy_store.current()
        quarantines = tuple(item.to_dict() for item in self.quarantine.snapshot())
        return AIGovernanceSnapshot(
            policy.revision,
            policy.fingerprint,
            quarantines,
            len(self.reviews.snapshot()),
        )
