from skeleton.frontier.gameforge_invariants import check_bounds

def test_bounds_accept_valid_usage():
    assert check_bounds(used=2, capacity=3).valid

def test_bounds_reports_overflow():
    report = check_bounds(used=4, capacity=3, name="queue")
    assert not report.valid
    assert "queue usage exceeds capacity" in report.violations
