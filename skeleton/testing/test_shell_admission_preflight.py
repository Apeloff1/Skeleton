from pathlib import Path
import sys
import pytest

from skeleton.shells.admission import CommandAdmission
from skeleton.shells.arguments import ArgumentPolicy, OptionRule
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.preflight import PreflightAnalyzer
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellCommand
from skeleton.shells.workspace import WorkspacePolicy


def catalog(tmp_path):
    spec = ExecutableSpec("python", str(Path(sys.executable).resolve()), tags=frozenset({"runtime"}))
    definition = CommandDefinition(
        spec,
        ArgumentPolicy(options={"-q": OptionRule("-q")}),
        environment=EnvironmentPolicy(rules={"MODE": EnvironmentValueRule(choices=frozenset({"test"}))}),
        required_capabilities=frozenset({ShellCapability.EXECUTE}),
        max_timeout=10,
        allow_stdin=False,
        allow_nonzero_success=False,
    )
    return CommandCatalog([definition])


def grant(*caps):
    return CapabilityGrant(frozenset(caps or {ShellCapability.EXECUTE}))


def test_command_catalog_default_denies_unknown():
    with pytest.raises(KeyError):
        CommandCatalog().get("python")


def test_command_catalog_freeze_blocks_mutation(tmp_path):
    c = catalog(tmp_path)
    frozen = c.freeze()
    assert "python" in frozen
    with pytest.raises(RuntimeError):
        c.register(c.get("python"), replace=True)


def test_admission_accepts_valid_command(tmp_path):
    admission = CommandAdmission(catalog(tmp_path), WorkspacePolicy((tmp_path,)))
    decision = admission.admit(ShellCommand("python", ("-q",), cwd=tmp_path), grant())
    assert decision.allowed
    assert decision.argument_count == 1


def test_admission_rejects_unknown_command(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(ShellCommand("other"), grant())


def test_admission_rejects_argument_policy_violation(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(ShellCommand("python", ("--bad",)), grant())


def test_admission_rejects_env_without_capability(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(ShellCommand("python", env={"MODE": "test"}), grant())


def test_admission_accepts_env_with_capability(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    decision = admission.admit(
        ShellCommand("python", env={"MODE": "test"}),
        grant(ShellCapability.EXECUTE, ShellCapability.CUSTOM_ENV),
    )
    assert decision.allowed


def test_admission_rejects_invalid_env_value_even_with_capability(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(
            ShellCommand("python", env={"MODE": "prod"}),
            grant(ShellCapability.EXECUTE, ShellCapability.CUSTOM_ENV),
        )


def test_admission_rejects_stdin_when_command_contract_disables_it(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(
            ShellCommand("python", stdin=b"x"),
            grant(ShellCapability.EXECUTE, ShellCapability.STDIN),
        )


def test_admission_rejects_nonzero_success_contract(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(
            ShellCommand("python", allowed_returncodes=frozenset({0, 2})),
            grant(ShellCapability.EXECUTE, ShellCapability.NONZERO_SUCCESS),
        )


def test_admission_rejects_command_timeout_over_definition(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    with pytest.raises(Exception):
        admission.admit(ShellCommand("python", timeout=11), grant())


def test_admission_inspect_turns_denial_into_safe_decision(tmp_path):
    admission = CommandAdmission(catalog(tmp_path))
    decision = admission.inspect(ShellCommand("python", ("--bad",)), grant())
    assert not decision.allowed
    assert "option" in decision.reason


def test_preflight_reports_multiple_commands_without_execution(tmp_path):
    analyzer = PreflightAnalyzer(CommandAdmission(catalog(tmp_path)))
    report = analyzer.commands(
        [
            ("good", ShellCommand("python", ("-q",))),
            ("bad", ShellCommand("python", ("--bad",))),
        ],
        grant(),
    )
    assert not report.allowed
    assert report.command_counts == {"python": 2}
    assert report.total_arguments == 2
    assert [item.allowed for item in report.items] == [True, False]
