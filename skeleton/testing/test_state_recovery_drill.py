from __future__ import annotations

import pytest

from scripts import state_recovery_drill as drill


def test_recovery_drill_refuses_non_scratch_database_names() -> None:
    for name in ("production", "galaxy_studio_db", "skeleton", ""):
        with pytest.raises(drill.RecoveryDrillError, match="refusing destructive"):
            drill.require_scratch_database(name)

    assert (
        drill.require_scratch_database("skeleton_recovery_drill_source")
        == "skeleton_recovery_drill_source"
    )


def test_recovery_journal_forbids_derived_rebuild_before_authority_verify() -> None:
    journal = drill.RecoveryJournal()

    journal.record("seed_authority")
    journal.record("backup_authority")
    journal.record("destroy_restore_target")
    journal.record("restore_authority")

    with pytest.raises(
        drill.RecoveryDrillError,
        match="expected verify_authority",
    ):
        journal.record("rebuild_derived")


def test_recovery_journal_requires_authority_verification_before_rebuild() -> None:
    journal = drill.RecoveryJournal()
    phases = [
        "seed_authority",
        "backup_authority",
        "destroy_restore_target",
        "restore_authority",
        "verify_authority",
        "rebuild_derived",
        "verify_derived",
        "ready",
    ]

    for phase in phases:
        journal.record(phase, evidence={"phase": phase})

    rendered = journal.as_dict()
    assert rendered["verified_authority"] is True
    assert rendered["complete"] is True
    assert [event["phase"] for event in rendered["events"]] == phases
    assert [event["sequence"] for event in rendered["events"]] == list(
        range(1, len(phases) + 1)
    )


def test_verify_snapshot_rejects_document_or_index_drift() -> None:
    expected = {
        "collections": {
            "rag_user_progress": {
                "count": 1,
                "documents_digest": "docs-a",
                "indexes_digest": "idx-a",
            }
        },
        "digest": "backup-a",
    }

    with pytest.raises(drill.RecoveryDrillError, match="documents_digest"):
        drill.verify_snapshot(
            expected,
            {
                "collections": {
                    "rag_user_progress": {
                        "count": 1,
                        "documents_digest": "docs-b",
                        "indexes_digest": "idx-a",
                    }
                },
                "digest": "restore-b",
            },
        )

    with pytest.raises(drill.RecoveryDrillError, match="indexes_digest"):
        drill.verify_snapshot(
            expected,
            {
                "collections": {
                    "rag_user_progress": {
                        "count": 1,
                        "documents_digest": "docs-a",
                        "indexes_digest": "idx-b",
                    }
                },
                "digest": "restore-b",
            },
        )


def test_verify_snapshot_returns_count_and_digest_evidence() -> None:
    expected = {
        "collections": {
            "rag_user_progress": {
                "count": 2,
                "documents_digest": "docs",
                "indexes_digest": "idx",
            },
            "rag_feedback": {
                "count": 1,
                "documents_digest": "feedback-docs",
                "indexes_digest": "feedback-idx",
            },
        },
        "digest": "backup-digest",
    }
    actual = {
        "collections": {
            name: dict(values) for name, values in expected["collections"].items()
        },
        "digest": "restore-digest",
    }

    evidence = drill.verify_snapshot(expected, actual)

    assert evidence == {
        "collections": {
            "rag_feedback": 1,
            "rag_user_progress": 2,
        },
        "backup_digest": "backup-digest",
        "restore_digest": "restore-digest",
        "verified_fields": ["count", "documents_digest", "indexes_digest"],
    }


def test_derived_rebuild_is_deterministic_from_verified_snapshot_shape() -> None:
    snapshot = {
        "collections": {
            "rag_learning_sessions": {
                "documents": [
                    {
                        "session_id": "session-2",
                        "user_id": "u2",
                        "content": "two",
                    },
                    {
                        "session_id": "session-1",
                        "user_id": "u1",
                        "content": "one",
                    },
                ]
            },
            "rag_feedback": {
                "documents": [
                    {
                        "feedback_id": "feedback-1",
                        "user_id": "u1",
                        "content": "useful",
                    }
                ]
            },
        }
    }

    first = drill.rebuild_derived_projection(snapshot)
    second = drill.rebuild_derived_projection(snapshot)

    assert first == second
    assert first["count"] == 3
    assert first["digest"] == second["digest"]
    assert [row["record_id"] for row in first["records"]] == [
        "feedback-1",
        "session-1",
        "session-2",
    ]


def test_failed_phase_stops_recovery_journal() -> None:
    journal = drill.RecoveryJournal()

    with pytest.raises(drill.RecoveryDrillError, match="seed_authority"):
        journal.record("seed_authority", status="failed")

    assert len(journal.events) == 1
    assert journal.events[0].status == "failed"
