import json

import pytest

from core.deployment_authorization import DeploymentAuthorizationError
from core.deployment_gateway import DeploymentGateway, DeploymentGatewayError


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
            "signed_independence_groups": 0,
            "required_groups": 3,
            "max_age_seconds": 3600,
            "quorum_capable": True,
            "signed_quorum_capable": False,
            "finality_required": True,
            "signed_finality_required": False,
        },
        "gossip": {"split_views": 0, "rollbacks": 0, "healthy": True},
        "witnesses": {"equivocations": 0, "healthy": True},
        "signed_witnesses": {"equivocations": 0, "healthy": True},
        "current_head": {"current_tree_size": 8, "current_root_sha256": "b" * 64, "finalized": True},
    }


class StablePlane:
    def __init__(self):
        self.root = "c" * 64
        self.allowed = True

    def system_root(self):
        return {"root_sha256": self.root}

    def assurance_report(self):
        if self.allowed:
            return _assurance()
        return {"posture": "blocked", "hard_failures": 1, "warnings": 0, "attestation_sha256": "d" * 64}

    def epistemic_finality(self):
        return _trust()


def _payload(artifact="artifact-v1"):
    return {"target": "product-runtime", "environment": "staging", "strategy": "rolling", "artifact": artifact}


def test_prepare_execute_and_idempotent_release_replay(tmp_path):
    plane = StablePlane(); gateway = DeploymentGateway(tmp_path, control_plane=plane)
    prepared = gateway.prepare(_payload())
    first = gateway.execute(prepared.authorization.id, prepared.plan)
    second = gateway.execute(prepared.authorization.id, prepared.plan)

    assert first.resumed is False
    assert second.resumed is True
    assert first.release == second.release
    assert gateway.authorizations.status()["consumed"] == 1
    assert gateway.releases.status()["releases"] == 1
    current = gateway.releases.current(target="product-runtime", environment="staging")
    assert current is not None and current.release_id == first.release.release_id


def test_root_or_plan_mutation_blocks_before_release_side_effect(tmp_path):
    plane = StablePlane(); gateway = DeploymentGateway(tmp_path, control_plane=plane)
    prepared = gateway.prepare(_payload())
    plane.root = "e" * 64
    with pytest.raises(DeploymentGatewayError, match="root changed"):
        gateway.execute(prepared.authorization.id, prepared.plan)
    assert gateway.releases.status()["releases"] == 0

    plane.root = "c" * 64
    second = gateway.prepare(_payload())
    with pytest.raises(DeploymentGatewayError, match="authorized plan"):
        gateway.execute(second.authorization.id, _payload("artifact-v2"))
    assert gateway.releases.status()["releases"] == 0


def test_consumed_but_not_activated_authorization_can_resume_only_under_same_safe_root(tmp_path):
    plane = StablePlane(); gateway = DeploymentGateway(tmp_path, control_plane=plane)
    prepared = gateway.prepare(_payload())
    consumption = gateway.authorizations.consume(
        prepared.authorization.id,
        current_system_root_sha256=prepared.authorization.system_root_sha256,
        plan=prepared.plan,
    )
    assert consumption.authorization_id == prepared.authorization.id
    assert gateway.releases.status()["releases"] == 0

    resumed = gateway.execute(prepared.authorization.id, prepared.plan)
    assert resumed.resumed is True
    assert gateway.releases.status()["releases"] == 1

    prepared2 = gateway.prepare(_payload("artifact-v2"))
    gateway.authorizations.consume(
        prepared2.authorization.id,
        current_system_root_sha256=prepared2.authorization.system_root_sha256,
        plan=prepared2.plan,
    )
    plane.root = "f" * 64
    with pytest.raises(DeploymentGatewayError, match="root changed"):
        gateway.execute(prepared2.authorization.id, prepared2.plan)


def test_fresh_assurance_failure_blocks_execution_even_when_root_is_unchanged(tmp_path):
    plane = StablePlane(); gateway = DeploymentGateway(tmp_path, control_plane=plane)
    prepared = gateway.prepare(_payload())
    plane.allowed = False
    with pytest.raises(DeploymentGatewayError, match="no longer authorizes"):
        gateway.execute(prepared.authorization.id, prepared.plan)
    assert gateway.authorizations.consumption(prepared.authorization.id) is None


def test_release_history_tamper_fails_closed(tmp_path):
    plane = StablePlane(); gateway = DeploymentGateway(tmp_path, control_plane=plane)
    prepared = gateway.prepare(_payload())
    executed = gateway.execute(prepared.authorization.id, prepared.plan)
    channel = next(path for path in (tmp_path / "releases").iterdir() if path.is_dir())
    history = channel / "releases.jsonl"
    row = json.loads(history.read_text(encoding="utf-8").strip())
    row["artifact"] = "tampered"
    history.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="release history hash mismatch"):
        gateway.releases.current(target=executed.release.target, environment=executed.release.environment)
