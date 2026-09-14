"""Operational runtime for externally witnessed deployment checkpoint publications.

This composes strict deployment-specific witness policy, the verified local checkpoint
publication ledger, durable signed-pin ingestion, canonical witness targets, and
freshness-bounded quorum into one runtime. It deliberately does not alter the system
root it observes, avoiding self-reference.

Trust advancement is an audit/update primitive, not a substitute for current-head
quorum. A previously witnessed publication can prove append-only ancestry to the
current publication, while a policy that requires external witnesses still requires a
fresh independent quorum on the current publication before deployment trust is
satisfied.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.deployment_checkpoint_ledger import DeploymentCheckpointLedger
from core.deployment_checkpoint_pin_config import (
    DeploymentCheckpointPinPolicy,
    load_deployment_checkpoint_pin_policy,
)
from core.deployment_checkpoint_pin_ledger import (
    DeploymentCheckpointPinEvent,
    DeploymentCheckpointPinLedger,
    DeploymentCheckpointPinQuorum,
)
from core.deployment_checkpoint_target import (
    DeploymentCheckpointWitnessTarget,
    build_deployment_checkpoint_witness_target,
)
from core.deployment_checkpoint_trust_advance import (
    DeploymentCheckpointTrustAdvance,
    build_deployment_checkpoint_trust_advance,
)
from core.deployment_checkpoint_witness import DeploymentCheckpointPinBundle, DeploymentCheckpointPinReceipt


class DeploymentCheckpointPinRuntime:
    def __init__(
        self,
        root: str | Path,
        *,
        checkpoint_ledger: DeploymentCheckpointLedger,
        policy: DeploymentCheckpointPinPolicy | None = None,
    ) -> None:
        if not isinstance(checkpoint_ledger, DeploymentCheckpointLedger):
            raise ValueError("checkpoint_ledger must be a DeploymentCheckpointLedger")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoints = checkpoint_ledger
        self.policy = policy if policy is not None else load_deployment_checkpoint_pin_policy()
        if not isinstance(self.policy, DeploymentCheckpointPinPolicy):
            raise ValueError("deployment checkpoint pin policy type mismatch")
        self.ledger = DeploymentCheckpointPinLedger(
            self.root / "ledger",
            checkpoint_ledger=self.checkpoints,
            trusted_witnesses=self.policy.witnesses,
            required_groups=self.policy.required_groups,
            max_age_seconds=self.policy.max_age_seconds,
        )

    def current_target(self) -> DeploymentCheckpointWitnessTarget | None:
        publication = self.checkpoints.latest()
        if publication is None:
            return None
        return build_deployment_checkpoint_witness_target(publication)

    def observe(self, receipt: DeploymentCheckpointPinReceipt) -> DeploymentCheckpointPinEvent:
        return self.ledger.observe(receipt)

    def quorum(
        self,
        *,
        publication_sequence: int | None = None,
        now: datetime | None = None,
    ) -> DeploymentCheckpointPinQuorum | None:
        return self.ledger.quorum(publication_sequence=publication_sequence, now=now)

    def latest_witnessed_quorum(self, *, now: datetime | None = None) -> DeploymentCheckpointPinQuorum | None:
        """Return the newest publication that currently has a fresh independent quorum."""
        history = self.checkpoints.history()
        for publication in reversed(history):
            quorum = self.quorum(publication_sequence=publication.sequence, now=now)
            if quorum is not None and quorum.reached:
                return quorum
        return None

    def portable_bundle(
        self,
        *,
        publication_sequence: int | None = None,
        now: datetime | None = None,
    ) -> DeploymentCheckpointPinBundle:
        return self.ledger.portable_bundle(publication_sequence=publication_sequence, now=now)

    def trust_advance(
        self,
        *,
        publication_sequence: int,
        now: datetime | None = None,
    ) -> DeploymentCheckpointTrustAdvance:
        """Advance a fresh witnessed anchor to the current append-only checkpoint head.

        The anchor bundle is constructed only after the configured independent-witness
        quorum is reached at ``now``. The returned packet remains independently
        verifiable against externally supplied witness keys, quorum policy, anchor
        verification time, and current publication head.
        """
        if type(publication_sequence) is not int or publication_sequence < 1:
            raise ValueError("publication_sequence must be a positive integer")
        bundle = self.portable_bundle(publication_sequence=publication_sequence, now=now)
        return build_deployment_checkpoint_trust_advance(
            pin_bundle=bundle,
            checkpoint_ledger=self.checkpoints,
        )

    def advance_latest_witnessed(self, *, now: datetime | None = None) -> DeploymentCheckpointTrustAdvance:
        """Build a trust-advance packet from the newest fresh witnessed publication."""
        quorum = self.latest_witnessed_quorum(now=now)
        if quorum is None:
            raise ValueError("no checkpoint publication has a fresh witness quorum")
        return self.trust_advance(publication_sequence=quorum.publication_sequence, now=now)

    def requirement_satisfied(self, *, now: datetime | None = None) -> bool:
        if not self.policy.required:
            return True
        quorum = self.quorum(now=now)
        return quorum is not None and quorum.reached

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        ledger = self.ledger.status(now=now)
        target = self.current_target()
        quorum = self.quorum(now=now)
        latest_witnessed = self.latest_witnessed_quorum(now=now)
        satisfied = not self.policy.required or (quorum is not None and quorum.reached)
        current_sequence = target.tree_size if target is not None else 0
        witnessed_sequence = latest_witnessed.publication_sequence if latest_witnessed is not None else 0
        publications_behind = max(0, current_sequence - witnessed_sequence) if witnessed_sequence else current_sequence
        return {
            "version": 1,
            "policy": {
                "required": self.policy.required,
                "required_groups": self.policy.required_groups,
                "max_age_seconds": self.policy.max_age_seconds,
                "trusted_witnesses": len(tuple(row for row in self.policy.witnesses if row.enabled)),
                "configured_independence_groups": len({
                    row.independence_group for row in self.policy.witnesses if row.enabled
                }),
            },
            "ledger": ledger,
            "current_target": None if target is None else asdict(target),
            "current_quorum": None if quorum is None else asdict(quorum),
            "latest_witnessed_quorum": None if latest_witnessed is None else asdict(latest_witnessed),
            "trust_frontier": {
                "current_publication_sequence": current_sequence,
                "latest_witnessed_publication_sequence": witnessed_sequence,
                "publications_behind": publications_behind,
                "advance_available": latest_witnessed is not None and publications_behind > 0,
            },
            "requirement_satisfied": satisfied,
            "verified": ledger.get("verified") is True,
            "cross_process_locking": ledger.get("cross_process_locking") is True,
        }
