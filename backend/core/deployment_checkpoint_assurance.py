"""Fail-closed assurance over externally witnessed deployment checkpoints.

The runtime summary is not trusted as an authorization oracle. This module recomputes
policy capability, current-head quorum, continuity readiness, and summary coherence
from primitive typed fields. Optional witnessing remains observational; required modes
become hard deployment-assurance requirements.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.system_assurance import AssuranceInvariant


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def deployment_checkpoint_witness_invariants(status: Mapping[str, Any]) -> tuple[AssuranceInvariant, ...]:
    if not isinstance(status, Mapping):
        return (
            AssuranceInvariant(
                "deployment.checkpoint-witness-runtime-coherent",
                "hard",
                False,
                "checkpoint witness status is not a mapping",
            ),
        )

    policy = _mapping(status.get("policy"))
    ledger = _mapping(status.get("ledger"))
    quorum = _mapping(status.get("current_quorum"))
    frontier = _mapping(status.get("trust_frontier"))

    required_raw = policy.get("required")
    continuity_raw = policy.get("continuity_required")
    required_groups = policy.get("required_groups")
    max_age_seconds = policy.get("max_age_seconds")
    trusted_witnesses = policy.get("trusted_witnesses")
    configured_groups = policy.get("configured_independence_groups")

    policy_shape = (
        type(required_raw) is bool
        and type(continuity_raw) is bool
        and _positive_int(required_groups)
        and _positive_int(max_age_seconds)
        and _nonnegative_int(trusted_witnesses)
        and _nonnegative_int(configured_groups)
        and (not continuity_raw or required_raw)
    )
    required = required_raw is True
    continuity_required = continuity_raw is True

    runtime_ok = (
        status.get("verified") is True
        and status.get("cross_process_locking") is True
        and ledger.get("verified") is True
        and ledger.get("cross_process_locking") is True
    )

    capability_ok = (
        policy_shape
        and (
            not required
            or (
                configured_groups >= required_groups
                and trusted_witnesses >= required_groups
            )
        )
    )

    quorum_shape = False
    current_reached = False
    if quorum:
        independent_groups = quorum.get("independent_groups")
        fresh_receipts = quorum.get("fresh_receipts")
        quorum_required = quorum.get("required_groups")
        publication_sequence = quorum.get("publication_sequence")
        reached_raw = quorum.get("reached")
        quorum_shape = (
            _nonnegative_int(independent_groups)
            and _nonnegative_int(fresh_receipts)
            and _positive_int(quorum_required)
            and _positive_int(publication_sequence)
            and type(reached_raw) is bool
            and independent_groups <= fresh_receipts
            and quorum_required == required_groups
            and reached_raw == (independent_groups >= quorum_required)
            and _sha256(quorum.get("publication_sha256"))
            and _sha256(quorum.get("attestation_sha256"))
        )
        current_reached = quorum_shape and reached_raw is True

    current_sequence = frontier.get("current_publication_sequence")
    latest_witnessed_sequence = frontier.get("latest_witnessed_publication_sequence")
    prior_witnessed_sequence = frontier.get("latest_prior_witnessed_publication_sequence")
    publications_behind = frontier.get("publications_behind")
    advance_available = frontier.get("advance_available")
    continuity_ready_raw = frontier.get("continuity_ready")

    frontier_types_ok = (
        _nonnegative_int(current_sequence)
        and _nonnegative_int(latest_witnessed_sequence)
        and _nonnegative_int(prior_witnessed_sequence)
        and _nonnegative_int(publications_behind)
        and type(advance_available) is bool
        and type(continuity_ready_raw) is bool
    )
    if frontier_types_ok:
        expected_behind = (
            max(0, current_sequence - latest_witnessed_sequence)
            if latest_witnessed_sequence
            else current_sequence
        )
        prior_order_ok = (
            prior_witnessed_sequence == 0
            or (current_sequence > 0 and prior_witnessed_sequence < current_sequence)
        )
        expected_advance = latest_witnessed_sequence > 0 and expected_behind > 0
        expected_continuity = (
            current_reached
            and (
                current_sequence <= 1
                or (prior_witnessed_sequence > 0 and prior_witnessed_sequence < current_sequence)
            )
        )
        frontier_shape = (
            latest_witnessed_sequence <= current_sequence
            and prior_order_ok
            and publications_behind == expected_behind
            and advance_available == expected_advance
            and continuity_ready_raw == expected_continuity
            and (not current_reached or latest_witnessed_sequence == current_sequence)
        )
    else:
        expected_continuity = False
        frontier_shape = False
    continuity_ready = frontier_shape and expected_continuity

    policy_satisfied = (
        policy_shape
        and (
            not required
            or (
                current_reached
                and (not continuity_required or continuity_ready)
            )
        )
    )
    summary_raw = status.get("requirement_satisfied")
    summary_ok = type(summary_raw) is bool and summary_raw == policy_satisfied

    return (
        AssuranceInvariant(
            "deployment.checkpoint-witness-runtime-coherent",
            "hard",
            runtime_ok,
            f"verified={status.get('verified', False)}, locking={ledger.get('lock_backend', 'missing')}",
        ),
        AssuranceInvariant(
            "deployment.checkpoint-witness-policy-shape",
            "hard",
            policy_shape and frontier_shape,
            f"required={required_raw}, continuity_required={continuity_raw}, groups={configured_groups}/{required_groups}",
        ),
        AssuranceInvariant(
            "deployment.checkpoint-witness-policy-capable",
            "hard",
            capability_ok,
            f"required={required}, trusted_witnesses={trusted_witnesses}, groups={configured_groups}/{required_groups}",
        ),
        AssuranceInvariant(
            "deployment.checkpoint-witness-current-quorum",
            "hard",
            (not required) or current_reached,
            f"required={required}, reached={current_reached}, quorum_shape={quorum_shape}",
        ),
        AssuranceInvariant(
            "deployment.checkpoint-witness-continuity",
            "hard",
            (not continuity_required) or continuity_ready,
            f"required={continuity_required}, continuity_ready={continuity_ready}",
        ),
        AssuranceInvariant(
            "deployment.checkpoint-witness-summary-coherent",
            "hard",
            summary_ok,
            f"reported={summary_raw}, recomputed={policy_satisfied}",
        ),
    )
