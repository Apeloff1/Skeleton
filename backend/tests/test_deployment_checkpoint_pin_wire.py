from __future__ import annotations

import base64
from dataclasses import asdict

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_ledger import DeploymentCheckpointLedger
from core.deployment_checkpoint_pin_wire import decode_deployment_checkpoint_pin_receipt
from core.deployment_checkpoint_witness import sign_deployment_checkpoint_pin
from core.deployment_evidence_checkpoint import DeploymentEvidenceCheckpoint


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


def _publication(tmp_path):
    # Use a real verified checkpoint publication from the same schema the runtime uses.
    checkpoint = DeploymentEvidenceCheckpoint(
        version=2,
        authorization_head_sha256="a" * 64,
        authorization_events=0,
        receipt_head_sha256="b" * 64,
        receipt_events=0,
        release_channels=(),
        completed_releases=0,
        fully_portable_releases=0,
        evidence_gap_count=0,
        release_channels_sha256="c" * 64,
        root_sha256="d" * 64,
        attestation_sha256="e" * 64,
    )
    # The manually assembled checkpoint above is intentionally not assumed valid;
    # construction through a real gateway is covered elsewhere. Here we only need
    # a publication parser fixture, so import the established helper lazily.
    from tests.test_deployment_checkpoint_pin_ledger import _gateway
    gateway = _gateway(tmp_path)
    publication = gateway.checkpoints.latest()
    assert publication is not None
    return publication


def _raw_receipt(tmp_path):
    publication = _publication(tmp_path)
    private_key, public_key = _keypair()
    receipt = sign_deployment_checkpoint_pin(
        publication,
        private_key_b64=private_key,
        public_key_b64=public_key,
        witness_id="wire-w0",
        independence_group="wire-org",
        observed_at="2026-09-14T20:00:00+00:00",
        nonce="wire-1",
    )
    return receipt, asdict(receipt)


def test_valid_json_shaped_receipt_round_trips(tmp_path):
    receipt, raw = _raw_receipt(tmp_path)
    decoded = decode_deployment_checkpoint_pin_receipt(raw)
    assert decoded == receipt


def test_unknown_outer_or_witness_fields_fail_closed(tmp_path):
    _, raw = _raw_receipt(tmp_path)
    raw["admin"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        decode_deployment_checkpoint_pin_receipt(raw)

    _, raw = _raw_receipt(tmp_path / "w")
    raw["witness"]["role"] = "trusted"
    with pytest.raises(ValueError, match="witness schema mismatch"):
        decode_deployment_checkpoint_pin_receipt(raw)


def test_version_and_digest_type_confusion_are_rejected(tmp_path):
    _, raw = _raw_receipt(tmp_path)
    raw["version"] = True
    with pytest.raises(ValueError, match="version malformed"):
        decode_deployment_checkpoint_pin_receipt(raw)

    _, raw = _raw_receipt(tmp_path / "d")
    raw["receipt_sha256"] = raw["receipt_sha256"].upper()
    with pytest.raises(ValueError, match="digest malformed"):
        decode_deployment_checkpoint_pin_receipt(raw)


def test_publication_schema_drift_fails_before_signature_verification(tmp_path):
    _, raw = _raw_receipt(tmp_path)
    raw["publication"]["checkpoint"]["unexpected"] = 1
    with pytest.raises(ValueError, match="portable canonical JSON"):
        decode_deployment_checkpoint_pin_receipt(raw)
