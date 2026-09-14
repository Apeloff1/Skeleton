from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_pin_runtime import DeploymentCheckpointPinRuntime
from core.deployment_checkpoint_trust_policy import (
    build_deployment_checkpoint_trust_policy_manifest,
)
from tests.test_deployment_checkpoint_pin_runtime import _gateway, _trusted


def _status(tmp_path, policy):
    gateway = _gateway(tmp_path)
    runtime = DeploymentCheckpointPinRuntime(
        tmp_path / "pins",
        checkpoint_ledger=gateway.checkpoints,
        policy=policy,
    )
    return runtime.status(), build_deployment_checkpoint_trust_policy_manifest(policy)


def test_required_policy_status_separates_deploy_authority_from_audit_bridge(tmp_path):
    _, witnesses = _trusted()
    policy = DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, False)
    status, manifest = _status(tmp_path, policy)

    assert status["policy"]["manifest_sha256"] == manifest.manifest_sha256
    assert status["policy"]["deploy_authority_proof_kinds"] == (
        "pin",
        "witnessed_continuity",
    )
    assert status["policy"]["audit_only_proof_kinds"] == ("trust_advance",)
    assert "trust_advance" not in status["policy"]["deploy_authority_proof_kinds"]


def test_continuity_required_status_only_advertises_two_endpoint_authority(tmp_path):
    _, witnesses = _trusted()
    policy = DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    status, manifest = _status(tmp_path, policy)

    assert status["policy"]["manifest_sha256"] == manifest.manifest_sha256
    assert status["policy"]["deploy_authority_proof_kinds"] == ("witnessed_continuity",)
    assert status["policy"]["audit_only_proof_kinds"] == ("trust_advance",)


def test_optional_policy_marks_no_external_proof_as_required(tmp_path):
    policy = DeploymentCheckpointPinPolicy((), 1, 300, False, False)
    status, manifest = _status(tmp_path, policy)

    assert status["policy"]["manifest_sha256"] == manifest.manifest_sha256
    assert status["policy"]["deploy_authority_proof_kinds"] == (
        "none-required",
        "pin",
        "witnessed_continuity",
    )
    assert status["policy"]["audit_only_proof_kinds"] == ("trust_advance",)
