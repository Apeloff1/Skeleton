from skeleton.automation.build_deadlock import detect
def test_stalled_work_detected():assert detect(fingerprints=("a","a","a","a"),pending_repairs=1,queued_tasks=0).detected
def test_idle_complete_not_deadlock():assert not detect(fingerprints=("a","a","a","a"),pending_repairs=0,queued_tasks=0).detected
