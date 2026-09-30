from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_p1_gap_closure_plan.py"
REGISTRY = ROOT / "machine/p1_risk_evidence_bindings.json"
MASTER = ROOT / "machine/ai_master_plan.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_p1_gap_closure_plan",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gap_closure_plan_matches_canonical_target_frontier() -> None:
    module = _module()
    report = module.build_gap_closure_plan(ROOT)

    assert report["gap_blocked_volume_count"] == 84
    assert report["gap_obligation_count"] == 168
    assert report["target_counts"] == {
        "hardened": {
            "volume_count": 70,
            "gap_obligation_count": 140,
        },
        "production": {
            "volume_count": 14,
            "gap_obligation_count": 28,
        },
    }
    assert report["lane_gap_obligation_counts"] == {
        "P1-L1": 30,
        "P1-L2": 54,
        "P1-L4": 16,
        "P1-L5": 28,
        "P1-L6": 40,
    }


def test_gap_closure_plan_is_non_authoritative() -> None:
    module = _module()
    report = module.build_gap_closure_plan(ROOT)

    assert report["non_authoritative"] is True
    assert report["mutates_gap_state"] is False
    assert report["mutates_risk_registry"] is False
    assert report["creates_bindings"] is False
    assert report["creates_accepted_risk"] is False
    assert report["human_signature_required_for_accepted_risk"] is True

    for packet in report["packets"]:
        assert packet["non_authoritative"] is True
        assert packet["mutates_gap_state"] is False
        assert packet["mutates_risk_registry"] is False
        assert packet["creates_bindings"] is False
        assert packet["creates_accepted_risk"] is False


def test_gap_obligations_are_unique_and_exactly_joined_to_volumes() -> None:
    module = _module()
    report = module.build_gap_closure_plan(ROOT)

    obligation_ids = []
    for packet in report["packets"]:
        assert packet["gap_count"] == len(packet["obligations"])
        assert packet["gap_count"] > 0
        assert packet["mapped_task_ids"]
        assert len(packet["packet_digest"]) == 64
        for obligation in packet["obligations"]:
            obligation_ids.append(obligation["obligation_id"])
            assert obligation["source_ref"].startswith(
                packet["volume_key"] + ":gap:"
            )
            assert obligation["blocking_by_default"] is True
            assert obligation["default_severity"] == "high"
            assert obligation["statement"]
            assert len(obligation["obligation_digest"]) == 64
            assert len(obligation["packet_digest"]) == 64
            assert obligation["available_evidence_sources"]

    assert len(obligation_ids) == 168
    assert len(set(obligation_ids)) == 168


def test_current_registry_preserves_existing_bindings_as_non_authoritative() -> None:
    module = _module()
    report = module.build_gap_closure_plan(ROOT)

    assert report["bound_gap_obligation_count"] == 12
    assert report["unbound_gap_obligation_count"] == 156

    for packet in report["packets"]:
        assert packet["bound_gap_count"] == sum(1 for obligation in packet["obligations"] if obligation["binding_present"])
        assert packet["unbound_gap_count"] == packet["gap_count"] - packet["bound_gap_count"]
        assert all(
            obligation["binding_present"] in {True, False}
            for obligation in packet["obligations"]
        )
    assert sum(
        1
        for packet in report["packets"]
        for obligation in packet["obligations"]
        if obligation["binding_present"]
    ) == 12


def test_resolution_paths_preserve_evidence_or_human_acceptance_boundary() -> None:
    module = _module()
    report = module.build_gap_closure_plan(ROOT)

    for packet in report["packets"]:
        for obligation in packet["obligations"]:
            paths = {
                row["kind"]: row
                for row in obligation["resolution_paths"]
            }
            assert set(paths) == {
                "evidence_binding_review",
                "human_signed_accepted_risk_review",
            }

            evidence = paths["evidence_binding_review"]
            assert evidence["allowed"] is True
            assert evidence["requires_materialized_evidence_refs"] is True
            assert evidence["requires_owner"] is True
            assert evidence["requires_classified_severity"] is True
            assert evidence["requires_review_at"] is True
            assert evidence["creates_binding"] is False

            accepted = paths["human_signed_accepted_risk_review"]
            assert accepted["allowed"] is True
            assert accepted["allowed_severities"] == ["high", "critical"]
            assert accepted["human_signer_required"] is True
            assert accepted["identity_bound_signature_required"] is True
            assert accepted["review_at_required"] is True
            assert accepted["expiry_required"] is True
            assert accepted["creates_acceptance"] is False


def test_gap_closure_planning_never_mutates_canonical_sources() -> None:
    module = _module()
    registry_before = REGISTRY.read_bytes()
    master_before = MASTER.read_bytes()

    first = module.build_gap_closure_plan(ROOT)
    second = module.build_gap_closure_plan(ROOT)

    assert first == second
    assert REGISTRY.read_bytes() == registry_before
    assert MASTER.read_bytes() == master_before
    assert len(first["report_digest"]) == 64


def test_gap_plan_never_emits_signer_identity_fields() -> None:
    module = _module()
    report = module.build_gap_closure_plan(ROOT)

    forbidden = {
        "signer_id",
        "signer_type",
        "signature_method",
        "signature_ref",
        "accepted_at",
        "signed_at_utc",
    }
    for packet in report["packets"]:
        assert not (forbidden & set(packet))
        for obligation in packet["obligations"]:
            assert not (forbidden & set(obligation))
            for path in obligation["resolution_paths"]:
                assert not (forbidden & set(path))
