from __future__ import annotations

from copy import deepcopy

import pytest

from core.assurance_composition import extend_assurance
from core.canonical_json import canonical_json_sha256
from core.deployment_checkpoint_assurance import deployment_checkpoint_witness_invariants
from core.system_assurance import AssuranceInvariant, AssuranceReport, verify_assurance


def _policy_manifest(*, required: bool, continuity: bool):
    payload = {
        "version": 1,
        "required_groups": 1,
        "max_age_seconds": 300,
        "required": required,
        "continuity_required": continuity,
        "witnesses": [
            {
                "id": "w0",
                "independence_group": "org-a",
                "public_key_fingerprint": "c" * 64,
            }
        ],
    }
    return {**payload, "manifest_sha256": canonical_json_sha256(payload)}


def _status(*, required=False, continuity=False, reached=False, current=1, latest=0, prior=0):
    required_groups = 1
    fresh = 1 if reached else 0
    groups = 1 if reached else 0
    behind = max(0, current - latest) if latest else current
    continuity_ready = reached and (current <= 1 or (prior > 0 and prior < current))
    satisfied = (not required) or (reached and (not continuity or continuity_ready))
    manifest = _policy_manifest(required=required, continuity=continuity)
    if not required:
        deploy_kinds = ["none-required", "pin", "witnessed_continuity"]
    elif continuity:
        deploy_kinds = ["witnessed_continuity"]
    else:
        deploy_kinds = ["pin", "witnessed_continuity"]
    return {
        "version": 1,
        "policy": {
            "required": required,
            "continuity_required": continuity,
            "required_groups": required_groups,
            "max_age_seconds": 300,
            "trusted_witnesses": 1,
            "configured_independence_groups": 1,
            "manifest_sha256": manifest["manifest_sha256"],
            "deploy_authority_proof_kinds": deploy_kinds,
            "audit_only_proof_kinds": ["trust_advance"],
        },
        "policy_manifest": manifest,
        "ledger": {
            "verified": True,
            "cross_process_locking": True,
            "lock_backend": "fcntl",
        },
        "current_quorum": {
            "publication_sequence": current,
            "publication_sha256": "a" * 64,
            "trusted_receipts": fresh,
            "fresh_receipts": fresh,
            "stale_receipts": 0,
            "independent_groups": groups,
            "required_groups": required_groups,
            "max_age_seconds": 300,
            "reached": reached,
            "witness_ids": ["w0"] if reached else [],
            "groups": ["org-a"] if reached else [],
            "attestation_sha256": "b" * 64,
        },
        "trust_frontier": {
            "current_publication_sequence": current,
            "latest_witnessed_publication_sequence": latest,
            "latest_prior_witnessed_publication_sequence": prior,
            "publications_behind": behind,
            "advance_available": latest > 0 and behind > 0,
            "continuity_ready": continuity_ready,
        },
        "requirement_satisfied": satisfied,
        "verified": True,
        "cross_process_locking": True,
    }


def _base_report():
    row = AssuranceInvariant("base.ok", "hard", True, "base invariant holds")
    draft = AssuranceReport("healthy", 0, 0, 100.0, 100.0, (row,), "")
    # Build a valid base through the composition helper's own verifier contract by
    # reproducing the established system-assurance digest shape locally.
    import hashlib
    import json
    from dataclasses import asdict

    payload = {
        "posture": draft.posture,
        "hard_failures": draft.hard_failures,
        "warnings": draft.warnings,
        "native_coverage_pct": draft.native_coverage_pct,
        "readiness_pct": draft.readiness_pct,
        "invariants": [asdict(row)],
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return AssuranceReport("healthy", 0, 0, 100.0, 100.0, (row,), digest)


def _by_id(rows):
    return {row.id: row for row in rows}


def test_optional_witness_policy_is_observational_not_degrading():
    rows = deployment_checkpoint_witness_invariants(_status())
    assert all(row.passed for row in rows)


def test_required_policy_recomputes_current_quorum_instead_of_trusting_summary():
    status = _status(required=True, reached=False)
    status["requirement_satisfied"] = True
    rows = _by_id(deployment_checkpoint_witness_invariants(status))
    assert rows["deployment.checkpoint-witness-current-quorum"].passed is False
    assert rows["deployment.checkpoint-witness-summary-coherent"].passed is False


def test_required_current_quorum_passes_only_when_primitive_counts_are_consistent():
    status = _status(required=True, reached=True, latest=1)
    rows = _by_id(deployment_checkpoint_witness_invariants(status))
    assert all(row.passed for row in rows.values())

    forged = deepcopy(status)
    forged["current_quorum"]["independent_groups"] = 0
    forged["current_quorum"]["reached"] = True
    forged["requirement_satisfied"] = True
    rows = _by_id(deployment_checkpoint_witness_invariants(forged))
    assert rows["deployment.checkpoint-witness-current-quorum"].passed is False


def test_continuity_policy_requires_prior_witnessed_epoch_after_genesis():
    status = _status(required=True, continuity=True, reached=True, current=2, latest=2, prior=0)
    status["requirement_satisfied"] = True
    rows = _by_id(deployment_checkpoint_witness_invariants(status))
    assert rows["deployment.checkpoint-witness-continuity"].passed is False
    assert rows["deployment.checkpoint-witness-summary-coherent"].passed is False

    valid = _status(required=True, continuity=True, reached=True, current=2, latest=2, prior=1)
    rows = _by_id(deployment_checkpoint_witness_invariants(valid))
    assert all(row.passed for row in rows.values())


def test_policy_manifest_digest_flags_and_fingerprint_are_hard_bound():
    for mutate in (
        lambda status: status["policy"].__setitem__("manifest_sha256", "f" * 64),
        lambda status: status["policy_manifest"].__setitem__("max_age_seconds", 301),
        lambda status: status["policy_manifest"]["witnesses"][0].__setitem__(
            "public_key_fingerprint", "d" * 64
        ),
        lambda status: status["policy"].__setitem__(
            "deploy_authority_proof_kinds", ["trust_advance"]
        ),
    ):
        status = _status(required=True, reached=True, latest=1)
        mutate(status)
        rows = _by_id(deployment_checkpoint_witness_invariants(status))
        assert rows["deployment.checkpoint-witness-policy-identity"].passed is False
        assert rows["deployment.checkpoint-witness-policy-capable"].passed is False


def test_missing_portable_policy_manifest_fails_closed_even_if_summary_looks_valid():
    status = _status(required=True, reached=True, latest=1)
    status.pop("policy_manifest")
    rows = _by_id(deployment_checkpoint_witness_invariants(status))
    assert rows["deployment.checkpoint-witness-policy-identity"].passed is False
    assert rows["deployment.checkpoint-witness-summary-coherent"].passed is False


def test_frontier_bool_integer_confusion_and_false_lag_claims_fail_closed():
    for key, value in (
        ("current_publication_sequence", True),
        ("publications_behind", False),
        ("latest_witnessed_publication_sequence", "1"),
    ):
        status = _status()
        status["trust_frontier"][key] = value
        rows = _by_id(deployment_checkpoint_witness_invariants(status))
        assert rows["deployment.checkpoint-witness-policy-shape"].passed is False

    status = _status(required=True, reached=True, current=3, latest=3, prior=2)
    status["trust_frontier"]["publications_behind"] = 99
    rows = _by_id(deployment_checkpoint_witness_invariants(status))
    assert rows["deployment.checkpoint-witness-policy-shape"].passed is False


def test_runtime_integrity_is_independent_hard_invariant():
    status = _status()
    status["ledger"]["verified"] = False
    rows = _by_id(deployment_checkpoint_witness_invariants(status))
    assert rows["deployment.checkpoint-witness-runtime-coherent"].passed is False


def test_assurance_extension_recomputes_posture_and_remains_verifiable():
    base = _base_report()
    extended = extend_assurance(
        base,
        (AssuranceInvariant("checkpoint.required", "hard", False, "missing quorum"),),
    )
    assert extended.posture == "blocked"
    assert extended.hard_failures == 1
    assert verify_assurance(extended) is True


def test_assurance_extension_rejects_duplicate_ids_and_invalid_base():
    base = _base_report()
    with pytest.raises(ValueError, match="unique"):
        extend_assurance(base, (AssuranceInvariant("base.ok", "hard", True, "duplicate"),))

    invalid = AssuranceReport("healthy", 0, 0, 100.0, 100.0, (), "0" * 64)
    with pytest.raises(ValueError, match="base assurance"):
        extend_assurance(invalid, ())
