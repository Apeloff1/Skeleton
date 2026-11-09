from dataclasses import asdict, replace
import hashlib
import json

from core.deployment_authorization import plan_digest
from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import (
    _authorization_event_schema,
    _proof_payload,
    _receipt_record_semantics,
    _release_record_semantics,
    _sha,
    _verify_chain_suffix,
    _verify_receipt_suffix,
    _verify_release_suffix,
    build_portable_deployment_proof,
    verify_portable_deployment_proof,
)
from core.deployment_planner import verify_deployment_plan


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


def _reseal(proof, **changes):
    raw = asdict(proof)
    raw.update(changes)
    raw.pop("proof_sha256", None)
    digest = hashlib.sha256(json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()
    return {**raw, "proof_sha256": digest}


def test_portable_proof_verifies_historical_deployment_against_newer_heads(tmp_path):
    gateway = _gateway(tmp_path)
    first = gateway.prepare(_input("artifact-v1"))
    gateway.execute(first.authorization.id, first.plan)
    second = gateway.prepare(_input("artifact-v2"))
    gateway.execute(second.authorization.id, second.plan)

    proof = build_portable_deployment_proof(gateway, first.authorization.id)
    assert proof.version == 3
    assert proof.preflight["allowed"] is True
    assert proof.preflight["stable"] is True
    assert proof.preflight["root_after_sha256"] == proof.pre_system_root_sha256
    assert verify_deployment_plan(proof.plan) is True
    assert plan_digest(proof.plan) == proof.plan_sha256
    assert proof.plan["target"] == proof.release["target"] == proof.transition_receipt["target"]
    assert proof.plan["environment"] == proof.release["environment"] == proof.transition_receipt["environment"]
    assert proof.plan["artifact"] == proof.release["artifact"] == proof.transition_receipt["artifact"]
    assert proof.authorization_suffix[0]["plan"] == proof.plan
    assert len(proof.authorization_suffix) >= 4
    assert len(proof.release_suffix) == 2
    assert len(proof.receipt_suffix) == 2
    assert verify_portable_deployment_proof(proof, **_pins(gateway, proof)) is True


def test_historical_proof_layers_each_validate_against_current_heads(tmp_path):
    gateway = _gateway(tmp_path)
    first = gateway.prepare(_input("artifact-v1"))
    gateway.execute(first.authorization.id, first.plan)
    second = gateway.prepare(_input("artifact-v2"))
    gateway.execute(second.authorization.id, second.plan)
    proof = build_portable_deployment_proof(gateway, first.authorization.id)
    pins = _pins(gateway, proof)

    assert _sha(_proof_payload(proof)) == proof.proof_sha256

    auth_suffix = tuple(proof.authorization_suffix)
    assert all(_authorization_event_schema(row) for row in auth_suffix), [set(row) for row in auth_suffix]
    assert _verify_chain_suffix(auth_suffix, expected_head=pins["expected_authorization_head_sha256"])

    release_suffix = tuple(proof.release_suffix)
    assert all(_release_record_semantics(row) for row in release_suffix), release_suffix
    assert _verify_release_suffix(release_suffix, expected_head=pins["expected_release_channel_head_sha256"])

    receipt_suffix = tuple(proof.receipt_suffix)
    assert all(_receipt_record_semantics(row) for row in receipt_suffix), receipt_suffix
    assert _verify_receipt_suffix(receipt_suffix, expected_head=pins["expected_receipt_head_sha256"])


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


def test_resealed_plan_substitution_still_fails_closed(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_input("artifact-v1"))
    gateway.execute(prepared.authorization.id, prepared.plan)
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    pins = _pins(gateway, proof)

    substituted = dict(proof.plan)
    substituted["artifact"] = "artifact-evil"
    candidate = dict(substituted)
    candidate.pop("plan_sha256")
    substituted["plan_sha256"] = hashlib.sha256(json.dumps(
        candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()

    assert verify_deployment_plan(substituted) is True
    assert verify_portable_deployment_proof(_reseal(proof, plan=substituted), **pins) is False


def test_missing_portable_plan_or_plan_digest_mismatch_fails_closed(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_input("artifact-v1"))
    gateway.execute(prepared.authorization.id, prepared.plan)
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    pins = _pins(gateway, proof)

    assert verify_portable_deployment_proof(_reseal(proof, plan={}), **pins) is False
    assert verify_portable_deployment_proof(_reseal(proof, plan_sha256="9" * 64), **pins) is False


def test_unconsumed_authorization_cannot_produce_deployment_proof(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_input("artifact-v1"))
    try:
        build_portable_deployment_proof(gateway, prepared.authorization.id)
    except ValueError as exc:
        assert "not been consumed" in str(exc)
    else:
        raise AssertionError("unconsumed authorization unexpectedly produced a proof")
