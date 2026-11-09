from skeleton.frontier.gameforge_deadline import Deadline


def test_deadline_tracks_capacity_and_exhaustion():
    deadline = Deadline(3)
    assert deadline.capacity == 3
    assert not deadline.exhausted
    assert deadline.spend(2)
    assert deadline.remaining == 1
    assert not deadline.spend(2)
    assert deadline.exhausted
    deadline.reset()
    assert deadline.remaining == 3
