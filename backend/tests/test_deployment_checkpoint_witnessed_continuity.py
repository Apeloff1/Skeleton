from __future__ import annotations

import base64
from dataclasses import replace
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_witness import (
    build_deployment_checkpoint_pin_bundle,
    sign_deployment_checkpoint_pin,
)
from core.deployment_checkpoint_witnessed_continuity import (
    build_deployment_checkpoint_witnessed_continuity,
    verify_deployment_checkpoint_witnessed_continuity,
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
            "configured": True, "configured_independence_groups": 2,
            "signed_independence_groups": 2, "required_groups": 2,
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
    gateway = DeploymentGateway(tmp_path, control_plane=plane)
    plane.gateway = gateway
    return gateway


def _deploy(gateway, artifact):
    prepared = gateway.prepare({
        "target": "product-runtime", "environment": "staging",
        "strategy": "rolling", "artifact": artifact,
    })
    gateway.execute(prepared.authorization.id, prepared.plan)


def _witness_material():
    keys = [_keypair(), _keypair()]
    witnesses = (
        TrustedWitness("w0", "org-a", True, keys[0][1]),
        TrustedWitness("w1", "org-b", True, keys[1][1]),
    )
    return keys, witnesses


def _bundle(publication, keys, witnesses, stamp, prefix):
    receipts = tuple(
        sign_deployment_checkpoint_pin(
            publication,
            private_key_b64=keys[i][0], public_key_b64=keys[i][1],
            witness_id=witnesses[i].id, independence_group=witnesses[i].independence_group,
            observed_at=stamp, nonce=f"{prefix}-{i}",
        )
        for i in range(2)
    )
    return build_deployment_checkpoint_pin_bundle(publication, receipts, required_groups=2)


def _continuity(tmp_path):
    gateway = _gateway(tmp_path)
    keys, witnesses = _witness_material()
    _deploy(gateway, "artifact-v1")
    previous = gateway.checkpoints.latest(); assert previous is not None
    previous_bundle = _bundle(previous, keys, witnesses, "2026-09-14T20:00:00+00:00", "old")
    _deploy(gateway, "artifact-v2")
    current = gateway.checkpoints.latest(); assert current is not None
    current_bundle = _bundle(current, keys, witnesses, "2026-09-14T20:05:00+00:00", "new")
    packet = build_deployment_checkpoint_witnessed_continuity(
        previous_bundle=previous_bundle,
        current_bundle=current_bundle,
        checkpoint_ledger=gateway.checkpoints,
    )
    return gateway, keys, witnesses, previous, current, packet


def test_two_witnessed_epochs_prove_append_only_continuity(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    assert verify_deployment_checkpoint_witnessed_continuity(
        packet,
        trusted_witnesses=witnesses,
        expected_required_groups=2,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is True


def test_endpoint_pins_and_quorum_policy_are_external_authority(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    common = dict(
        trusted_witnesses=witnesses,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        witness_max_age_seconds=300,
    )
    assert verify_deployment_checkpoint_witnessed_continuity(
        packet, expected_required_groups=2,
        expected_previous_publication_sha256="e" * 64,
        expected_current_publication_sha256=current.sha256, **common,
    ) is False
    assert verify_deployment_checkpoint_witnessed_continuity(
        packet, expected_required_groups=2,
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256="f" * 64, **common,
    ) is False
    assert verify_deployment_checkpoint_witnessed_continuity(
        packet, expected_required_groups=3,
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256, **common,
    ) is False


def test_stale_endpoint_quorum_and_tampered_suffix_fail_closed(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    assert verify_deployment_checkpoint_witnessed_continuity(
        packet,
        trusted_witnesses=witnesses,
        expected_required_groups=2,
        previous_verified_at="2026-09-14T20:05:01+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is False

    first = packet.extension_proof.publications[0]
    bad_first = replace(first, checkpoint_root_sha256="d" * 64)
    bad_extension = replace(
        packet.extension_proof,
        publications=(bad_first, *packet.extension_proof.publications[1:]),
    )
    tampered = replace(packet, extension_proof=bad_extension)
    assert verify_deployment_checkpoint_witnessed_continuity(
        tampered,
        trusted_witnesses=witnesses,
        expected_required_groups=2,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is False


def test_builder_rejects_non_advancing_epochs(tmp_path):
    gateway = _gateway(tmp_path)
    keys, witnesses = _witness_material()
    publication = gateway.checkpoints.latest(); assert publication is not None
    bundle = _bundle(publication, keys, witnesses, "2026-09-14T20:00:00+00:00", "same")
    try:
        build_deployment_checkpoint_witnessed_continuity(
            previous_bundle=bundle,
            current_bundle=bundle,
            checkpoint_ledger=gateway.checkpoints,
        )
    except ValueError as exc:
        assert "strictly newer" in str(exc)
    else:
        raise AssertionError("same witnessed epoch unexpectedly formed a continuity proof")
