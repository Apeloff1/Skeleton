"""Bounded, read-only actor/epoch migration inventory for guarded Jeeves.

Operator diagnostic only. It reads a finite number of canonical conversation
threads and memory records from their EXISTING distinct databases, checks the
shared epoch collection with primary/linearizable reads and outputs counts,
never private actor IDs, transcript text or memory contents.

Even a clean inventory is NOT proof of quiescence, a complete writer registry,
historical backup custody or a safe migration window. This tool never writes
or provisions epochs, indexes, replica configuration or application data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any

from skeleton.persistence.docker_epoch_preflight import (
    MongoEpochCapabilityError, _authenticated_internal_uri, probe_epoch_capability,
)
from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch

_MAX_RECORDS = 4096
_DEADLINE_S = 30
_IDENT = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class DockerEpochInventoryError(RuntimeError):
    """Read-only migration inventory cannot establish bounded evidence."""


def _actor(value: object) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value.encode("utf-8", "strict")) > 512 or "\x00" in value):
        raise DockerEpochInventoryError("canonical actor identity is malformed")
    return value


def _read_actors(collection: Any, field: str, *, budget: int, deadline: float) -> tuple[set[tuple[str, str]], int, bool]:
    """Scan at most N+1 records; if exceeded, fail proof of completeness."""
    results: set[tuple[str, str]] = set()
    seen = 0
    truncated = False
    cursor = collection.find(
        {}, projection={"tenant_id": 1, field: 1, "_id": 0},
        limit=budget + 1, max_time_ms=5000,
    )
    for row in cursor:
        if time.monotonic() > deadline:
            raise DockerEpochInventoryError("canonical actor inventory time budget exhausted")
        seen += 1
        if seen > budget:
            truncated = True
            break
        if not isinstance(row, dict):
            raise DockerEpochInventoryError("canonical source record is malformed")
        results.add((_actor(row.get("tenant_id")), _actor(row.get(field))))
    return results, min(seen, budget), truncated


def audit_epoch_inventory(
    client: Any, *, backend_database: str, engine_database: str,
    max_records: int = 1024,
) -> dict[str, object]:
    """Read only distinct canonical stores and stable epoch witnesses."""
    if (type(max_records) is not int or not 1 <= max_records <= _MAX_RECORDS
            or not isinstance(backend_database, str) or not _IDENT.fullmatch(backend_database)
            or not isinstance(engine_database, str) or not _IDENT.fullmatch(engine_database)
            or backend_database == engine_database
            or backend_database == "skeleton_guarded_source"
            or engine_database == "skeleton_guarded_source"):
        raise DockerEpochInventoryError("epoch inventory database/budget contract is invalid")
    try:
        from pymongo.read_concern import ReadConcern
        from pymongo.read_preferences import ReadPreference

        probe_epoch_capability(client)
        deadline = time.monotonic() + _DEADLINE_S
        conversation = client[backend_database].get_collection(
            "conversation_threads", read_concern=ReadConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        )
        memory = client[engine_database].get_collection(
            "canonical_memory_records", read_concern=ReadConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        )
        epoch = client["skeleton_guarded_source"].get_collection(
            "canonical_source_epochs", read_concern=ReadConcern("linearizable"),
            read_preference=ReadPreference.PRIMARY,
        )
        conversations, conversation_rows, clipped_c = _read_actors(
            conversation, "owner_id", budget=max_records, deadline=deadline,
        )
        memories, memory_rows, clipped_m = _read_actors(
            memory, "subject_id", budget=max_records, deadline=deadline,
        )
        actors = conversations | memories
        missing, unstable = 0, 0
        # A partial inventory must not emit a misleading epoch sufficiency
        # claim; do not spend per-actor probes on an already-truncated scan.
        if not clipped_c and not clipped_m:
            for tenant, actor in sorted(actors):
                if time.monotonic() > deadline:
                    raise DockerEpochInventoryError("actor epoch read time budget exhausted")
                doc = epoch.find_one(
                    {"_id": MongoCanonicalSourceEpoch._key(tenant, actor),
                     "tenant_id": tenant, "actor_id": actor},
                    projection={"_id": 1, "phase": 1, "writer_token": 1, "epoch": 1},
                    max_time_ms=2000,
                )
                if doc is None:
                    missing += 1
                elif (not isinstance(doc, dict) or doc.get("phase") != "stable"
                      or doc.get("writer_token") is not None
                      or type(doc.get("epoch")) is not int or doc["epoch"] < 2
                      or doc["epoch"] % 2 != 0):
                    unstable += 1
        return {
            "schema": "skeleton.local-ai.mongo-epoch-inventory.v1",
            "status": "read_only_inventory_not_quiescence_or_migration_qualified",
            "conversation_records_scanned": conversation_rows,
            "memory_records_scanned": memory_rows,
            "unique_actor_count": len(actors),
            "conversation_scan_truncated": clipped_c,
            "memory_scan_truncated": clipped_m,
            "actors_without_epoch": missing if not (clipped_c or clipped_m) else None,
            "actors_unstable_or_quarantined": unstable if not (clipped_c or clipped_m) else None,
            "all_sampled_actor_epochs_stable": (
                missing == 0 and unstable == 0 and not clipped_c and not clipped_m
            ),
            "bounded_complete_for_selected_collections": not (clipped_c or clipped_m),
            "writer_quiescence_verified": False,
            "external_writers_excluded": False,
            "actor_migration_complete": False,
            "guarded_chat_qualified": False,
            "collections_modified": False,
        }
    except (DockerEpochInventoryError, MongoEpochCapabilityError):
        raise
    except Exception:
        raise DockerEpochInventoryError("canonical actor inventory database read unavailable") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-database", required=True)
    parser.add_argument("--max-records", type=int, default=1024)
    args = parser.parse_args(argv)
    try:
        from pymongo import MongoClient
        uri = _authenticated_internal_uri(os.getenv("MONGO_URL"))
        backend_database = os.getenv("DB_NAME", "tutolage")
        with MongoClient(
            uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=1500,
            socketTimeoutMS=3000, directConnection=True,
            retryWrites=False,
        ) as client:
            result = audit_epoch_inventory(
                client, backend_database=backend_database,
                engine_database=args.engine_database,
                max_records=args.max_records,
            )
        print(json.dumps({"ok": True, **result}, sort_keys=True))
        return 0
    except (MongoEpochCapabilityError, DockerEpochInventoryError, ValueError, TypeError):
        print(json.dumps({"ok": False, "error": "read-only epoch inventory unavailable"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
