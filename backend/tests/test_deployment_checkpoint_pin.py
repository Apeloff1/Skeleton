from __future__ import annotations

import base64
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_pin import sign_checkpoint_pin, verify_checkpoint_pin
from core.deployment_gateway import DeploymentGateway


def _keys():
    private = Ed25519PrivateKey.generate()
    private_b64 = base64.b64encode(private.private_bytes_raw()).decode("ascii")
    public_b64 = base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")
    return private_b64, public_b64


def _assurance():
    return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}


def _trust():
    return {
        "integrity_healthy": True,
        "finality_satisfied": True,
        "deploy_ready": True,
        "policy": {
            "configured": True, "configured_independence_groups": 3,
            "signed_independence_groups": 0, "required_groups": 3,
            "max_age_seconds": 3600, "quorum_capable": True,
            "signed_quorum_capable": False, "finality_required": True,
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

    def system_root(self):
        import hashlib
        release_head = self.gateway.releases.status()["head_set_sha256"] if self.gateway else ""
        return {"root_sha256": hashlib.sha256(("root\0" + release_head).encode()).hexdigest()}

    def assurance_report(self):
        return _assurance()

    def epistemic_finality(self):
        return _trust()


def _publication(tmp_path):
    plane = Plane()
    gateway = DeploymentGateway(tmp_path, control_plane=plane)
    plane.gateway = gateway
    prepared = gateway.prepare({
        "target": "product-runtime", "environment": "staging",
        "strategy": "rolling", "artifact": "artifact-v1",
    })
    gateway.execute(prepared.authorization.id, prepared.plan)
    publication = gateway.checkpoints.latest()
    assert publication is not None
    return publication


def test_signed_checkpoint_pin_verifies_against_external_key_and_expected_pins(tmp_path):
    publication = _publication(tmp_path)
    private_b64, public_b64 = _keys()
    receipt = sign_checkpoint_pin(
        publication=publication,
        private_key_b64=private_b64,
        public_key_b64=public_b64,
        observer_id="auditor-1",
        independence_group="external-audit",
        observed_at=datetime.now(UTC).isoformat(),
        nonce="audit-run-001",
    )

    assert verify_checkpoint_pin(
        receipt,
        public_key_b64=public_b64,
        expected_observer_id="auditor-1",
        expected_group="external-audit",
        expected_ledger_head_sha256=publication.sha256,
        expected_checkpoint_root_sha256=publication.checkpoint_root_sha256,
    ) is True


def test_receipt_cannot_self_assert_trust_key_or_group(tmp_path):
    publication = _publication(tmp_path)
    private_b64, public_b64 = _keys()
    _, other_public = _keys()
    receipt = sign_checkpoint_pin(
        publication=publication, private_key_b64=private_b64, public_key_b64=public_b64,
        observer_id="auditor-1", independence_group="external-audit",
        observed_at=datetime.now(UTC).isoformat(), nonce="n-1",
    )

    assert verify_checkpoint_pin(receipt, public_key_b64=other_public) is False
    assert verify_checkpoint_pin(receipt, public_key_b64=public_b64, expected_group="other-group") is False
    assert verify_checkpoint_pin(receipt, public_key_b64=public_b64, expected_observer_id="auditor-2") is False


def test_substituted_head_root_and_signature_fail(tmp_path):
    publication = _publication(tmp_path)
    private_b64, public_b64 = _keys()
    receipt = sign_checkpoint_pin(
        publication=publication, private_key_b64=private_b64, public_key_b64=public_b64,
        observer_id="auditor-1", independence_group="external-audit",
        observed_at=datetime.now(UTC).isoformat(), nonce="n-2",
    )

    assert verify_checkpoint_pin(receipt, public_key_b64=public_b64,
                                 expected_ledger_head_sha256="f" * 64) is False
    assert verify_checkpoint_pin(receipt, public_key_b64=public_b64,
                                 expected_checkpoint_root_sha256="e" * 64) is False
    tampered = replace(receipt, ledger_head_sha256="d" * 64)
    assert verify_checkpoint_pin(tampered, public_key_b64=public_b64) is False
    signature = bytearray(base64.b64decode(receipt.signature_b64))
    signature[0] ^= 1
    tampered_sig = replace(receipt, signature_b64=base64.b64encode(bytes(signature)).decode("ascii"))
    assert verify_checkpoint_pin(tampered_sig, public_key_b64=public_b64) is False


def test_type_confusion_and_noncanonical_inputs_fail_closed(tmp_path):
    publication = _publication(tmp_path)
    private_b64, public_b64 = _keys()
    receipt = sign_checkpoint_pin(
        publication=publication, private_key_b64=private_b64, public_key_b64=public_b64,
        observer_id="auditor-1", independence_group="external-audit",
        observed_at="2026-09-14T20:00:00+00:00", nonce="n-3",
    )

    raw = asdict(receipt)
    raw["sequence"] = True
    assert verify_checkpoint_pin(raw, public_key_b64=public_b64) is False

    raw = asdict(receipt)
    raw["observed_at"] = "2026-09-14T22:00:00+02:00"
    assert verify_checkpoint_pin(raw, public_key_b64=public_b64) is False

    raw = asdict(receipt)
    raw["signature_b64"] = raw["signature_b64"].rstrip("=")
    assert verify_checkpoint_pin(raw, public_key_b64=public_b64) is False


def test_signing_rejects_mismatched_keys(tmp_path):
    publication = _publication(tmp_path)
    private_b64, _ = _keys()
    _, other_public = _keys()
    with pytest.raises(ValueError, match="does not match"):
        sign_checkpoint_pin(
            publication=publication,
            private_key_b64=private_b64,
            public_key_b64=other_public,
            observer_id="auditor-1",
            independence_group="external-audit",
            observed_at=datetime.now(UTC).isoformat(),
            nonce="n-4",
        )
