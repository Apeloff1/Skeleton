from skeleton.automation.advanced_bots import ADVANCED_BOTS, allowed


def test_advanced_roster_is_nontrivial():
    assert len(ADVANCED_BOTS) >= 8


def test_policy_rejects_control_plane():
    assert not allowed(ADVANCED_BOTS[0], [".github/workflows/x.yml"])


def test_policy_bounds_changes():
    assert not allowed(ADVANCED_BOTS[0], [f"skeleton/x{i}.py" for i in range(7)])
    assert allowed(ADVANCED_BOTS[0], ["skeleton/x.py"])
