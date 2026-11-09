from skeleton.frontier.contracts.recovery_contract import RecoveryContract

def test_recovery_contract_records_attempts():
    item = RecoveryContract("r1", 2, True)
    assert item.attempts == 2
    assert item.recovered
