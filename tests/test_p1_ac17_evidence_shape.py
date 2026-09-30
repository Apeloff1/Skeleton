AXIS_ID = 'AC-17'
EXPECTED_MODES = ('tenant_isolation','cache_key_binding','privacy_boundary','cross_tenant_adversarial')
SAFETY = {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}

def test_ac17_contract():
    assert AXIS_ID == 'AC-17'
    assert len(EXPECTED_MODES) == 4
    assert SAFETY['non_authoritative'] is True
