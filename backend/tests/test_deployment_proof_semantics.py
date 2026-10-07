from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import build_portable_deployment_proof, verify_portable_deployment_proof


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _record_hash(row: dict) -> str:
    return hashlib.sha256(_canonical({k: v for k, v in row.items() if k != "sha256"})).hexdigest()


def _reseal(raw: dict) -> dict:
    candidate = dict(raw)
    candidate.pop("proof_sha256", None)
    candidate["proof_sha256"] = hashlib.sha256(_canonical(candidate)).hexdigest()
    return candidate


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


def _verify_with_embedded_heads(raw: dict) -> bool:
    return verify_portable_deployment_proof(
        raw,
        expected_authorization_head_sha256=raw["authorization_head_sha256"],
        expected_release_channel_head_sha256=raw["release_channel_head_sha256"],
        expected_receipt_head_sha256=raw["receipt_head_sha256"],
    )


def test_resealed_and_repinned_forged_release_id_fails_semantic_verification(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, "artifact-v1")
    proof = build_portable_deployment_proof(gateway, prepared.authorization.id)
    raw = asdict(proof)

    release = dict(raw["release"])
    forged_release_id = "f" * 64
    assert forged_release_id != release["release_id"]
    release["release_id"] = forged_release_id
    release["sha256"] = _record_hash(release)
    raw["release"] = release
    raw["release_suffix"] = (dict(release),)
    raw["release_channel_head_sha256"] = release["sha256"]

    receipt = dict(raw["transition_receipt"])
    receipt["release_id"] = forged_release_id
    receipt["release_sha256"] = release["sha256"]
    receipt["sha256"] = _record_hash(receipt)
    raw["transition_receipt"] = receipt
    raw["receipt_suffix"] = (dict(receipt),)
    raw["receipt_head_sha256"] = receipt["sha256"]
    forged = _reseal(raw)

    assert _verify_with_embedded_heads(forged) is False


def test_repinned_release_suffix_cannot_break_previous_release_identity_link(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    proof = build_portable_deployment_proof(gateway, first.authorization.id)
    raw = asdict(proof)
    suffix = [dict(row) for row in raw["release_suffix"]]
    assert len(suffix) == 2

    suffix[1]["previous_release_id"] = "f" * 64
    suffix[1]["sha256"] = _record_hash(suffix[1])
    raw["release_suffix"] = tuple(suffix)
    raw["release_channel_head_sha256"] = suffix[-1]["sha256"]
    forged = _reseal(raw)

    assert _verify_with_embedded_heads(forged) is False


def test_repinned_receipt_suffix_cannot_claim_noop_root_transition(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    proof = build_portable_deployment_proof(gateway, first.authorization.id)
    raw = asdict(proof)
    suffix = [dict(row) for row in raw["receipt_suffix"]]
    assert len(suffix) == 2

    suffix[1]["post_system_root_sha256"] = suffix[1]["pre_system_root_sha256"]
    suffix[1]["sha256"] = _record_hash(suffix[1])
    raw["receipt_suffix"] = tuple(suffix)
    raw["receipt_head_sha256"] = suffix[-1]["sha256"]
    forged = _reseal(raw)

    assert _verify_with_embedded_heads(forged) is False


def test_resealed_top_level_schema_extension_is_rejected(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, "artifact-v1")
    raw = asdict(build_portable_deployment_proof(gateway, prepared.authorization.id))
    raw["operator_override"] = "accept-anyway"
    forged = _reseal(raw)

    assert _verify_with_embedded_heads(forged) is False


def test_resealed_release_record_extension_is_rejected_even_when_repinned(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, "artifact-v1")
    raw = asdict(build_portable_deployment_proof(gateway, prepared.authorization.id))

    release = dict(raw["release"])
    release["unmodeled_policy"] = "ignore-health-gates"
    release["sha256"] = _record_hash(release)
    raw["release"] = release
    raw["release_suffix"] = (dict(release),)
    raw["release_channel_head_sha256"] = release["sha256"]

    receipt = dict(raw["transition_receipt"])
    receipt["release_sha256"] = release["sha256"]
    receipt["sha256"] = _record_hash(receipt)
    raw["transition_receipt"] = receipt
    raw["receipt_suffix"] = (dict(receipt),)
    raw["receipt_head_sha256"] = receipt["sha256"]
    forged = _reseal(raw)

    assert _verify_with_embedded_heads(forged) is False


def test_nonfinite_nested_proof_value_is_rejected_even_when_resealed(tmp_path):
    gateway = _gateway(tmp_path)
    prepared = _deploy(gateway, "artifact-v1")
    raw = asdict(build_portable_deployment_proof(gateway, prepared.authorization.id))
    raw["preflight"] = dict(raw["preflight"])
    raw["preflight"]["forged_metric"] = float("nan")
    forged = _reseal(raw)

    assert _verify_with_embedded_heads(forged) is False
