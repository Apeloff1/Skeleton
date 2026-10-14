#!/usr/bin/env python3
"""Rehearse VOL-005 state migration compatibility against real repositories.

The rehearsal creates deliberately legacy SQLite schemas for the execution,
tool-receipt and quota stores, opens them through the current production
repositories, and proves that schema upgrades preserve pre-upgrade identity and
state while materializing all required current columns.

It also validates state-topology maturity and binds the rehearsal into both the
state-recovery and release migration qualification workflows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Sequence

from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = Path("machine/state_topology.json")
CONSTRUCTION = Path("machine/ai_app_construction.json")
MASTERPLAN = Path("machine/ai_master_plan.json")
RECOVERY_WORKFLOW = Path(".github/workflows/state-recovery-drill.yml")
RELEASE_WORKFLOW = Path(
    ".github/workflows/p1-migration-rollback-compatibility.yml"
)
QUALIFICATION_GAP = (
    "independent exact-head VOL-005 Data & Persistence Closure "
    "qualification remains pending"
)
REQUIRED_VOL005_PATHS = {
    "machine/state_topology.json",
    "machine/state_backup_policy.json",
    "skeleton/persistence",
    "backend/services/database.py",
    "scripts/state_recovery_drill.py",
    "scripts/state_migration_compatibility.py",
    "scripts/verify_state_authority_closure.py",
    ".github/workflows/state-recovery-drill.yml",
    ".github/workflows/p1-migration-rollback-compatibility.yml",
}
REQUIRED_VOL005_TESTS = {
    "skeleton/testing/test_state_recovery_drill.py",
    "skeleton/testing/test_state_migration_compatibility.py",
    "skeleton/testing/test_operation_store.py",
    "backend/tests/test_rag_state_authority.py",
    "tests/test_state_authority_independent_verifier.py",
}
REQUIRED_VOL005_EVALUATIONS = {
    "scripts/state_migration_compatibility.py",
    "scripts/verify_state_authority_closure.py",
    ".github/workflows/state-recovery-drill.yml",
    ".github/workflows/p1-migration-rollback-compatibility.yml",
}


class MigrationCompatibilityError(RuntimeError):
    """VOL-005 migration compatibility could not be rehearsed safely."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationCompatibilityError(
            f"cannot load JSON authority {path}"
        ) from exc
    if not isinstance(value, dict):
        raise MigrationCompatibilityError(f"{path} must contain an object")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _columns(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(str(path))
    try:
        return {
            str(row[1])
            for row in connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }
    finally:
        connection.close()


def _reset(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            sidecar.unlink()


def _request() -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id="legacy-operation",
        execution_id="legacy-execution",
        objective="Preserve legacy execution identity through schema migration.",
        context_policy={"policy": "legacy-compatible"},
        tool_policy={"mode": "scoped"},
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 8,
            "max_repairs": 1,
        },
        stop_policy={"max_turns": 4},
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )


def _legacy_execution_rehearsal(path: Path) -> dict[str, Any]:
    _reset(path)
    request = _request()
    request_json = json.dumps(
        request.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE ai_execution_state (
                namespace TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                identity_digest TEXT NOT NULL,
                request_json TEXT NOT NULL,
                state TEXT NOT NULL,
                version INTEGER NOT NULL,
                latest_turn_index INTEGER NOT NULL,
                checkpoint_version INTEGER NOT NULL,
                cancellation_requested INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(namespace, execution_id),
                UNIQUE(namespace, operation_id, execution_id)
            );

            CREATE TABLE ai_execution_turn (
                namespace TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                parent_turn_id TEXT,
                turn_json TEXT NOT NULL,
                PRIMARY KEY(namespace, execution_id, turn_id),
                UNIQUE(namespace, execution_id, turn_index),
                FOREIGN KEY(namespace, execution_id)
                    REFERENCES ai_execution_state(namespace, execution_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE ai_execution_checkpoint (
                namespace TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                checkpoint_version INTEGER NOT NULL,
                checkpoint_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(namespace, execution_id, checkpoint_version),
                FOREIGN KEY(namespace, execution_id)
                    REFERENCES ai_execution_state(namespace, execution_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE ai_execution_result (
                namespace TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                result_json TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY(namespace, execution_id),
                FOREIGN KEY(namespace, execution_id)
                    REFERENCES ai_execution_state(namespace, execution_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE ai_execution_outbox (
                namespace TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                execution_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                published_at TEXT,
                PRIMARY KEY(namespace, outbox_id),
                UNIQUE(namespace, execution_id, event_type, execution_version),
                FOREIGN KEY(namespace, execution_id)
                    REFERENCES ai_execution_state(namespace, execution_id)
                    ON DELETE CASCADE
            );
            """
        )
        connection.execute(
            """
            INSERT INTO ai_execution_state(
                namespace, execution_id, operation_id, identity_digest,
                request_json, state, version, latest_turn_index,
                checkpoint_version, cancellation_requested, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ai_execution",
                request.execution_id,
                request.operation_id,
                request.identity_digest,
                request_json,
                "created",
                1,
                -1,
                0,
                0,
                "2026-10-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    repository = SQLiteExecutionRepository(path)
    restored = repository.get(request.execution_id)
    repository.close()

    state_columns = _columns(path, "ai_execution_state")
    turn_columns = _columns(path, "ai_execution_turn")
    checkpoint_columns = _columns(path, "ai_execution_checkpoint")
    result_columns = _columns(path, "ai_execution_result")
    outbox_columns = _columns(path, "ai_execution_outbox")

    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute(
            """
            SELECT identity_digest, state_digest, state, version
            FROM ai_execution_state
            WHERE namespace = ? AND execution_id = ?
            """,
            ("ai_execution", request.execution_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise MigrationCompatibilityError(
            "execution migration lost the legacy execution row"
        )
    if restored.request.identity_digest != request.identity_digest:
        raise MigrationCompatibilityError(
            "execution migration changed request identity"
        )
    if row[0] != request.identity_digest:
        raise MigrationCompatibilityError(
            "execution migration changed persisted identity digest"
        )
    if not isinstance(row[1], str) or len(row[1]) != 64:
        raise MigrationCompatibilityError(
            "execution migration did not backfill state digest"
        )
    expected = {
        "ai_execution_state": "state_digest",
        "ai_execution_turn": "turn_digest",
        "ai_execution_checkpoint": "checkpoint_digest",
        "ai_execution_result": "result_digest",
        "ai_execution_outbox": "payload_digest",
    }
    actual = {
        "ai_execution_state": state_columns,
        "ai_execution_turn": turn_columns,
        "ai_execution_checkpoint": checkpoint_columns,
        "ai_execution_result": result_columns,
        "ai_execution_outbox": outbox_columns,
    }
    for table, column in expected.items():
        if column not in actual[table]:
            raise MigrationCompatibilityError(
                f"execution migration did not add {table}.{column}"
            )

    return {
        "store": "execution",
        "legacy_row_preserved": True,
        "identity_digest_preserved": True,
        "state_digest_backfilled": True,
        "state": row[2],
        "version": int(row[3]),
        "added_digest_columns": expected,
    }


def _legacy_tool_receipt_rehearsal(path: Path) -> dict[str, Any]:
    _reset(path)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE tool_execution_receipt (
                namespace TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_id TEXT NOT NULL,
                tool_id TEXT NOT NULL,
                arguments_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                reserved_at TEXT NOT NULL,
                receipt_json TEXT,
                completed_at TEXT,
                PRIMARY KEY(
                    namespace, tenant_id, operation_id, idempotency_key
                )
            );
            """
        )
        connection.execute(
            """
            INSERT INTO tool_execution_receipt(
                namespace, tenant_id, operation_id, idempotency_key,
                request_id, tool_id, arguments_digest, state,
                reserved_at, receipt_json, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                "tool_execution",
                "tenant-legacy",
                "operation-legacy",
                "idempotency-legacy",
                "request-legacy",
                "repo.read",
                "a" * 64,
                "pending",
                "2026-10-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    store = SQLiteToolReceiptStore(path)
    pending = store.pending()
    store.close()

    columns = _columns(path, "tool_execution_receipt")
    required = {
        "execution_id",
        "turn_id",
        "call_id",
        "data_class",
        "transfer_purpose",
    }
    missing = sorted(required - columns)
    if missing:
        raise MigrationCompatibilityError(
            "tool receipt migration missing columns: " + ", ".join(missing)
        )

    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute(
            """
            SELECT tenant_id, operation_id, idempotency_key,
                   execution_id, turn_id, call_id,
                   data_class, transfer_purpose, state
            FROM tool_execution_receipt
            WHERE namespace = 'tool_execution'
            """
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise MigrationCompatibilityError(
            "tool receipt migration lost the legacy reservation"
        )
    if tuple(row[:3]) != (
        "tenant-legacy",
        "operation-legacy",
        "idempotency-legacy",
    ):
        raise MigrationCompatibilityError(
            "tool receipt migration changed reservation identity"
        )
    if tuple(row[3:6]) != (None, None, None):
        raise MigrationCompatibilityError(
            "legacy receipt lineage columns must default to null"
        )
    if row[6] != "internal" or row[7] != "tool-execution":
        raise MigrationCompatibilityError(
            "legacy receipt governance defaults drifted"
        )
    if pending != (
        ("tenant-legacy", "operation-legacy", "idempotency-legacy"),
    ):
        raise MigrationCompatibilityError(
            "tool receipt migration changed pending reservation identity"
        )

    return {
        "store": "tool_receipts",
        "legacy_row_preserved": True,
        "pending_identity_preserved": True,
        "lineage_defaults": "null",
        "data_class_default": row[6],
        "transfer_purpose_default": row[7],
        "added_columns": sorted(required),
    }


def _legacy_quota_rehearsal(path: Path) -> dict[str, Any]:
    _reset(path)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE tenant_quota (
                tenant_id TEXT PRIMARY KEY,
                window_id TEXT NOT NULL,
                max_operations INTEGER NOT NULL,
                max_input_tokens INTEGER NOT NULL,
                max_output_tokens INTEGER NOT NULL,
                max_cost_usd REAL NOT NULL,
                max_tool_calls INTEGER NOT NULL,
                max_artifact_bytes INTEGER NOT NULL,
                max_concurrent_operations INTEGER NOT NULL,
                committed_operations INTEGER NOT NULL DEFAULT 0,
                committed_input_tokens INTEGER NOT NULL DEFAULT 0,
                committed_output_tokens INTEGER NOT NULL DEFAULT 0,
                committed_cost_usd REAL NOT NULL DEFAULT 0,
                committed_tool_calls INTEGER NOT NULL DEFAULT 0,
                committed_artifact_bytes INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE quota_reservations (
                reservation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                window_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                estimate_operations INTEGER NOT NULL,
                estimate_input_tokens INTEGER NOT NULL,
                estimate_output_tokens INTEGER NOT NULL,
                estimate_cost_usd REAL NOT NULL,
                estimate_tool_calls INTEGER NOT NULL,
                estimate_artifact_bytes INTEGER NOT NULL,
                reserved_at REAL NOT NULL,
                UNIQUE (tenant_id, operation_id)
            );

            CREATE TABLE quota_completions (
                reservation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                window_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                estimate_operations INTEGER NOT NULL,
                estimate_input_tokens INTEGER NOT NULL,
                estimate_output_tokens INTEGER NOT NULL,
                estimate_cost_usd REAL NOT NULL,
                estimate_tool_calls INTEGER NOT NULL,
                estimate_artifact_bytes INTEGER NOT NULL,
                actual_operations INTEGER NOT NULL,
                actual_input_tokens INTEGER NOT NULL,
                actual_output_tokens INTEGER NOT NULL,
                actual_cost_usd REAL NOT NULL,
                actual_tool_calls INTEGER NOT NULL,
                actual_artifact_bytes INTEGER NOT NULL,
                overrun_dimensions TEXT NOT NULL,
                completed_at REAL NOT NULL,
                UNIQUE (tenant_id, operation_id)
            );

            CREATE TABLE quota_usage_events (
                event_id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                window_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                category TEXT NOT NULL,
                delta_operations INTEGER NOT NULL DEFAULT 0,
                delta_input_tokens INTEGER NOT NULL DEFAULT 0,
                delta_output_tokens INTEGER NOT NULL DEFAULT 0,
                delta_cost_usd REAL NOT NULL DEFAULT 0,
                delta_tool_calls INTEGER NOT NULL DEFAULT 0,
                delta_artifact_bytes INTEGER NOT NULL DEFAULT 0,
                recorded_at REAL NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO tenant_quota(
                tenant_id, window_id, max_operations,
                max_input_tokens, max_output_tokens, max_cost_usd,
                max_tool_calls, max_artifact_bytes, max_concurrent_operations,
                committed_operations, committed_input_tokens,
                committed_output_tokens, committed_cost_usd,
                committed_tool_calls, committed_artifact_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tenant-legacy",
                "window-legacy",
                10,
                1000,
                2000,
                50.0,
                20,
                777,
                4,
                2,
                100,
                200,
                3.5,
                4,
                333,
            ),
        )
        connection.execute(
            """
            INSERT INTO quota_reservations(
                reservation_id, tenant_id, window_id, operation_id,
                estimate_operations, estimate_input_tokens,
                estimate_output_tokens, estimate_cost_usd,
                estimate_tool_calls, estimate_artifact_bytes, reserved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "reservation-legacy",
                "tenant-legacy",
                "window-legacy",
                "operation-reserved",
                1,
                10,
                20,
                0.5,
                1,
                55,
                1.0,
            ),
        )
        connection.execute(
            """
            INSERT INTO quota_completions(
                reservation_id, tenant_id, window_id, operation_id,
                estimate_operations, estimate_input_tokens,
                estimate_output_tokens, estimate_cost_usd,
                estimate_tool_calls, estimate_artifact_bytes,
                actual_operations, actual_input_tokens,
                actual_output_tokens, actual_cost_usd,
                actual_tool_calls, actual_artifact_bytes,
                overrun_dimensions, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "completion-legacy",
                "tenant-legacy",
                "window-legacy",
                "operation-completed",
                1,
                10,
                20,
                0.5,
                1,
                55,
                1,
                9,
                18,
                0.4,
                1,
                44,
                "[]",
                2.0,
            ),
        )
        connection.execute(
            """
            INSERT INTO quota_usage_events(
                event_id, reservation_id, tenant_id, window_id, operation_id,
                category, delta_operations, delta_input_tokens,
                delta_output_tokens, delta_cost_usd, delta_tool_calls,
                delta_artifact_bytes, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event-legacy",
                "reservation-legacy",
                "tenant-legacy",
                "window-legacy",
                "operation-reserved",
                "artifact",
                0,
                0,
                0,
                0.0,
                0,
                12,
                1.5,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    SqliteTenantQuotaLedger(path)

    required_columns = {
        "tenant_quota": {"max_storage_bytes", "committed_storage_bytes"},
        "quota_reservations": {"estimate_storage_bytes"},
        "quota_completions": {
            "estimate_storage_bytes",
            "actual_storage_bytes",
        },
        "quota_usage_events": {"delta_storage_bytes"},
    }
    for table, columns in required_columns.items():
        missing = sorted(columns - _columns(path, table))
        if missing:
            raise MigrationCompatibilityError(
                f"quota migration missing {table} columns: {', '.join(missing)}"
            )

    connection = sqlite3.connect(str(path))
    try:
        quota = connection.execute(
            """
            SELECT max_artifact_bytes, max_storage_bytes,
                   committed_artifact_bytes, committed_storage_bytes
            FROM tenant_quota WHERE tenant_id = 'tenant-legacy'
            """
        ).fetchone()
        reservation = connection.execute(
            """
            SELECT estimate_artifact_bytes, estimate_storage_bytes
            FROM quota_reservations
            WHERE reservation_id = 'reservation-legacy'
            """
        ).fetchone()
        completion = connection.execute(
            """
            SELECT estimate_storage_bytes, actual_storage_bytes
            FROM quota_completions
            WHERE reservation_id = 'completion-legacy'
            """
        ).fetchone()
        event = connection.execute(
            """
            SELECT delta_artifact_bytes, delta_storage_bytes
            FROM quota_usage_events WHERE event_id = 'event-legacy'
            """
        ).fetchone()
    finally:
        connection.close()

    if quota is None or quota[1] != quota[0] or quota[0] != 777:
        raise MigrationCompatibilityError(
            "quota migration did not preserve legacy storage capacity semantics"
        )
    if quota[2] != 333 or quota[3] != 0:
        raise MigrationCompatibilityError(
            "quota migration changed legacy committed artifact usage"
        )
    if reservation is None or tuple(reservation) != (55, 0):
        raise MigrationCompatibilityError(
            "quota reservation migration defaults drifted"
        )
    if completion is None or tuple(completion) != (0, 0):
        raise MigrationCompatibilityError(
            "quota completion migration defaults drifted"
        )
    if event is None or tuple(event) != (12, 0):
        raise MigrationCompatibilityError(
            "quota usage-event migration defaults drifted"
        )

    return {
        "store": "quota",
        "legacy_rows_preserved": True,
        "max_storage_inherited_from_artifact_limit": True,
        "storage_usage_defaults_zero": True,
        "added_columns": {
            table: sorted(columns)
            for table, columns in sorted(required_columns.items())
        },
    }


def _verify_topology_maturity(root: Path) -> dict[str, Any]:
    topology = _load(root / TOPOLOGY)
    construction = _load(root / CONSTRUCTION)
    gaps = {
        row.get("id"): row
        for row in construction.get("gap_register", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    domains = [
        row
        for row in topology.get("state_domains", [])
        if isinstance(row, dict)
    ]
    authoritative: list[str] = []
    stale_gap_refs: list[str] = []
    partial_authorities: list[str] = []
    for domain in domains:
        domain_id = str(domain.get("id", ""))
        gap_id = domain.get("gap")
        if isinstance(gap_id, str):
            gap = gaps.get(gap_id)
            if gap is None:
                raise MigrationCompatibilityError(
                    f"state domain {domain_id} references unknown gap {gap_id}"
                )
            if gap.get("status") == "closed":
                stale_gap_refs.append(domain_id)
        if domain.get("authority") == "authoritative":
            authoritative.append(domain_id)
            status = str(domain.get("status", "")).lower()
            if "partial" in status or "transitional" in status:
                partial_authorities.append(domain_id)
            for field in ("migration", "backup_restore"):
                value = domain.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise MigrationCompatibilityError(
                        f"authoritative state domain {domain_id} lacks {field}"
                    )

    if stale_gap_refs:
        raise MigrationCompatibilityError(
            "closed construction gaps still annotate state authority: "
            + ", ".join(sorted(stale_gap_refs))
        )
    if partial_authorities:
        raise MigrationCompatibilityError(
            "authoritative state remains partially bound: "
            + ", ".join(sorted(partial_authorities))
        )

    link = topology.get("migration_compatibility")
    expected = {
        "tool": "scripts/state_migration_compatibility.py",
        "test": "skeleton/testing/test_state_migration_compatibility.py",
        "release_workflow": RELEASE_WORKFLOW.as_posix(),
        "recovery_workflow": RECOVERY_WORKFLOW.as_posix(),
    }
    if not isinstance(link, dict):
        raise MigrationCompatibilityError(
            "state topology must bind migration_compatibility"
        )
    for key, value in expected.items():
        if link.get(key) != value:
            raise MigrationCompatibilityError(
                f"migration_compatibility.{key} must be {value}"
            )
        if not (root / value).is_file():
            raise MigrationCompatibilityError(
                f"migration compatibility path is missing: {value}"
            )

    return {
        "topology_version": topology.get("topology_version"),
        "authoritative_domain_count": len(authoritative),
        "authoritative_domains": sorted(authoritative),
        "closed_gap_references": 0,
        "partial_authorities": 0,
    }


def _verify_workflow_binding(root: Path) -> dict[str, Any]:
    tokens = (
        "scripts/state_migration_compatibility.py",
        "skeleton/testing/test_state_migration_compatibility.py",
    )
    result: dict[str, Any] = {}
    for name, relative in (
        ("recovery", RECOVERY_WORKFLOW),
        ("release", RELEASE_WORKFLOW),
    ):
        try:
            source = (root / relative).read_text(encoding="utf-8")
        except OSError as exc:
            raise MigrationCompatibilityError(
                f"cannot read workflow {relative}"
            ) from exc
        missing = [token for token in tokens if token not in source]
        if missing:
            raise MigrationCompatibilityError(
                f"{name} workflow does not bind migration rehearsal: "
                + ", ".join(missing)
            )
        result[name] = {
            "workflow": relative.as_posix(),
            "digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        }
    return result


def _verify_masterplan(root: Path) -> dict[str, Any]:
    master = _load(root / MASTERPLAN)
    volume = next(
        (
            row
            for row in master.get("volumes", [])
            if isinstance(row, dict) and row.get("key") == "VOL-005"
        ),
        None,
    )
    if not isinstance(volume, dict):
        raise MigrationCompatibilityError("masterplan missing VOL-005")
    if volume.get("title") != "Data & Persistence":
        raise MigrationCompatibilityError("VOL-005 title drift")
    if volume.get("implementation_status") not in {
        "implemented",
        "hardened",
        "verified",
    }:
        raise MigrationCompatibilityError(
            "VOL-005 implementation status is below implemented"
        )
    live_gaps = list(volume.get("gaps") or [])
    if live_gaps not in ([QUALIFICATION_GAP], []):
        raise MigrationCompatibilityError(
            "VOL-005 gap state must be pending exact-head qualification or signed"
        )
    if live_gaps and volume.get("completion_checkbox") is True:
        raise MigrationCompatibilityError(
            "VOL-005 cannot remain signed with pending qualification"
        )
    if not live_gaps and volume.get("completion_checkbox") is not True:
        raise MigrationCompatibilityError(
            "VOL-005 cannot clear qualification gap before signoff"
        )

    paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    evaluations = set(volume.get("evaluations") or [])
    missing_paths = sorted(REQUIRED_VOL005_PATHS - paths)
    missing_tests = sorted(REQUIRED_VOL005_TESTS - tests)
    missing_evaluations = sorted(REQUIRED_VOL005_EVALUATIONS - evaluations)
    if missing_paths:
        raise MigrationCompatibilityError(
            "VOL-005 implementation path binding incomplete: "
            + ", ".join(missing_paths)
        )
    if missing_tests:
        raise MigrationCompatibilityError(
            "VOL-005 test binding incomplete: " + ", ".join(missing_tests)
        )
    if missing_evaluations:
        raise MigrationCompatibilityError(
            "VOL-005 evaluation binding incomplete: "
            + ", ".join(missing_evaluations)
        )

    binding = {
        "key": volume.get("key"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "enterprise_grade_state": volume.get("enterprise_grade_state"),
        "enterprise_grade_target": volume.get("enterprise_grade_target"),
        "gaps": live_gaps,
        "implementation_paths": sorted(paths),
        "tests": sorted(tests),
        "evaluations": sorted(evaluations),
    }
    binding["binding_digest"] = _digest(binding)
    return binding


def run_rehearsal(root: Path, workdir: Path) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    execution = _legacy_execution_rehearsal(
        workdir / "legacy-execution.sqlite3"
    )
    tool_receipts = _legacy_tool_receipt_rehearsal(
        workdir / "legacy-tool-receipts.sqlite3"
    )
    quota = _legacy_quota_rehearsal(
        workdir / "legacy-quota.sqlite3"
    )
    topology = _verify_topology_maturity(root)
    workflows = _verify_workflow_binding(root)
    volume = _verify_masterplan(root)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "kind": "vol005-state-migration-compatibility",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume": "VOL-005",
        "stores": {
            "execution": execution,
            "tool_receipts": tool_receipts,
            "quota": quota,
        },
        "topology": topology,
        "workflow_binding": workflows,
        "volume_binding": volume,
        "passed": True,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.workdir is None:
        temporary = tempfile.TemporaryDirectory(
            prefix="skeleton_state_migration_"
        )
        workdir = Path(temporary.name)
    else:
        workdir = args.workdir

    try:
        receipt = run_rehearsal(ROOT, workdir)
    except (MigrationCompatibilityError, OSError, sqlite3.Error) as exc:
        print(f"state-migration-compatibility: FAIL: {exc}")
        if temporary is not None:
            temporary.cleanup()
        return 1

    rendered = json.dumps(receipt, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    else:
        print(
            "state-migration-compatibility: OK "
            f"({receipt['receipt_digest']})"
        )
    if temporary is not None:
        temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
