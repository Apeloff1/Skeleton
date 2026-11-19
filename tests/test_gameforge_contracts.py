from skeleton.frontier.gameforge_contracts import ContractVersion

def test_contract_versions_require_same_major_and_name():
    base = ContractVersion("admission")
    assert base.compatible_with(ContractVersion("admission", 1, 9))
    assert not base.compatible_with(ContractVersion("admission", 2))
    assert not base.compatible_with(ContractVersion("receipt"))
