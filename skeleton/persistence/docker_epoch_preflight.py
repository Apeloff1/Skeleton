"""Read-only, dual-service capability proof for guarded local Mongo source epochs.

This probe is intentionally *not* the cross-process writer migration.
It verifies an authenticated replica-set primary and an actual linearizable
read against the same canonical epoch collection from each application
container. It never creates records, indexes, collections or replicas.
A shared digest is process identity evidence, not a writer-custody certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

_SCHEMA = "skeleton.local-ai.mongo-epoch-capability.v1"
_REPLSET = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_PROCESS_ID = re.compile(r"[a-f0-9]{24}\Z")
_REQUIRED_HOST = "mongo:27017"
_READ_TIMEOUT_MS = 2000


class MongoEpochCapabilityError(RuntimeError):
    """The live Mongo server cannot qualify protected-source epoch reads."""


def _authenticated_internal_uri(uri: object) -> str:
    if not isinstance(uri, str) or not 1 <= len(uri) <= 8192:
        raise MongoEpochCapabilityError("authenticated internal Mongo URI required")
    try:
        parsed = urlsplit(uri)
        query = parse_qs(parsed.query, keep_blank_values=True)
        approved = (
            parsed.scheme == "mongodb"
            and parsed.hostname == "mongo"
            and parsed.port == 27017
            and parsed.username is not None and bool(parsed.username)
            and parsed.password is not None and bool(parsed.password)
            and parsed.fragment == ""
            and "authSource" in query
            and len(query["authSource"]) == 1
            and query["authSource"][0] == "admin"
            and parsed.path.startswith("/")
        )
    except (ValueError, TypeError):
        approved = False
    if not approved:
        raise MongoEpochCapabilityError("Mongo URI must use authenticated internal service")
    return uri


def _primary_identity(hello: object) -> tuple[str, str]:
    if not isinstance(hello, Mapping):
        raise MongoEpochCapabilityError("Mongo hello response is unavailable")
    name = hello.get("setName")
    primary = hello.get("primary")
    me = hello.get("me")
    from bson.objectid import ObjectId

    version = hello.get("topologyVersion")
    process = version.get("processId") if isinstance(version, Mapping) else None
    if (
        hello.get("isWritablePrimary") is not True
        or not isinstance(name, str) or not _REPLSET.fullmatch(name)
        or primary != _REQUIRED_HOST or me != _REQUIRED_HOST
        or not isinstance(process, (str, bytes, ObjectId))
    ):
        raise MongoEpochCapabilityError("replica-set primary identity is not qualified")
    process_str = process.hex() if isinstance(process, bytes) else str(process)
    if not _PROCESS_ID.fullmatch(process_str):
        raise MongoEpochCapabilityError("Mongo process identity is unverified")
    return name, process_str


def probe_epoch_capability(client: Any) -> dict[str, object]:
    """Run exactly one hello plus one *read-only* linearizable collection read."""
    try:
        from pymongo.read_concern import ReadConcern
        from pymongo.read_preferences import ReadPreference

        hello = client.admin.command({"hello": 1, "maxTimeMS": _READ_TIMEOUT_MS})
        set_name, process_id = _primary_identity(hello)
        # The epoch DB is shared independently of the existing application's
        # conversation and memory database namespaces. No indexes are created.
        collection = client["skeleton_guarded_source"].get_collection(
            "canonical_source_epochs",
            read_concern=ReadConcern("linearizable"),
            read_preference=ReadPreference.PRIMARY,
        )
        sentinel = collection.find_one(
            {"_id": "__skeleton_docker_epoch_capability_read_only__"},
            projection={"_id": 1}, max_time_ms=_READ_TIMEOUT_MS,
        )
        if sentinel is not None:
            # A reserved probe must never be interpreted as genuine actor
            # data or a pre-provisioned source epoch; deny any collision.
            raise MongoEpochCapabilityError(
                "reserved canonical epoch probe identity is occupied"
            )
    except MongoEpochCapabilityError:
        raise
    except Exception as exc:
        # Driver exceptions may echo credentials or connection strings.
        raise MongoEpochCapabilityError("linearizable primary read unavailable") from None

    fingerprint = hashlib.sha256((
        "skeleton.docker.mongo.primary.v1\x00" + set_name + "\x00"
        + _REQUIRED_HOST + "\x00" + process_id
    ).encode("ascii")).hexdigest()
    return {
        "schema": _SCHEMA,
        "status": "replica_primary_linearizable_read_verified_not_writer_fenced",
        "replica_set": set_name,
        "primary_fingerprint_sha256": fingerprint,
        "replica_primary_observed": True,
        "linearizable_read_executed": True,
        "epoch_records_created": False,
        "shared_epoch_writers_bound": False,
        "actor_migration_complete": False,
        "guarded_chat_qualified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("backend", "engine"), required=True)
    args = parser.parse_args(argv)
    try:
        from pymongo import MongoClient

        key = "MONGO_URL" if args.role == "backend" else "SKL_MONGO_URI"
        uri = _authenticated_internal_uri(os.environ.get(key))
        # The same explicit timeout budget applies to both deployment owners.
        with MongoClient(
            uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=1500,
            socketTimeoutMS=3000, retryWrites=False, directConnection=True,
        ) as client:
            result = probe_epoch_capability(client)
        print(json.dumps({"ok": True, "role": args.role, **result}, sort_keys=True))
        return 0
    except (MongoEpochCapabilityError, OSError, ValueError, TypeError):
        print(json.dumps({
            "ok": False, "error": "guarded source epoch capability unavailable",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
