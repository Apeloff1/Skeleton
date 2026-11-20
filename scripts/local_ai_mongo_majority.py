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
    default_write = concern.get("defaultWriteConcern", {})
    if (not isinstance(topology, dict) or not isinstance(current, list)
            or not isinstance(configured, list)
            or not isinstance(default_write, dict)
            or not 3 <= len(configured) <= 31
            or len(current) != len(configured)):
        raise ValueError("invalid bounded replica shape")
    # Guard against duplicated _id aliases, bool pretending to be an int,
    # malformed arbiter/voter flags and a missing elected primary identity.
    voter_ids = set()
    configured_ids = set()
    configured_names = {}
    for member in configured:
        if not isinstance(member, dict):
            raise ValueError("invalid member")
        ident = member.get("_id")
        votes = member.get("votes", 1)
        arbiter = member.get("arbiterOnly", False)
        name = member.get("host")
        if (not isinstance(ident, int) or isinstance(ident, bool)
                or ident < 0 or ident in configured_ids
                or not isinstance(votes, int) or isinstance(votes, bool)
                or votes not in (0, 1) or type(arbiter) is not bool
                or not isinstance(name, str) or not 0 < len(name) <= 255
                or name in configured_names.values()):
            raise ValueError("invalid configured voter identity")
        configured_ids.add(ident)
        configured_names[ident] = name
        if votes == 1 and not arbiter:
            voter_ids.add(ident)
    status_ids = set()
    healthy_data = set()
    self_status = []
    primary_count = 0
    for member in current:
        if not isinstance(member, dict):
            raise ValueError("invalid status")
        ident = member.get("_id")
        state = member.get("state")
        health = member.get("health")
        name = member.get("name")
        own = member.get("self", False)
        if (not isinstance(ident, int) or isinstance(ident, bool)
                or ident not in configured_ids or ident in status_ids
                or not isinstance(state, int) or isinstance(state, bool)
                or not isinstance(health, (int, float))
                or isinstance(health, bool)
                or health not in (0, 1)
                or name != configured_names[ident] or type(own) is not bool):
            raise ValueError("invalid member status identity")
        status_ids.add(ident)
        if state == 1:
            primary_count += 1
        if own:
            self_status.append(member)
        if ident in voter_ids and health == 1 and state in (1, 2):
            healthy_data.add(ident)
    if status_ids != configured_ids:
        raise ValueError("configured and live identity drift")
    local_primary_verified = (
        len(self_status) == 1
        and self_status[0].get("state") == 1
        and self_status[0].get("_id") in voter_ids
        and hello.get("me") == self_status[0].get("name")
        and primary_count == 1
        and status.get("myState") == 1
    )
    journal_policy = topology.get("writeConcernMajorityJournalDefault") is True
    # MongoDB setDefaultRWConcern accepts global w / wtimeout; an explicit
    # global 'j=true' is NOT mandatory. With the replica journal policy true,
    # w=majority waits for a majority of journaled writes. Explicit j=false
    # or any malformed j value remains disallowed.
    default_not_weakened = (
        "j" not in default_write or default_write.get("j") is True
    )
    payload = {
        "schema": "skeleton.local-ai.docker.mongo-backend-probe.v1",
        "ok": True,
        "primary_observed": hello.get("isWritablePrimary") is True,
        "replica_set_configured": (
            isinstance(hello.get("setName"), str)
            and bool(hello.get("setName"))
            and hello.get("setName") == status.get("set")
            and hello.get("setName") == topology.get("_id")
        ),
        "primary_state_confirmed": local_primary_verified,
        "membership_identity_verified": status_ids == configured_ids,
        "single_primary_identity_verified": local_primary_verified,
        "configured_members": len(configured),
        "data_bearing_voting_members": len(voter_ids),
        "healthy_data_bearing_voters": len(healthy_data),
        "majority_journal_default": journal_policy,
        "default_write_majority": default_write.get("w") == "majority",
        "default_write_journaled": journal_policy and default_not_weakened,
    }
except Exception:
    # No Mongo URI, hostnames, member names, exception or query text emitted.
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
        "primary_state_confirmed", "membership_identity_verified",
        "single_primary_identity_verified", "configured_members",
        "data_bearing_voting_members", "healthy_data_bearing_voters",
        "majority_journal_default", "default_write_majority",
        "default_write_journaled",
    }
    if set(result) != expected:
        raise MongoMajorityError("Mongo evidence contains unsupported fields")
    for name in (
        "primary_observed", "replica_set_configured", "primary_state_confirmed",
        "membership_identity_verified", "single_primary_identity_verified",
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
