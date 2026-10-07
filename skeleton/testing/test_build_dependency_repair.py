from skeleton.automation.build_dependency_repair import diagnose
def test_missing_dependency_quarantines():assert diagnose("t",("x",),set(),set()).action=="quarantine"
def test_known_unfinished_waits():assert diagnose("t",("x",),{"x"},set()).action=="wait"
def test_done_ready():assert diagnose("t",("x",),{"x"},{"x"}).action=="ready"
