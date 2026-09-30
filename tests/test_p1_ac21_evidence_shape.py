AXIS_ID = 'AC-21'
EXPECTED_MODES = ('lease_partition','fencing','state_convergence','stale_worker_rejection')
SAFETY = {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}

def test_ac21_contract():
    assert AXIS_ID == 'AC-21'
    assert len(EXPECTED_MODES) == 4
    assert SAFETY == {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}
