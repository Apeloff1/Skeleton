from dataclasses import replace

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY
from core.capability_readiness import evaluate_readiness, verify_readiness
from core.product_control_plane import ProductControlPlane


def test_default_control_plane_readiness_is_evidence_backed(tmp_path):
    plane = ProductControlPlane(tmp_path)
    report = plane.readiness_report()
    assert report["canonical_actions"] == 21
    assert report["ready_actions"] == 12
    assert report["ready_pct"] == 57.1
    assert report["governed_unbound"] == 9
    assert report["unsafe_actions"] == 0
    assert report["policy_gaps"] == 0
    assert len(report["attestation_sha256"]) == 64


def test_readiness_requires_policy_executor_and_provenance(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    policy = plane.policy.snapshot()
    report = evaluate_readiness(
        canonical_policy=CANONICAL_PRODUCT_POLICY,
        policy_domains=[{"domain": item.domain, "rules": [
            {"action": rule.action} for rule in item.rules
        ]} for item in policy.charters],
        executor_bindings=[],
        receipt_stats={"version": 2},
    )
    assert report.ready_actions == 0
    assert report.governed_unbound == 21
    assert verify_readiness(report) is True


def test_state_executor_without_replay_safety_is_unsafe(tmp_path):
    plane = ProductControlPlane(tmp_path)
    policy = plane.policy.snapshot()
    bindings = list(plane.executors.snapshot())
    target = next(item for item in bindings if item["action"] == "project.create")
    target["replay_safe"] = False
    report = evaluate_readiness(
        canonical_policy=CANONICAL_PRODUCT_POLICY,
        policy_domains=[{"domain": item.domain, "rules": [
            {"action": rule.action} for rule in item.rules
        ]} for item in policy.charters],
        executor_bindings=bindings,
        receipt_stats=plane.receipts.stats(),
    )
    row = next(item for item in report.actions if item.action == "project.create")
    assert row.state == "unsafe"
    assert "effect_not_replay_safe" in row.blockers


def test_readiness_attestation_detects_mutation(tmp_path):
    plane = ProductControlPlane(tmp_path)
    report = plane._readiness_model()
    assert verify_readiness(report) is True
    mutated = replace(report, ready_actions=report.ready_actions + 1)
    assert verify_readiness(mutated) is False
