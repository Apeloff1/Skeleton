from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from core.deployment_evidence_checkpoint import (
    DEPLOYMENT_EVIDENCE_CHECKPOINT_VERSION,
    build_deployment_evidence_checkpoint,
    verify_deployment_evidence_checkpoint,
    verify_deployment_proof_against_checkpoint,
)
from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import build_portable_deployment_proof


def _assurance():
    return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}


def _trust():
    return {
        "integrity_healthy": True,
        "finality_satisfied": True,
        "deploy_ready": True,
        "policy": {
            "configured": True,
            "configured_independence_groups": 3,
            "signed_independence_groups": 0,
            "required_groups": 3,
            "max_age_seconds": 3600,
            "quorum_capable": True,
            "signed_quorum_capable": False,
            "finality_required": True,
            "signed_finality_required": False,
        },
        "gossip": {"split_views": 0, "rollbacks": 0, "healthy": True},
        "witnesses": {"equivocations": 0, "healthy": True},
        "signed_witnesses": {"equivocations": 0, "healthy": True},
        "current_head": {"current_tree_size": 8, "current_root_sha256": "b" * 64, "finalized": True},
    }


class Plane:
    def __init__(self):
        self.gateway = None
        self.seed = "c" * 64

    def system_root(self):
        release_head = self.gateway.releases.status()["head_set_sha256"] if self.gateway else ""
        return {"root_sha256": hashlib.sha256(f"{self.seed}\0{release_head}".encode()).hexdigest()}

    def assurance_report(self):
        return _assurance()

    def epistemic_finality(self):
        return _trust()


def _gateway(tmp_path):
    plane = Plane()
    gateway = DeploymentGateway(tmp_path, control_plane=plane)
    plane.gateway = gateway
    return gateway


def _deploy(gateway, *, artifact: str, target: str = "product-runtime", environment: str = "staging"):
    prepared = gateway.prepare({
        "target": target,
        "environment": environment,
        "strategy": "rolling",
        "artifact": artifact,
    })
    gateway.execute(prepared.authorization.id, prepared.plan)
    return prepared


def test_checkpoint_binds_all_current_deployment_evidence_heads(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-a")
    _deploy(gateway, artifact="artifact-b", target="worker-runtime")

    checkpoint = build_deployment_evidence_checkpoint(gateway)
    assert checkpoint.version == DEPLOYMENT_EVIDENCE_CHECKPOINT_VERSION == 2
    assert verify_deployment_evidence_checkpoint(checkpoint) is True
    assert checkpoint.authorization_events == 4
    assert checkpoint.receipt_events == 2
    assert checkpoint.completed_releases == 2
    assert checkpoint.fully_portable_releases == 2
    assert checkpoint.evidence_gap_count == 0
    assert len(checkpoint.release_channels) == 2
    assert {row.target for row in checkpoint.release_channels} == {"product-runtime", "worker-runtime"}


def test_historical_proof_verifies_against_later_unified_checkpoint(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, artifact="artifact-v1")
    _deploy(gateway, artifact="artifact-v2")
    proof = build_portable_deployment_proof(gateway, first.authorization.id)
    checkpoint = build_deployment_evidence_checkpoint(gateway)

    assert verify_deployment_proof_against_checkpoint(
        proof,
        checkpoint,
        expected_checkpoint_root_sha256=checkpoint.root_sha256,
    ) is True


def test_checkpoint_root_must_be_pinned_out_of_band(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, artifact="artifact-v1")
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    checkpoint = build_deployment_evidence_checkpoint(gateway)

    assert verify_deployment_proof_against_checkpoint(
        proof,
        checkpoint,
        expected_checkpoint_root_sha256="f" * 64,
    ) is False


def test_checkpoint_tamper_fails_even_when_counts_still_look_plausible(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-v1")
    checkpoint = build_deployment_evidence_checkpoint(gateway)

    tampered = replace(checkpoint, fully_portable_releases=0)
    assert verify_deployment_evidence_checkpoint(tampered) is False


def test_checkpoint_rejects_boolean_event_count_type_confusion(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-v1")
    checkpoint = build_deployment_evidence_checkpoint(gateway)

    assert verify_deployment_evidence_checkpoint(replace(checkpoint, authorization_events=True)) is False
    assert verify_deployment_evidence_checkpoint(replace(checkpoint, receipt_events=False)) is False


def test_proof_cannot_borrow_head_from_another_release_channel(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, artifact="artifact-a", target="runtime-a")
    _deploy(gateway, artifact="artifact-b", target="runtime-b")
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    checkpoint = build_deployment_evidence_checkpoint(gateway)
    wrong = tuple(
        replace(row, target="runtime-a") if row.target == "runtime-b" else row
        for row in checkpoint.release_channels
        if row.target != "runtime-a"
    )
    forged = replace(checkpoint, release_channels=wrong)

    assert verify_deployment_evidence_checkpoint(forged) is False
    assert verify_deployment_proof_against_checkpoint(
        proof, forged, expected_checkpoint_root_sha256=forged.root_sha256,
    ) is False


def test_checkpoint_with_evidence_gap_is_not_authority_for_proof(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, artifact="artifact-v1")
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    monkeypatch.setattr(gateway, "evidence_gaps", lambda: [{"kind": "synthetic-gap"}])
    checkpoint = build_deployment_evidence_checkpoint(gateway)

    assert verify_deployment_evidence_checkpoint(checkpoint) is True
    assert checkpoint.evidence_gap_count == 1
    assert verify_deployment_proof_against_checkpoint(
        proof,
        checkpoint,
        expected_checkpoint_root_sha256=checkpoint.root_sha256,
    ) is False


def test_checkpoint_builder_rejects_coerced_portability_counts(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-v1")
    real = gateway.portability_status()
    monkeypatch.setattr(gateway, "portability_status", lambda: {**real, "completed_releases": "1"})

    with pytest.raises(ValueError, match="completed_releases"):
        build_deployment_evidence_checkpoint(gateway)


def test_checkpoint_builder_rejects_coerced_authorization_event_counts(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-v1")
    real_status = gateway.authorizations.status
    monkeypatch.setattr(gateway.authorizations, "status", lambda: {**real_status(), "issued": "1"})

    with pytest.raises(ValueError, match="issued"):
        build_deployment_evidence_checkpoint(gateway)


def test_checkpoint_builder_rejects_coerced_receipt_event_counts(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-v1")
    real_status = gateway.receipts.status
    monkeypatch.setattr(gateway.receipts, "status", lambda: {**real_status(), "receipts": True})

    with pytest.raises(ValueError, match="receipts"):
        build_deployment_evidence_checkpoint(gateway)


def test_checkpoint_builder_refuses_unverified_ledger_status(tmp_path, monkeypatch):
    gateway = _gateway(tmp_path)
    _deploy(gateway, artifact="artifact-v1")
    real_status = gateway.authorizations.status
    monkeypatch.setattr(gateway.authorizations, "status", lambda: {**real_status(), "verified": False})

    with pytest.raises(ValueError, match="authorization ledger is not verified"):
        build_deployment_evidence_checkpoint(gateway)
