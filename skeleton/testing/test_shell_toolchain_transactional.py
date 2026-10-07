"""End-to-end transactional toolchain execution regressions."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.compiler import (
    ToolchainCompilerLimits,
    compile_toolchain,
)
from skeleton.shells.toolchains.execution import (
    ToolchainExecutionPlane,
    ToolchainInvocation,
)
from skeleton.shells.toolchains.transactional import (
    ToolchainMutationPolicyRouter,
    TransactionalToolchainError,
    TransactionalToolchainExecutionPlane,
    zero_mutation_policy,
)
from skeleton.shells.toolchains.types import (
    CommandEffect,
    CommandRisk,
    LogicalCommandContract,
)
from skeleton.shells.workspace_txn.backup import ContentAddressedBackupStore
from skeleton.shells.workspace_txn.scanner import WorkspaceScanner
from skeleton.shells.workspace_txn.transaction import WorkspaceTransactionManager


def _contract(
    name: str,
    effects: frozenset[CommandEffect],
) -> LogicalCommandContract:
    script = ValueConstraint(
        pattern=r"[^\x00\r\n]{1,4096}",
        min_length=1,
        max_length=4096,
    )
    return LogicalCommandContract(
        name=name,
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
        effects=effects,
        risk=CommandRisk.LOW,
        tags=frozenset({"transaction-test"}),
    )


def _plane(
    tmp_path: Path,
    *contracts: LogicalCommandContract,
) -> tuple[Path, TransactionalToolchainExecutionPlane]:
    root = tmp_path / "workspace"
    root.mkdir()
    backup = tmp_path / "backups"
    compiled = compile_toolchain(
        ToolchainCatalog(contracts),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(root,),
        limits=ToolchainCompilerLimits(
            default_timeout=1.0,
            absolute_max_timeout=5.0,
            max_output_bytes=1024 * 1024,
            large_output_threshold_bytes=2 * 1024 * 1024,
        ),
    )
    base = ToolchainExecutionPlane(compiled)
    manager = WorkspaceTransactionManager(
        compiled.executor,
        scanner=WorkspaceScanner(),
        backup_store=ContentAddressedBackupStore(backup),
    )
    return root, TransactionalToolchainExecutionPlane(base, manager)


def test_zero_mutation_policy_rejects_any_change(tmp_path: Path):
    root, plane = _plane(
        tmp_path,
        _contract("test.read", frozenset({CommandEffect.READ})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            (
                "-c",
                "from pathlib import Path; Path('unexpected.txt').write_text('x')",
            ),
            timeout=1.0,
        )
    )
    assert result.execution_ok
    assert not result.policy_allowed
    assert result.rolled_back
    assert result.transaction.reverted
    assert not (root / "unexpected.txt").exists()
    assert result.mutation_policy_name == "toolchain-zero-mutation"


def test_read_contract_without_changes_is_accepted(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract("test.read", frozenset({CommandEffect.READ})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            ("-c", "print('read-only')"),
            timeout=1.0,
        )
    )
    assert result.ok
    assert result.execution_ok
    assert result.policy_allowed
    assert not result.rolled_back


def test_source_write_contract_is_accepted(tmp_path: Path):
    root, plane = _plane(
        tmp_path,
        _contract("test.write", frozenset({CommandEffect.WRITE})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.write",
            (
                "-c",
                "from pathlib import Path; Path('source.txt').write_text('hello')",
            ),
            timeout=1.0,
        )
    )
    assert result.ok
    assert result.mutation_policy_name == "source-edit"
    assert (root / "source.txt").read_text(encoding="utf-8") == "hello"


def test_source_write_to_protected_dotenv_is_rolled_back(tmp_path: Path):
    root, plane = _plane(
        tmp_path,
        _contract("test.write", frozenset({CommandEffect.WRITE})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.write",
            (
                "-c",
                "from pathlib import Path; Path('.env').write_text('SECRET=value')",
            ),
            timeout=1.0,
        )
    )
    assert result.execution_ok
    assert not result.policy_allowed
    assert result.rolled_back
    assert not (root / ".env").exists()


def test_build_write_routes_to_generated_output_policy(tmp_path: Path):
    root, plane = _plane(
        tmp_path,
        _contract(
            "test.build",
            frozenset({CommandEffect.BUILD, CommandEffect.WRITE}),
        ),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.build",
            (
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('build').mkdir(); "
                    "Path('build/out.bin').write_bytes(b'abc')"
                ),
            ),
            timeout=1.0,
        )
    )
    assert result.ok
    assert result.mutation_policy_name == "generated-output"
    assert (root / "build/out.bin").read_bytes() == b"abc"


def test_package_write_routes_to_generated_output_policy(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract(
            "test.package",
            frozenset({CommandEffect.PACKAGE, CommandEffect.WRITE}),
        ),
    )
    explanation = plane.explain("test.package")
    assert explanation["transaction"]["policy_name"] == "generated-output"


def test_format_write_routes_to_source_edit_policy(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract(
            "test.format",
            frozenset({CommandEffect.FORMAT, CommandEffect.WRITE}),
        ),
    )
    explanation = plane.explain("test.format")
    assert explanation["transaction"]["policy_name"] == "source-edit"


def test_lint_contract_routes_to_zero_mutation_policy(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract(
            "test.lint",
            frozenset({CommandEffect.LINT}),
        ),
    )
    explanation = plane.explain("test.lint")
    assert explanation["transaction"]["policy_name"] == "toolchain-zero-mutation"


def test_explicit_router_override_takes_precedence(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    backup = tmp_path / "backups"
    contract = _contract("test.write", frozenset({CommandEffect.WRITE}))
    compiled = compile_toolchain(
        ToolchainCatalog((contract,)),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(root,),
        limits=ToolchainCompilerLimits(
            default_timeout=1.0,
            absolute_max_timeout=5.0,
            max_output_bytes=1024 * 1024,
            large_output_threshold_bytes=2 * 1024 * 1024,
        ),
    )
    base = ToolchainExecutionPlane(compiled)
    manager = WorkspaceTransactionManager(
        compiled.executor,
        scanner=WorkspaceScanner(),
        backup_store=ContentAddressedBackupStore(backup),
    )
    router = ToolchainMutationPolicyRouter(
        explicit={"test.write": zero_mutation_policy()}
    )
    plane = TransactionalToolchainExecutionPlane(
        base,
        manager,
        router=router,
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.write",
            (
                "-c",
                "from pathlib import Path; Path('write.txt').write_text('x')",
            ),
            timeout=1.0,
        )
    )
    assert result.rolled_back
    assert not (root / "write.txt").exists()
    assert result.mutation_policy_name == "toolchain-zero-mutation"


def test_transaction_plane_requires_same_executor(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    backup = tmp_path / "backups"
    contract = _contract("test.read", frozenset({CommandEffect.READ}))
    first = compile_toolchain(
        ToolchainCatalog((contract,)),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(root,),
    )
    second = compile_toolchain(
        ToolchainCatalog((contract,)),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(root,),
    )
    manager = WorkspaceTransactionManager(
        second.executor,
        scanner=WorkspaceScanner(),
        backup_store=ContentAddressedBackupStore(backup),
    )
    with pytest.raises(TransactionalToolchainError, match="compiled toolchain executor"):
        TransactionalToolchainExecutionPlane(
            ToolchainExecutionPlane(first),
            manager,
        )


def test_transaction_metadata_binds_contract_identity(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract("test.read", frozenset({CommandEffect.READ})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            ("-c", "print('metadata')"),
            timeout=1.0,
        )
    )
    metadata = result.transaction.receipt.metadata
    assert metadata["toolchain_contract"] == "test.read"
    assert metadata["toolchain_executable_key"] == "python"
    assert metadata["mutation_policy"] == "toolchain-zero-mutation"


def test_transaction_and_execution_share_correlation_id(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract("test.read", frozenset({CommandEffect.READ})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            ("-c", "print('correlation')"),
            timeout=1.0,
            correlation_id="fixed-correlation",
        )
    )
    assert result.prepared.correlation_id == "fixed-correlation"
    assert result.transaction.receipt.correlation_id == "fixed-correlation"
    assert result.transaction.execution.correlation_id == "fixed-correlation"


def test_transaction_result_serializes_policy_evidence(tmp_path: Path):
    _, plane = _plane(
        tmp_path,
        _contract("test.read", frozenset({CommandEffect.READ})),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            ("-c", "print('serialize')"),
            timeout=1.0,
        )
    )
    payload = result.to_dict()
    assert payload["contract"] == "test.read"
    assert len(payload["mutation_policy_digest"]) == 64
    assert payload["transaction"]["decision"]["allowed"] is True
