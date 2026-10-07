from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_witness import (
    build_deployment_checkpoint_pin_bundle,
    sign_deployment_checkpoint_pin,
    verify_deployment_checkpoint_pin,
    verify_deployment_checkpoint_pin_bundle,
)
from core.deployment_gateway import DeploymentGateway
from core.transparency_witness import TrustedWitness


def _keypair():
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(private_raw).decode(), base64.b64encode(public_raw).decode()


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


def _registry(groups=("org-a", "org-b", "org-c")):
    keys = [_keypair() for _ in groups]
    witnesses = tuple(TrustedWitness(f"w{i}", group, True, keys[i][1]) for i, group in enumerate(groups))
    return keys, witnesses


def _pins(publication, keys, witnesses, *, observed_at: str):
    return tuple(
        sign_deployment_checkpoint_pin(
            publication,
            private_key_b64=keys[i][0],
            public_key_b64=keys[i][1],
            witness_id=witness.id,
            independence_group=witness.independence_group,
            observed_at=observed_at,
            nonce=f"pin-{i}",
        )
        for i, witness in enumerate(witnesses)
    )


def test_three_independent_signed_pins_verify_offline(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest()
    assert publication is not None
    keys, witnesses = _registry()
    observed = "2026-09-14T20:00:00+00:00"
    receipts = _pins(publication, keys, witnesses, observed_at=observed)
    bundle = build_deployment_checkpoint_pin_bundle(publication, receipts, required_groups=3)

    assert all(
        verify_deployment_checkpoint_pin(
            receipts[i],
            public_key_b64=keys[i][1],
            expected_group=witnesses[i].independence_group,
            expected_publication_head_sha256=publication.sha256,
        )
        for i in range(3)
    )
    assert verify_deployment_checkpoint_pin_bundle(
        bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
        max_age_seconds=300,
    ) is True


def test_wrong_external_key_group_or_publication_head_fails(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    receipt = _pins(publication, keys, witnesses[:1], observed_at="2026-09-14T20:00:00+00:00")[0]

    assert verify_deployment_checkpoint_pin(
        receipt, public_key_b64=keys[1][1], expected_group="org-a",
        expected_publication_head_sha256=publication.sha256,
    ) is False
    assert verify_deployment_checkpoint_pin(
        receipt, public_key_b64=keys[0][1], expected_group="org-b",
        expected_publication_head_sha256=publication.sha256,
    ) is False
    assert verify_deployment_checkpoint_pin(
        receipt, public_key_b64=keys[0][1], expected_group="org-a",
        expected_publication_head_sha256="f" * 64,
    ) is False


def test_same_independence_group_cannot_manufacture_quorum(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry(("same-org", "same-org", "same-org"))
    receipts = _pins(publication, keys, witnesses, observed_at="2026-09-14T20:00:00+00:00")
    bundle = build_deployment_checkpoint_pin_bundle(publication, receipts, required_groups=3)

    assert verify_deployment_checkpoint_pin_bundle(
        bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_bundle_cannot_self_lower_external_quorum_requirement(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    receipt = _pins(publication, keys, witnesses[:1], observed_at="2026-09-14T20:00:00+00:00")[0]
    weak = build_deployment_checkpoint_pin_bundle(publication, (receipt,), required_groups=1)

    assert verify_deployment_checkpoint_pin_bundle(
        weak,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_stale_and_future_witness_pins_fail_freshness(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()

    stale_receipts = _pins(publication, keys, witnesses, observed_at="2026-09-14T19:00:00+00:00")
    stale_bundle = build_deployment_checkpoint_pin_bundle(publication, stale_receipts, required_groups=3)
    assert verify_deployment_checkpoint_pin_bundle(
        stale_bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:00:01+00:00",
        max_age_seconds=3600,
    ) is False

    future_receipts = _pins(publication, keys, witnesses, observed_at="2026-09-14T20:00:02+00:00")
    future_bundle = build_deployment_checkpoint_pin_bundle(publication, future_receipts, required_groups=3)
    assert verify_deployment_checkpoint_pin_bundle(
        future_bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:00:01+00:00",
        max_age_seconds=3600,
    ) is False


def test_receipt_and_bundle_tampering_fail_even_with_valid_signatures(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    receipts = _pins(publication, keys, witnesses, observed_at="2026-09-14T20:00:00+00:00")
    bundle = build_deployment_checkpoint_pin_bundle(publication, receipts, required_groups=3)

    tampered_receipt = replace(receipts[0], receipt_sha256="f" * 64)
    assert verify_deployment_checkpoint_pin(
        tampered_receipt,
        public_key_b64=keys[0][1],
        expected_group="org-a",
        expected_publication_head_sha256=publication.sha256,
    ) is False

    tampered_bundle = replace(bundle, checkpoint_root_sha256="e" * 64)
    assert verify_deployment_checkpoint_pin_bundle(
        tampered_bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_type_confused_quorum_and_time_policy_fail_closed(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    receipts = _pins(publication, keys, witnesses, observed_at="2026-09-14T20:00:00+00:00")
    bundle = build_deployment_checkpoint_pin_bundle(publication, receipts, required_groups=3)

    assert verify_deployment_checkpoint_pin_bundle(
        replace(bundle, required_groups=True),
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False
    assert verify_deployment_checkpoint_pin_bundle(
        bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=True,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False
    assert verify_deployment_checkpoint_pin_bundle(
        bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
        max_age_seconds=True,
    ) is False
