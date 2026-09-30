AXIS_ID = 'AC-12'
MODES = ('canonicalization_fuzz','toctou_race','resource_binding','path_network_adversarial')
SAFETY = {'non_authoritative': True, 'creates_binding': False, 'accepts_risk': False, 'lowers_severity': False, 'promotes_maturity': False}

def build_contract():
    return {'axis_id': AXIS_ID, 'modes': MODES, 'safety': SAFETY}

if __name__ == '__main__':
    print(build_contract())
