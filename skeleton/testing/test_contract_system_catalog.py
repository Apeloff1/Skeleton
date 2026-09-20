import pytest

from skeleton.contracts.system_catalog import (
    CATALOG,
    ContractSpec,
    ContractTier,
    audit_catalog,
    dependency_closure,
    impacted_contracts,
    ownership_conflicts,
    topological_order,
    validate_catalog,
)


def test_catalog_is_valid_and_topologically_stable():
    validate_catalog()
    order = [item.contract_id for item in topological_order()]
    assert set(order) == {item.contract_id for item in CATALOG}
    positions = {name: index for index, name in enumerate(order)}
    for item in CATALOG:
        for dependency in item.depends_on:
            assert positions[dependency] < positions[item.contract_id]


def test_catalog_rejects_unknown_dependency():
    catalog = (
        ContractSpec("a", "scripts/check_a_contract.py", ContractTier.ROOT, ("missing",)),
    )
    with pytest.raises(ValueError, match="unknown dependencies"):
        validate_catalog(catalog)


def test_catalog_rejects_cycles():
    catalog = (
        ContractSpec("a", "scripts/check_a_contract.py", ContractTier.ROOT, ("b",)),
        ContractSpec("b", "scripts/check_b_contract.py", ContractTier.ROOT, ("a",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_catalog(catalog)


def test_catalog_rejects_duplicate_checker_ownership():
    catalog = (
        ContractSpec("a", "scripts/check_a_contract.py", ContractTier.ROOT),
        ContractSpec("b", "scripts/check_a_contract.py", ContractTier.SECURITY),
    )
    with pytest.raises(ValueError, match="duplicate contract checker"):
        validate_catalog(catalog)


def test_impacted_contracts_propagate_to_dependents():
    impacted = impacted_contracts(["skeleton/pr_automation/runner_engine.py"])
    assert "automerge" in impacted
    assert "runner-v2" in impacted
    assert "defense-control-plane" in impacted
    assert "merge-readiness" in impacted


def test_toolchain_change_reaches_root_readiness():
    impacted = impacted_contracts(["backend/pyproject.toml"])
    assert impacted == ("toolchain", "merge-readiness")


def test_unowned_path_has_no_false_contract_impact():
    assert impacted_contracts(["docs/unrelated-note.md"]) == ()


def test_catalog_audit_is_clean():
    audit = audit_catalog()
    assert audit.clean
    assert audit.ownership_conflicts == ()
    assert audit.orphan_dependencies == ()


def test_exact_duplicate_ownership_is_reported():
    catalog = (
        ContractSpec("a", "scripts/check_a_contract.py", ContractTier.ROOT, owns=("shared/",)),
        ContractSpec("b", "scripts/check_b_contract.py", ContractTier.SECURITY, owns=("shared/",)),
    )
    assert ownership_conflicts(catalog) == (("shared/", "a", "b"),)


def test_dependency_closure_is_topologically_ordered():
    closure = dependency_closure("merge-readiness")
    assert "runner-v2" in closure
    assert "automerge" in closure
    assert "toolchain" in closure
    assert "defense-control-plane" in closure
    assert closure.index("automerge") < closure.index("runner-v2")
    assert closure.index("runner-v2") < closure.index("defense-control-plane")


def test_unknown_dependency_closure_fails_closed():
    with pytest.raises(KeyError):
        dependency_closure("does-not-exist")
