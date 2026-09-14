import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.deployment_checkpoint_witness import sign_deployment_checkpoint_pin
from core.deployment_gateway import DeploymentGatewayError
from core.product_control_plane import ProductControlPlane


def _deployment(artifact="release-artifact-v1"):
    return {
        "target": "product-runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": artifact,
    }


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


def _configure_required_witness(monkeypatch, public_key: str, *, continuity: bool = False):
    monkeypatch.setenv(
        "DEPLOYMENT_CHECKPOINT_TRUSTED_WITNESSES_JSON",
        '[{"id":"release-witness","independence_group":"independent-a","enabled":true,"public_key_b64":"'
        + public_key + '"}]',
    )
    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_WITNESS_QUORUM", "1")
    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_SIGNED_PINS_REQUIRED", "true")
    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_CONTINUITY_REQUIRED", "true" if continuity else "false")


def _observe_current(plane: ProductControlPlane, private_key: str, public_key: str, nonce: str):
    publication = plane.deployments.checkpoints.latest()
    assert publication is not None
    receipt = sign_deployment_checkpoint_pin(
        publication,
        private_key_b64=private_key,
        public_key_b64=public_key,
        witness_id="release-witness",
        independence_group="independent-a",
        observed_at=publication.published_at,
        nonce=nonce,
    )
    return plane.deployment_checkpoint_pins.observe(receipt)


def test_authorization_does_not_mutate_bound_root_but_release_activation_does(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    before = plane.system_root()
    before_components = {row["name"]: row["sha256"] for row in before["components"]}

    prepared = plane.deployments.prepare(_deployment())
    after_prepare = plane.system_root()
    assert prepared.authorization.system_root_sha256 == before["root_sha256"]
    assert after_prepare["root_sha256"] == before["root_sha256"]

    executed = plane.deployments.execute(prepared.authorization.id, prepared.plan)
    after_execute = plane.system_root()
    after_components = {row["name"]: row["sha256"] for row in after_execute["components"]}

    assert executed.resumed is False
    assert after_execute["root_sha256"] != before["root_sha256"]
    assert before_components["deployments"] != after_components["deployments"]
    assert plane.deployments.status()["release_backend"]["releases"] == 1

    replay = plane.deployments.execute(prepared.authorization.id, prepared.plan)
    assert replay.resumed is True
    assert replay.release.release_id == executed.release.release_id
    assert plane.deployments.status()["release_backend"]["releases"] == 1


def test_required_checkpoint_witness_blocks_prepare_until_current_head_is_pinned(tmp_path, monkeypatch):
    private_key, public_key = _keypair()
    _configure_required_witness(monkeypatch, public_key)
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)

    assurance = plane.assurance_report()
    assert assurance["posture"] == "blocked"
    assert any(
        row["id"] == "deployment.checkpoint-witness-current-quorum" and row["passed"] is False
        for row in assurance["invariants"]
    )
    with pytest.raises(DeploymentGatewayError, match="preflight blocked authorization"):
        plane.deployments.prepare(_deployment())

    root_before = plane.system_root()["root_sha256"]
    _observe_current(plane, private_key, public_key, "genesis")
    assert plane.system_root()["root_sha256"] == root_before
    assert plane.assurance_report()["hard_failures"] == 0
    prepared = plane.deployments.prepare(_deployment())
    assert prepared.authorization.id


def test_continuous_witness_policy_requires_new_authorization_checkpoint_before_execute(tmp_path, monkeypatch):
    private_key, public_key = _keypair()
    _configure_required_witness(monkeypatch, public_key, continuity=True)
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)

    _observe_current(plane, private_key, public_key, "genesis")
    assert plane.deployment_checkpoint_pins.requirement_satisfied() is True
    prepared = plane.deployments.prepare(_deployment("release-artifact-v2"))

    # Authorization issuance is root-neutral but advances checkpoint evidence. The new
    # current publication must be independently witnessed before the side effect.
    assert plane.deployment_checkpoint_pins.requirement_satisfied() is False
    blocked = plane.assurance_report()
    assert blocked["posture"] == "blocked"
    with pytest.raises(DeploymentGatewayError, match="fresh deployment preflight no longer authorizes deployment"):
        plane.deployments.execute(prepared.authorization.id, prepared.plan)

    root_before_pin = plane.system_root()["root_sha256"]
    _observe_current(plane, private_key, public_key, "authorization-checkpoint")
    assert plane.system_root()["root_sha256"] == root_before_pin
    witness = plane.deployment_checkpoint_pins.status()
    assert witness["requirement_satisfied"] is True
    assert witness["trust_frontier"]["continuity_ready"] is True
    assert plane.assurance_report()["hard_failures"] == 0

    executed = plane.deployments.execute(prepared.authorization.id, prepared.plan)
    assert executed.release.artifact == "release-artifact-v2"
    assert plane.deployments.status()["release_backend"]["releases"] == 1
