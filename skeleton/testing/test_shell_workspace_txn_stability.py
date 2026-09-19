"""Stability regressions for long-lived workspace transactions and rollback."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import sys
import time

import pytest

from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.compiler import ToolchainCompilerLimits, compile_toolchain
from skeleton.shells.toolchains.execution import ToolchainExecutionPlane, ToolchainInvocation
from skeleton.shells.toolchains.transactional import (
    TransactionalToolchainExecutionPlane,
    zero_mutation_policy,
)
from skeleton.shells.toolchains.types import (
    CommandEffect,
    CommandRisk,
    LogicalCommandContract,
)
from skeleton.shells.workspace_txn.backup import BackupError, ContentAddressedBackupStore
from skeleton.shells.workspace_txn.lease import (
    WorkspaceLeaseHeartbeat,
    WorkspaceLeaseRegistry,
)
from skeleton.shells.workspace_txn.journal import TransactionJournal
from skeleton.shells.workspace_txn.recovery import TransactionRecoveryInspector
from skeleton.shells.workspace_txn.scanner import WorkspaceScanner
from skeleton.shells.workspace_txn.transaction import (
    TransactionConfig,
    WorkspaceTransactionManager,
)
from skeleton.shells.workspace_txn.types import (
    RollbackReport,
    WorkspaceTransactionState,
)


def _contract(name: str = "test.read") -> LogicalCommandContract:
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
        max_timeout=5.0,
        effects=frozenset({CommandEffect.READ}),
        risk=CommandRisk.LOW,
        tags=frozenset({"transaction-stability"}),
    )


def _manager(
    tmp_path: Path,
    *,
    config: TransactionConfig | None = None,
    backup_inside_workspace: bool = False,
):
    root = tmp_path / "workspace"
    root.mkdir()
    backup = root / ".backup" if backup_inside_workspace else tmp_path / "backup"
    contract = _contract()
    compiled = compile_toolchain(
        ToolchainCatalog((contract,)),
        executable_paths={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(root,),
        limits=ToolchainCompilerLimits(
            default_timeout=1.0,
            absolute_max_timeout=10.0,
            max_output_bytes=1024 * 1024,
            large_output_threshold_bytes=2 * 1024 * 1024,
        ),
    )
    manager = WorkspaceTransactionManager(
        compiled.executor,
        scanner=WorkspaceScanner(),
        backup_store=ContentAddressedBackupStore(backup),
        config=config,
    )
    plane = TransactionalToolchainExecutionPlane(
        ToolchainExecutionPlane(compiled),
        manager,
    )
    return root, manager, plane


def test_transaction_config_rejects_renew_interval_at_or_above_ttl():
    with pytest.raises(ValueError, match="below lease ttl"):
        TransactionConfig(
            lease_ttl_seconds=1.0,
            lease_renew_interval_seconds=1.0,
        )


def test_transaction_config_rejects_nonpositive_renew_interval():
    with pytest.raises(ValueError, match="positive"):
        TransactionConfig(
            lease_ttl_seconds=1.0,
            lease_renew_interval_seconds=0.0,
        )


def test_lease_heartbeat_keeps_short_ttl_alive():
    registry = WorkspaceLeaseRegistry()
    lease = registry.acquire("workspace", "owner", ttl_seconds=0.15)
    heartbeat = WorkspaceLeaseHeartbeat(
        registry,
        lease,
        ttl_seconds=0.15,
        interval_seconds=0.03,
    ).start()
    try:
        time.sleep(0.35)
        assert heartbeat.require_healthy().lease_id == lease.lease_id
        assert registry.active("workspace") is not None
    finally:
        heartbeat.stop()
        registry.release(lease)


def test_lease_heartbeat_context_manager_stops_cleanly():
    registry = WorkspaceLeaseRegistry()
    lease = registry.acquire("workspace", "owner", ttl_seconds=1.0)
    with WorkspaceLeaseHeartbeat(
        registry,
        lease,
        ttl_seconds=1.0,
        interval_seconds=0.05,
    ) as heartbeat:
        assert heartbeat.running
        heartbeat.require_healthy()
    assert not heartbeat.running
    registry.release(lease)


def test_transaction_survives_command_longer_than_original_lease_ttl(tmp_path: Path):
    root, _, plane = _manager(
        tmp_path,
        config=TransactionConfig(
            lease_ttl_seconds=0.12,
            lease_renew_interval_seconds=0.03,
        ),
    )
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            (
                "-c",
                "import time; time.sleep(0.30); print('alive')",
            ),
            cwd=root,
            timeout=1.0,
        )
    )
    assert result.ok
    assert result.transaction.execution.result.stdout_text().strip() == "alive"


def test_backup_store_inside_workspace_is_rejected_before_execution(tmp_path: Path):
    root, manager, plane = _manager(
        tmp_path,
        backup_inside_workspace=True,
    )
    marker = root / "must-not-exist.txt"
    with pytest.raises(BackupError, match="outside"):
        plane.execute(
            ToolchainInvocation(
                "test.read",
                (
                    "-c",
                    (
                        "from pathlib import Path; "
                        "Path('must-not-exist.txt').write_text('bad')"
                    ),
                ),
                cwd=root,
                timeout=1.0,
            )
        )
    assert not marker.exists()
    assert manager.journal.length() == 0


def test_rollback_restores_existing_file_bytes_and_mtime(tmp_path: Path):
    root, _, plane = _manager(tmp_path)
    target = root / "existing.txt"
    target.write_text("before", encoding="utf-8")
    stamp = 1_700_000_000_123_456_789
    os.utime(target, ns=(stamp, stamp))
    before_mtime = target.stat().st_mtime_ns

    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            (
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('existing.txt').write_text('after')"
                ),
            ),
            cwd=root,
            timeout=1.0,
        )
    )

    assert result.rolled_back
    assert result.transaction.rollback is not None
    assert result.transaction.rollback.ok
    assert target.read_text(encoding="utf-8") == "before"
    assert target.stat().st_mtime_ns == before_mtime
    assert result.transaction.rollback.final_snapshot_digest == result.transaction.before.digest


def test_rollback_restores_workspace_root_mtime_after_top_level_create(tmp_path: Path):
    root, _, plane = _manager(tmp_path)
    stamp = 1_700_000_000_987_654_321
    os.utime(root, ns=(stamp, stamp))
    before_mtime = root.stat().st_mtime_ns

    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            (
                "-c",
                "from pathlib import Path; Path('top-level.txt').write_text('unexpected')",
            ),
            cwd=root,
            timeout=1.0,
        )
    )

    assert result.rolled_back
    assert result.transaction.rollback is not None
    assert result.transaction.rollback.ok
    assert not (root / "top-level.txt").exists()
    assert result.transaction.backup is not None
    assert result.transaction.backup.root_mtime_ns == before_mtime
    assert root.stat().st_mtime_ns == before_mtime


def test_backup_manifest_root_metadata_is_integrity_bound(tmp_path: Path):
    root, manager, _ = _manager(tmp_path)
    snapshot = manager.scanner.scan(root)
    manifest = manager.backup_store.create_manifest(root, snapshot)
    assert manager.backup_store.verify_manifest(manifest)
    assert manifest.root_mode is not None
    assert manifest.root_mtime_ns is not None

    tampered = replace(
        manifest,
        root_mtime_ns=manifest.root_mtime_ns + 1,
    )
    assert not manager.backup_store.verify_manifest(tampered)


def test_rollback_restores_parent_directory_mtime_after_created_child(tmp_path: Path):
    root, _, plane = _manager(tmp_path)
    parent = root / "existing"
    parent.mkdir()
    stamp = 1_700_000_001_123_456_789
    os.utime(parent, ns=(stamp, stamp))
    before_mtime = parent.stat().st_mtime_ns

    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            (
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('existing/new.txt').write_text('unexpected')"
                ),
            ),
            cwd=root,
            timeout=1.0,
        )
    )

    assert result.rolled_back
    assert result.transaction.rollback is not None
    assert result.transaction.rollback.ok
    assert not (parent / "new.txt").exists()
    assert parent.stat().st_mtime_ns == before_mtime
    assert result.transaction.rollback.final_snapshot_digest == result.transaction.before.digest


def test_rollback_restores_deleted_file_with_original_mtime(tmp_path: Path):
    root, _, plane = _manager(tmp_path)
    target = root / "delete-me.txt"
    target.write_text("important", encoding="utf-8")
    stamp = 1_700_000_002_123_456_789
    os.utime(target, ns=(stamp, stamp))
    before_mtime = target.stat().st_mtime_ns

    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            (
                "-c",
                "from pathlib import Path; Path('delete-me.txt').unlink()",
            ),
            cwd=root,
            timeout=1.0,
        )
    )

    assert result.rolled_back
    assert result.transaction.rollback is not None
    assert result.transaction.rollback.ok
    assert target.read_text(encoding="utf-8") == "important"
    assert target.stat().st_mtime_ns == before_mtime


def test_terminal_rollback_failure_is_not_overwritten_by_aborted(tmp_path: Path, monkeypatch):
    root, manager, plane = _manager(tmp_path)

    def fail_rollback(root_path, before, changes, manifest):
        return RollbackReport(
            started_at="start",
            finished_at="finish",
            actions=(),
            verified=False,
            before_snapshot_digest=before.digest,
            final_snapshot_digest="0" * 64,
        )

    monkeypatch.setattr(manager.rollback_engine, "rollback", fail_rollback)

    with pytest.raises(RuntimeError, match="did not restore"):
        plane.execute(
            ToolchainInvocation(
                "test.read",
                (
                    "-c",
                    (
                        "from pathlib import Path; "
                        "Path('unexpected.txt').write_text('x')"
                    ),
                ),
                cwd=root,
                timeout=1.0,
            )
        )

    events = manager.journal.events()
    assert events[-1].kind == WorkspaceTransactionState.ROLLBACK_FAILED.value
    assert WorkspaceTransactionState.ABORTED.value not in {
        event.kind for event in events
    }


def test_external_backup_store_remains_valid(tmp_path: Path):
    root, manager, plane = _manager(tmp_path)
    result = plane.execute(
        ToolchainInvocation(
            "test.read",
            ("-c", "print('stable')"),
            cwd=root,
            timeout=1.0,
        )
    )
    assert result.ok
    assert manager.backup_store.storage_root.resolve() not in {
        root,
        *root.parents,
    }


def test_zero_mutation_policy_still_fails_closed(tmp_path: Path):
    policy = zero_mutation_policy()
    assert policy.name == "toolchain-zero-mutation"
    assert policy.fail_on_warning


def test_recovery_treats_rejected_transaction_as_incomplete():
    journal = TransactionJournal()
    transaction_id = "txn-rejected"
    journal.append(
        transaction_id,
        WorkspaceTransactionState.CREATED.value,
        {},
    )
    journal.append(
        transaction_id,
        WorkspaceTransactionState.EXECUTING.value,
        {},
    )
    journal.append(
        transaction_id,
        WorkspaceTransactionState.REVIEWING.value,
        {},
    )
    journal.append(
        transaction_id,
        WorkspaceTransactionState.REJECTED.value,
        {},
    )

    candidates = TransactionRecoveryInspector(journal).candidates()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.transaction_id == transaction_id
    assert candidate.last_state == WorkspaceTransactionState.REJECTED.value
    assert candidate.needs_manual_review
    assert not candidate.safe_to_forget


def test_recovery_terminal_states_match_state_machine():
    terminal = {
        WorkspaceTransactionState.ACCEPTED.value,
        WorkspaceTransactionState.ROLLED_BACK.value,
        WorkspaceTransactionState.ROLLBACK_FAILED.value,
        WorkspaceTransactionState.ABORTED.value,
    }
    for index, state in enumerate(sorted(terminal)):
        journal = TransactionJournal()
        transaction_id = f"terminal-{index}"
        journal.append(transaction_id, state, {})
        assert TransactionRecoveryInspector(journal).candidates() == ()


def test_transaction_rejects_command_cwd_outside_protected_root(tmp_path: Path):
    root, manager, plane = _manager(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="outside compiled roots|inside the protected workspace"):
        plane.execute(
            ToolchainInvocation(
                "test.read",
                ("-c", "print('outside')"),
                cwd=outside,
                timeout=1.0,
            )
        )

    assert manager.journal.length() == 0
    assert root.exists()


def test_transaction_manager_binds_missing_cwd_to_root(tmp_path: Path):
    root, manager, _ = _manager(tmp_path)
    command = manager.executor.runner.policy.executables["test.read"]
    assert command == str(Path(sys.executable).resolve())

    from skeleton.shells.runner import ShellCommand

    result = manager.execute(
        root,
        ShellCommand(
            "test.read",
            ("-c", "print('root-bound')"),
            cwd=None,
            timeout=1.0,
        ),
        policy=zero_mutation_policy(),
    )

    assert result.accepted
    assert result.execution.result.stdout_text().strip() == "root-bound"
    assert result.execution.final_receipt.command == "test.read"
