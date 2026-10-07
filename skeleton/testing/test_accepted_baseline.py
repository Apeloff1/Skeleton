from skeleton.automation.accepted_baseline import make
def test_baseline_binds_untracked_content():assert make(head_sha="a"*40,tracked_diff="x",untracked={"n.py":b"1"}).digest()!=make(head_sha="a"*40,tracked_diff="x",untracked={"n.py":b"2"}).digest()
