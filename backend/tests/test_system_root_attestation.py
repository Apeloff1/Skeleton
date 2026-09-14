from core.product_control_plane import ProductControlPlane
from core.system_root_attestation import build_root_attestation, diff_root_attestations, verify_root_attestation


def test_root_attestation_is_deterministic_and_order_independent():
    left = build_root_attestation({"policy": {"v": 1}, "audit": {"head": "a"}})
    right = build_root_attestation({"audit": {"head": "a"}, "policy": {"v": 1}})
    assert left == right
    assert len(left.root_sha256) == 64
    assert verify_root_attestation(left, {"policy": {"v": 1}, "audit": {"head": "a"}}) is True


def test_component_diff_localizes_change():
    before = build_root_attestation({"policy": {"v": 1}, "audit": {"head": "a"}})
    after = build_root_attestation({"policy": {"v": 1}, "audit": {"head": "b"}})
    diff = diff_root_attestations(before, after)
    assert set(diff) == {"audit"}
    assert before.root_sha256 != after.root_sha256


def test_control_plane_root_changes_when_durable_evidence_changes(tmp_path):
    plane = ProductControlPlane(tmp_path)
    before = plane.system_root()
    plane.admit(
        capability_id="studio", domain="studio", action="build.submit",
        principal="creator", actor_weight=0, payload={"target": "web"},
    )
    after = plane.system_root()
    assert before["root_sha256"] != after["root_sha256"]
    before_map = {item["name"]: item["sha256"] for item in before["components"]}
    after_map = {item["name"]: item["sha256"] for item in after["components"]}
    assert before_map["policy"] == after_map["policy"]
    assert before_map["lifecycle"] != after_map["lifecycle"]
    assert before_map["audit"] != after_map["audit"]
    assert before_map["outbox"] != after_map["outbox"]


def test_system_root_includes_all_critical_evidence_domains(tmp_path):
    root = ProductControlPlane(tmp_path).system_root()
    names = {item["name"] for item in root["components"]}
    assert names == {
        "policy", "executors", "readiness", "lifecycle", "audit", "outbox", "receipts", "kernel",
        "curiosity_runtime", "epistemic_root", "epistemic_transparency", "epistemic_gossip",
    }
