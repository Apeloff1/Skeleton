from skeleton.frontier.contracts.admission_contract import AdmissionContract

def test_admission_contract_is_immutable():
    item = AdmissionContract("r1", True, "accept")
    assert item.request_id == "r1"
    assert item.accepted
