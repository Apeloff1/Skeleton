"""Stress-style contract tests for assurance replay protection."""

from skeleton.kernel.assurance_replay_guard import AssuranceReplayGuard


def test_many_unique_events_are_admitted() -> None:
    guard = AssuranceReplayGuard()

    for index in range(250):
        decision = guard.admit(
            task_id=f"task-{index}",
            evidence_digest=f"digest-{index}",
            state="ACCEPTED",
        )
        assert decision.accepted

    assert guard.size() == 250


def test_same_identity_and_digest_is_rejected() -> None:
    guard = AssuranceReplayGuard()

    first = guard.admit(
        task_id="task-a",
        evidence_digest="digest-a",
        state="ACCEPTED",
    )
    second = guard.admit(
        task_id="task-a",
        evidence_digest="digest-a",
        state="ACCEPTED",
    )

    assert first.accepted
    assert not second.accepted
    assert second.reason == "duplicate"
