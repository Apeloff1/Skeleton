"""Feature-gate, isolation, namespace, and command-contract regressions."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.contract_lint import CommandContractLinter, ContractSeverity
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.feature_gates import FeatureGate, FeatureGateRegistry
from skeleton.shells.isolation import (
    IsolationInspector,
    IsolationLevel,
    IsolationObservation,
    IsolationRequirement,
)
from skeleton.shells.namespace import NamespaceRegistry, ShellNamespace
from skeleton.shells.registry import ExecutableSpec


def make_definition(
    name="python",
    *,
    args=None,
    env=None,
    allow_stdin=False,
    allow_nonzero=False,
    capabilities=None,
):
    return CommandDefinition(
        ExecutableSpec(name, sys.executable),
        args or ArgumentPolicy.allow_any(),
        environment=env or EnvironmentPolicy.empty(),
        required_capabilities=frozenset(capabilities or {ShellCapability.EXECUTE}),
        allow_stdin=allow_stdin,
        allow_nonzero_success=allow_nonzero,
    )


@pytest.mark.parametrize("percent", [-1, 101, 1.5, True])
def test_feature_gate_rejects_invalid_rollout(percent):
    with pytest.raises(ValueError):
        FeatureGate("x", enabled=True, rollout_percent=percent)


def test_feature_gate_disabled_is_false():
    assert not FeatureGate("x").evaluate("principal")


def test_feature_gate_enabled_zero_is_false():
    gate = FeatureGate("x", enabled=True, rollout_percent=0)
    assert not gate.evaluate("principal")


def test_feature_gate_enabled_hundred_is_true():
    gate = FeatureGate("x", enabled=True, rollout_percent=100)
    assert gate.evaluate("principal")


def test_feature_gate_allow_overrides_disabled():
    gate = FeatureGate("x", enabled=False, allow_principals=frozenset({"p"}))
    assert gate.evaluate("p")


def test_feature_gate_deny_overrides_enabled():
    gate = FeatureGate(
        "x",
        enabled=True,
        rollout_percent=100,
        deny_principals=frozenset({"p"}),
    )
    assert not gate.evaluate("p")


def test_feature_gate_rejects_allow_deny_overlap():
    with pytest.raises(ValueError):
        FeatureGate(
            "x",
            allow_principals=frozenset({"p"}),
            deny_principals=frozenset({"p"}),
        )


def test_feature_gate_deterministic_rollout():
    gate = FeatureGate("x", enabled=True, rollout_percent=50)
    first = gate.evaluate("principal-a")
    assert gate.evaluate("principal-a") is first


def test_feature_gate_different_names_have_independent_bucket():
    a = FeatureGate("a", enabled=True, rollout_percent=50)
    b = FeatureGate("b", enabled=True, rollout_percent=50)
    values = {(a.evaluate(f"p{i}"), b.evaluate(f"p{i}")) for i in range(100)}
    assert len(values) > 1


def test_feature_registry_set_get_enabled():
    registry = FeatureGateRegistry()
    registry.set(FeatureGate("x", enabled=True, rollout_percent=100))
    assert registry.get("x").name == "x"
    assert registry.enabled("x", "p")


def test_feature_registry_missing_is_disabled():
    assert not FeatureGateRegistry().enabled("missing", "p")


def test_feature_registry_replace_same_name():
    registry = FeatureGateRegistry(max_gates=1)
    registry.set(FeatureGate("x"))
    registry.set(FeatureGate("x", enabled=True, rollout_percent=100))
    assert registry.enabled("x", "p")


def test_feature_registry_capacity_bound():
    registry = FeatureGateRegistry(max_gates=1)
    registry.set(FeatureGate("x"))
    with pytest.raises(RuntimeError):
        registry.set(FeatureGate("y"))


def test_feature_registry_remove():
    registry = FeatureGateRegistry()
    registry.set(FeatureGate("x"))
    assert registry.remove("x")
    assert not registry.remove("x")


def test_feature_registry_snapshot_sorted():
    registry = FeatureGateRegistry()
    registry.set(FeatureGate("b"))
    registry.set(FeatureGate("a"))
    assert [gate.name for gate in registry.snapshot()] == ["a", "b"]


def test_isolation_defaults_are_restrictive():
    requirement = IsolationRequirement()
    assert requirement.level is IsolationLevel.WORKSPACE
    assert requirement.require_private_tmp
    assert requirement.require_clean_environment
    assert not requirement.allow_network
    assert not requirement.allow_home


def test_isolation_requires_absolute_write_roots():
    with pytest.raises(ValueError):
        IsolationRequirement(allowed_write_roots=("relative/path",))


def test_isolation_stricter_level_is_narrower(tmp_path):
    parent = IsolationRequirement(level=IsolationLevel.WORKSPACE, allowed_write_roots=(str(tmp_path),))
    child = IsolationRequirement(level=IsolationLevel.SANDBOXED, allowed_write_roots=(str(tmp_path),))
    assert child.no_wider_than(parent)


def test_isolation_weaker_level_is_not_narrower():
    parent = IsolationRequirement(level=IsolationLevel.SANDBOXED)
    child = IsolationRequirement(level=IsolationLevel.HOST)
    assert not child.no_wider_than(parent)


def test_isolation_cannot_add_network_when_parent_denies():
    parent = IsolationRequirement(allow_network=False)
    child = IsolationRequirement(allow_network=True)
    assert not child.no_wider_than(parent)


def test_isolation_can_remove_network():
    parent = IsolationRequirement(allow_network=True)
    child = IsolationRequirement(allow_network=False)
    assert child.no_wider_than(parent)


def test_isolation_write_root_must_remain_inside_parent(tmp_path):
    root = tmp_path / "root"
    child_root = root / "child"
    root.mkdir()
    child_root.mkdir()
    parent = IsolationRequirement(allowed_write_roots=(str(root),))
    child = IsolationRequirement(allowed_write_roots=(str(child_root),))
    assert child.no_wider_than(parent)


def test_isolation_write_root_escape_rejected(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    parent = IsolationRequirement(allowed_write_roots=(str(a),))
    child = IsolationRequirement(allowed_write_roots=(str(b),))
    assert not child.no_wider_than(parent)


def test_isolation_inspector_accepts_matching_observation(tmp_path):
    requirement = IsolationRequirement(
        level=IsolationLevel.SANDBOXED,
        require_readonly_source=True,
        allowed_write_roots=(str(tmp_path),),
    )
    observation = IsolationObservation(
        private_tmp=True,
        clean_environment=True,
        readonly_source=True,
        network_enabled=False,
        home_visible=False,
        write_roots=(str(tmp_path / "out"),),
    )
    assert IsolationInspector().inspect(requirement, observation).allowed


@pytest.mark.parametrize(
    "observation,reason",
    [
        (
            IsolationObservation(False, True, False, False, False),
            "private temporary",
        ),
        (
            IsolationObservation(True, False, False, False, False),
            "clean environment",
        ),
        (
            IsolationObservation(True, True, False, True, False),
            "network",
        ),
        (
            IsolationObservation(True, True, False, False, True),
            "home",
        ),
    ],
)
def test_isolation_inspector_rejects_violations(observation, reason):
    decision = IsolationInspector().inspect(IsolationRequirement(), observation)
    assert not decision.allowed
    assert any(reason in item for item in decision.reasons)


def test_namespace_allows_unrestricted_principal_and_command():
    namespace = ShellNamespace("core")
    assert namespace.allows_principal("p")
    assert namespace.allows_command("python")


def test_namespace_principal_allowlist():
    namespace = ShellNamespace("core", principals=frozenset({"p"}))
    assert namespace.allows_principal("p")
    assert not namespace.allows_principal("q")


def test_namespace_command_prefix():
    namespace = ShellNamespace("core", command_prefixes=frozenset({"build."}))
    assert namespace.allows_command("build.compile")
    assert not namespace.allows_command("test.pytest")


def test_namespace_disabled_denies_all():
    namespace = ShellNamespace("core", enabled=False)
    assert not namespace.allows_principal("p")
    assert not namespace.allows_command("python")


def test_namespace_registry_authorizes():
    registry = NamespaceRegistry()
    registry.set(
        ShellNamespace(
            "core",
            principals=frozenset({"p"}),
            command_prefixes=frozenset({"py"}),
        )
    )
    registry.authorize("core", principal="p", command="python")


def test_namespace_registry_denies_principal():
    registry = NamespaceRegistry()
    registry.set(ShellNamespace("core", principals=frozenset({"p"})))
    with pytest.raises(PermissionError):
        registry.authorize("core", principal="q", command="python")


def test_namespace_registry_denies_command():
    registry = NamespaceRegistry()
    registry.set(ShellNamespace("core", command_prefixes=frozenset({"git"})))
    with pytest.raises(PermissionError):
        registry.authorize("core", principal="p", command="python")


def test_namespace_registry_capacity():
    registry = NamespaceRegistry(max_namespaces=1)
    registry.set(ShellNamespace("a"))
    with pytest.raises(RuntimeError):
        registry.set(ShellNamespace("b"))


def test_contract_lint_clean_basic_definition():
    catalog = CommandCatalog((make_definition(),))
    report = CommandContractLinter().lint(catalog)
    assert report.ok


def test_contract_lint_stdin_without_specific_capability_warns():
    definition = make_definition(allow_stdin=True)
    findings = CommandContractLinter().lint_definition(definition)
    assert any(item.code == "stdin_without_explicit_capability" for item in findings)


def test_contract_lint_nonzero_without_specific_capability_warns():
    definition = make_definition(allow_nonzero=True)
    findings = CommandContractLinter().lint_definition(definition)
    assert any(item.code == "nonzero_without_explicit_capability" for item in findings)


def test_contract_lint_large_argument_count_warns():
    definition = make_definition(args=ArgumentPolicy.allow_any(max_total_args=300))
    findings = CommandContractLinter().lint_definition(definition)
    assert any(item.code == "large_argument_count" for item in findings)


def test_contract_lint_large_argument_bytes_warns():
    definition = make_definition(args=ArgumentPolicy.allow_any(max_total_bytes=256 * 1024))
    findings = CommandContractLinter().lint_definition(definition)
    assert any(item.code == "large_argument_bytes" for item in findings)


def test_contract_lint_large_environment_surface_warns():
    rules = {f"K{i}": EnvironmentValueRule() for i in range(129)}
    definition = make_definition(env=EnvironmentPolicy(rules=rules))
    findings = CommandContractLinter().lint_definition(definition)
    assert any(item.code == "large_environment_surface" for item in findings)


def test_contract_lint_environment_inheritance_is_info():
    definition = make_definition(
        env=EnvironmentPolicy(
            rules={"PATH": EnvironmentValueRule()},
            inherited=frozenset({"PATH"}),
        )
    )
    findings = CommandContractLinter().lint_definition(definition)
    match = [item for item in findings if item.code == "environment_inheritance"]
    assert match
    assert match[0].severity is ContractSeverity.INFO
