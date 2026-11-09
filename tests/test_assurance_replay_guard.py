from skeleton.kernel.assurance_replay_guard import AssuranceReplayGuard


def test_replay_guard_accepts_first_event():
    guard = AssuranceReplayGuard()

    decision = guard.admit(
        task_id="task-1",
        evidence_digest="digest-1",
        state="ACCEPTED",
    )

    assert decision.accepted
    assert decision.reason == "accepted"


def test_replay_guard_blocks_duplicate_event():
    guard = AssuranceReplayGuard()

    first = guard.admit(
        task_id="task-1",
        evidence_digest="digest-1",
        state="ACCEPTED",
    )
    second = guard.admit(
        task_id="task-1",
        evidence_digest="digest-1",
        state="ACCEPTED",
    )

    assert first.accepted
    assert not second.accepted
    assert second.reason == "duplicate"


def test_replay_guard_requires_identity():
    guard = AssuranceReplayGuard()

    decision = guard.admit(
        task_id="",
        evidence_digest="digest-1",
        state="ACCEPTED",
    )

    assert not decision.accepted
