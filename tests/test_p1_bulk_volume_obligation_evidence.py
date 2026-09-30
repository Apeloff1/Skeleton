from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import pytest

from scripts.build_p1_bulk_volume_obligation_evidence import (
    CATEGORY,
    EXPECTED_CANDIDATES,
    EXPECTED_CANDIDATE_GAPS,
    EXPECTED_CANDIDATE_RISKS,
    EXPECTED_EXISTING_BINDINGS,
    EXPECTED_PRIMARY_VOLUMES,
    EXPECTED_VOLUME_GAPS,
    EXPECTED_VOLUME_OBLIGATIONS,
    EXPECTED_VOLUME_RISKS,
    BulkVolumeEvidenceError,
    build_bulk_volume_evidence,
)
from scripts.reconcile_p1_risk_evidence import MASTER, REGISTRY, ROOT

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_bulk_volume_evidence(ROOT, expected_head=TEST_HEAD)


def test_bulk_volume_inventory_covers_the_full_primary_frontier() -> None:
    report = _report()

    assert report["covered_volume_count"] == EXPECTED_PRIMARY_VOLUMES == 107
    assert report["covered_obligation_count"] == EXPECTED_VOLUME_OBLIGATIONS == 489
    assert report["covered_risk_count"] == EXPECTED_VOLUME_RISKS == 281
    assert report["covered_gap_count"] == EXPECTED_VOLUME_GAPS == 208
    assert report["already_bound_count"] == EXPECTED_EXISTING_BINDINGS == 34
    assert report["candidate_binding_count"] == EXPECTED_CANDIDATES == 455
    assert report["candidate_risk_count"] == EXPECTED_CANDIDATE_RISKS == 269
    assert report["candidate_gap_count"] == EXPECTED_CANDIDATE_GAPS == 186
    assert report["adversarial_axis_count"] == 0


def test_bulk_candidates_preserve_governance_authority_boundaries() -> None:
    report = _report()

    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["lowers_severity"] is False
    assert report["clears_source_obligations"] is False
    assert report["promotes_maturity"] is False

    candidates = [row for row in report["records"] if not row["binding_present"]]
    assert len(candidates) == 455
    assert all(row["recommended_severity"] == "high" for row in candidates)
    assert all(row["recommended_disposition"] == "evidence" for row in candidates)
    assert all(row["accepted_risk"] is False for row in candidates)
    assert all(row["candidate_evidence_ref"]["category"] == CATEGORY for row in candidates)
    assert all(
        row["candidate_evidence_ref"]["digest"] == row["packet_digest"]
        for row in candidates
    )
    assert all(
        row["candidate_evidence_ref"]["source"].endswith(":" + TEST_HEAD)
        for row in candidates
    )


def test_every_primary_volume_has_materialized_tracked_evidence_surfaces() -> None:
    report = _report()
    volumes = report["volume_evidence"]

    assert len(volumes) == 107
    assert report["unique_materialized_surface_count"] > 100

    for volume_key, packet in volumes.items():
        assert packet["accountability_id"] == "ACC-" + volume_key
        assert packet["lane_id"].startswith("P1-L")
        assert packet["required_evidence_modes"]
        assert packet["implementation_surfaces"]
        assert packet["test_surfaces"]
        assert packet["evaluation_surfaces"]
        assert len(packet["volume_packet_digest"]) == 64

        for group in (
            packet["implementation_surfaces"],
            packet["test_surfaces"],
            packet["evaluation_surfaces"],
        ):
            for surface in group:
                assert surface["tracked_entry_count"] >= 1
                assert len(surface["tracked_manifest_digest"]) == 64
                assert surface["kind"] in {"file", "directory", "pathspec"}

        provenance = packet["provenance_classes"]
        assert provenance["git_head"] >= 1
        assert provenance["github_actions_job"] >= 1
        assert provenance["github_actions_run"] >= 1
        assert provenance["github_commit"] >= 1


def test_bulk_records_remain_bound_to_canonical_source_statements() -> None:
    report = _report()
    master = json.loads((ROOT / MASTER).read_text(encoding="utf-8"))
    by_key = {row["key"]: row for row in master["volumes"]}

    for record in report["records"]:
        volume = by_key[record["volume_key"]]
        source = volume["risks"] if record["kind"] == "risk" else volume["gaps"]
        assert record["statement"] in source
        assert record["owner_id"] == "ACC-" + record["volume_key"]
        assert len(record["obligation_digest"]) == 64


def test_compiler_does_not_mutate_governed_registry() -> None:
    before = (ROOT / REGISTRY).read_bytes()
    _report()
    after = (ROOT / REGISTRY).read_bytes()
    assert before == after


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_invalid_exact_head_fails_closed(head: str) -> None:
    with pytest.raises(
        BulkVolumeEvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_bulk_volume_evidence(ROOT, expected_head=head)
