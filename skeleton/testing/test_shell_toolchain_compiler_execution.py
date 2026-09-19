"""End-to-end tests for compiled logical toolchain authority."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest

from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.errors import ArgumentRejected, EnvironmentRejected
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.runner import ShellCommand
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.compiler import (
    CommandEnvironmentPolicySet,
    ToolchainAuthorityPolicy,
    ToolchainCompileError,
    ToolchainCompilerLimits,
    compile_toolchain,
)
from skeleton.shells.toolchains.execution import (
    ToolchainExecutionPlane,
    ToolchainInvocation,
    ToolchainInvocationError,
)
from skeleton.shells.toolchains.manifest import (
    build_authority_manifest,
    diff_authority_manifests,
    require_no_authority_widening,
    verify_authority_manifest,
)
from skeleton.shells.toolchains.types import (
    CommandEffect,
    CommandRisk,
    LogicalCommandContract,
)


def _python_contract(
    name: str = "test.python",
    *,
    env_key: str | None = None,
    risk: CommandRisk = CommandRisk.LOW,
    effects: frozenset[CommandEffect] = frozenset({CommandEffect.PROCESS}),
    max_timeout: float = 2.0,
    allow_stdin: bool = False,
    allow_nonzero_success: bool = False,
) -> LogicalCommandContract:
    script = ValueConstraint(
        pattern=r"[^\x00\r\n]{1,4096}",
        min_length=1,
        max_length=4096,
    )
    arguments = ArgumentPolicy(
        options={
            "-c": OptionRule(
                "-c",
                takes_value=True,
                value=script,
            )
        },
        min_positionals=0,
        max_positionals=0,
        max_total_args=2,
        max_total_bytes=8192,
    )
    if env_key is None:
        environment = EnvironmentPolicy.empty()
    else:
        environment = EnvironmentPolicy(
            rules={
                env_key: EnvironmentValueRule(
                    pattern=r"[^\x00\r\n]{0,128}",
                    max_bytes=128,
                )
            }
        )
    return LogicalCommandContract(
        name=name,
        executable_key="python",
        arguments=arguments,
        environment=environment,
        max_timeout=max_timeout,
        allow_stdin=allow_stdin,
        allow_nonzero_success=allow_nonzero_success,
        effects=effects,
        risk=risk,
        tags=frozenset({"test", "python"}),
        description="Synthetic python contract for compiler integration tests.",
    )


def _compile(tmp_path: Path, *contracts: LogicalCommandContract, receipts=None):
    return compile_toolchain(
        ToolchainCatalog(contracts or (_python_contract(),)),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(tmp_path,),
        limits=ToolchainCompilerLimits(
            default_timeout=1.0,
            absolute_max_timeout=10.0,
            max_output_bytes=1024 * 1024,
            large_output_threshold_bytes=2 * 1024 * 1024,
        ),
        receipt_chain=receipts,
    )


def test_compile_builds_logical_executable_mapping(tmp_path: Path):
    compiled = _compile(tmp_path, _python_contract())
    policy = compiled.runner_policy()
    assert tuple(policy.executables) == ("test.python",)
    assert Path(policy.executables["test.python"]) == Path(sys.executable).resolve()


def test_compile_builds_argument_policy_set(tmp_path: Path):
    compiled = _compile(tmp_path, _python_contract())
    validated = compiled.arguments.validate(
        "test.python",
        ("-c", "print('ok')"),
    )
    assert validated == ("-c", "print('ok')")


def test_compile_builds_per_command_environment_router(tmp_path: Path):
    contract = _python_contract(env_key="SAFE_ENV")
    compiled = _compile(tmp_path, contract)
    built = compiled.environments.build(
        contract.name,
        {"SAFE_ENV": "present"},
    )
    assert built["SAFE_ENV"] == "present"


def test_environment_router_rejects_unknown_command():
    router = CommandEnvironmentPolicySet({})
    with pytest.raises(ToolchainCompileError):
        router.build("missing", {})


def test_compile_rejects_missing_executable_binding(tmp_path: Path):
    with pytest.raises(ToolchainCompileError, match="missing executable binding"):
        compile_toolchain(
            ToolchainCatalog((_python_contract(),)),
            executable_paths={},
            cwd_roots=(tmp_path,),
        )


def test_compile_rejects_empty_workspace_roots():
    with pytest.raises(ToolchainCompileError, match="workspace root"):
        compile_toolchain(
            ToolchainCatalog((_python_contract(),)),
            executable_paths={"python": str(Path(sys.executable).resolve())},
            cwd_roots=(),
        )


def test_compile_rejects_contract_timeout_over_absolute_bound(tmp_path: Path):
    contract = _python_contract(max_timeout=11.0)
    with pytest.raises(ToolchainCompileError, match="timeout exceeds"):
        compile_toolchain(
            ToolchainCatalog((contract,)),
            executable_paths={"python": str(Path(sys.executable).resolve())},
            cwd_roots=(tmp_path,),
            limits=ToolchainCompilerLimits(
                default_timeout=1.0,
                absolute_max_timeout=10.0,
            ),
        )


def test_authority_policy_accepts_effect_enums():
    contract = _python_contract(effects=frozenset({CommandEffect.PROCESS}))
    policy = ToolchainAuthorityPolicy(
        max_risk=CommandRisk.LOW,
        allow_effects=frozenset({CommandEffect.PROCESS}),
    )
    assert policy.accepts(contract)


def test_authority_policy_denies_unlisted_effect():
    contract = _python_contract(effects=frozenset({CommandEffect.PROCESS}))
    policy = ToolchainAuthorityPolicy(
        max_risk=CommandRisk.LOW,
        allow_effects=frozenset({CommandEffect.READ}),
    )
    assert not policy.accepts(contract)


def test_authority_policy_denies_higher_risk():
    contract = _python_contract(risk=CommandRisk.HIGH)
    policy = ToolchainAuthorityPolicy(max_risk=CommandRisk.MODERATE)
    assert not policy.accepts(contract)


def test_authority_policy_denies_explicit_name():
    contract = _python_contract()
    policy = ToolchainAuthorityPolicy(
        max_risk=CommandRisk.HIGH,
        denied_names=frozenset({contract.name}),
    )
    assert not policy.accepts(contract)


def test_compile_authority_filter_can_empty_selection(tmp_path: Path):
    contract = _python_contract(risk=CommandRisk.HIGH)
    with pytest.raises(ToolchainCompileError, match="selection is empty"):
        compile_toolchain(
            ToolchainCatalog((contract,)),
            executable_paths={"python": str(Path(sys.executable).resolve())},
            cwd_roots=(tmp_path,),
            authority=ToolchainAuthorityPolicy(max_risk=CommandRisk.LOW),
        )


def test_execution_plane_prepares_bounded_command(tmp_path: Path):
    compiled = _compile(tmp_path, _python_contract())
    plane = ToolchainExecutionPlane(compiled)
    prepared = plane.prepare(
        ToolchainInvocation(
            "test.python",
            ("-c", "print('ok')"),
            timeout=1.0,
        )
    )
    assert prepared.command.command == "test.python"
    assert prepared.command.args == ("-c", "print('ok')")
    assert prepared.command.cwd == tmp_path.resolve()
    assert prepared.command.timeout == 1.0


def test_execution_plane_executes_through_shell_executor(tmp_path: Path):
    receipts = ReceiptChain()
    compiled = _compile(
        tmp_path,
        _python_contract(),
        receipts=receipts,
    )
    result = ToolchainExecutionPlane(compiled).execute(
        ToolchainInvocation(
            "test.python",
            ("-c", "print('compiled-toolchain')"),
            timeout=1.0,
        )
    )
    assert result.ok
    assert result.outcome.result.stdout_text().strip() == "compiled-toolchain"
    assert result.outcome.final_receipt.command == "test.python"
    assert receipts.verify()
    assert len(receipts.snapshot()) == 1


def test_execution_plane_rejects_unknown_contract(tmp_path: Path):
    plane = ToolchainExecutionPlane(_compile(tmp_path, _python_contract()))
    with pytest.raises(KeyError):
        plane.prepare(ToolchainInvocation("missing", ()))


def test_execution_plane_rejects_unknown_option(tmp_path: Path):
    plane = ToolchainExecutionPlane(_compile(tmp_path, _python_contract()))
    with pytest.raises(ArgumentRejected):
        plane.prepare(
            ToolchainInvocation(
                "test.python",
                ("--unknown",),
            )
        )


def test_execution_plane_rejects_timeout_widening(tmp_path: Path):
    plane = ToolchainExecutionPlane(_compile(tmp_path, _python_contract()))
    with pytest.raises(ToolchainInvocationError, match="contract maximum"):
        plane.prepare(
            ToolchainInvocation(
                "test.python",
                ("-c", "print(1)"),
                timeout=3.0,
            )
        )


def test_execution_plane_rejects_stdin_when_contract_denies(tmp_path: Path):
    plane = ToolchainExecutionPlane(_compile(tmp_path, _python_contract()))
    with pytest.raises(ToolchainInvocationError, match="stdin"):
        plane.prepare(
            ToolchainInvocation(
                "test.python",
                ("-c", "print(1)"),
                stdin=b"payload",
            )
        )


def test_execution_plane_allows_stdin_when_contract_allows(tmp_path: Path):
    contract = _python_contract(allow_stdin=True)
    plane = ToolchainExecutionPlane(_compile(tmp_path, contract))
    prepared = plane.prepare(
        ToolchainInvocation(
            contract.name,
            ("-c", "print('ok')"),
            stdin=b"payload",
        )
    )
    assert prepared.command.stdin == b"payload"


def test_execution_plane_rejects_nonzero_success_when_contract_denies(tmp_path: Path):
    plane = ToolchainExecutionPlane(_compile(tmp_path, _python_contract()))
    with pytest.raises(ToolchainInvocationError, match="non-zero"):
        plane.prepare(
            ToolchainInvocation(
                "test.python",
                ("-c", "raise SystemExit(7)"),
                allowed_returncodes=frozenset({0, 7}),
            )
        )


def test_execution_plane_allows_nonzero_success_when_contract_allows(tmp_path: Path):
    contract = _python_contract(allow_nonzero_success=True)
    plane = ToolchainExecutionPlane(_compile(tmp_path, contract))
    result = plane.execute(
        ToolchainInvocation(
            contract.name,
            ("-c", "raise SystemExit(7)"),
            allowed_returncodes=frozenset({7}),
        )
    )
    assert result.ok
    assert result.outcome.result.returncode == 7


def test_execution_plane_rejects_cwd_escape(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    compiled = compile_toolchain(
        ToolchainCatalog((_python_contract(),)),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(root,),
    )
    plane = ToolchainExecutionPlane(compiled)
    with pytest.raises(ToolchainInvocationError, match="outside compiled roots"):
        plane.prepare(
            ToolchainInvocation(
                "test.python",
                ("-c", "print(1)"),
                cwd=outside,
            )
        )


def test_executor_preserves_per_command_environment_isolation(tmp_path: Path):
    first = _python_contract("test.first", env_key="FIRST_ENV")
    second = _python_contract("test.second", env_key="SECOND_ENV")
    compiled = _compile(tmp_path, first, second)
    with pytest.raises(EnvironmentRejected):
        compiled.executor.execute(
            ShellCommand(
                "test.first",
                ("-c", "print(1)"),
                cwd=tmp_path,
                env={"SECOND_ENV": "cross-command-leak"},
                timeout=1.0,
            )
        )


def test_execution_plane_explain_is_redacted_from_absolute_path(tmp_path: Path):
    compiled = _compile(tmp_path, _python_contract())
    explanation = ToolchainExecutionPlane(compiled).explain("test.python")
    assert explanation["executable_key"] == "python"
    assert str(Path(sys.executable).resolve()) not in repr(explanation)


def test_manifest_is_deterministic():
    contract = _python_contract()
    first = build_authority_manifest((contract,))
    second = build_authority_manifest((contract,))
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()
    assert verify_authority_manifest(first)


def test_manifest_diff_detects_added_contract():
    first = build_authority_manifest((_python_contract("test.one"),))
    second = build_authority_manifest(
        (
            _python_contract("test.one"),
            _python_contract("test.two"),
        )
    )
    diff = diff_authority_manifests(first, second)
    assert diff.added == ("test.two",)
    assert diff.widening


def test_manifest_diff_treats_removal_as_narrowing():
    first = build_authority_manifest(
        (
            _python_contract("test.one"),
            _python_contract("test.two"),
        )
    )
    second = build_authority_manifest((_python_contract("test.one"),))
    diff = diff_authority_manifests(first, second)
    assert diff.removed == ("test.two",)
    assert diff.narrowing_only
    assert not diff.widening


def test_manifest_diff_detects_risk_widening():
    low = _python_contract(risk=CommandRisk.LOW)
    high = replace(low, risk=CommandRisk.HIGH)
    diff = diff_authority_manifests(
        build_authority_manifest((low,)),
        build_authority_manifest((high,)),
    )
    assert diff.widening
    assert diff.changed[0].widening
    assert "risk" in diff.changed[0].widening_fields


def test_manifest_diff_detects_timeout_widening():
    short = _python_contract(max_timeout=1.0)
    long = replace(short, max_timeout=2.0)
    diff = diff_authority_manifests(
        build_authority_manifest((short,)),
        build_authority_manifest((long,)),
    )
    assert diff.widening
    assert "max_timeout" in diff.changed[0].widening_fields


def test_manifest_diff_detects_stdin_widening():
    denied = _python_contract(allow_stdin=False)
    allowed = replace(denied, allow_stdin=True)
    diff = diff_authority_manifests(
        build_authority_manifest((denied,)),
        build_authority_manifest((allowed,)),
    )
    assert diff.widening
    assert "allow_stdin" in diff.changed[0].widening_fields


def test_manifest_diff_detects_environment_widening():
    before = _python_contract()
    after = _python_contract(env_key="SAFE_ENV")
    diff = diff_authority_manifests(
        build_authority_manifest((before,)),
        build_authority_manifest((after,)),
    )
    assert diff.widening
    assert "environment_keys" in diff.changed[0].widening_fields


def test_manifest_requires_explicit_approval_for_widening():
    first = build_authority_manifest((_python_contract("test.one"),))
    second = build_authority_manifest(
        (
            _python_contract("test.one"),
            _python_contract("test.two"),
        )
    )
    with pytest.raises(RuntimeError, match="explicit approval"):
        require_no_authority_widening(first, second)


def test_manifest_allows_pure_removal():
    first = build_authority_manifest(
        (
            _python_contract("test.one"),
            _python_contract("test.two"),
        )
    )
    second = build_authority_manifest((_python_contract("test.one"),))
    diff = require_no_authority_widening(first, second)
    assert diff.narrowing_only
