AXIS_ID = "AC-10"
EXPECTED_MODES = ("credential_rotation", "revocation_replay", "identity_restore", "historical_signature_verify")


def test_ac10_modes_are_exact():
    assert AXIS_ID == "AC-10"
    assert len(EXPECTED_MODES) == 4
    assert EXPECTED_MODES[0] == "credential_rotation"
    assert EXPECTED_MODES[-1] == "historical_signature_verify"
