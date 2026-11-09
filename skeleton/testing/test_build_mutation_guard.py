import pytest
from skeleton.automation.build_worktree_snapshot import snapshot
from skeleton.automation.build_mutation_guard import require_unchanged
def test_mutation_rejected():
 a=snapshot(head_sha="a",tracked_diff=b"x",staged_diff=b"",untracked={});b=snapshot(head_sha="a",tracked_diff=b"y",staged_diff=b"",untracked={})
 with pytest.raises(ValueError):require_unchanged(a,b)
