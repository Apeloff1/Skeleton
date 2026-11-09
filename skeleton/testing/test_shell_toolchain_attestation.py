"""Executable attestation regressions for compiled toolchains."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys

import pytest

from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint
from skeleton.shells.toolchains.attestation import (
    AttestedToolchainExecutionPlane,
    ExecutableAttestationError,
    ExecutableAttestationPolicy,
    ExecutableAttestor,
    attest_compiled_toolchain,
)
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.compiler import (
    ToolchainCompilerLimits,
    compile_toolchain,
)
from skeleton.shells.toolchains.execution import (
    ToolchainExecutionPlane,
    ToolchainInvocation,
)
from skeleton.shells.toolchains.types import (
    CommandEffect,
    CommandRisk,
    LogicalCommandContract,
)


def _copy_executable(tmp_path: Path) -> Path:
    target = tmp_path / "python-copy"
    shutil.copy2(Path(sys.executable).resolve(), target)
    target.chmod(0o755)
    return target


def _contract() -> LogicalCommandContract:
    script = ValueConstraint(
        pattern=r"[^\x00\r\n]{1,4096}",
        min_length=1,
        max_length=4096,
    )
    return LogicalCommandContract(
        name="test.python",
        executable_key="python",
        arguments=ArgumentPolicy(
            options={
                "-c": OptionRule(
                    "-c",
                    takes_value=True,
                    value=script,
                )
            },
            min_positionals=0,
            max_positionals=0,
        ),
        max_timeout=2.0,
        effects=frozenset({CommandEffect.PROCESS}),
        risk=CommandRisk.LOW,
        tags=frozenset({"test", "attestation"}),
    )


def _compiled(tmp_path: Path, executable: Path):
    return compile_toolchain(
        ToolchainCatalog((_contract(),)),
        executable_paths={"python": str(executable)},
        cwd_roots=(tmp_path,),
        limits=ToolchainCompilerLimits(
            default_timeout=1.0,
            absolute_max_timeout=5.0,
            max_output_bytes=1024 * 1024,
            large_output_threshold_bytes=2 * 1024 * 1024,
        ),
    )


def test_attestor_captures_content_digest(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestation = ExecutableAttestor().capture("python", executable)
    assert attestation.executable_key == "python"
    assert attestation.size == executable.stat().st_size
    assert len(attestation.sha256) == 64
    assert Path(attestation.resolved_path) == executable.resolve()


def test_attestation_public_dict_redacts_paths(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestation = ExecutableAttestor().capture("python", executable)
    payload = attestation.to_dict()
    assert "requested_path" not in payload
    assert "resolved_path" not in payload
    assert str(executable) not in repr(payload)


def test_attestation_can_include_paths_for_operator_evidence(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestation = ExecutableAttestor().capture("python", executable)
    payload = attestation.to_dict(include_paths=True)
    assert payload["requested_path"] == str(executable)
    assert payload["resolved_path"] == str(executable.resolve())


def test_attestor_rejects_relative_path(tmp_path: Path, monkeypatch):
    executable = _copy_executable(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ExecutableAttestationError, match="absolute path"):
        ExecutableAttestor().capture("python", executable.name)


def test_attestor_rejects_world_writable_executable(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    executable.chmod(0o777)
    with pytest.raises(ExecutableAttestationError, match="world-writable"):
        ExecutableAttestor().capture("python", executable)


def test_attestor_can_optionally_reject_group_writable_executable(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    executable.chmod(0o775)
    attestor = ExecutableAttestor(
        ExecutableAttestationPolicy(reject_group_writable=True)
    )
    with pytest.raises(ExecutableAttestationError, match="group-writable"):
        attestor.capture("python", executable)


def test_attestor_rejects_non_executable_regular_file(tmp_path: Path):
    target = tmp_path / "plain"
    target.write_bytes(b"not executable")
    target.chmod(0o644)
    with pytest.raises(ExecutableAttestationError, match="not executable"):
        ExecutableAttestor().capture("plain", target)


def test_attestor_respects_binary_size_bound(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor(
        ExecutableAttestationPolicy(max_binary_bytes=1)
    )
    with pytest.raises(ExecutableAttestationError, match="byte bound"):
        attestor.capture("python", executable)


def test_verify_accepts_unchanged_executable(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor()
    captured = attestor.capture("python", executable)
    verification = attestor.verify(captured)
    assert verification.valid
    assert verification.reasons == ()
    assert verification.actual_sha256 == captured.sha256


def test_verify_detects_same_inode_content_mutation(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor()
    captured = attestor.capture("python", executable)

    with executable.open("r+b") as handle:
        first = handle.read(1)
        handle.seek(0)
        handle.write(b"X" if first != b"X" else b"Y")
        handle.flush()
        os.fsync(handle.fileno())

    verification = attestor.verify(captured)
    assert not verification.valid
    assert "content digest changed" in verification.reasons


def test_verify_detects_executable_replacement(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor()
    captured = attestor.capture("python", executable)

    replacement = tmp_path / "replacement"
    shutil.copy2(Path(sys.executable).resolve(), replacement)
    replacement.chmod(0o755)
    os.replace(replacement, executable)

    verification = attestor.verify(captured)
    assert not verification.valid
    assert "inode changed" in verification.reasons


def test_attestation_set_is_deterministic_for_same_files(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor()
    first = attestor.capture_many({"python": str(executable)})
    second = attestor.capture_many({"python": str(executable)})
    assert first.digest == second.digest
    assert first.names() == ("python",)


def test_attestation_set_verifies_all_members(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor()
    values = attestor.capture_many({"python": str(executable)})
    checks = attestor.verify_set(values)
    assert len(checks) == 1
    assert checks[0].valid
    attestor.require_set(values)


def test_attest_compiled_toolchain_uses_executable_keys(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    compiled = _compiled(tmp_path, executable)
    attestations = attest_compiled_toolchain(compiled)
    assert attestations.names() == ("python",)
    assert attestations.get("python").sha256


def test_attested_execution_succeeds_when_binary_is_unchanged(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    compiled = _compiled(tmp_path, executable)
    base = ToolchainExecutionPlane(compiled)
    attestations = attest_compiled_toolchain(compiled)
    plane = AttestedToolchainExecutionPlane(base, attestations)

    result = plane.execute(
        ToolchainInvocation(
            "test.python",
            ("-c", "print('attested')"),
            timeout=1.0,
        )
    )
    assert result.ok
    assert result.outcome.result.stdout_text().strip() == "attested"


def test_attested_execution_fails_closed_after_binary_mutation(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    compiled = _compiled(tmp_path, executable)
    base = ToolchainExecutionPlane(compiled)
    attestations = attest_compiled_toolchain(compiled)
    plane = AttestedToolchainExecutionPlane(base, attestations)

    with executable.open("r+b") as handle:
        first = handle.read(1)
        handle.seek(0)
        handle.write(b"X" if first != b"X" else b"Y")
        handle.flush()
        os.fsync(handle.fileno())

    with pytest.raises(ExecutableAttestationError, match="attestation failed"):
        plane.execute(
            ToolchainInvocation(
                "test.python",
                ("-c", "print('must-not-run')"),
                timeout=1.0,
            )
        )


def test_attested_plane_verifies_only_selected_contract_binary(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    compiled = _compiled(tmp_path, executable)
    base = ToolchainExecutionPlane(compiled)
    attestations = attest_compiled_toolchain(compiled)
    plane = AttestedToolchainExecutionPlane(base, attestations)
    verification = plane.verify_contract("test.python")
    assert verification.valid


def test_verification_require_raises_with_reasons(tmp_path: Path):
    executable = _copy_executable(tmp_path)
    attestor = ExecutableAttestor()
    captured = attestor.capture("python", executable)
    executable.chmod(0o777)
    verification = attestor.verify(captured)
    assert not verification.valid
    with pytest.raises(ExecutableAttestationError):
        verification.require()
