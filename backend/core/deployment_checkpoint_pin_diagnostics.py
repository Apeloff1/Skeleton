"""Deterministic diagnostics for deployment checkpoint witness readiness.

This layer is deliberately non-authoritative: deployment decisions remain driven by
verified assurance invariants. Diagnostics explain those decisions from the canonical
pin runtime using machine-readable blocker/warning codes and concrete witness-group
state so operators can repair quorum or continuity without guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.deployment_checkpoint_pin_runtime import DeploymentCheckpointPinRuntime

DEPLOYMENT_CHECKPOINT_PIN_DIAGNOSTICS_VERSION = 1


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinDiagnostics:
    version: int
    ready: bool
    required: bool
    continuity_required: bool
    current_publication_sequence: int
    current_publication_sha256: str
    required_groups: int
    configured_groups: tuple[str, ...]
    current_fresh_groups: tuple[str, ...]
    candidate_missing_groups: tuple[str, ...]
    current_fresh_receipts: int
    current_stale_receipts: int
    latest_witnessed_publication_sequence: int
    latest_prior_witnessed_publication_sequence: int
    publications_behind: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


def diagnose_deployment_checkpoint_pins(
    runtime: DeploymentCheckpointPinRuntime,
    *,
    now: datetime | None = None,
) -> DeploymentCheckpointPinDiagnostics:
    if not isinstance(runtime, DeploymentCheckpointPinRuntime):
        raise ValueError("runtime must be a DeploymentCheckpointPinRuntime")

    status = runtime.status(now=now)
    policy = runtime.policy
    target = runtime.current_target()
    quorum = runtime.quorum(now=now)
    history = runtime.checkpoints.history()
    latest = runtime.latest_witnessed_quorum(now=now)
    prior = runtime.latest_prior_witnessed_quorum(now=now)

    configured_groups = tuple(sorted({
        row.independence_group for row in policy.witnesses if row.enabled
    }))
    current_groups = tuple(quorum.groups) if quorum is not None else ()
    missing_groups = tuple(group for group in configured_groups if group not in set(current_groups))
    current_sequence = target.tree_size if target is not None else 0
    current_sha = target.publication_sha256 if target is not None else ""
    latest_sequence = latest.publication_sequence if latest is not None else 0
    prior_sequence = prior.publication_sequence if prior is not None else 0
    publications_behind = (
        max(0, current_sequence - latest_sequence) if latest_sequence else current_sequence
    )
    fresh_receipts = quorum.fresh_receipts if quorum is not None else 0
    stale_receipts = quorum.stale_receipts if quorum is not None else 0
    current_reached = quorum is not None and quorum.reached

    blockers: list[str] = []
    warnings: list[str] = []
    ledger = status.get("ledger", {})
    if not (
        status.get("verified") is True
        and status.get("cross_process_locking") is True
        and isinstance(ledger, dict)
        and ledger.get("verified") is True
        and ledger.get("cross_process_locking") is True
    ):
        blockers.append("witness_runtime_integrity_failed")

    quorum_capable = len(configured_groups) >= policy.required_groups
    if policy.required and not quorum_capable:
        blockers.append("witness_policy_not_quorum_capable")
    if policy.required and not current_reached:
        blockers.append("current_checkpoint_quorum_missing")
    elif not policy.required and not current_reached:
        warnings.append("current_checkpoint_not_independently_witnessed")

    if stale_receipts:
        warnings.append("current_checkpoint_has_stale_receipts")

    continuity_missing = (
        policy.continuity_required
        and len(history) > 1
        and (prior is None or prior.publication_sequence >= history[-1].sequence)
    )
    if continuity_missing:
        blockers.append("prior_witnessed_checkpoint_missing")
    elif not policy.continuity_required and len(history) > 1 and prior is None:
        warnings.append("no_fresh_prior_witnessed_checkpoint")

    if publications_behind > 0:
        warnings.append("witness_frontier_behind_current_head")

    ready = not blockers and (
        not policy.required
        or (
            current_reached
            and (
                not policy.continuity_required
                or len(history) <= 1
                or prior_sequence > 0
            )
        )
    )

    return DeploymentCheckpointPinDiagnostics(
        version=DEPLOYMENT_CHECKPOINT_PIN_DIAGNOSTICS_VERSION,
        ready=ready,
        required=policy.required,
        continuity_required=policy.continuity_required,
        current_publication_sequence=current_sequence,
        current_publication_sha256=current_sha,
        required_groups=policy.required_groups,
        configured_groups=configured_groups,
        current_fresh_groups=current_groups,
        candidate_missing_groups=missing_groups,
        current_fresh_receipts=fresh_receipts,
        current_stale_receipts=stale_receipts,
        latest_witnessed_publication_sequence=latest_sequence,
        latest_prior_witnessed_publication_sequence=prior_sequence,
        publications_behind=publications_behind,
        blockers=tuple(blockers),
        warnings=tuple(dict.fromkeys(warnings)),
    )
