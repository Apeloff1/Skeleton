"""Dragon analysis queue and game-builder handoff regression tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_analysis_queue import (
    DragonAnalysisQueue, JobStatus,
)
from skeleton.ai.webcrawler.dragon_game_builder_bridge import (
    VisualEvent, ReviewedObservation, review_recording,
    prepare_game_builder_handoff,
)
from skeleton.ai.webcrawler.dragon_game_mechanics import (
    GameMechanicsMemory, Mechanic, PreferenceSignal,
)
from skeleton.ai.webcrawler.dragon_game_forge import (
    DragonGameForge, GameDesignConstraint,
)


def queue():
    return DragonAnalysisQueue(sqlite3.connect(":memory:"))


def submit(q, owner="alice"):
    return q.submit(
        owner, recording_digest="a" * 64, game_label="Original Game",
        now=100, capture_consent=True, analysis_consent=True,
        authorized=True,
    )


def test_queue_is_idempotent():
    q = queue()
    assert submit(q) == submit(q)


def test_queue_owner_isolation():
    q = queue()
    a = submit(q)
    b = submit(q, owner="bob")
    assert q.get("alice", b.job_id, authorized=True) is None
    assert q.erase("alice", authorized=True) == 1
    assert q.get("bob", b.job_id, authorized=True)


def test_queue_requires_both_consents():
    q = queue()
    with pytest.raises(PermissionError):
        q.submit(
            "alice", recording_digest="a" * 64,
            game_label="Game", now=100,
            capture_consent=True, analysis_consent=False,
            authorized=True,
        )


def test_approval_requires_human():
    q = queue()
    job = submit(q)
    q.advance("alice", job.job_id, JobStatus.RUNNING,
              now=101, authorized=True)
    q.advance("alice", job.job_id, JobStatus.AWAITING_REVIEW,
              now=102, authorized=True)
    with pytest.raises(PermissionError):
        q.advance("alice", job.job_id, JobStatus.APPROVED,
                  now=103, authorized=True)
    approved = q.advance(
        "alice", job.job_id, JobStatus.APPROVED,
        now=103, authorized=True, human_approved=True,
    )
    assert approved.status is JobStatus.APPROVED


def test_illegal_transition_fails_closed():
    q = queue()
    job = submit(q)
    with pytest.raises(ValueError):
        q.advance("alice", job.job_id, JobStatus.APPROVED,
                  now=101, authorized=True, human_approved=True)


def test_time_cannot_reverse():
    q = queue()
    job = submit(q)
    with pytest.raises(ValueError):
        q.advance("alice", job.job_id, JobStatus.RUNNING,
                  now=99, authorized=True)


def test_unclassified_visual_event_cannot_be_stored():
    store = GameMechanicsMemory(sqlite3.connect(":memory:"))
    with pytest.raises(ValueError, match="classified"):
        review_recording(
            store, owner="alice", game_label="Game",
            duration_ms=20000, capture_consent=True,
            analysis_consent=True, authorized=True,
            observations=(ReviewedObservation(
                VisualEvent(1000, "unclassified_visual_change", .9,
                            "scene cut", 1000),
                Mechanic.MOVEMENT, PreferenceSignal.UNKNOWN, False,
            ),),
        )


def test_review_and_builder_handoff():
    store = GameMechanicsMemory(sqlite3.connect(":memory:"))
    review_recording(
        store, owner="alice", game_label="Game",
        duration_ms=20000, capture_consent=True,
        analysis_consent=True, authorized=True,
        observations=(ReviewedObservation(
            VisualEvent(1000, "confirmed_movement", .9,
                        "Responsive acceleration", 1000),
            Mechanic.MOVEMENT, PreferenceSignal.ENJOYED, True,
        ),),
    )
    forge = DragonGameForge()
    constraints = GameDesignConstraint(
        "platform adventure", "desktop",
        ("keyboard access",), ("original world",),
    )
    with pytest.raises(PermissionError):
        prepare_game_builder_handoff(
            store, forge, owner="alice", constraints=constraints,
            authorized=True, human_approved=False,
        )
    handoff = prepare_game_builder_handoff(
        store, forge, owner="alice", constraints=constraints,
        authorized=True, human_approved=True,
    )
    assert handoff.prototype.mechanics[0].mechanic is Mechanic.MOVEMENT
    assert handoff.requires_original_assets
    assert len(handoff.manifest_fingerprint) == 64
