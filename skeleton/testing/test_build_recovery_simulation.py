from skeleton.automation.build_recovery_simulation import simulate
def test_all_crash_phases_have_expected_recovery():assert all(x.passed for x in simulate())
