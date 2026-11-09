from skeleton.automation.build_crash_matrix import matrix,expectation
def test_every_phase_has_recovery():assert len(matrix())==7 and all(x.action for x in matrix())
def test_pre_validation_crashes_rollback():assert expectation("validating").action=="rollback"
def test_committed_survives():assert expectation("committed").accepted_survives
