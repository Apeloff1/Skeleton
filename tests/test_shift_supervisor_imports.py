def test_shift_supervisor_public_imports():
    import core.shift_supervisor as supervisor

    assert supervisor.SMBShiftManager is not None
    assert supervisor.SecretaryBot is not None
    assert supervisor.ModelGateway is not None
