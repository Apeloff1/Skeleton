from __future__ import annotations

import hashlib

from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import (
    _authorization_event_schema,
    _proof_payload,
    _sha,
    _verify_chain_suffix,
    _verify_receipt_suffix,
    _verify_release_suffix,
    _release_record_semantics,
    _receipt_record_semantics,
    build_portable_deployment_proof,
    verify_portable_deployment_proof,
)


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


def _deploy(gateway, artifact: str):
    prepared = gateway.prepare({
        "target": "product-runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": artifact,
    })
    gateway.execute(prepared.authorization.id, prepared.plan)
    return prepared


def test_historical_proof_suffixes_remain_valid_against_current_heads(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    proof = build_portable_deployment_proof(gateway, first.authorization.id)

    assert _sha(_proof_payload(proof)) == proof.proof_sha256

    auth = tuple(proof.authorization_suffix)
    assert all(_authorization_event_schema(row) for row in auth)
    assert _verify_chain_suffix(auth, expected_head=gateway.authorizations.status()["head_sha256"])

    releases = tuple(proof.release_suffix)
    assert all(_release_record_semantics(row) for row in releases)
    assert _verify_release_suffix(
        releases,
        expected_head=gateway.releases.current(
            target=proof.release["target"], environment=proof.release["environment"]
        ).sha256,
    )

    receipts = tuple(proof.receipt_suffix)
    assert all(_receipt_record_semantics(row) for row in receipts)
    assert _verify_receipt_suffix(receipts, expected_head=gateway.receipts.status()["head_sha256"])

    assert verify_portable_deployment_proof(
        proof,
        expected_authorization_head_sha256=gateway.authorizations.status()["head_sha256"],
        expected_release_channel_head_sha256=gateway.releases.current(
            target=proof.release["target"], environment=proof.release["environment"]
        ).sha256,
        expected_receipt_head_sha256=gateway.receipts.status()["head_sha256"],
    )
