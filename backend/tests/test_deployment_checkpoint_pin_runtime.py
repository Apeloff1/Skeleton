from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_pin_runtime import DeploymentCheckpointPinRuntime
from core.deployment_checkpoint_trust_advance import verify_deployment_checkpoint_trust_advance
from core.deployment_checkpoint_witness import sign_deployment_checkpoint_pin
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
            "configured_independence_groups": 2,
            "signed_independence_groups": 2,
            "required_groups": 2,
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


def _trusted():
    keys = [_keypair(), _keypair()]
    witnesses = (
        TrustedWitness("w0", "org-a", True, keys[0][1]),
        TrustedWitness("w1", "org-b", True, keys[1][1]),
    )
    return keys, witnesses


def _sign(publication, key, witness, nonce):
    return sign_deployment_checkpoint_pin(
        publication,
        private_key_b64=key[0],
        public_key_b64=key[1],
        witness_id=witness.id,
        independence_group=witness.independence_group,
        observed_at="2026-09-14T20:00:00+00:00",
        nonce=nonce,
    )


def test_optional_policy_is_satisfied_without_external_witnesses(tmp_path):
    gateway = _gateway(tmp_path)
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy((), 1, 300, False),
    )
    status = runtime.status(now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC))
    assert status["requirement_satisfied"] is True
    assert status["current_quorum"]["reached"] is False
    assert status["latest_witnessed_quorum"] is None
    assert status["trust_frontier"]["latest_witnessed_publication_sequence"] == 0
    assert status["trust_frontier"]["advance_available"] is False
    assert status["verified"] is True


def test_required_policy_needs_fresh_independent_quorum_for_current_publication(tmp_path):
    gateway = _gateway(tmp_path)
    keys, witnesses = _trusted()
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy(witnesses, 2, 300, True),
    )
    now = datetime(2026, 9, 14, 20, 1, tzinfo=UTC)
    publication = gateway.checkpoints.latest(); assert publication is not None
    assert runtime.requirement_satisfied(now=now) is False

    runtime.observe(_sign(publication, keys[0], witnesses[0], "a"))
    assert runtime.requirement_satisfied(now=now) is False
    runtime.observe(_sign(publication, keys[1], witnesses[1], "b"))
    assert runtime.requirement_satisfied(now=now) is True
    witnessed = runtime.status(now=now)
    assert witnessed["trust_frontier"]["latest_witnessed_publication_sequence"] == publication.sequence
    assert witnessed["trust_frontier"]["publications_behind"] == 0
    assert witnessed["trust_frontier"]["advance_available"] is False

    prepared = gateway.prepare({
        "target": "runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "artifact-v1",
    })
    assert prepared.authorization.id
    newer = gateway.checkpoints.latest(); assert newer is not None
    assert newer.sha256 != publication.sha256
    assert runtime.requirement_satisfied(now=now) is False
    stale_frontier = runtime.status(now=now)["trust_frontier"]
    assert stale_frontier["latest_witnessed_publication_sequence"] == publication.sequence
    assert stale_frontier["publications_behind"] == newer.sequence - publication.sequence
    assert stale_frontier["advance_available"] is True


def test_witnessed_anchor_can_advance_history_without_satisfying_current_quorum(tmp_path):
    gateway = _gateway(tmp_path)
    keys, witnesses = _trusted()
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy(witnesses, 2, 300, True),
    )
    now = datetime(2026, 9, 14, 20, 1, tzinfo=UTC)
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    runtime.observe(_sign(anchor, keys[0], witnesses[0], "anchor-a"))
    runtime.observe(_sign(anchor, keys[1], witnesses[1], "anchor-b"))
    assert runtime.requirement_satisfied(now=now) is True

    gateway.prepare({
        "target": "runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "artifact-v2",
    })
    current = gateway.checkpoints.latest(); assert current is not None
    assert current.sha256 != anchor.sha256
    assert runtime.requirement_satisfied(now=now) is False

    packet = runtime.trust_advance(publication_sequence=anchor.sequence, now=now)
    latest_packet = runtime.advance_latest_witnessed(now=now)
    assert latest_packet == packet
    assert packet.anchor_publication_sha256 == anchor.sha256
    assert packet.current_publication_sha256 == current.sha256
    assert verify_deployment_checkpoint_trust_advance(
        packet,
        trusted_witnesses=witnesses,
        expected_required_groups=2,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is True
    assert runtime.requirement_satisfied(now=now) is False


def test_trust_advance_rejects_unwitnessed_anchor(tmp_path):
    gateway = _gateway(tmp_path)
    _, witnesses = _trusted()
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy(witnesses, 2, 300, True),
    )
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    try:
        runtime.trust_advance(
            publication_sequence=anchor.sequence,
            now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC),
        )
    except ValueError as exc:
        assert "quorum" in str(exc)
    else:
        raise AssertionError("unwitnessed anchor unexpectedly produced a trust-advance packet")
    try:
        runtime.advance_latest_witnessed(now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC))
    except ValueError as exc:
        assert "fresh witness quorum" in str(exc)
    else:
        raise AssertionError("unwitnessed history unexpectedly produced a trust-advance packet")


def test_witness_target_rotates_with_publication_history(tmp_path):
    gateway = _gateway(tmp_path)
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy((), 1, 300, False),
    )
    first = runtime.current_target(); assert first is not None
    gateway.prepare({
        "target": "runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": "artifact-v1",
    })
    second = runtime.current_target(); assert second is not None
    assert second.tree_size > first.tree_size
    assert second.publication_sha256 != first.publication_sha256
    assert second.target_sha256 != first.target_sha256
