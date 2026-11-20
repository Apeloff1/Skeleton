#!/usr/bin/env python3
"""Read-only REAL Mongo journal/epoch capability from each Docker service.

Run only via the canonical local Docker operator's existing service `exec`;
it makes no Docker changes. Every Mongo connection uses an existing
authenticated service-local environment URI and directConnection=True.
No writer epoch, source record, migration, index, collection, credential,
volume, model or chat turn is created or changed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from skeleton.persistence.docker_epoch_preflight import (
    _authenticated_internal_uri, probe_epoch_capability,
)
from skeleton.persistence.docker_epoch_writer_policy import (
    observe_writer_policy_sync,
)

SCHEMA = "skeleton.local-ai.mongo-real-dual-writer-journal-probe.v1"


class RealJournalProbeError(RuntimeError):
    """Physical read-only Mongo journal gate cannot attest a live service."""


def probe_real_journal(client: Any, *, role: str) -> dict[str, object]:
    """Require stable primary/linearizable read before and after journal census."""
    if role not in ("backend", "engine"):
        raise RealJournalProbeError("unknown canonical Docker application role")
    try:
        first = probe_epoch_capability(client)
        writer = observe_writer_policy_sync(client)
        second = probe_epoch_capability(client)
        if (first != second
                or first.get("linearizable_read_executed") is not True
                or writer.get("primary_identity_stable_across_probe") is not True
                or writer.get("explicit_majority_journal_policy") is not True
                or writer.get("database_writes_performed") is not False):
            raise RealJournalProbeError("physical journal/read witness changed")
        # Do not publish database addresses, process IDs, actor keys, data
        # or credential material. Digest is stable only for the primary
        # process seen by the independently authenticated epoch reader.
        return {
            "schema": SCHEMA,
            "ok": True,
            "role": role,
            "status": "real_dual_service_read_only_journal_not_writer_custody",
            "replica_set": first["replica_set"],
            "primary_fingerprint_sha256": first["primary_fingerprint_sha256"],
            "configured_members": writer["configured_members"],
            "data_bearing_voters": writer["data_bearing_voters"],
            "healthy_data_bearing_voters": writer["healthy_data_bearing_voters"],
            "exact_config_and_status_members_verified": True,
            "primary_identity_stable_across_probe": True,
            "linearizable_read_before_and_after": True,
            "explicit_majority_default": True,
            "explicit_majority_journal_policy": True,
            "database_documents_read": False,
            "database_writes_performed": False,
            "docker_state_modified": False,
            "production_writers_enrolled": False,
            "external_writer_registry_qualified": False,
            "actor_migration_qualified": False,
            "protected_chat_qualified": False,
            "release_authorized": False,
        }
    except RealJournalProbeError:
        raise
    except Exception:
        raise RealJournalProbeError(
            "authenticated real Mongo journal probe unavailable"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("backend", "engine"), required=True)
    args = parser.parse_args(argv)
    try:
        from pymongo import MongoClient

        key = "MONGO_URL" if args.role == "backend" else "SKL_MONGO_URI"
        uri = _authenticated_internal_uri(os.environ.get(key))
        with MongoClient(
            uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=1500,
            socketTimeoutMS=3000, directConnection=True, retryWrites=False,
        ) as client:
            result = probe_real_journal(client, role=args.role)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        # Mongo driver exceptions may include URI credentials/host private data.
        print(json.dumps({"ok": False, "error":
                          "read-only dual-service Mongo journal denied"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
