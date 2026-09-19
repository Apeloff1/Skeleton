from __future__ import annotations

import ast
from pathlib import Path

import pytest

import skeleton.ubuntu.operations as ops
from skeleton.ubuntu.operations import (
    RESOURCE_SPECS,
    UbuntuAction,
    UbuntuPlan,
    audit_plan,
    canonical_plan_json,
    diff_plans,
    merge_plans,
    plan_digest,
    plan_package_apt,
    plan_resources,
    resource_spec,
    resource_specs,
    validate_package_apt,
    validate_plan,
    validate_resource_reference,
)


def test_action_is_bounded_and_serializable() -> None:
    action = UbuntuAction(
        "package-apt:curl",
        ("ubuntu", "package", "apt", "curl", "present"),
        "install curl",
    )
    assert action.as_dict()["name"] == "package-apt:curl"
    assert action.as_dict()["argv"] == ("ubuntu", "package", "apt", "curl", "present")


def test_empty_argv_is_rejected() -> None:
    with pytest.raises(ValueError, match="argv"):
        UbuntuAction("x", (), "test")


def test_timeout_is_bounded() -> None:
    with pytest.raises(ValueError, match="timeout"):
        UbuntuAction("x", ("ubuntu", "noop"), "test", timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout"):
        UbuntuAction("x", ("ubuntu", "noop"), "test", timeout_seconds=3601)


def test_nul_and_oversized_text_are_rejected() -> None:
    with pytest.raises(ValueError, match="bounded"):
        UbuntuAction("bad\\x00name", ("ubuntu", "noop"), "test")
    with pytest.raises(ValueError, match="bounded"):
        UbuntuAction("x", ("ubuntu", "noop"), "a" * 4097)


def test_package_planning_is_deterministic() -> None:
    first = plan_package_apt(("curl", "git", "python3"))
    second = plan_package_apt(("curl", "git", "python3"))
    assert first.names() == (
        "package-apt:curl",
        "package-apt:git",
        "package-apt:python3",
    )
    assert first == second
    assert validate_plan(first) == ()


def test_package_absent_requires_disabled_state() -> None:
    with pytest.raises(ValueError, match="enabled"):
        validate_package_apt("curl", "absent")
    action = validate_package_apt("curl", "absent", enabled=False)
    assert action.argv[-1] == "absent"


def test_plan_append_and_extend_preserve_immutability() -> None:
    base = UbuntuPlan(metadata={"domain": "test"})
    action = UbuntuAction("a", ("ubuntu", "noop", "a"), "test")
    appended = base.append(action)
    extended = base.extend((action,))
    assert base.actions == ()
    assert appended.actions == (action,)
    assert extended.actions == (action,)
    assert base.metadata == {"domain": "test"}


def test_duplicate_action_names_fail_validation() -> None:
    action = UbuntuAction("same", ("ubuntu", "noop"), "test")
    plan = UbuntuPlan((action, action))
    assert validate_plan(plan) == ("duplicate action: same",)


def test_merge_rejects_duplicate_actions() -> None:
    action = UbuntuAction("same", ("ubuntu", "noop"), "test")
    with pytest.raises(ValueError, match="duplicate action"):
        merge_plans(UbuntuPlan((action,)), UbuntuPlan((action,)))


def test_merge_preserves_order() -> None:
    a = UbuntuAction("a", ("ubuntu", "noop", "a"), "test")
    b = UbuntuAction("b", ("ubuntu", "noop", "b"), "test")
    merged = merge_plans(UbuntuPlan((a,)), UbuntuPlan((b,)))
    assert merged.names() == ("a", "b")


def test_plan_contains_no_shell_command_string() -> None:
    plan = plan_package_apt(("curl",))
    assert plan.actions[0].argv[0] == "ubuntu"
    assert all(isinstance(part, str) for part in plan.actions[0].argv)
    assert "shell=True" not in repr(plan)


def test_registry_contains_eight_domains_and_eighty_resources() -> None:
    assert len(RESOURCE_SPECS) == 80
    assert {spec.domain for spec in RESOURCE_SPECS} == {
        "package",
        "service",
        "network",
        "storage",
        "runtime",
        "security",
        "cloud",
        "ci",
    }
    assert len({spec.resource_id for spec in RESOURCE_SPECS}) == 80
    assert len({spec.key_prefix for spec in RESOURCE_SPECS}) == 80


@pytest.mark.parametrize("spec", RESOURCE_SPECS, ids=lambda spec: spec.resource_id)
def test_every_resource_preserves_original_class_and_helper_contract(spec) -> None:
    plan_type = getattr(ops, spec.class_name)
    validator = getattr(ops, f"validate_{spec.resource_id}")
    planner = getattr(ops, f"plan_{spec.resource_id}")
    auditor = getattr(ops, f"audit_{spec.resource_id}")

    policy = plan_type("sample")
    action = policy.action()
    assert action.name == f"{spec.key_prefix}:sample"
    assert action.argv == ("ubuntu", spec.domain, spec.resource, "sample", "present")
    assert validator("sample") == action

    planned = planner(("alpha", "beta"))
    assert planned.names() == (
        f"{spec.key_prefix}:alpha",
        f"{spec.key_prefix}:beta",
    )
    evidence = auditor(planned)
    assert evidence["ok"] is True
    assert evidence["count"] == 2
    assert evidence["resource"] == spec.key_prefix


@pytest.mark.parametrize("spec", RESOURCE_SPECS, ids=lambda spec: spec.resource_id)
def test_generic_registry_planner_matches_resource_helper(spec) -> None:
    generic = plan_resources(spec.resource_id, ("alpha", "beta"))
    specific = getattr(ops, f"plan_{spec.resource_id}")(("alpha", "beta"))
    assert generic == specific


@pytest.mark.parametrize("spec", RESOURCE_SPECS, ids=lambda spec: spec.resource_id)
def test_resource_policy_validation_is_uniform(spec) -> None:
    plan_type = getattr(ops, spec.class_name)
    assert plan_type("x", desired="present").validate() == ()
    assert plan_type("x", desired="latest").validate() == ()
    assert plan_type("x", desired="running").validate() == ()
    assert plan_type("x", desired="stopped").validate() == ()
    assert "absent resource cannot be enabled" in plan_type("x", desired="absent").validate()
    restart_absent = plan_type("x", desired="absent", enabled=False, restart=True)
    assert "restart conflicts with state" in restart_absent.validate()
    assert plan_type("x", desired="mystery").validate() == ("unsupported desired state",)


def test_resource_lookup_is_deterministic() -> None:
    apt = resource_spec("package_apt")
    assert apt.domain == "package"
    assert apt.resource == "apt"
    assert apt.class_name == "PackageAptPlan"
    assert resource_specs(domain="package")[0] == apt
    assert len(resource_specs(domain="package")) == 10
    with pytest.raises(KeyError, match="unknown Ubuntu resource"):
        resource_spec("package_missing")


def test_resource_reference_validation() -> None:
    spec, identifier = validate_resource_reference("network-dns:resolver")
    assert spec.resource_id == "network_dns"
    assert identifier == "resolver"
    with pytest.raises(ValueError, match="contain"):
        validate_resource_reference("network-dns")
    with pytest.raises(ValueError, match="unknown"):
        validate_resource_reference("unknown-kind:value")


def test_plan_digest_is_canonical_and_content_sensitive() -> None:
    first = plan_package_apt(("curl", "git"))
    second = plan_package_apt(("curl", "git"))
    reversed_plan = plan_package_apt(("git", "curl"))
    assert canonical_plan_json(first) == canonical_plan_json(second)
    assert plan_digest(first) == plan_digest(second)
    assert len(plan_digest(first)) == 64
    assert plan_digest(first) != plan_digest(reversed_plan)


def test_audit_plan_reports_known_and_unknown_actions() -> None:
    known = plan_package_apt(("curl",))
    card = audit_plan(known)
    assert card["ok"] is True
    assert card["action_count"] == 1
    assert card["resource_counts"]["package-apt"] == 1
    assert card["digest"] == plan_digest(known)

    unknown = UbuntuPlan((UbuntuAction("custom:thing", ("ubuntu", "noop"), "test"),))
    unknown_card = audit_plan(unknown)
    assert unknown_card["ok"] is False
    assert unknown_card["unknown_actions"] == ("custom:thing",)


def test_plan_diff_is_order_independent_for_identity_sets() -> None:
    before = plan_package_apt(("curl", "git"))
    after = plan_package_apt(("git", "python3"))
    diff = diff_plans(before, after)
    assert diff.added == ("package-apt:python3",)
    assert diff.removed == ("package-apt:curl",)
    assert diff.retained == ("package-apt:git",)
    assert diff.changed is True
    assert diff_plans(before, before).changed is False


def test_numbered_contracts_are_lazy_but_backward_compatible() -> None:
    first = getattr(ops, "ubuntu_contract_4050")
    last = getattr(ops, "ubuntu_contract_9000")
    assert first("worker") == "ubuntu-4050:worker"
    assert last("worker") == "ubuntu-9000:worker"
    assert ops.ubuntu_contract("worker", 4050) == "ubuntu-4050:worker"
    with pytest.raises(ValueError, match="absolute"):
        first("/etc/passwd")
    with pytest.raises(AttributeError):
        getattr(ops, "ubuntu_contract_4051")
    with pytest.raises(ValueError, match="contract id"):
        ops.ubuntu_contract("worker", True)


def test_ubuntu_package_is_execution_free_by_import_contract() -> None:
    root = Path(ops.__file__).resolve().parent
    forbidden = {"subprocess", "socket", "shlex", "pty"}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".", 1)[0] for alias in node.names}
                assert not (imported & forbidden), (path, imported & forbidden)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".", 1)[0] not in forbidden, path


def test_monolith_padding_was_removed() -> None:
    source = Path(ops.__file__).read_text(encoding="utf-8")
    assert "def ubuntu_contract_4050" not in source
    assert "def ubuntu_contract_9000" not in source
    assert source.count("def ubuntu_contract_") == 0
    assert len(source.splitlines()) < 500


def test_domain_modules_are_bounded_and_static() -> None:
    root = Path(ops.__file__).resolve().parent
    domain_paths = [
        root / "package.py",
        root / "service.py",
        root / "network.py",
        root / "storage.py",
        root / "runtime.py",
        root / "security.py",
        root / "cloud.py",
        root / "ci.py",
    ]
    assert all(path.exists() for path in domain_paths)
    assert all(len(path.read_text(encoding="utf-8").splitlines()) < 650 for path in domain_paths)
    assert sum(len(path.read_text(encoding="utf-8").splitlines()) for path in domain_paths) < 4500
