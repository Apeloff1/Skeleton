from __future__ import annotations

from dataclasses import replace
import hashlib

from core.deployment_checkpoint_target import (
    build_deployment_checkpoint_witness_target,
    verify_deployment_checkpoint_witness_target,
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
            "signed_independence_groups": 3,
            "required_groups": 3,
            "max_age_seconds": 3600,
            "quorum_capable": True,
            "signed_quorum_capable": True,
            "finality_required": True,
            "signed_finality_required": True,
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
    gateway = DeploymentGateway(tmp_path / "gateway", control_plane=plane)
    plane.gateway = gateway
    return gateway


def test_target_is_self_verifying_and_bound_to_publication(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest()
    assert publication is not None

    target = build_deployment_checkpoint_witness_target(publication)

    assert target.tree_size == publication.sequence
    assert target.publication_sha256 == publication.sha256
    assert target.checkpoint_root_sha256 == publication.checkpoint_root_sha256
    assert verify_deployment_checkpoint_witness_target(target, publication=publication) is True


def test_target_rejects_type_confusion_and_field_tampering(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    target = build_deployment_checkpoint_witness_target(publication)

    assert verify_deployment_checkpoint_witness_target(
        replace(target, tree_size=True), publication=publication,
    ) is False
    assert verify_deployment_checkpoint_witness_target(
        replace(target, publication_sha256="f" * 64), publication=publication,
    ) is False
    assert verify_deployment_checkpoint_witness_target(
        replace(target, target_sha256="e" * 64), publication=publication,
    ) is False


def test_old_target_cannot_be_rebound_to_new_publication(tmp_path):
    gateway = _gateway(tmp_path)
    first = gateway.checkpoints.latest(); assert first is not None
    first_target = build_deployment_checkpoint_witness_target(first)

    prepared = gateway.prepare({
        "target": "runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "artifact-v1",
    })
    second = gateway.checkpoints.latest(); assert second is not None

    assert second.sequence > first.sequence
    assert second.sha256 != first.sha256
    assert verify_deployment_checkpoint_witness_target(first_target, publication=second) is False
    second_target = build_deployment_checkpoint_witness_target(second)
    assert second_target.target_sha256 != first_target.target_sha256
    assert verify_deployment_checkpoint_witness_target(second_target, publication=second) is True
