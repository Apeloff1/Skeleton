#!/usr/bin/env python3
"""Read-only, fail-closed Mongo majority durability CAPABILITY admission.

Never creates a replica set, changes defaults, writes user data, rotates
credentials or grants the shared Jeeves writer-epoch authority. Queries only
an already-running, exact-image-ID backend through its canonical internal
Docker Compose boundary using the backend's EXISTING authenticated PyMongo
client. The snippet emits only allowlisted small numeric/bool evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_offline_compose as binding
from scripts import local_ai_offline_launch as launch

SCHEMA = "skeleton.local-ai.docker.mongo-majority-capability.v1"
MAX_BYTES = 8192

# Executed ONLY inside the admitted backend container; the operator process
# never receives the Mongo URI or credentials. No mutations and no raw
# exceptions are written to stdout or stderr.
_BACKEND_SNIPPET = r"""
import json
try:
    from core.databases import get_sync_client
    admin = get_sync_client().admin
    hello = admin.command({"hello": 1, "maxTimeMS": 5000})
    status = admin.command({"replSetGetStatus": 1, "maxTimeMS": 5000})
    config = admin.command({"replSetGetConfig": 1, "maxTimeMS": 5000})
    concern = admin.command({"getDefaultRWConcern": 1, "maxTimeMS": 5000})
    topology = config.get("config", {})
    current = status.get("members", [])
    configured = topology.get("members", [])
    if (not isinstance(current, list)
            or not isinstance(configured, list)):
        raise ValueError("invalid member shape")
    configured_hosts = {}
    seen_hosts = set()
    voting_data_ids = set()
    for member in configured:
        if not isinstance(member, dict):
            raise ValueError("invalid Mongo configuration member")
        member_id = member.get("_id")
        member_host = member.get("host")
        votes = member.get("votes", 1)
        arbiter = member.get("arbiterOnly", False)
        if (type(member_id) is not int or member_id < 0
                or not isinstance(member_host, str)
                or not 0 < len(member_host) <= 255
                or member_id in configured_hosts or member_host in seen_hosts
                or type(votes) is not int or votes not in (0, 1)
                or type(arbiter) is not bool):
            raise ValueError("invalid Mongo voting member identity")
        configured_hosts[member_id] = member_host
        seen_hosts.add(member_host)
        if votes == 1 and not arbiter:
            voting_data_ids.add(member_id)
    healthy_data = set()
    seen_status = set()
    for item in current:
        if not isinstance(item, dict):
            raise ValueError("invalid Mongo status member")
        member_id = item.get("_id")
        health = item.get("health")
        state = item.get("state")
        if (type(member_id) is not int or member_id in seen_status
                or member_id not in configured_hosts
                or item.get("name") != configured_hosts[member_id]):
            raise ValueError("Mongo status/config identity mismatch")
        seen_status.add(member_id)
        if (member_id in voting_data_ids
                and type(health) in (int, float) and health == 1
                and type(state) is int and state in (1, 2)):
            healthy_data.add(member_id)
    if seen_status != set(configured_hosts):
        raise ValueError("Mongo status membership changed during admission")
    default_write = concern.get("defaultWriteConcern") or {}
    if not isinstance(default_write, dict):
        raise ValueError("invalid default write concern")
    payload = {
        "schema": "skeleton.local-ai.docker.mongo-backend-probe.v1",
        "ok": True,
        "primary_observed": hello.get("isWritablePrimary") is True,
        "replica_set_configured": isinstance(hello.get("setName"), str)
                                  and bool(hello.get("setName"))
                                  and hello.get("setName") == status.get("set")
                                  and hello.get("setName") == topology.get("_id"),
        "primary_state_confirmed": status.get("myState") == 1,
        "configured_members": len(configured),
        "data_bearing_voting_members": len(voting_data_ids),
        "healthy_data_bearing_voters": len(healthy_data),
        "majority_journal_default": topology.get("writeConcernMajorityJournalDefault")
                                     is True,
        "default_write_majority": default_write.get("w") == "majority",
        "default_write_journaled": default_write.get("j") is True,
    }
except Exception:
    # A missing replica set or admin capability is an expected admission
    # failure on the existing standalone Mongo Compose service. Never
    # expose Mongo hostname, credentials, exception or app data.
    payload = {"schema": "skeleton.local-ai.docker.mongo-backend-probe.v1",
               "ok": False}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
"""


class MongoMajorityError(host.LocalDockerError):
    """Durable majority quorum evidence unavailable on the local host."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for key, value in pairs:
        if key in rows:
            raise MongoMajorityError("duplicate Mongo evidence field")
        rows[key] = value
    return rows


def _invalid_float(value: str) -> None:
    raise MongoMajorityError("nonfinite Mongo evidence field")


def _decode(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str) or not 0 < len(payload) <= MAX_BYTES:
        raise MongoMajorityError("bounded Mongo evidence unavailable")
    try:
        result = json.loads(payload, object_pairs_hook=_unique,
                            parse_constant=_invalid_float)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise MongoMajorityError("Mongo evidence is not canonical JSON") from None
    if not isinstance(result, dict) or result.get("schema") != (
        "skeleton.local-ai.docker.mongo-backend-probe.v1"
    ):
        raise MongoMajorityError("physical Mongo evidence contract changed")
    if result.get("ok") is not True:
        raise MongoMajorityError("authenticated Mongo replica set is unavailable")
    expected = {
        "schema", "ok", "primary_observed", "replica_set_configured",
        "primary_state_confirmed", "configured_members",
        "data_bearing_voting_members", "healthy_data_bearing_voters",
        "majority_journal_default", "default_write_majority",
        "default_write_journaled",
    }
    if set(result) != expected:
        raise MongoMajorityError("Mongo evidence contains unsupported fields")
    for name in (
        "primary_observed", "replica_set_configured", "primary_state_confirmed",
        "majority_journal_default", "default_write_majority",
        "default_write_journaled",
    ):
        if result[name] is not True:
            raise MongoMajorityError("Mongo majority journal policy unqualified")
    members = result["configured_members"]
    voters = result["data_bearing_voting_members"]
    healthy = result["healthy_data_bearing_voters"]
    if (any(type(x) is not int for x in (members, voters, healthy))
            or not 3 <= voters <= members <= 31
            or not voters // 2 + 1 <= healthy <= voters):
        raise MongoMajorityError("Mongo healthy majority voters unavailable")
    return result


def inspect_mongo_majority(mode: str, archive: Path,
                           overlay_directory: Path, *,
                           expected_receipt_sha256: str,
                           root: Path = host.ROOT) -> dict[str, Any]:
    """Only admit a real replicated, journaled quorum; no DB state changes."""
    images = binding.verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    before = launch.attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    if (before.get("containers_observed") != 4
            or before.get("source_receipt_file_sha256")
            != images.get("source_receipt_file_sha256")):
        raise MongoMajorityError("canonical Mongo container identity is unverified")
    argv = [
        *launch._prefix(mode, overlay_directory, root),
        "exec", "-T", "backend", "python", "-c", _BACKEND_SNIPPET,
    ]
    try:
        raw = host._run(argv, root=root, capture=True)
    except host.LocalDockerError:
        raise MongoMajorityError("Mongo replica authority probe failed") from None
    proof = _decode(raw)
    after = launch.attest_running_offline(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256,
        root=root,
    )
    if after != before:
        raise MongoMajorityError("physical Mongo container changed during quorum probe")
    return {
        "schema": SCHEMA,
        "status": "live_mongo_majority_readonly_capability_not_writer_epoch",
        "mode": mode,
        "source_receipt_file_sha256": images["source_receipt_file_sha256"],
        "data_bearing_voting_members": proof["data_bearing_voting_members"],
        "healthy_data_bearing_voters": proof["healthy_data_bearing_voters"],
        "explicit_majority_write_default_observed": True,
        "majority_write_journaling_observed": True,
        "real_primary_replica_status_observed": True,
        "actual_mongo_database_documents_read": False,
        "database_writes_performed": False,
        "docker_state_mutated": False,
        "cross_host_failure_domains_verified": False,
        "external_writer_exclusion_verified": False,
        "shared_mongo_writer_epoch_verified": False,
        "actor_migration_verified": False,
        "coherent_mongo_sqlite_chroma_restore_qualified": False,
        "protected_chat_qualified": False,
        "release_qualified": False,
    }


__all__ = ["inspect_mongo_majority"]
