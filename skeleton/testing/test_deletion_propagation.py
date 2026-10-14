from __future__ import annotations

import hashlib

import pytest

from skeleton.security.deletion_propagation import (
    DeletionPropagationConflict,
    DeletionResurrectionDenied,
    SQLiteDeletionPropagationAuthority,
)


DIGEST = hashlib.sha256(b"subject-payload-v1").hexdigest()
SURFACES = ("memory", "retrieval-index", "artifact-cache", "backup-catalog")


def _issue(
    authority: SQLiteDeletionPropagationAuthority,
    *,
    request_id: str = "delete-001",
    expected_previous_generation: int | None = None,
):
    return authority.issue(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        request_id=request_id,
        source_digest=DIGEST,
        required_surfaces=SURFACES,
        issued_at_ns=100,
        authority_ref="privacy-authority:tenant-a",
        expected_previous_generation=expected_previous_generation,
    )


def test_tombstone_is_restart_safe_and_generation_monotonic(tmp_path) -> None:
    path = tmp_path / "deletion.sqlite3"
    first = SQLiteDeletionPropagationAuthority(path)
    tombstone = _issue(first)
    assert tombstone.generation == 1
    first.close()

    reopened = SQLiteDeletionPropagationAuthority(path)
    recovered = reopened.latest(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
    )
    assert recovered == tombstone
    second = reopened.issue(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        request_id="delete-002",
        source_digest=hashlib.sha256(b"subject-payload-v2").hexdigest(),
        required_surfaces=SURFACES,
        issued_at_ns=200,
        authority_ref="privacy-authority:tenant-a",
        expected_previous_generation=1,
    )
    assert second.generation == 2


def test_request_replay_is_stable_and_conflicting_replay_fails(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "replay.sqlite3")
    first = _issue(authority)
    again = _issue(authority)
    assert again == first

    with pytest.raises(
        DeletionPropagationConflict,
        match="different deletion intent",
    ):
        authority.issue(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            request_id="delete-001",
            source_digest=hashlib.sha256(b"different").hexdigest(),
            required_surfaces=SURFACES,
            issued_at_ns=100,
            authority_ref="privacy-authority:tenant-a",
        )


def test_acknowledgements_must_match_latest_generation_and_scope(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "acks.sqlite3")
    tombstone = _issue(authority)
    ack = authority.acknowledge(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        generation=tombstone.generation,
        surface="memory",
        evidence_ref="memory:purge:receipt-1",
        acknowledged_at_ns=110,
    )
    assert ack.surface == "memory"

    with pytest.raises(
        DeletionPropagationConflict,
        match="outside tombstone propagation scope",
    ):
        authority.acknowledge(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            generation=1,
            surface="unknown-cache",
            evidence_ref="unknown:receipt",
            acknowledged_at_ns=111,
        )

    authority.issue(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        request_id="delete-002",
        source_digest=hashlib.sha256(b"second").hexdigest(),
        required_surfaces=SURFACES,
        issued_at_ns=200,
        authority_ref="privacy-authority:tenant-a",
        expected_previous_generation=1,
    )
    with pytest.raises(
        DeletionPropagationConflict,
        match="stale or future",
    ):
        authority.acknowledge(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            generation=1,
            surface="retrieval-index",
            evidence_ref="index:old-generation",
            acknowledged_at_ns=210,
        )


def test_conflicting_surface_acknowledgement_fails_closed(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "ack-conflict.sqlite3")
    _issue(authority)
    authority.acknowledge(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        generation=1,
        surface="memory",
        evidence_ref="memory:purge:receipt-1",
        acknowledged_at_ns=110,
    )
    with pytest.raises(
        DeletionPropagationConflict,
        match="different evidence",
    ):
        authority.acknowledge(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            generation=1,
            surface="memory",
            evidence_ref="memory:purge:receipt-forged",
            acknowledged_at_ns=110,
        )


def test_completion_requires_every_declared_surface(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "coverage.sqlite3")
    _issue(authority)
    for index, surface in enumerate(SURFACES[:-1], start=1):
        authority.acknowledge(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            generation=1,
            surface=surface,
            evidence_ref=f"{surface}:purged",
            acknowledged_at_ns=100 + index,
        )
    partial = authority.status(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
    )
    assert partial is not None
    assert partial.complete is False
    assert partial.missing_surfaces == ("backup-catalog",)

    authority.acknowledge(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        generation=1,
        surface="backup-catalog",
        evidence_ref="backup-catalog:tombstoned",
        acknowledged_at_ns=120,
    )
    complete = authority.status(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
    )
    assert complete is not None
    assert complete.complete is True
    evidence = authority.completion_evidence(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
    )
    assert evidence["complete"] is True
    assert evidence["missing_surfaces"] == []


@pytest.mark.parametrize("source_generation", [0, 1])
def test_stale_cache_or_restore_cannot_resurrect_deleted_subject(
    tmp_path,
    source_generation,
) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "resurrection.sqlite3")
    _issue(authority)
    with pytest.raises(
        DeletionResurrectionDenied,
        match="at or before",
    ):
        authority.guard_source_generation(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            source_generation=source_generation,
        )


def test_new_generation_requires_explicit_creation_authority(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "new-generation.sqlite3")
    _issue(authority)
    with pytest.raises(
        DeletionResurrectionDenied,
        match="explicit creation authority",
    ):
        authority.guard_source_generation(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            source_generation=2,
        )

    decision = authority.guard_source_generation(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        source_generation=2,
        creation_authority_ref="write-authority:new-user-consent",
    )
    assert decision.permitted is True
    assert decision.reason == "newer_authorized_generation"
    assert decision.latest_tombstone_generation == 1


def test_tenant_scope_is_part_of_tombstone_identity(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "tenant.sqlite3")
    _issue(authority)
    assert authority.latest(
        tenant_id="tenant-b",
        target_ref="subject:user-42",
    ) is None
    decision = authority.guard_source_generation(
        tenant_id="tenant-b",
        target_ref="subject:user-42",
        source_generation=0,
    )
    assert decision.permitted is True
    assert decision.reason == "no_tombstone"


def test_compare_and_swap_blocks_concurrent_generation_drift(tmp_path) -> None:
    authority = SQLiteDeletionPropagationAuthority(tmp_path / "cas.sqlite3")
    _issue(authority)
    authority.issue(
        tenant_id="tenant-a",
        target_ref="subject:user-42",
        request_id="delete-002",
        source_digest=hashlib.sha256(b"second").hexdigest(),
        required_surfaces=SURFACES,
        issued_at_ns=200,
        authority_ref="privacy-authority:tenant-a",
        expected_previous_generation=1,
    )
    with pytest.raises(
        DeletionPropagationConflict,
        match="compare-and-swap",
    ):
        authority.issue(
            tenant_id="tenant-a",
            target_ref="subject:user-42",
            request_id="delete-003",
            source_digest=hashlib.sha256(b"third").hexdigest(),
            required_surfaces=SURFACES,
            issued_at_ns=300,
            authority_ref="privacy-authority:tenant-a",
            expected_previous_generation=1,
        )
