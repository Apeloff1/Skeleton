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
from datetime import datetime, timezone
from pathlib import Path
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
    projected.sort(key=canonical_json)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["live-mongo"])
    parser.add_argument("--uri", required=True)
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
    if args.mode != "live-mongo":
        raise RecoveryDrillError("unsupported recovery drill mode")
    result = run_live_mongo_drill(
        args.uri,
        source_database=args.source_database,
        restored_database=args.restored_database,
        cleanup=not args.no_cleanup,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
