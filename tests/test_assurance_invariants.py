from skeleton.kernel.assurance_invariants import (
    accepted_event_is_valid,
    has_digest,
    has_identity,
)


def test_identity_required():
    assert has_identity({"task_id": "task-1"})
    assert not has_identity({})


def test_digest_required():
    assert has_digest({"digest": "abc"})
    assert not has_digest({})


def test_acceptance_requires_identity_and_digest():
    assert accepted_event_is_valid({"task_id": "task-1", "digest": "abc"})
    assert not accepted_event_is_valid({"task_id": "task-1"})
