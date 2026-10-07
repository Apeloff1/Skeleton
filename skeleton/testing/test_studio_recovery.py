from skeleton.automation.studio_recovery import decide_recovery

def test_uncommitted_same_head_rolls_back():
    assert decide_recovery({"phase":"validating","base_commit_sha":"a"},current_head="a").action=="rollback"

def test_changed_head_fails_closed():
    assert decide_recovery({"phase":"applied","base_commit_sha":"a"},current_head="b").action=="fail_closed"

def test_committed_retires():
    assert decide_recovery({"phase":"committed","base_commit_sha":"a"},current_head="b").action=="retire_journal"

def test_unknown_phase_fails_closed():
    assert decide_recovery({"phase":"wat"},current_head="a").action=="fail_closed"
