from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.security.data_deletion import (
    DataDeletionError,
    DeletionRequest,
    DeletionTombstone,
    assess_deletion_evidence,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request() -> DeletionRequest:
    return DeletionRequest(
        request_id="delete-1",
        target_refs=("record-a", "record-b"),
        required_surfaces=("primary", "replica", "index", "cache", "artifact", "backup"),
        reason_code="user-request",
        requested_at_ns=100,
    )


def _tombstone(
    target: str,
    surface: str,
    *,
    tombstone_id: str | None = None,
    request_id: str = "delete-1",
    deleted_at_ns: int = 150,
) -> DeletionTombstone:
    return DeletionTombstone(
        tombstone_id=tombstone_id or f"ts-{target}-{surface}",
        request_id=request_id,
        target_ref=target,
        surface=surface,
        source_digest=_sha(f"{target}:{surface}"),
        deleted_at_ns=deleted_at_ns,
    )


def test_deletion_request_canonicalizes_scope() -> None:
    request = DeletionRequest(
        request_id="delete-1",
        target_refs=("record-b", "record-a", "record-a"),
        required_surfaces=("replica", "primary", "replica"),
        reason_code="user-request",
        requested_at_ns=100,
    )

    assert request.target_refs == ("record-a", "record-b")
    assert request.required_surfaces == ("primary", "replica")
    assert len(request.digest) == 64


def test_complete_deletion_evidence_requires_every_target_surface_pair() -> None:
    request = _request()
    tombstones = tuple(
        _tombstone(target, surface)
        for target in request.target_refs
        for surface in request.required_surfaces
    )

    evidence = assess_deletion_evidence(
        evidence_id="evidence-complete",
        request=request,
        tombstones=reversed(tombstones),
        assessed_at_ns=200,
    )

    assert evidence.coverage_complete is True
    assert evidence.missing_pairs == ()
    assert len(evidence.covered_pairs) == (
        len(request.target_refs) * len(request.required_surfaces)
    )
    assert evidence.external_side_effects is False
    assert len(evidence.digest) == 64


def test_partial_deletion_evidence_reports_exact_missing_pairs() -> None:
    request = DeletionRequest(
        request_id="delete-1",
        target_refs=("record-a",),
        required_surfaces=("primary", "backup"),
        reason_code="user-request",
        requested_at_ns=100,
    )

    evidence = assess_deletion_evidence(
        evidence_id="evidence-partial",
        request=request,
        tombstones=(_tombstone("record-a", "primary"),),
        assessed_at_ns=200,
    )

    assert evidence.coverage_complete is False
    assert evidence.covered_pairs == (("record-a", "primary"),)
    assert evidence.missing_pairs == (("record-a", "backup"),)


def test_deletion_evidence_is_deterministic_across_tombstone_order() -> None:
    request = DeletionRequest(
        request_id="delete-1",
        target_refs=("record-a",),
        required_surfaces=("primary", "backup"),
        reason_code="user-request",
        requested_at_ns=100,
    )
    rows = (
        _tombstone("record-a", "primary"),
        _tombstone("record-a", "backup"),
    )

    first = assess_deletion_evidence(
        evidence_id="evidence-stable",
        request=request,
        tombstones=rows,
        assessed_at_ns=200,
    )
    second = assess_deletion_evidence(
        evidence_id="evidence-stable",
        request=request,
        tombstones=reversed(rows),
        assessed_at_ns=200,
    )

    assert first == second
    assert first.digest == second.digest


def test_tombstone_must_block_resurrection() -> None:
    with pytest.raises(DataDeletionError, match="block resurrection"):
        DeletionTombstone(
            tombstone_id="ts-bad",
            request_id="delete-1",
            target_ref="record-a",
            surface="backup",
            source_digest=_sha("record-a:backup"),
            deleted_at_ns=150,
            resurrection_blocked=False,
        )


def test_assessment_rejects_out_of_scope_tombstones() -> None:
    request = DeletionRequest(
        request_id="delete-1",
        target_refs=("record-a",),
        required_surfaces=("primary",),
        reason_code="user-request",
        requested_at_ns=100,
    )

    with pytest.raises(DataDeletionError, match="outside declared deletion scope"):
        assess_deletion_evidence(
            evidence_id="evidence-outside",
            request=request,
            tombstones=(_tombstone("record-a", "backup"),),
            assessed_at_ns=200,
        )


def test_assessment_rejects_request_identity_mismatch() -> None:
    with pytest.raises(DataDeletionError, match="request identity mismatch"):
        assess_deletion_evidence(
            evidence_id="evidence-wrong-request",
            request=_request(),
            tombstones=(
                _tombstone(
                    "record-a",
                    "primary",
                    request_id="delete-other",
                ),
            ),
            assessed_at_ns=200,
        )


def test_assessment_rejects_duplicate_target_surface_evidence() -> None:
    first = _tombstone(
        "record-a",
        "primary",
        tombstone_id="ts-1",
    )
    second = _tombstone(
        "record-a",
        "primary",
        tombstone_id="ts-2",
    )

    with pytest.raises(DataDeletionError, match="duplicate tombstone"):
        assess_deletion_evidence(
            evidence_id="evidence-duplicate",
            request=_request(),
            tombstones=(first, second),
            assessed_at_ns=200,
        )


def test_assessment_rejects_duplicate_tombstone_ids() -> None:
    first = _tombstone(
        "record-a",
        "primary",
        tombstone_id="same-id",
    )
    second = _tombstone(
        "record-a",
        "replica",
        tombstone_id="same-id",
    )

    with pytest.raises(DataDeletionError, match="IDs must be unique"):
        assess_deletion_evidence(
            evidence_id="evidence-duplicate-id",
            request=_request(),
            tombstones=(first, second),
            assessed_at_ns=200,
        )


def test_assessment_rejects_temporal_impossibilities() -> None:
    request = _request()

    with pytest.raises(DataDeletionError, match="predates deletion request"):
        assess_deletion_evidence(
            evidence_id="evidence-old-tombstone",
            request=request,
            tombstones=(
                _tombstone(
                    "record-a",
                    "primary",
                    deleted_at_ns=99,
                ),
            ),
            assessed_at_ns=200,
        )

    with pytest.raises(DataDeletionError, match="predates tombstone"):
        assess_deletion_evidence(
            evidence_id="evidence-old-assessment",
            request=request,
            tombstones=(
                _tombstone(
                    "record-a",
                    "primary",
                    deleted_at_ns=150,
                ),
            ),
            assessed_at_ns=149,
        )


def test_deletion_contracts_reject_empty_scope_and_bad_digest() -> None:
    with pytest.raises(DataDeletionError, match="target_ref must be non-empty"):
        DeletionRequest(
            request_id="delete-1",
            target_refs=(),
            required_surfaces=("primary",),
            reason_code="user-request",
            requested_at_ns=100,
        )

    with pytest.raises(DataDeletionError, match="sha256"):
        DeletionTombstone(
            tombstone_id="ts-bad-digest",
            request_id="delete-1",
            target_ref="record-a",
            surface="primary",
            source_digest="not-a-digest",
            deleted_at_ns=150,
        )
