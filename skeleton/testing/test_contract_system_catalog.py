import pytest

from skeleton.contracts.system_catalog import (
    CATALOG,
    ContractSpec,
    ContractTier,
    active_contracts,
    audit_catalog,
    dependency_closure,
    impacted_contracts,
    ownership_conflicts,
    privilege_escalations,
    unowned_paths,
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


def test_evidence_consumer_must_depend_on_producer():
    catalog = (
        ContractSpec("producer", "scripts/check_p_contract.py", ContractTier.SECURITY),
        ContractSpec(
            "consumer",
            "scripts/check_c_contract.py",
            ContractTier.ROOT,
            consumes_evidence=(("producer", 1),),
        ),
    )
    with pytest.raises(ValueError, match="non-dependency"):
        validate_catalog(catalog)


def test_evidence_version_mismatch_fails_closed():
    catalog = (
        ContractSpec(
            "producer",
            "scripts/check_p_contract.py",
            ContractTier.SECURITY,
            evidence_version=2,
        ),
        ContractSpec(
            "consumer",
            "scripts/check_c_contract.py",
            ContractTier.ROOT,
            depends_on=("producer",),
            consumes_evidence=(("producer", 1),),
        ),
    )
    with pytest.raises(ValueError, match="evidence version mismatch"):
        validate_catalog(catalog)


def test_evidence_version_match_is_valid():
    catalog = (
        ContractSpec(
            "producer",
            "scripts/check_p_contract.py",
            ContractTier.SECURITY,
            evidence_version=2,
        ),
        ContractSpec(
            "consumer",
            "scripts/check_c_contract.py",
            ContractTier.ROOT,
            depends_on=("producer",),
            consumes_evidence=(("producer", 2),),
        ),
    )
    validate_catalog(catalog)


def test_boolean_evidence_version_is_rejected():
    catalog = (
        ContractSpec(
            "producer",
            "scripts/check_p_contract.py",
            ContractTier.SECURITY,
            evidence_version=True,
        ),
    )
    # bool is an int subclass; contract versions must remain explicit integers.
    with pytest.raises(ValueError):
        validate_catalog(catalog)


def test_privilege_escalation_requires_upstream_authority():
    catalog = (
        ContractSpec(
            "root",
            "scripts/check_root_contract.py",
            ContractTier.ROOT,
            privileges=("contents:read",),
        ),
        ContractSpec(
            "child",
            "scripts/check_child_contract.py",
            ContractTier.PRIVILEGED,
            depends_on=("root",),
            privileges=("contents:write",),
        ),
    )
    assert privilege_escalations(catalog) == (
        ("child", "contents:write", "not-inherited"),
    )


def test_inherited_privilege_is_accepted():
    catalog = (
        ContractSpec(
            "root",
            "scripts/check_root_contract.py",
            ContractTier.ROOT,
            privileges=("contents:read",),
        ),
        ContractSpec(
            "child",
            "scripts/check_child_contract.py",
            ContractTier.PRIVILEGED,
            depends_on=("root",),
            privileges=("contents:read",),
        ),
    )
    assert privilege_escalations(catalog) == ()


def test_invalid_privilege_name_fails_closed():
    catalog = (
        ContractSpec(
            "root",
            "scripts/check_root_contract.py",
            ContractTier.ROOT,
            privileges=("Contents Write",),
        ),
    )
    with pytest.raises(ValueError, match="invalid privilege"):
        validate_catalog(catalog)


def test_control_plane_orphan_surface_detection():
    assert unowned_paths(
        [
            ".github/workflows/new-privileged-plane.yml",
            "docs/readme.md",
        ]
    ) == (".github/workflows/new-privileged-plane.yml",)


def test_contract_system_checker_is_intentionally_self_owned():
    assert unowned_paths(["scripts/check_contract_system.py"]) == ()


def test_contract_maturity_must_be_positive_integer():
    with pytest.raises(ValueError, match="maturity"):
        validate_catalog((
            ContractSpec("a", "scripts/check_a_contract.py", ContractTier.ROOT, maturity=0),
        ))
    with pytest.raises(ValueError, match="maturity"):
        validate_catalog((
            ContractSpec("a", "scripts/check_a_contract.py", ContractTier.ROOT, maturity=True),
        ))


def test_superseded_contract_is_removed_from_active_set():
    catalog = (
        ContractSpec("legacy", "scripts/check_legacy_contract.py", ContractTier.ROOT),
        ContractSpec(
            "current",
            "scripts/check_current_contract.py",
            ContractTier.ROOT,
            supersedes=("legacy",),
            maturity=2,
        ),
    )
    validate_catalog(catalog)
    assert tuple(item.contract_id for item in active_contracts(catalog)) == ("current",)


def test_unknown_supersession_fails_closed():
    catalog = (
        ContractSpec(
            "current",
            "scripts/check_current_contract.py",
            ContractTier.ROOT,
            supersedes=("missing",),
        ),
    )
    with pytest.raises(ValueError, match="supersedes unknown"):
        validate_catalog(catalog)


def test_self_supersession_fails_closed():
    catalog = (
        ContractSpec(
            "current",
            "scripts/check_current_contract.py",
            ContractTier.ROOT,
            supersedes=("current",),
        ),
    )
    with pytest.raises(ValueError, match="self supersession"):
        validate_catalog(catalog)
