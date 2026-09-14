"""Operational runtime for externally witnessed deployment checkpoint publications.

This composes strict deployment-specific witness policy, the verified local checkpoint
publication ledger, durable signed-pin ingestion, canonical witness targets, and
freshness-bounded quorum into one runtime. It deliberately does not alter the system
root it observes, avoiding self-reference.

Trust advancement is an audit/update primitive, not a substitute for current-head
quorum. A previously witnessed publication can prove append-only ancestry to the
current publication, while a policy that requires external witnesses still requires a
fresh independent quorum on the current publication before deployment trust is
satisfied. Witnessed continuity is stronger again: both endpoints must have fresh
independent quorums and the complete append-only bridge must verify.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.canonical_json import canonical_json_clone
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
from core.deployment_checkpoint_trust_policy import build_deployment_checkpoint_trust_policy_manifest
from core.deployment_checkpoint_witness import DeploymentCheckpointPinBundle, DeploymentCheckpointPinReceipt
from core.deployment_checkpoint_witnessed_continuity import (
    DeploymentCheckpointWitnessedContinuity,
    build_deployment_checkpoint_witnessed_continuity,
)


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
        history = self.checkpoints.history()
        for publication in reversed(history):
            quorum = self.quorum(publication_sequence=publication.sequence, now=now)
            if quorum is not None and quorum.reached:
                return quorum
        return None

    def latest_prior_witnessed_quorum(self, *, now: datetime | None = None) -> DeploymentCheckpointPinQuorum | None:
        history = self.checkpoints.history()
        if len(history) < 2:
            return None
        for publication in reversed(history[:-1]):
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
        if type(publication_sequence) is not int or publication_sequence < 1:
            raise ValueError("publication_sequence must be a positive integer")
        bundle = self.portable_bundle(publication_sequence=publication_sequence, now=now)
        return build_deployment_checkpoint_trust_advance(pin_bundle=bundle, checkpoint_ledger=self.checkpoints)

    def advance_latest_witnessed(self, *, now: datetime | None = None) -> DeploymentCheckpointTrustAdvance:
        quorum = self.latest_witnessed_quorum(now=now)
        if quorum is None:
            raise ValueError("no checkpoint publication has a fresh witness quorum")
        return self.trust_advance(publication_sequence=quorum.publication_sequence, now=now)

    def witnessed_continuity(
        self,
        *,
        previous_publication_sequence: int,
        now: datetime | None = None,
    ) -> DeploymentCheckpointWitnessedContinuity:
        if type(previous_publication_sequence) is not int or previous_publication_sequence < 1:
            raise ValueError("previous_publication_sequence must be a positive integer")
        latest = self.checkpoints.latest()
        if latest is None:
            raise ValueError("checkpoint publication history is empty")
        if previous_publication_sequence >= latest.sequence:
            raise ValueError("previous witnessed publication must precede the current head")
        previous_bundle = self.portable_bundle(publication_sequence=previous_publication_sequence, now=now)
        current_bundle = self.portable_bundle(publication_sequence=latest.sequence, now=now)
        return build_deployment_checkpoint_witnessed_continuity(
            previous_bundle=previous_bundle,
            current_bundle=current_bundle,
            checkpoint_ledger=self.checkpoints,
        )

    def latest_witnessed_continuity(self, *, now: datetime | None = None) -> DeploymentCheckpointWitnessedContinuity:
        previous = self.latest_prior_witnessed_quorum(now=now)
        if previous is None:
            raise ValueError("no prior checkpoint publication has a fresh witness quorum")
        current = self.quorum(now=now)
        if current is None or not current.reached:
            raise ValueError("current checkpoint publication lacks a fresh witness quorum")
        return self.witnessed_continuity(previous_publication_sequence=previous.publication_sequence, now=now)

    def requirement_satisfied(self, *, now: datetime | None = None) -> bool:
        if not self.policy.required:
            return True
        current = self.quorum(now=now)
        current_ok = current is not None and current.reached
        if not current_ok:
            return False
        if not self.policy.continuity_required:
            return True
        history = self.checkpoints.history()
        if len(history) <= 1:
            # Genesis has no earlier publication to bridge; a fresh quorum establishes
            # the initial external trust anchor. Continuity becomes mandatory once the
            # journal advances beyond genesis.
            return True
        previous = self.latest_prior_witnessed_quorum(now=now)
        return previous is not None and previous.publication_sequence < history[-1].sequence

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        ledger = self.ledger.status(now=now)
        target = self.current_target()
        quorum = self.quorum(now=now)
        latest_witnessed = self.latest_witnessed_quorum(now=now)
        prior_witnessed = self.latest_prior_witnessed_quorum(now=now)
        current_sequence = target.tree_size if target is not None else 0
        witnessed_sequence = latest_witnessed.publication_sequence if latest_witnessed is not None else 0
        publications_behind = max(0, current_sequence - witnessed_sequence) if witnessed_sequence else current_sequence
        continuity_ready = (
            quorum is not None and quorum.reached
            and (
                current_sequence <= 1
                or (prior_witnessed is not None and prior_witnessed.publication_sequence < current_sequence)
            )
        )
        satisfied = self.requirement_satisfied(now=now)
        manifest = build_deployment_checkpoint_trust_policy_manifest(self.policy)
        portable_manifest = canonical_json_clone(asdict(manifest))
        if not self.policy.required:
            deploy_authority_proofs = ["none-required", "pin", "witnessed_continuity"]
        elif self.policy.continuity_required:
            deploy_authority_proofs = ["witnessed_continuity"]
        else:
            deploy_authority_proofs = ["pin", "witnessed_continuity"]
        return {
            "version": 1,
            "policy": {
                "required": self.policy.required,
                "continuity_required": self.policy.continuity_required,
                "required_groups": self.policy.required_groups,
                "max_age_seconds": self.policy.max_age_seconds,
                "trusted_witnesses": len(tuple(row for row in self.policy.witnesses if row.enabled)),
                "configured_independence_groups": len({
                    row.independence_group for row in self.policy.witnesses if row.enabled
                }),
                "manifest_sha256": manifest.manifest_sha256,
                "deploy_authority_proof_kinds": deploy_authority_proofs,
                "audit_only_proof_kinds": ["trust_advance"],
            },
            "policy_manifest": portable_manifest,
            "ledger": ledger,
            "current_target": None if target is None else asdict(target),
            "current_quorum": None if quorum is None else asdict(quorum),
            "latest_witnessed_quorum": None if latest_witnessed is None else asdict(latest_witnessed),
            "trust_frontier": {
                "current_publication_sequence": current_sequence,
                "latest_witnessed_publication_sequence": witnessed_sequence,
                "latest_prior_witnessed_publication_sequence": (
                    prior_witnessed.publication_sequence if prior_witnessed is not None else 0
                ),
                "publications_behind": publications_behind,
                "advance_available": latest_witnessed is not None and publications_behind > 0,
                "continuity_ready": continuity_ready,
            },
            "requirement_satisfied": satisfied,
            "verified": ledger.get("verified") is True,
            "cross_process_locking": ledger.get("cross_process_locking") is True,
        }
