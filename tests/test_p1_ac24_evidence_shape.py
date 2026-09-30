AXIS_ID = 'AC-24'
EXPECTED_MODES = ('partition_recovery','lease_revalidation','rollback_convergence','stale_state_rejection')
SAFETY = {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}

def test_ac24_contract():
    assert AXIS_ID == 'AC-24'
    assert len(EXPECTED_MODES) == 4
    assert SAFETY['non_authoritative'] is True
    assert SAFETY['creates_binding'] is False
    assert SAFETY['accepts_risk'] is False
    assert SAFETY['lowers_severity'] is False
    assert SAFETY['promotes_maturity'] is False
