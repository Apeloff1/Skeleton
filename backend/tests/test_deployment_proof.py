from dataclasses import replace
import hashlib

from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import build_portable_deployment_proof, verify_portable_deployment_proof


def _assurance():
    return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}


def _trust():
    return {
        "integrity_healthy": True,
        "finality_satisfied": True,
        "deploy_ready": True,
        "policy": {
            "configured": True, "configured_independence_groups": 3, "signed_independence_groups": 0,
            "required_groups": 3, "max_age_seconds": 3600, "quorum_capable": True,
            "signed_quorum_capable": False, "finality_required": True, "signed_finality_required": False,
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


def _input(artifact):
    return {"target": "product-runtime", "environment": "staging", "strategy": "rolling", "artifact": artifact}


def _pins(gateway, proof):
    return {
        "expected_authorization_head_sha256": gateway.authorizations.status()["head_sha256"],
        "expected_release_channel_head_sha256": gateway.releases.current(
            target=proof.release["target"], environment=proof.release["environment"]
        ).sha256,
        "expected_receipt_head_sha256": gateway.receipts.status()["head_sha256"],
    }


def test_portable_proof_verifies_historical_deployment_against_newer_heads(tmp_path):
    gateway = _gateway(tmp_path)
    first = gateway.prepare(_input("artifact-v1"))
    gateway.execute(first.authorization.id, first.plan)
    second = gateway.prepare(_input("artifact-v2"))
    gateway.execute(second.authorization.id, second.plan)

    proof = build_portable_deployment_proof(gateway, first.authorization.id)
    assert proof.version == 2
    assert proof.preflight["allowed"] is True
    assert proof.preflight["stable"] is True
    assert proof.preflight["root_after_sha256"] == proof.pre_system_root_sha256
    assert len(proof.authorization_suffix) >= 4
    assert len(proof.release_suffix) == 2
    assert len(proof.receipt_suffix) == 2
    assert verify_portable_deployment_proof(proof, **_pins(gateway, proof)) is True


def test_portable_proof_requires_external_head_pins(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_input("artifact-v1"))
    gateway.execute(prepared.authorization.id, prepared.plan)
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    pins = _pins(gateway, proof)

    assert verify_portable_deployment_proof(
        proof, **{**pins, "expected_authorization_head_sha256": "0" * 64}
    ) is False
    assert verify_portable_deployment_proof(
        proof, **{**pins, "expected_release_channel_head_sha256": "1" * 64}
    ) is False
    assert verify_portable_deployment_proof(
        proof, **{**pins, "expected_receipt_head_sha256": "2" * 64}
    ) is False


def test_cross_link_preflight_or_packet_tampering_fails_closed(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_input("artifact-v1"))
    gateway.execute(prepared.authorization.id, prepared.plan)
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    pins = _pins(gateway, proof)

    assert verify_portable_deployment_proof(replace(proof, post_system_root_sha256="f" * 64), **pins) is False

    preflight = dict(proof.preflight)
    preflight["stable"] = False
    assert verify_portable_deployment_proof(replace(proof, preflight=preflight), **pins) is False

    preflight = dict(proof.preflight)
    preflight["root_after_sha256"] = "e" * 64
    assert verify_portable_deployment_proof(replace(proof, preflight=preflight), **pins) is False

    receipt = dict(proof.transition_receipt)
    receipt["artifact"] = "substituted"
    assert verify_portable_deployment_proof(replace(proof, transition_receipt=receipt), **pins) is False

    release_suffix = list(proof.release_suffix)
    release_suffix[0] = {**release_suffix[0], "artifact": "substituted"}
    assert verify_portable_deployment_proof(replace(proof, release_suffix=tuple(release_suffix)), **pins) is False


def test_unconsumed_authorization_cannot_produce_deployment_proof(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_input("artifact-v1"))
    try:
        build_portable_deployment_proof(gateway, prepared.authorization.id)
    except ValueError as exc:
        assert "not been consumed" in str(exc)
    else:
        raise AssertionError("unconsumed authorization unexpectedly produced a proof")
