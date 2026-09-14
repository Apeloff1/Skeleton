import hashlib
import json

import pytest

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
    """Minimal control plane whose root includes activated release state."""

    def __init__(self):
        self.root_seed = "c" * 64
        self.allowed = True
        self.gateway: DeploymentGateway | None = None

    def bind(self, gateway: DeploymentGateway) -> None:
        self.gateway = gateway

    def system_root(self):
        release_head = self.gateway.releases.status()["head_set_sha256"] if self.gateway is not None else ""
        digest = hashlib.sha256(f"{self.root_seed}\0{release_head}".encode("utf-8")).hexdigest()
        return {"root_sha256": digest}

    def assurance_report(self):
        if self.allowed:
            return _assurance()
        return {"posture": "blocked", "hard_failures": 1, "warnings": 0, "attestation_sha256": "d" * 64}

    def epistemic_finality(self):
        return _trust()


def _gateway(tmp_path):
    plane = StablePlane()
    gateway = DeploymentGateway(tmp_path, control_plane=plane)
    plane.bind(gateway)
    return plane, gateway


def _payload(artifact="artifact-v1"):
    return {"target": "product-runtime", "environment": "staging", "strategy": "rolling", "artifact": artifact}


def test_prepare_execute_and_idempotent_release_replay(tmp_path):
    plane, gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_payload())
    first = gateway.execute(prepared.authorization.id, prepared.plan)
    second = gateway.execute(prepared.authorization.id, prepared.plan)

    assert first.resumed is False
    assert second.resumed is True
    assert first.release == second.release
    assert first.transition_receipt == second.transition_receipt
    assert first.transition_receipt.pre_system_root_sha256 != first.transition_receipt.post_system_root_sha256
    assert gateway.authorizations.status()["consumed"] == 1
    assert gateway.releases.status()["releases"] == 1
    assert gateway.receipts.status()["receipts"] == 1
    status = gateway.status()
    assert status["verified"] is True
    assert status["independently_verifiable"] is True
    assert status["portability"] == {
        "proof_version": 3,
        "completed_releases": 1,
        "fully_portable": 1,
        "legacy_or_incomplete": 0,
        "legacy_preflight_hash_only": 0,
        "legacy_plan_hash_only": 0,
        "incomplete_transition_evidence": 0,
        "all_completed_releases_portable": True,
    }
    proof = gateway.portable_proof(prepared.authorization.id)
    assert proof.plan == prepared.plan
    assert proof.plan_sha256 == first.release.plan_sha256
    current = gateway.releases.current(target="product-runtime", environment="staging")
    assert current is not None and current.release_id == first.release.release_id


def test_root_or_plan_mutation_blocks_before_release_side_effect(tmp_path):
    plane, gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_payload())
    plane.root_seed = "e" * 64
    with pytest.raises(DeploymentGatewayError, match="root changed"):
        gateway.execute(prepared.authorization.id, prepared.plan)
    assert gateway.releases.status()["releases"] == 0

    plane.root_seed = "c" * 64
    second = gateway.prepare(_payload())
    with pytest.raises(DeploymentGatewayError, match="authorized plan"):
        gateway.execute(second.authorization.id, _payload("artifact-v2"))
    assert gateway.releases.status()["releases"] == 0


def test_consumed_but_not_activated_authorization_is_explicit_evidence_gap_until_recovered(tmp_path):
    plane, gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_payload())
    consumption = gateway.authorizations.consume(
        prepared.authorization.id,
        current_system_root_sha256=prepared.authorization.system_root_sha256,
        plan=prepared.plan,
    )
    assert consumption.authorization_id == prepared.authorization.id
    assert gateway.releases.status()["releases"] == 0
    incomplete = gateway.status()
    assert incomplete["verified"] is False
    assert incomplete["independently_verifiable"] is False
    assert {row["kind"] for row in incomplete["evidence_gaps"]} == {"consumption_without_release"}

    resumed = gateway.execute(prepared.authorization.id, prepared.plan)
    assert resumed.resumed is True
    assert gateway.releases.status()["releases"] == 1
    assert gateway.status()["verified"] is True
    assert gateway.status()["independently_verifiable"] is True

    prepared2 = gateway.prepare(_payload("artifact-v2"))
    gateway.authorizations.consume(
        prepared2.authorization.id,
        current_system_root_sha256=prepared2.authorization.system_root_sha256,
        plan=prepared2.plan,
    )
    plane.root_seed = "f" * 64
    with pytest.raises(DeploymentGatewayError, match="root changed"):
        gateway.execute(prepared2.authorization.id, prepared2.plan)
    assert any(row["kind"] == "consumption_without_release" for row in gateway.status()["evidence_gaps"])


def test_fresh_assurance_failure_blocks_execution_even_when_root_is_unchanged(tmp_path):
    plane, gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_payload())
    plane.allowed = False
    with pytest.raises(DeploymentGatewayError, match="no longer authorizes"):
        gateway.execute(prepared.authorization.id, prepared.plan)
    assert gateway.authorizations.consumption(prepared.authorization.id) is None


def test_release_history_tamper_fails_closed(tmp_path):
    plane, gateway = _gateway(tmp_path)
    prepared = gateway.prepare(_payload())
    executed = gateway.execute(prepared.authorization.id, prepared.plan)
    channel = next(path for path in (tmp_path / "releases").iterdir() if path.is_dir())
    history = channel / "releases.jsonl"
    row = json.loads(history.read_text(encoding="utf-8").strip())
    row["artifact"] = "tampered"
    history.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="release history hash mismatch"):
        gateway.releases.current(target=executed.release.target, environment=executed.release.environment)
