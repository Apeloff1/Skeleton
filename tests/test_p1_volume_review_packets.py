from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_p1_volume_review_packets.py"
HEAD = "a" * 40


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_p1_volume_review_packets",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_review_packets_cover_exactly_blocked_primary_volumes() -> None:
    module = _module()
    manifest = module.build_packets(root=ROOT, commit_sha=HEAD)

    assert manifest["primary_volume_count"] == 107
    assert manifest["target_floor_eligible_count"] == 3
    assert manifest["review_packet_count"] == 104
    assert manifest["eligible_volume_keys"] == [
        "VOL-013",
        "VOL-014",
        "VOL-253",
    ]
    assert len(manifest["packet_volume_keys"]) == 104
    assert len(set(manifest["packet_volume_keys"])) == 104
    assert len(manifest["packets"]) == 104
    assert len(manifest["manifest_digest"]) == 64


def test_review_packets_bind_exact_head_and_evidence() -> None:
    module = _module()
    manifest = module.build_packets(root=ROOT, commit_sha=HEAD)

    assert manifest["source_commit"] == HEAD
    assert len(manifest["closure_ledger_digest"]) == 64

    for packet in manifest["packets"]:
        assert packet["source_commit"] == HEAD
        assert packet["mapped_task_ids"]
        assert packet["mapped_task_evidence_refs"]
        assert len(packet["evidence_digest"]) == 64
        assert len(packet["volume_metadata_digest"]) == 64
        assert len(packet["packet_digest"]) == 64
        assert all(
            not ref.startswith("planned:")
            for ref in packet["mapped_task_evidence_refs"]
        )


def test_review_packets_are_unsigned_and_non_authoritative() -> None:
    module = _module()
    manifest = module.build_packets(root=ROOT, commit_sha=HEAD)

    for field in (
        "non_authoritative",
        "signed",
        "applicable",
        "accountability_mutation_authority",
        "maturity_mutation_authority",
        "promotion_authority",
    ):
        expected = field == "non_authoritative"
        assert manifest[field] is expected

    for packet in manifest["packets"]:
        assert packet["signed"] is False
        assert packet["applicable"] is False
        assert packet["accountability_mutation_authority"] is False
        assert packet["maturity_mutation_authority"] is False
        assert packet["promotion_authority"] is False

        for review in (
            packet["implementation_review"],
            packet["verification_review"],
        ):
            assert review["review_state"] == "unsigned"
            assert review["signature_method"] is None
            assert review["signature_ref"] is None
            assert review["reviewer_id"] is None
            assert review["reviewed_at_utc"] is None
            assert review["application_authority"] is False


def test_review_order_preserves_independent_verification_boundary() -> None:
    module = _module()
    manifest = module.build_packets(root=ROOT, commit_sha=HEAD)

    for packet in manifest["packets"]:
        implementation = packet["implementation_review"]
        verification = packet["verification_review"]

        assert implementation["review_type"] == "implementation_signoff"
        assert implementation["required_role"] == "implementation_owner"
        assert implementation["independence_required"] is False
        assert implementation["prerequisite_actions"] == []

        assert (
            verification["review_type"]
            == "independent_verification_signoff"
        )
        assert verification["required_role"] == "independent_verifier"
        assert verification["independence_required"] is True
        assert "implementation_signoff" in verification[
            "prerequisite_actions"
        ]
        assert "accountability_maturity_status" in verification[
            "prerequisite_actions"
        ]


def test_hardened_and_production_packets_preserve_gap_blockers() -> None:
    module = _module()
    manifest = module.build_packets(root=ROOT, commit_sha=HEAD)

    rows = {
        packet["volume_key"]: packet
        for packet in manifest["packets"]
    }
    gap_rows = [
        packet
        for packet in manifest["packets"]
        if "resolve_volume_gaps" in packet["required_actions"]
    ]
    assert len(gap_rows) == 84

    for packet in gap_rows:
        assert packet["unresolved_gaps"]
        assert "resolve_volume_gaps" in packet[
            "verification_review"
        ]["prerequisite_actions"]

    assert "VOL-409" in rows
    assert rows["VOL-409"]["target_floor"] == "production"
    assert rows["VOL-409"]["unresolved_gaps"]


def test_review_packets_exclude_already_floor_eligible_volumes() -> None:
    module = _module()
    manifest = module.build_packets(root=ROOT, commit_sha=HEAD)

    packet_keys = set(manifest["packet_volume_keys"])
    assert {"VOL-013", "VOL-014", "VOL-253"}.isdisjoint(packet_keys)


@pytest.mark.parametrize(
    "value",
    (
        "",
        "A" * 40,
        "a" * 39,
        "a" * 41,
        "not-a-sha",
    ),
)
def test_review_packet_head_must_be_exact_git_sha(value: str) -> None:
    module = _module()

    with pytest.raises(
        module.ReviewPacketError,
        match="40-character git SHA",
    ):
        module.build_packets(root=ROOT, commit_sha=value)


def test_packet_build_does_not_mutate_canonical_sources() -> None:
    module = _module()
    paths = (
        ROOT / "machine/ai_master_plan.json",
        ROOT / "machine/ai_build_accountability.json",
        ROOT / "machine/ai_p1_task_backlog.json",
        ROOT / "machine/ai_p1_execution_map.json",
    )
    before = [path.read_bytes() for path in paths]

    module.build_packets(root=ROOT, commit_sha=HEAD)

    after = [path.read_bytes() for path in paths]
    assert before == after
