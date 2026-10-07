from __future__ import annotations

from dataclasses import asdict
import hashlib

from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import build_portable_deployment_proof
from core.deployment_proof_diagnostics import (
    diagnose_portable_deployment_proof,
    verify_deployment_proof_verdict,
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


def _proof(tmp_path):
    plane = Plane()
    gateway = DeploymentGateway(tmp_path, control_plane=plane)
    plane.gateway = gateway
    prepared = gateway.prepare({
        "target": "product-runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "artifact-v1",
    })
    gateway.execute(prepared.authorization.id, prepared.plan)
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    pins = {
        "expected_authorization_head_sha256": gateway.authorizations.status()["head_sha256"],
        "expected_release_channel_head_sha256": gateway.releases.current(
            target=proof.release["target"], environment=proof.release["environment"],
        ).sha256,
        "expected_receipt_head_sha256": gateway.receipts.status()["head_sha256"],
    }
    return proof, pins


def test_valid_proof_returns_attested_verified_diagnostic(tmp_path):
    proof, pins = _proof(tmp_path)
    verdict = diagnose_portable_deployment_proof(proof, **pins)
    assert verdict.valid is True
    assert verdict.stage == "verified"
    assert verdict.proof_sha256 == proof.proof_sha256
    assert verify_deployment_proof_verdict(verdict) is True


def test_wrong_external_pin_is_identified_before_internal_layers(tmp_path):
    proof, pins = _proof(tmp_path)
    verdict = diagnose_portable_deployment_proof(
        proof,
        **{**pins, "expected_receipt_head_sha256": "f" * 64},
    )
    assert verdict.valid is False
    assert verdict.stage == "external_pins"
    assert "receipt" in verdict.reason
    assert verify_deployment_proof_verdict(verdict) is True


def test_packet_tamper_is_classified_at_packet_layer(tmp_path):
    proof, pins = _proof(tmp_path)
    raw = asdict(proof)
    raw["post_system_root_sha256"] = "e" * 64
    verdict = diagnose_portable_deployment_proof(raw, **pins)
    assert verdict.valid is False
    assert verdict.stage == "packet"
    assert "hash mismatch" in verdict.reason


def test_resealed_semantically_invalid_plan_is_classified_as_plan_failure(tmp_path):
    proof, pins = _proof(tmp_path)
    raw = asdict(proof)
    raw["plan"] = dict(raw["plan"])
    raw["plan"]["rollback"] = dict(raw["plan"]["rollback"])
    raw["plan"]["rollback"]["automatic"] = False
    from core.canonical_json import canonical_json_sha256
    payload = {key: value for key, value in raw.items() if key != "proof_sha256"}
    raw["proof_sha256"] = canonical_json_sha256(payload)

    verdict = diagnose_portable_deployment_proof(raw, **pins)
    assert verdict.valid is False
    assert verdict.stage == "plan"
    assert "semantic" in verdict.reason


def test_diagnostic_attestation_detects_operator_side_mutation(tmp_path):
    proof, pins = _proof(tmp_path)
    verdict = diagnose_portable_deployment_proof(proof, **pins)
    raw = asdict(verdict)
    raw["reason"] = "trust me"
    from core.deployment_proof_diagnostics import DeploymentProofVerdict
    forged = DeploymentProofVerdict(**raw)
    assert verify_deployment_proof_verdict(forged) is False
