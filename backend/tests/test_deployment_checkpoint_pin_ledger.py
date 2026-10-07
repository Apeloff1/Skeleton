from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_pin_ledger import (
    DeploymentCheckpointPinLedger,
    DeploymentCheckpointPinLedgerError,
    DeploymentCheckpointPinRejected,
)
from core.deployment_checkpoint_witness import (
    sign_deployment_checkpoint_pin,
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


def _receipt(publication, key, witness, *, stamp, nonce):
    return sign_deployment_checkpoint_pin(
        publication,
        private_key_b64=key[0],
        public_key_b64=key[1],
        witness_id=witness.id,
        independence_group=witness.independence_group,
        observed_at=stamp,
        nonce=nonce,
    )


def test_ingestion_is_durable_idempotent_and_exports_portable_quorum(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses,
        required_groups=3,
        max_age_seconds=300,
    )
    stamp = "2026-09-14T20:00:00+00:00"
    events = []
    for i in range(3):
        receipt = _receipt(publication, keys[i], witnesses[i], stamp=stamp, nonce=f"n-{i}")
        event = ledger.observe(receipt)
        assert ledger.observe(receipt) == event
        events.append(event)

    assert [event.sequence for event in events] == [1, 2, 3]
    quorum = ledger.quorum(now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC))
    assert quorum is not None
    assert quorum.reached is True
    assert quorum.independent_groups == 3
    assert quorum.fresh_receipts == 3

    reloaded = DeploymentCheckpointPinLedger(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses,
        required_groups=3,
        max_age_seconds=300,
    )
    assert len(reloaded.snapshot()) == 3
    bundle = reloaded.portable_bundle(now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC))
    assert verify_deployment_checkpoint_pin_bundle(
        bundle,
        trusted_witnesses=witnesses,
        expected_publication_head_sha256=publication.sha256,
        expected_required_groups=3,
        verified_at="2026-09-14T20:01:00+00:00",
        max_age_seconds=300,
    ) is True


def test_conflicting_valid_resign_from_same_witness_is_rejected(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins", checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses, required_groups=1,
    )
    first = _receipt(publication, keys[0], witnesses[0], stamp="2026-09-14T20:00:00+00:00", nonce="first")
    second = _receipt(publication, keys[0], witnesses[0], stamp="2026-09-14T20:00:01+00:00", nonce="second")
    ledger.observe(first)
    with pytest.raises(DeploymentCheckpointPinRejected, match="conflicting pin"):
        ledger.observe(second)


def test_correlated_groups_and_stale_or_future_pins_do_not_reach_quorum(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry(("same", "same", "other"))
    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins", checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses, required_groups=3, max_age_seconds=60,
    )
    stamps = (
        "2026-09-14T20:00:30+00:00",
        "2026-09-14T20:00:30+00:00",
        "2026-09-14T19:59:00+00:00",
    )
    for i, stamp in enumerate(stamps):
        ledger.observe(_receipt(publication, keys[i], witnesses[i], stamp=stamp, nonce=f"n-{i}"))
    quorum = ledger.quorum(now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC))
    assert quorum is not None
    assert quorum.reached is False
    assert quorum.independent_groups == 1
    assert quorum.stale_receipts == 1

    future_gateway = _gateway(tmp_path / "future")
    future_publication = future_gateway.checkpoints.latest(); assert future_publication is not None
    future_ledger = DeploymentCheckpointPinLedger(
        tmp_path / "future-pins", checkpoint_ledger=future_gateway.checkpoints,
        trusted_witnesses=witnesses, required_groups=1, max_age_seconds=60,
    )
    future_ledger.observe(_receipt(
        future_publication, keys[0], witnesses[0],
        stamp="2026-09-14T20:01:01+00:00", nonce="future",
    ))
    future_quorum = future_ledger.quorum(now=datetime(2026, 9, 14, 20, 1, tzinfo=UTC))
    assert future_quorum is not None
    assert future_quorum.reached is False
    assert future_quorum.stale_receipts == 1


def test_untrusted_or_nonlocal_publication_receipts_are_rejected(tmp_path):
    gateway = _gateway(tmp_path / "a")
    other_gateway = _gateway(tmp_path / "b")
    publication = gateway.checkpoints.latest(); assert publication is not None
    other = other_gateway.checkpoints.latest(); assert other is not None
    keys, witnesses = _registry()
    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins", checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses[:1], required_groups=1,
    )

    untrusted = _receipt(publication, keys[1], witnesses[1], stamp="2026-09-14T20:00:00+00:00", nonce="u")
    with pytest.raises(DeploymentCheckpointPinRejected, match="not trusted"):
        ledger.observe(untrusted)

    # Advance the other ledger so the signed publication identity cannot coincide.
    prepared = other_gateway.prepare({
        "target": "runtime", "environment": "staging", "strategy": "rolling", "artifact": "other-v1",
    })
    assert prepared.authorization.id
    other = other_gateway.checkpoints.latest(); assert other is not None
    nonlocal_receipt = _receipt(other, keys[0], witnesses[0], stamp="2026-09-14T20:00:00+00:00", nonce="x")
    with pytest.raises(DeploymentCheckpointPinRejected, match="local verified publication"):
        ledger.observe(nonlocal_receipt)


def test_journal_tampering_is_detected_on_reload(tmp_path):
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest(); assert publication is not None
    keys, witnesses = _registry()
    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins", checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses[:1], required_groups=1,
    )
    ledger.observe(_receipt(publication, keys[0], witnesses[0], stamp="2026-09-14T20:00:00+00:00", nonce="n"))
    line = json.loads(ledger.path.read_text().strip())
    line["sequence"] = 2
    ledger.path.write_text(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(DeploymentCheckpointPinLedgerError):
        DeploymentCheckpointPinLedger(
            tmp_path / "pins", checkpoint_ledger=gateway.checkpoints,
            trusted_witnesses=witnesses[:1], required_groups=1,
        )


def test_policy_and_quorum_time_reject_bool_and_naive_types(tmp_path):
    gateway = _gateway(tmp_path)
    _, witnesses = _registry()
    with pytest.raises(ValueError, match="integer between"):
        DeploymentCheckpointPinLedger(
            tmp_path / "pins-a", checkpoint_ledger=gateway.checkpoints,
            trusted_witnesses=witnesses, required_groups=True,
        )
    with pytest.raises(ValueError, match="integer between"):
        DeploymentCheckpointPinLedger(
            tmp_path / "pins-b", checkpoint_ledger=gateway.checkpoints,
            trusted_witnesses=witnesses, max_age_seconds=True,
        )

    ledger = DeploymentCheckpointPinLedger(
        tmp_path / "pins-c", checkpoint_ledger=gateway.checkpoints,
        trusted_witnesses=witnesses, required_groups=1,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        ledger.quorum(now=datetime(2026, 9, 14, 20, 0))
