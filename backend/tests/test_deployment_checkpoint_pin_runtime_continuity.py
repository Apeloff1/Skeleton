from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_pin_runtime import DeploymentCheckpointPinRuntime
from core.deployment_checkpoint_witness import sign_deployment_checkpoint_pin
from core.deployment_checkpoint_witnessed_continuity import verify_deployment_checkpoint_witnessed_continuity
from core.deployment_gateway import DeploymentGateway
from core.transparency_witness import TrustedWitness


def _keys():
    private = Ed25519PrivateKey.generate()
    return (
        base64.b64encode(private.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        )).decode(),
        base64.b64encode(private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )).decode(),
    )


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
    def __init__(self): self.gateway = None
    def system_root(self):
        head = self.gateway.releases.status()["head_set_sha256"] if self.gateway else ""
        return {"root_sha256": hashlib.sha256(("root\0" + head).encode()).hexdigest()}
    def assurance_report(self):
        return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}
    def epistemic_finality(self): return _trust()


def _setup(tmp_path):
    plane = Plane()
    gateway = DeploymentGateway(tmp_path / "gateway", control_plane=plane)
    plane.gateway = gateway
    pairs = [_keys(), _keys()]
    witnesses = (
        TrustedWitness("w0", "org-a", True, pairs[0][1]),
        TrustedWitness("w1", "org-b", True, pairs[1][1]),
    )
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins", checkpoint_ledger=gateway.checkpoints,
        policy=DeploymentCheckpointPinPolicy(witnesses, 2, 300, True),
    )
    return gateway, runtime, pairs, witnesses


def _witness(runtime, publication, pairs, witnesses, prefix, observed_at):
    for i in range(2):
        runtime.observe(sign_deployment_checkpoint_pin(
            publication,
            private_key_b64=pairs[i][0], public_key_b64=pairs[i][1],
            witness_id=witnesses[i].id,
            independence_group=witnesses[i].independence_group,
            observed_at=observed_at, nonce=f"{prefix}-{i}",
        ))


def test_runtime_builds_two_epoch_witnessed_continuity(tmp_path):
    gateway, runtime, pairs, witnesses = _setup(tmp_path)
    previous = gateway.checkpoints.latest(); assert previous is not None
    _witness(runtime, previous, pairs, witnesses, "previous", "2026-09-14T20:00:00+00:00")

    gateway.prepare({
        "target": "runtime", "environment": "staging",
        "strategy": "rolling", "artifact": "artifact-v1",
    })
    current = gateway.checkpoints.latest(); assert current is not None
    _witness(runtime, current, pairs, witnesses, "current", "2026-09-14T20:02:00+00:00")

    now = datetime(2026, 9, 14, 20, 3, tzinfo=UTC)
    status = runtime.status(now=now)
    assert status["trust_frontier"]["continuity_ready"] is True
    assert status["trust_frontier"]["latest_prior_witnessed_publication_sequence"] == previous.sequence
    assert status["trust_frontier"]["latest_witnessed_publication_sequence"] == current.sequence

    packet = runtime.latest_witnessed_continuity(now=now)
    assert verify_deployment_checkpoint_witnessed_continuity(
        packet,
        trusted_witnesses=witnesses,
        expected_required_groups=2,
        previous_verified_at="2026-09-14T20:03:00+00:00",
        current_verified_at="2026-09-14T20:03:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is True


def test_current_quorum_without_prior_epoch_is_not_continuity(tmp_path):
    gateway, runtime, pairs, witnesses = _setup(tmp_path)
    current = gateway.checkpoints.latest(); assert current is not None
    _witness(runtime, current, pairs, witnesses, "current-only", "2026-09-14T20:00:00+00:00")
    now = datetime(2026, 9, 14, 20, 1, tzinfo=UTC)

    status = runtime.status(now=now)
    assert status["requirement_satisfied"] is True
    assert status["trust_frontier"]["continuity_ready"] is False
    try:
        runtime.latest_witnessed_continuity(now=now)
    except ValueError as exc:
        assert "prior checkpoint" in str(exc)
    else:
        raise AssertionError("single witnessed epoch unexpectedly formed continuity")
