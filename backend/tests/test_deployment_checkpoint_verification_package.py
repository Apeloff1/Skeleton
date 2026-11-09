from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from core.canonical_json import canonical_json_clone
from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_trust_policy import build_deployment_checkpoint_trust_policy_manifest
from core.deployment_checkpoint_verification_package import (
    PROOF_PIN,
    PROOF_TRUST_ADVANCE,
    PROOF_WITNESSED_CONTINUITY,
    build_deployment_checkpoint_verification_package,
    decode_deployment_checkpoint_verification_package,
    verify_deployment_checkpoint_verification_package,
)
from tests.test_deployment_checkpoint_trust_advance import _deploy, _gateway, _witnessed_anchor
from tests.test_deployment_checkpoint_witnessed_continuity import _continuity


def test_witnessed_continuity_package_round_trips_as_strict_json(tmp_path):
    _, _, witnesses, _, _, packet = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_WITNESSED_CONTINUITY,
        proof=packet,
    )
    decoded = decode_deployment_checkpoint_verification_package(
        canonical_json_clone(asdict(package))
    )
    assert decoded == package
    assert verify_deployment_checkpoint_verification_package(decoded) is True


def test_builder_rejects_proof_kind_type_splicing(tmp_path):
    _, _, witnesses, _, _, packet = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    with pytest.raises(ValueError, match="kind/type mismatch"):
        build_deployment_checkpoint_verification_package(
            policy_manifest=manifest,
            proof_kind=PROOF_TRUST_ADVANCE,
            proof=packet,
        )


def test_wire_rejects_kind_switch_even_when_nested_proof_is_untouched(tmp_path):
    _, _, witnesses, _, _, packet = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_WITNESSED_CONTINUITY,
        proof=packet,
    )
    raw = canonical_json_clone(asdict(package))
    raw["proof_kind"] = PROOF_TRUST_ADVANCE
    with pytest.raises(ValueError):
        decode_deployment_checkpoint_verification_package(raw)


def test_package_digest_binds_policy_manifest_and_nested_proof(tmp_path):
    _, _, witnesses, _, _, packet = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_WITNESSED_CONTINUITY,
        proof=packet,
    )

    raw = canonical_json_clone(asdict(package))
    raw["policy_manifest"]["required_groups"] = 1
    with pytest.raises(ValueError):
        decode_deployment_checkpoint_verification_package(raw)

    raw = canonical_json_clone(asdict(package))
    raw["proof"]["attestation_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="package integrity failed"):
        decode_deployment_checkpoint_verification_package(raw)


def test_package_version_and_digest_type_confusion_fail_closed(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    publication = gateway.checkpoints.latest()
    assert publication is not None
    witnesses, bundle = _witnessed_anchor(publication)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, True, False)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_PIN,
        proof=bundle,
    )

    assert verify_deployment_checkpoint_verification_package(
        replace(package, version=True)
    ) is False

    raw = canonical_json_clone(asdict(package))
    raw["version"] = True
    with pytest.raises(ValueError, match="version malformed"):
        decode_deployment_checkpoint_verification_package(raw)

    raw = canonical_json_clone(asdict(package))
    raw["package_sha256"] = raw["package_sha256"].upper()
    with pytest.raises(ValueError, match="digest malformed"):
        decode_deployment_checkpoint_verification_package(raw)
