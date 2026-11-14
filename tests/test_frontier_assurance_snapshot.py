from skeleton.frontier.assurance.snapshot import Snapshot


def test_snapshot_captures_stable_digest():
    snapshot = Snapshot.capture(3, {"mode": "safe", "count": 2})
    assert snapshot.sequence == 3
    assert snapshot.digest
    assert snapshot.digest == Snapshot.capture(3, {"count": 2, "mode": "safe"}).digest
