from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from core.deployment_checkpoint_proof import (
    build_deployment_checkpoint_publication_proof,
    verify_deployment_checkpoint_publication_extension,
    verify_deployment_checkpoint_publication_proof,
)
from core.deployment_gateway import DeploymentGateway


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


def _deploy(gateway: DeploymentGateway, artifact: str):
    prepared = gateway.prepare({
        "target": "product-runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": artifact,
    })
    return gateway.execute(prepared.authorization.id, prepared.plan)


def test_historical_publication_proves_membership_against_current_pinned_head(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    history = gateway.checkpoints.history()
    assert len(history) >= 5

    proof = build_deployment_checkpoint_publication_proof(gateway.checkpoints, 2)
    current_head = gateway.checkpoints.status()["head_sha256"]

    assert proof.start_sequence == 2
    assert proof.end_sequence == history[-1].sequence
    assert proof.ledger_head_sha256 == current_head
    assert verify_deployment_checkpoint_publication_proof(
        proof,
        expected_ledger_head_sha256=current_head,
        expected_start_checkpoint_root_sha256=history[1].checkpoint_root_sha256,
    ) is True


def test_external_head_and_start_root_are_not_self_asserted(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    proof = build_deployment_checkpoint_publication_proof(gateway.checkpoints, 1)

    assert verify_deployment_checkpoint_publication_proof(
        proof,
        expected_ledger_head_sha256="f" * 64,
    ) is False
    assert verify_deployment_checkpoint_publication_proof(
        proof,
        expected_ledger_head_sha256=proof.ledger_head_sha256,
        expected_start_checkpoint_root_sha256="e" * 64,
    ) is False
    assert verify_deployment_checkpoint_publication_proof(
        proof,
        expected_ledger_head_sha256=proof.ledger_head_sha256,
        expected_start_publication_sha256="d" * 64,
    ) is False


def test_publication_tampering_fails_even_when_outer_proof_shape_is_unchanged(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    proof = build_deployment_checkpoint_publication_proof(gateway.checkpoints, 1)
    first = proof.publications[0]
    tampered_publication = replace(first, published_at="2026-09-14T00:00:00+00:00")
    tampered = replace(proof, publications=(tampered_publication, *proof.publications[1:]))

    assert verify_deployment_checkpoint_publication_proof(
        tampered,
        expected_ledger_head_sha256=proof.ledger_head_sha256,
    ) is False


def test_truncated_suffix_cannot_verify_against_newer_external_head(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    proof = build_deployment_checkpoint_publication_proof(gateway.checkpoints, 1)
    assert len(proof.publications) >= 3
    old_head = proof.publications[-2].sha256
    truncated = replace(
        proof,
        end_sequence=proof.publications[-2].sequence,
        end_checkpoint_root_sha256=proof.publications[-2].checkpoint_root_sha256,
        ledger_head_sha256=old_head,
        publications=proof.publications[:-1],
    )

    assert verify_deployment_checkpoint_publication_proof(
        truncated,
        expected_ledger_head_sha256=proof.ledger_head_sha256,
    ) is False


def test_old_pinned_publication_head_can_advance_trust_without_genesis_replay(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    old_history = gateway.checkpoints.history()
    anchor = old_history[-1]

    _deploy(gateway, "artifact-v2")
    proof = build_deployment_checkpoint_publication_proof(gateway.checkpoints, anchor.sequence)
    new_head = gateway.checkpoints.status()["head_sha256"]

    assert proof.publications[0].sha256 == anchor.sha256
    assert proof.start_sequence == anchor.sequence
    assert proof.start_sequence > 1
    assert verify_deployment_checkpoint_publication_extension(
        proof,
        expected_previous_ledger_head_sha256=anchor.sha256,
        expected_current_ledger_head_sha256=new_head,
    ) is True


def test_checkpoint_extension_rejects_wrong_old_pin_and_forked_anchor(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.history()[-1]
    _deploy(gateway, "artifact-v2")
    proof = build_deployment_checkpoint_publication_proof(gateway.checkpoints, anchor.sequence)

    assert verify_deployment_checkpoint_publication_extension(
        proof,
        expected_previous_ledger_head_sha256="f" * 64,
        expected_current_ledger_head_sha256=proof.ledger_head_sha256,
    ) is False

    forked_anchor = replace(proof.publications[0], previous_sha256="e" * 64)
    forked = replace(proof, publications=(forked_anchor, *proof.publications[1:]))
    assert verify_deployment_checkpoint_publication_extension(
        forked,
        expected_previous_ledger_head_sha256=anchor.sha256,
        expected_current_ledger_head_sha256=proof.ledger_head_sha256,
    ) is False


def test_builder_rejects_boolean_and_out_of_range_sequences(tmp_path):
    gateway = _gateway(tmp_path)
    with pytest.raises(ValueError, match="positive integer"):
        build_deployment_checkpoint_publication_proof(gateway.checkpoints, True)
    with pytest.raises(ValueError, match="positive integer"):
        build_deployment_checkpoint_publication_proof(gateway.checkpoints, 0)
    with pytest.raises(KeyError):
        build_deployment_checkpoint_publication_proof(gateway.checkpoints, 999)
