from skeleton.automation.build_worktree_snapshot import snapshot
def test_untracked_is_part_of_snapshot():assert snapshot(head_sha="a",tracked_diff=b"",staged_diff=b"",untracked={}).digest()!=snapshot(head_sha="a",tracked_diff=b"",staged_diff=b"",untracked={"x":b"1"}).digest()
def test_staged_is_part_of_snapshot():assert snapshot(head_sha="a",tracked_diff=b"",staged_diff=b"x",untracked={}).digest()!=snapshot(head_sha="a",tracked_diff=b"",staged_diff=b"y",untracked={}).digest()
