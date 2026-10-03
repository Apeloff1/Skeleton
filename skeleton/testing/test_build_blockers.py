from skeleton.automation.build_blockers import classify
def test_authority_is_terminal(): assert classify(authority_invalid=True).action=="quarantine"
def test_validation_repairs(): assert classify(validation_failed=True).action=="repair"
def test_ci_diagnoses(): assert classify(ci_failed=True).action=="diagnose"
