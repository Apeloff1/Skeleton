from skeleton.frontier.gameforge_errors import AdmissionRejected, ContractViolation, FrontierError

def test_error_taxonomy_is_stable():
    assert issubclass(AdmissionRejected, FrontierError)
    assert issubclass(ContractViolation, FrontierError)
