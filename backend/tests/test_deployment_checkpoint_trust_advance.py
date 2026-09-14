from __future__ import annotations

import base64
from dataclasses import replace
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_trust_advance import (
    build_deployment_checkpoint_trust_advance,
    verify_deployment_checkpoint_trust_advance,
)
from core.deployment_checkpoint_witness import (
    build_deployment_checkpoint_pin_bundle,
    sign_deployment_checkpoint_pin,
)
from core.deployment_gateway import DeploymentGateway
from core.transparency_witness import TrustedWitness


def _keypair():
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(private_raw).decode(), base64.b64encode(public_raw).decode()


def _assurance():
    return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}


def _trust():
    return {
        "integrity_healthy": True, "finality_satisfied": True, "deploy_ready": True,
        "policy": {
            "configured": True, "configured_independence_groups": 3,
            "signed_independence_groups": 3, "required_groups": 3,
            "max_age_seconds": 3600, "quorum_capable": True,
            "signed_quorum_capable": True, "finality_required": True,
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

    def system_root(self):
        release_head = self.gateway.releases.status()["head_set_sha256"] if self.gateway else ""
        return {"root_sha256": hashlib.sha256(("root\0" + release_head).encode()).hexdigest()}

    def assurance_report(self):
        return _assurance()

    def epistemic_finality(self):
        return _trust()


def _gateway(tmp_path):
    plane = Plane()
    gateway = DeploymentGateway(tmp_path / "gateway", control_plane=plane)
    plane.gateway = gateway
    return gateway


def _deploy(gateway, artifact):
    prepared = gateway.prepare({
        "target": "product-runtime", "environment": "staging",
        "strategy": "rolling", "artifact": artifact,
    })
    gateway.execute(prepared.authorization.id, prepared.plan)


def _witnessed_anchor(publication):
    keys = [_keypair() for _ in range(3)]
    witnesses = tuple(
        TrustedWitness(f"w{i}", f"org-{i}", True, keys[i][1]) for i in range(3)
    )
    receipts = tuple(
        sign_deployment_checkpoint_pin(
            publication,
            private_key_b64=keys[i][0], public_key_b64=keys[i][1],
            witness_id=witnesses[i].id, independence_group=witnesses[i].independence_group,
            observed_at="2026-09-14T20:00:00+00:00", nonce=f"pin-{i}",
        )
        for i in range(3)
    )
    return witnesses, build_deployment_checkpoint_pin_bundle(publication, receipts, required_groups=3)


def test_witnessed_anchor_advances_to_current_publication_head(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    witnesses, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")

    packet = build_deployment_checkpoint_trust_advance(
        pin_bundle=bundle, checkpoint_ledger=gateway.checkpoints,
    )
    current = gateway.checkpoints.latest(); assert current is not None

    assert packet.anchor_publication_sha256 == anchor.sha256
    assert packet.current_publication_sha256 == current.sha256
    assert verify_deployment_checkpoint_trust_advance(
        packet,
        trusted_witnesses=witnesses,
        expected_required_groups=3,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is True


def test_current_head_and_external_witness_policy_cannot_be_self_asserted(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    witnesses, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    packet = build_deployment_checkpoint_trust_advance(pin_bundle=bundle, checkpoint_ledger=gateway.checkpoints)

    assert verify_deployment_checkpoint_trust_advance(
        packet, trusted_witnesses=witnesses, expected_required_groups=3,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256="f" * 64,
    ) is False
    assert verify_deployment_checkpoint_trust_advance(
        packet, trusted_witnesses=witnesses, expected_required_groups=4,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256=packet.current_publication_sha256,
    ) is False


def test_stale_anchor_and_tampered_suffix_fail_closed(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    witnesses, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    packet = build_deployment_checkpoint_trust_advance(pin_bundle=bundle, checkpoint_ledger=gateway.checkpoints)

    assert verify_deployment_checkpoint_trust_advance(
        packet, trusted_witnesses=witnesses, expected_required_groups=3,
        anchor_verified_at="2026-09-14T21:00:01+00:00",
        expected_current_publication_sha256=packet.current_publication_sha256,
        witness_max_age_seconds=3600,
    ) is False

    first = packet.extension_proof.publications[0]
    bad_first = replace(first, previous_sha256="e" * 64)
    bad_extension = replace(
        packet.extension_proof,
        publications=(bad_first, *packet.extension_proof.publications[1:]),
    )
    tampered = replace(packet, extension_proof=bad_extension)
    assert verify_deployment_checkpoint_trust_advance(
        tampered, trusted_witnesses=witnesses, expected_required_groups=3,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256=packet.current_publication_sha256,
    ) is False
