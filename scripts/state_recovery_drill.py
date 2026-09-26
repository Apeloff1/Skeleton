#!/usr/bin/env python3
"""Authoritative-first Mongo recovery drill for Skeleton.

The drill uses scratch database names only. It:
1. seeds representative canonical product state,
2. captures a logical backup with index metadata,
3. destroys/restores into a separate scratch database,
4. verifies document/index digests and counts,
5. only then permits a derived-projection rebuild phase,
6. emits a machine-readable recovery journal.

No production database name is accepted by default. The script deliberately
imports PyMongo only for live execution so contract/unit tests can import this
module without a Mongo client dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

SCRATCH_PREFIX = "skeleton_recovery_drill_"


class RecoveryDrillError(RuntimeError):
    """Recovery drill violated an ordering, integrity, or safety invariant."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def require_scratch_database(name: str) -> str:
    value = str(name).strip()
    if not value.startswith(SCRATCH_PREFIX):
        raise RecoveryDrillError(
            f"refusing destructive recovery drill outside {SCRATCH_PREFIX}* database"
        )
    if len(value) > 120:
        raise RecoveryDrillError("scratch database name is too long")
    return value


def canonical_json(value: Any) -> str:
    """Stable JSON for simple drill metadata."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def digest_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RecoveryEvent:
    sequence: int
    phase: str
    status: str
    at_utc: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "phase": self.phase,
            "status": self.status,
            "at_utc": self.at_utc,
            "evidence": dict(self.evidence),
        }


class RecoveryJournal:
    """Append-only recovery ordering ledger."""

    _ORDER = (
        "seed_authority",
        "backup_authority",
        "destroy_restore_target",
        "restore_authority",
        "verify_authority",
        "rebuild_derived",
        "verify_derived",
        "ready",
    )

    def __init__(self) -> None:
        self.events: list[RecoveryEvent] = []

    @property
    def verified_authority(self) -> bool:
        return any(
            event.phase == "verify_authority" and event.status == "passed"
            for event in self.events
        )

    def record(
        self,
        phase: str,
        *,
        status: str = "passed",
        evidence: Mapping[str, Any] | None = None,
    ) -> RecoveryEvent:
        if phase not in self._ORDER:
            raise RecoveryDrillError(f"unknown recovery phase: {phase}")
        expected_index = len(self.events)
        if expected_index >= len(self._ORDER):
            raise RecoveryDrillError("recovery journal is already terminal")
        expected = self._ORDER[expected_index]
        if phase != expected:
            raise RecoveryDrillError(
                f"recovery order violation: expected {expected}, got {phase}"
            )
        if phase == "rebuild_derived" and not self.verified_authority:
            raise RecoveryDrillError(
                "derived rebuild forbidden before authoritative verification"
            )
        event = RecoveryEvent(
            sequence=expected_index + 1,
            phase=phase,
            status=str(status),
            at_utc=utc_now(),
            evidence=dict(evidence or {}),
        )
        self.events.append(event)
        if status != "passed":
            raise RecoveryDrillError(f"recovery phase failed: {phase}")
        return event

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "policy": "authoritative-first-derived-second",
            "verified_authority": self.verified_authority,
            "complete": len(self.events) == len(self._ORDER),
            "events": [event.as_dict() for event in self.events],
        }


def _normalize_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(document)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return result


def _normalize_index(index: Mapping[str, Any]) -> dict[str, Any]:
    key = index.get("key", {})
    if hasattr(key, "items"):
        key_items = [[str(k), v] for k, v in key.items()]
    else:
        key_items = list(key)
    return {
        "name": str(index.get("name", "")),
        "key": key_items,
        "unique": bool(index.get("unique", False)),
        "sparse": bool(index.get("sparse", False)),
    }


def capture_database(database: Any) -> dict[str, Any]:
    """Capture canonical docs + user indexes from a PyMongo-like database."""
    collections: dict[str, Any] = {}
    for name in sorted(database.list_collection_names()):
        collection = database[name]
        documents = sorted(
            (_normalize_document(row) for row in collection.find({})),
            key=canonical_json,
        )
        indexes = sorted(
            (
                _normalize_index(index)
                for index in collection.list_indexes()
                if str(index.get("name")) != "_id_"
            ),
            key=canonical_json,
        )
        collections[name] = {
            "documents": documents,
            "indexes": indexes,
            "count": len(documents),
            "documents_digest": digest_payload(documents),
            "indexes_digest": digest_payload(indexes),
        }
    snapshot = {
        "collections": collections,
        "collection_count": len(collections),
    }
    snapshot["digest"] = digest_payload(snapshot)
    return snapshot


def restore_database(database: Any, snapshot: Mapping[str, Any]) -> None:
    """Restore a capture into an empty scratch database."""
    database.client.drop_database(database.name)
    for name, entry in snapshot.get("collections", {}).items():
        collection = database[name]
        documents = list(entry.get("documents", []))
        if documents:
            # _id values are string-normalized by capture, which is intentional
            # for this logical recovery drill.
            collection.insert_many(documents)
        for index in entry.get("indexes", []):
            keys = [(str(key), value) for key, value in index.get("key", [])]
            kwargs: dict[str, Any] = {
                "name": str(index.get("name") or ""),
                "unique": bool(index.get("unique", False)),
                "sparse": bool(index.get("sparse", False)),
            }
            collection.create_index(keys, **kwargs)


def verify_snapshot(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> dict[str, Any]:
    expected_collections = expected.get("collections", {})
    actual_collections = actual.get("collections", {})
    if set(expected_collections) != set(actual_collections):
        raise RecoveryDrillError("restored collection set differs from backup")
    mismatches: list[str] = []
    counts: dict[str, int] = {}
    for name in sorted(expected_collections):
        before = expected_collections[name]
        after = actual_collections[name]
        counts[name] = int(after.get("count", 0))
        for field in ("count", "documents_digest", "indexes_digest"):
            if before.get(field) != after.get(field):
                mismatches.append(f"{name}:{field}")
    if mismatches:
        raise RecoveryDrillError(
            "authoritative restore verification mismatch: " + ", ".join(mismatches)
        )
    return {
        "collections": counts,
        "backup_digest": expected.get("digest"),
        "restore_digest": actual.get("digest"),
        "verified_fields": ["count", "documents_digest", "indexes_digest"],
    }


def seed_authoritative_state(database: Any) -> dict[str, int]:
    """Seed representative canonical app state for a destructive scratch drill."""
    database.client.drop_database(database.name)

    progress = database["rag_user_progress"]
    progress.create_index([("user_id", 1), ("domain", 1)], unique=True)
    progress.insert_many(
        [
            {
                "progress_id": "u1:python",
                "user_id": "u1",
                "domain": "python",
                "mastery_level": 0.75,
                "concepts_learned": ["loops", "asyncio"],
                "concept_count": 2,
                "total_hours": 8.5,
                "authority": "mongo",
                "schema_version": 1,
            },
            {
                "progress_id": "u2:systems",
                "user_id": "u2",
                "domain": "systems",
                "mastery_level": 0.4,
                "concepts_learned": ["queues"],
                "concept_count": 1,
                "total_hours": 3.0,
                "authority": "mongo",
                "schema_version": 1,
            },
        ]
    )

    sessions = database["rag_learning_sessions"]
    sessions.create_index("session_id", unique=True)
    sessions.create_index([("user_id", 1), ("timestamp", -1)])
    sessions.insert_many(
        [
            {
                "session_id": "session-1",
                "user_id": "u1",
                "topic": "python",
                "content": "authoritative lesson one",
                "duration_minutes": 20,
                "mastery_delta": 0.1,
                "timestamp": "2026-09-21T18:00:00Z",
                "authority": "mongo",
                "schema_version": 1,
            },
            {
                "session_id": "session-2",
                "user_id": "u2",
                "topic": "systems",
                "content": "authoritative lesson two",
                "duration_minutes": 15,
                "mastery_delta": 0.05,
                "timestamp": "2026-09-21T18:05:00Z",
                "authority": "mongo",
                "schema_version": 1,
            },
        ]
    )

    feedback = database["rag_feedback"]
    feedback.create_index("feedback_id", unique=True)
    feedback.insert_one(
        {
            "feedback_id": "feedback-1",
            "user_id": "u1",
            "feedback_type": "rating",
            "content": "useful",
            "rating": 5,
            "timestamp": "2026-09-21T18:10:00Z",
            "authority": "mongo",
            "schema_version": 1,
        }
    )

    return {
        "rag_user_progress": 2,
        "rag_learning_sessions": 2,
        "rag_feedback": 1,
    }


def rebuild_derived_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in for derived index/cache reconstruction.

    The product's actual Chroma rebuild is tested in
    backend/tests/test_rag_state_authority.py. This drill verifies that rebuild
    input is taken only from the already-verified restored authority.
    """
    collections = snapshot.get("collections", {})
    projected: list[dict[str, Any]] = []
    for source in ("rag_learning_sessions", "rag_feedback"):
        for document in collections.get(source, {}).get("documents", []):
            record_id = document.get("session_id") or document.get("feedback_id")
            projected.append(
                {
                    "source": source,
                    "record_id": str(record_id),
                    "tenant_or_user": str(document.get("user_id", "")),
                    "digest": digest_payload(document),
                }
            )
    projected.sort(
        key=lambda row: (str(row["source"]), str(row["record_id"]))
    )
    return {
        "count": len(projected),
        "digest": digest_payload(projected),
        "records": projected,
    }


def run_live_mongo_drill(
    uri: str,
    *,
    source_database: str,
    restored_database: str,
    cleanup: bool = True,
) -> dict[str, Any]:
    source_name = require_scratch_database(source_database)
    restored_name = require_scratch_database(restored_database)
    if source_name == restored_name:
        raise RecoveryDrillError("source and restored database names must differ")

    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RecoveryDrillError(
            "live Mongo drill requires pymongo"
        ) from exc

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
        appname="skeleton-state-recovery-drill",
    )
    journal = RecoveryJournal()
    try:
        client.admin.command("ping")
        source = client[source_name]
        restored = client[restored_name]

        seeded = seed_authoritative_state(source)
        journal.record("seed_authority", evidence={"counts": seeded})

        backup = capture_database(source)
        journal.record(
            "backup_authority",
            evidence={
                "digest": backup["digest"],
                "collection_count": backup["collection_count"],
            },
        )

        client.drop_database(restored_name)
        journal.record(
            "destroy_restore_target",
            evidence={"database": restored_name},
        )

        restore_database(restored, backup)
        journal.record(
            "restore_authority",
            evidence={"database": restored_name},
        )

        restored_snapshot = capture_database(restored)
        verification = verify_snapshot(backup, restored_snapshot)
        journal.record("verify_authority", evidence=verification)

        projection = rebuild_derived_projection(restored_snapshot)
        journal.record(
            "rebuild_derived",
            evidence={
                "projection_count": projection["count"],
                "projection_digest": projection["digest"],
            },
        )

        projection_again = rebuild_derived_projection(restored_snapshot)
        if projection_again != projection:
            raise RecoveryDrillError("derived rebuild is not deterministic")
        journal.record(
            "verify_derived",
            evidence={
                "projection_count": projection["count"],
                "projection_digest": projection["digest"],
                "deterministic": True,
            },
        )

        journal.record(
            "ready",
            evidence={
                "authoritative_verified": True,
                "derived_rebuild_verified": True,
            },
        )
        return {
            "status": "passed",
            "source_database": source_name,
            "restored_database": restored_name,
            "backup_digest": backup["digest"],
            "restore_digest": restored_snapshot["digest"],
            "derived_projection_digest": projection["digest"],
            "journal": journal.as_dict(),
        }
    finally:
        if cleanup:
            client.drop_database(source_name)
            client.drop_database(restored_name)
        client.close()



@dataclass(frozen=True, slots=True)
class SQLiteRecoveryEvent:
    sequence: int
    phase: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "phase": self.phase,
            "evidence": dict(self.evidence),
        }


class SQLiteRecoveryJournal:
    """Strict restore ordering for authoritative operation SQLite state."""

    _ORDER = (
        "seed_operation_authority",
        "backup_operation_authority",
        "destroy_operation_authority",
        "restore_operation_authority",
        "verify_operation_authority",
        "reconcile_operation_outbox",
        "ready",
    )

    def __init__(self) -> None:
        self.events: list[SQLiteRecoveryEvent] = []

    def record(
        self,
        phase: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> SQLiteRecoveryEvent:
        index = len(self.events)
        if index >= len(self._ORDER):
            raise RecoveryDrillError("SQLite recovery journal is already terminal")
        expected = self._ORDER[index]
        if phase != expected:
            raise RecoveryDrillError(
                f"SQLite recovery order violation: expected {expected}, got {phase}"
            )
        event = SQLiteRecoveryEvent(
            sequence=index + 1,
            phase=phase,
            evidence=dict(evidence or {}),
        )
        self.events.append(event)
        return event

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "policy": "operation-authority-first-outbox-second",
            "complete": len(self.events) == len(self._ORDER),
            "events": [event.as_dict() for event in self.events],
        }


def capture_sqlite_database(path: str | Path) -> dict[str, Any]:
    """Capture deterministic schema/data evidence from one SQLite database."""

    database_path = Path(path)
    if not database_path.is_file():
        raise RecoveryDrillError(
            f"SQLite database does not exist: {database_path}"
        )
    conn = sqlite3.connect(str(database_path))
    conn.row_factory = sqlite3.Row
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise RecoveryDrillError("SQLite integrity_check failed")
        schema_rows = conn.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        schema = [
            {
                "type": str(row["type"]),
                "name": str(row["name"]),
                "table": str(row["tbl_name"]),
                "sql": None if row["sql"] is None else str(row["sql"]),
            }
            for row in schema_rows
        ]
        tables: dict[str, Any] = {}
        for entry in schema:
            if entry["type"] != "table":
                continue
            table = entry["name"]
            escaped = '"' + table.replace('"', '""') + '"'
            columns = [
                str(row["name"])
                for row in conn.execute(
                    f"PRAGMA table_info({escaped})"
                ).fetchall()
            ]
            rows = [
                [row[column] for column in columns]
                for row in conn.execute(
                    f"SELECT * FROM {escaped}"
                ).fetchall()
            ]
            rows.sort(key=canonical_json)
            tables[table] = {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "rows_digest": digest_payload(rows),
            }
        payload = {
            "schema": schema,
            "tables": tables,
            "integrity": "ok",
        }
        payload["digest"] = digest_payload(payload)
        return payload
    finally:
        conn.close()


def online_backup_sqlite(
    source: str | Path,
    destination: str | Path,
) -> None:
    """Create a transactionally consistent SQLite backup using its backup API."""

    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.is_file():
        raise RecoveryDrillError(
            f"SQLite backup source does not exist: {source_path}"
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()

    src = sqlite3.connect(str(source_path))
    dst = sqlite3.connect(str(destination_path))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def verify_sqlite_snapshot(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> dict[str, Any]:
    if expected.get("digest") != actual.get("digest"):
        raise RecoveryDrillError(
            "restored SQLite authority differs from backup"
        )
    expected_tables = expected.get("tables", {})
    actual_tables = actual.get("tables", {})
    if set(expected_tables) != set(actual_tables):
        raise RecoveryDrillError(
            "restored SQLite table set differs from backup"
        )
    return {
        "digest": actual.get("digest"),
        "tables": {
            name: int(actual_tables[name].get("row_count", 0))
            for name in sorted(actual_tables)
        },
        "integrity": actual.get("integrity"),
    }


class _RecoveryReasoner:
    def reason(self, **_kwargs):
        return {"answer": "recovery-drill"}


def run_operation_sqlite_drill(
    workdir: str | Path,
    *,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Destroy/restore canonical operation state and reconcile its outbox."""

    from skeleton.contracts.operation import OperationEnvelope, OperationState
    from skeleton.frontier.operation_stream import ReplayCursor
    from skeleton.frontier.operation_stream_store import (
        SQLiteOperationEventStore,
    )
    from skeleton.persistence.operation_runtime import DurableOperationRuntime
    from skeleton.persistence.operation_store import SQLiteOperationStore

    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    source_path = root / "operation_state.sqlite"
    backup_path = root / "operation_state.backup.sqlite"
    restored_path = root / "operation_state.restored.sqlite"
    stream_path = root / "operation_stream.restored.sqlite"
    for candidate in (
        source_path,
        backup_path,
        restored_path,
        stream_path,
    ):
        if candidate.exists():
            candidate.unlink()

    journal = SQLiteRecoveryJournal()
    created_at = datetime(
        2026,
        9,
        26,
        0,
        0,
        tzinfo=timezone.utc,
    )
    operation_id = "00000000-0000-4000-8000-000000000901"
    with SQLiteOperationStore(source_path) as operations:
        current = operations.create(
            OperationEnvelope(
                operation_id=operation_id,
                tenant_id="tenant-recovery",
                actor_id="state-recovery-drill",
                capability="intelligence.reason",
                created_at=created_at,
                deadline=created_at + timedelta(minutes=10),
                idempotency_key="state-recovery-operation",
                trace_id="state-recovery-trace",
            ),
            now=created_at,
        )
        for index, state in enumerate(
            (
                OperationState.VALIDATED,
                OperationState.AUTHORIZED,
                OperationState.ADMITTED,
            ),
            start=1,
        ):
            current = operations.transition(
                operation_id,
                state,
                expected_version=current.version,
                now=created_at + timedelta(seconds=index),
            )
        pending = operations.pending_outbox(
            operation_id=operation_id
        )
        expected_outbox_ids = [item.outbox_id for item in pending]
        journal.record(
            "seed_operation_authority",
            evidence={
                "operation_id": operation_id,
                "state": current.envelope.state.value,
                "version": current.version,
                "pending_outbox": len(pending),
                "outbox_ids": expected_outbox_ids,
            },
        )

    source_snapshot = capture_sqlite_database(source_path)
    online_backup_sqlite(source_path, backup_path)
    backup_snapshot = capture_sqlite_database(backup_path)
    verify_sqlite_snapshot(source_snapshot, backup_snapshot)
    journal.record(
        "backup_operation_authority",
        evidence={
            "digest": backup_snapshot["digest"],
            "tables": {
                name: value["row_count"]
                for name, value in backup_snapshot["tables"].items()
            },
        },
    )

    source_path.unlink()
    journal.record(
        "destroy_operation_authority",
        evidence={"destroyed": str(source_path)},
    )

    online_backup_sqlite(backup_path, restored_path)
    journal.record(
        "restore_operation_authority",
        evidence={"restored": str(restored_path)},
    )

    restored_snapshot = capture_sqlite_database(restored_path)
    verification = verify_sqlite_snapshot(
        backup_snapshot,
        restored_snapshot,
    )
    restored_store = SQLiteOperationStore(restored_path)
    restored = restored_store.get(operation_id)
    restored_pending = restored_store.pending_outbox(
        operation_id=operation_id
    )
    if restored.envelope.state is not OperationState.ADMITTED:
        restored_store.close()
        raise RecoveryDrillError(
            "restored operation state is not the backed-up authority"
        )
    if restored.version != 4:
        restored_store.close()
        raise RecoveryDrillError(
            "restored operation version changed"
        )
    if [item.outbox_id for item in restored_pending] != expected_outbox_ids:
        restored_store.close()
        raise RecoveryDrillError(
            "restored pending outbox identity changed"
        )
    journal.record(
        "verify_operation_authority",
        evidence={
            **verification,
            "state": restored.envelope.state.value,
            "version": restored.version,
            "pending_outbox": len(restored_pending),
        },
    )

    runtime = DurableOperationRuntime(
        _RecoveryReasoner(),
        restored_store,
        SQLiteOperationEventStore(stream_path),
    )
    report = runtime.dispatch_outbox(operation_id=operation_id)
    events = runtime.stream.replay(ReplayCursor(operation_id))
    if report.remaining != 0:
        runtime.close()
        raise RecoveryDrillError(
            "restored operation outbox did not fully reconcile"
        )
    if [event.event_id for event in events] != expected_outbox_ids:
        runtime.close()
        raise RecoveryDrillError(
            "restored stream does not preserve outbox event identity"
        )
    journal.record(
        "reconcile_operation_outbox",
        evidence={
            "published": report.published,
            "remaining": report.remaining,
            "event_types": [event.type for event in events],
            "event_ids": [event.event_id for event in events],
        },
    )
    runtime.close()

    journal.record(
        "ready",
        evidence={
            "authoritative_restore_verified": True,
            "outbox_reconciliation_verified": True,
        },
    )
    result = {
        "status": "passed",
        "operation_id": operation_id,
        "backup_digest": backup_snapshot["digest"],
        "restore_digest": restored_snapshot["digest"],
        "journal": journal.as_dict(),
    }
    if cleanup:
        for candidate in (
            source_path,
            backup_path,
            restored_path,
            stream_path,
        ):
            if candidate.exists():
                candidate.unlink()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["live-mongo", "live-sqlite"])
    parser.add_argument("--uri")
    parser.add_argument("--workdir")
    parser.add_argument(
        "--source-database",
        default=f"{SCRATCH_PREFIX}source",
    )
    parser.add_argument(
        "--restored-database",
        default=f"{SCRATCH_PREFIX}restored",
    )
    parser.add_argument("--output")
    parser.add_argument("--no-cleanup", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.mode == "live-mongo":
        if not args.uri:
            raise RecoveryDrillError("live-mongo requires --uri")
        result = run_live_mongo_drill(
            args.uri,
            source_database=args.source_database,
            restored_database=args.restored_database,
            cleanup=not args.no_cleanup,
        )
    elif args.mode == "live-sqlite":
        if not args.workdir:
            raise RecoveryDrillError("live-sqlite requires --workdir")
        result = run_operation_sqlite_drill(
            args.workdir,
            cleanup=not args.no_cleanup,
        )
    else:
        raise RecoveryDrillError("unsupported recovery drill mode")
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
