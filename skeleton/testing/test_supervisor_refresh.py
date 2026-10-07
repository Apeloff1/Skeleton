from skeleton.automation.supervisor_refresh import require_fresh
def test_same_generation_waits():assert not require_fresh(previous_generation="a",current_generation="a",accepted=1,terminal=False).ready
def test_new_generation_advances():assert require_fresh(previous_generation="a",current_generation="b",accepted=1,terminal=False).ready
