from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from core.deployment_gateway import DeploymentGateway
from core.deployment_proof import build_portable_deployment_proof, verify_portable_deployment_proof


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _record_hash(row: dict) -> str:
    payload = {key: value for key, value in row.items() if key != "sha256"}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _reseal(raw: dict) -> dict:
    candidate = dict(raw)
    candidate.pop("proof_sha256", None)
    candidate["proof_sha256"] = hashlib.sha256(_canonical(candidate)).hexdigest()
    return candidate


def _assurance():
    return {
        "posture": "healthy",
        "hard_failures": 0,
        "warnings": 0,
        "attestation_sha256": "a" * 64,
    }


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
        "current_head": {
            "current_tree_size": 8,
            "current_root_sha256": "b" * 64,
            "finalized": True,
        },
    }


class Plane:
    def __init__(self):
        self.gateway = None
        self.seed = "c" * 64

    def system_root(self):
        release_head = self.gateway.releases.status()["head_set_sha256"] if self.gateway else ""
        digest = hashlib.sha256(f"{self.seed}\0{release_head}".encode()).hexdigest()
        return {"root_sha256": digest}

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
    prepared = gateway.prepare(
        {
            "target": "product-runtime",
            "environment": "staging",
            "strategy": "rolling",
            "artifact": artifact,
        }
    )
    gateway.execute(prepared.authorization.id, prepared.plan)
    return prepared


def _verify(raw: dict, *, authorization_head: str, release_head: str, receipt_head: str) -> bool:
    return verify_portable_deployment_proof(
        raw,
        expected_authorization_head_sha256=authorization_head,
        expected_release_channel_head_sha256=release_head,
        expected_receipt_head_sha256=receipt_head,
    )


def test_current_pinned_heads_accept_complete_historical_suffixes(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")

    raw = asdict(build_portable_deployment_proof(gateway, first.authorization.id))

    assert _verify(
        raw,
        authorization_head=raw["authorization_head_sha256"],
        release_head=raw["release_channel_head_sha256"],
        receipt_head=raw["receipt_head_sha256"],
    )


def test_release_history_sequence_gap_is_rejected_after_rehash_and_repin(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    raw = asdict(build_portable_deployment_proof(gateway, first.authorization.id))

    suffix = [dict(row) for row in raw["release_suffix"]]
    assert len(suffix) == 2
    suffix[1]["sequence"] = suffix[0]["sequence"] + 2
    suffix[1]["sha256"] = _record_hash(suffix[1])
    raw["release_suffix"] = tuple(suffix)
    raw["release_channel_head_sha256"] = suffix[-1]["sha256"]
    forged = _reseal(raw)

    assert not _verify(
        forged,
        authorization_head=forged["authorization_head_sha256"],
        release_head=forged["release_channel_head_sha256"],
        receipt_head=forged["receipt_head_sha256"],
    )


def test_receipt_history_sequence_gap_is_rejected_after_rehash_and_repin(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    raw = asdict(build_portable_deployment_proof(gateway, first.authorization.id))

    suffix = [dict(row) for row in raw["receipt_suffix"]]
    assert len(suffix) == 2
    suffix[1]["sequence"] = suffix[0]["sequence"] + 2
    suffix[1]["sha256"] = _record_hash(suffix[1])
    raw["receipt_suffix"] = tuple(suffix)
    raw["receipt_head_sha256"] = suffix[-1]["sha256"]
    forged = _reseal(raw)

    assert not _verify(
        forged,
        authorization_head=forged["authorization_head_sha256"],
        release_head=forged["release_channel_head_sha256"],
        receipt_head=forged["receipt_head_sha256"],
    )


def test_truncated_histories_fail_against_out_of_band_current_heads(tmp_path):
    gateway = _gateway(tmp_path)
    first = _deploy(gateway, "artifact-v1")
    _deploy(gateway, "artifact-v2")
    raw = asdict(build_portable_deployment_proof(gateway, first.authorization.id))

    current_authorization_head = raw["authorization_head_sha256"]
    current_release_head = raw["release_channel_head_sha256"]
    current_receipt_head = raw["receipt_head_sha256"]

    release_suffix = [dict(row) for row in raw["release_suffix"]]
    receipt_suffix = [dict(row) for row in raw["receipt_suffix"]]
    assert len(release_suffix) == 2
    assert len(receipt_suffix) == 2

    raw["release_suffix"] = (release_suffix[0],)
    raw["release_channel_head_sha256"] = release_suffix[0]["sha256"]
    raw["receipt_suffix"] = (receipt_suffix[0],)
    raw["receipt_head_sha256"] = receipt_suffix[0]["sha256"]
    truncated = _reseal(raw)

    assert not _verify(
        truncated,
        authorization_head=current_authorization_head,
        release_head=current_release_head,
        receipt_head=current_receipt_head,
    )
