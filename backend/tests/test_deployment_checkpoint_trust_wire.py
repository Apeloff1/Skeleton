from __future__ import annotations

from dataclasses import asdict

import pytest

from core.canonical_json import canonical_json_clone
from core.deployment_checkpoint_trust_advance import (
    build_deployment_checkpoint_trust_advance,
    verify_deployment_checkpoint_trust_advance,
)
from core.deployment_checkpoint_trust_wire import (
    decode_deployment_checkpoint_pin_bundle,
    decode_deployment_checkpoint_publication_proof,
    decode_deployment_checkpoint_trust_advance,
    decode_deployment_checkpoint_witnessed_continuity,
)
from core.deployment_checkpoint_witnessed_continuity import (
    verify_deployment_checkpoint_witnessed_continuity,
)
from tests.test_deployment_checkpoint_trust_advance import _deploy, _gateway, _witnessed_anchor
from tests.test_deployment_checkpoint_witnessed_continuity import _continuity


def _json(value):
    return canonical_json_clone(asdict(value))


def test_trust_advance_json_round_trip_remains_offline_verifiable(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    witnesses, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    current = gateway.checkpoints.latest(); assert current is not None
    packet = build_deployment_checkpoint_trust_advance(
        pin_bundle=bundle,
        checkpoint_ledger=gateway.checkpoints,
    )

    decoded = decode_deployment_checkpoint_trust_advance(_json(packet))
    assert decoded == packet
    assert verify_deployment_checkpoint_trust_advance(
        decoded,
        trusted_witnesses=witnesses,
        expected_required_groups=3,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is True


def test_witnessed_continuity_json_round_trip_remains_offline_verifiable(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    decoded = decode_deployment_checkpoint_witnessed_continuity(_json(packet))
    assert decoded == packet
    assert verify_deployment_checkpoint_witnessed_continuity(
        decoded,
        trusted_witnesses=witnesses,
        expected_required_groups=2,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
        witness_max_age_seconds=300,
    ) is True


def test_bundle_decoder_rejects_unsorted_duplicate_and_mismatched_receipts(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    publication = gateway.checkpoints.latest(); assert publication is not None
    _, bundle = _witnessed_anchor(publication)
    raw = _json(bundle)

    raw["receipts"] = list(reversed(raw["receipts"]))
    with pytest.raises(ValueError, match="unique and sorted"):
        decode_deployment_checkpoint_pin_bundle(raw)

    raw = _json(bundle)
    raw["receipts"][1] = raw["receipts"][0]
    with pytest.raises(ValueError, match="unique and sorted"):
        decode_deployment_checkpoint_pin_bundle(raw)

    raw = _json(bundle)
    raw["publication_sequence"] = raw["publication_sequence"] + 1
    with pytest.raises(ValueError, match="receipt target mismatch"):
        decode_deployment_checkpoint_pin_bundle(raw)


def test_publication_proof_decoder_rejects_bool_sequences_and_endpoint_substitution(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    _, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    packet = build_deployment_checkpoint_trust_advance(
        pin_bundle=bundle,
        checkpoint_ledger=gateway.checkpoints,
    )
    proof_raw = _json(packet.extension_proof)
    proof_raw["start_sequence"] = True
    with pytest.raises(ValueError, match="positive integer"):
        decode_deployment_checkpoint_publication_proof(proof_raw)

    proof_raw = _json(packet.extension_proof)
    proof_raw["ledger_head_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="ledger head mismatch"):
        decode_deployment_checkpoint_publication_proof(proof_raw)


def test_trust_packet_decoders_reject_unknown_fields_and_cross_endpoint_splicing(tmp_path):
    gateway = _gateway(tmp_path / "advance")
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest(); assert anchor is not None
    _, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    advance = build_deployment_checkpoint_trust_advance(
        pin_bundle=bundle,
        checkpoint_ledger=gateway.checkpoints,
    )
    raw = _json(advance)
    raw["server_authorized"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        decode_deployment_checkpoint_trust_advance(raw)

    _, _, _, _, _, continuity = _continuity(tmp_path / "continuity")
    raw = _json(continuity)
    raw["current_publication_sha256"] = raw["previous_publication_sha256"]
    with pytest.raises(ValueError, match="current bundle mismatch"):
        decode_deployment_checkpoint_witnessed_continuity(raw)


def test_nested_wire_containers_must_be_json_arrays(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    publication = gateway.checkpoints.latest(); assert publication is not None
    _, bundle = _witnessed_anchor(publication)
    raw = _json(bundle)
    raw["receipts"] = tuple(raw["receipts"])
    with pytest.raises(ValueError, match="JSON array"):
        decode_deployment_checkpoint_pin_bundle(raw)
