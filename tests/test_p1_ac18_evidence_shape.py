AXIS_ID = 'AC-18'
EXPECTED_MODES = ('state_privacy','migration_boundary','cache_invalidation','restore_consistency')
SAFETY = {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}

def test_ac18_contract():
    assert AXIS_ID == 'AC-18'
    assert len(EXPECTED_MODES) == 4
    assert SAFETY['non_authoritative'] is True
    assert SAFETY['creates_binding'] is False
    assert SAFETY['promotes_maturity'] is False
