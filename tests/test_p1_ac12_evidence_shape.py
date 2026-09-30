AXIS_ID = 'AC-12'
EXPECTED_MODES = ('canonicalization_fuzz','toctou_race','resource_binding','path_network_adversarial')
SAFETY = {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}

def test_ac12_contract():
    assert AXIS_ID == 'AC-12'
    assert len(EXPECTED_MODES) == 4
    assert SAFETY['non_authoritative'] is True
