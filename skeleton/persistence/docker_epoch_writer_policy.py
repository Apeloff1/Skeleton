"""Read-only journaled-majority policy admission for *real* Docker writers.

This is stronger than a bare replica-set hello or a synthetic Mongo smoke.
It validates the current authenticated Mongo primary, configured data-bearing
voters, live member identities, effective majority-journal policy and actual
majority default before an opt-in backend or engine can attach writer fencing.

No Mongo mutations, lease creation, credential output, provider selection,
source migration, chat readiness, or production merge/release authorization.
This is only a point-in-time capability witness, never a global writer census.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Mapping
from typing import Any

from skeleton.persistence.docker_epoch_preflight import _primary_identity


class MongoWriterPolicyError(RuntimeError):
    """Read-only policy cannot admit live canonical Mongo writes."""


_SCHEMA = "skeleton.local-ai.mongo-writer-journal-policy.v1"
_MAX_MEMBERS = 31
_COMMAND_MS = 2000
_DEADLINE_S = 12


def _row(raw: object, name: str) -> Mapping[str, Any]:
    if (not isinstance(raw, Mapping) or type(raw.get("ok")) not in (int, float)
            or not math.isfinite(raw["ok"]) or raw["ok"] != 1):
        raise MongoWriterPolicyError("authenticated Mongo writer policy unavailable")
    return raw


def validate_writer_policy(
    before: object, status: object, config: object,
    concern: object, after: object,
) -> dict[str, object]:
    """Validate five independent read-only responses without leaking hosts.

    All five responses must come from the caller's admitted authenticated
    client. Identifiers are checked for equality but never emitted.
    """
    try:
        first = _row(before, "hello")
        second = _row(after, "hello-recheck")
        live = _row(status, "status")
        raw_config = _row(config, "config")
        defaults = _row(concern, "concern")
        identity = _primary_identity(first)
        identity_fingerprint = hashlib.sha256((
            "skeleton.docker.mongo.primary.v1\x00" + identity[0] +
            "\x00mongo:27017\x00" + identity[1]
        ).encode("ascii")).hexdigest()
        if _primary_identity(second) != identity:
            raise MongoWriterPolicyError("replica primary identity changed during admission")
        set_name = identity[0]
        members = raw_config.get("config")
        current = live.get("members")
        write_default = defaults.get("defaultWriteConcern")
        if (not isinstance(members, Mapping)
                or members.get("_id") != set_name
                or live.get("set") != set_name
                or live.get("myState") != 1
                or not isinstance(write_default, Mapping)
                or write_default.get("w") != "majority"
                or write_default.get("j", True) is not True
                or members.get("writeConcernMajorityJournalDefault") is not True
                or not isinstance(current, list)):
            raise MongoWriterPolicyError("Mongo majority journal policy unavailable")
        declared = members.get("members")
        if (not isinstance(declared, list)
                or not 3 <= len(declared) <= _MAX_MEMBERS
                or len(declared) != len(current)):
            raise MongoWriterPolicyError("Mongo voting topology incomplete")
        voter_ids: set[int] = set()
        declared_ids: set[int] = set()
        declared_hosts: set[str] = set()
        name_by_id: dict[int, str] = {}
        for member in declared:
            if not isinstance(member, Mapping):
                raise MongoWriterPolicyError("configured Mongo member malformed")
            ident, host = member.get("_id"), member.get("host")
            votes, arbiter = member.get("votes", 1), member.get("arbiterOnly", False)
            if (type(ident) is not int or ident < 0 or ident in declared_ids
                    or type(votes) is not int or votes not in (0, 1)
                    or type(arbiter) is not bool
                    or not isinstance(host, str) or not 0 < len(host) <= 255
                    or any(c in host for c in "\x00\n\r")
                    or host in declared_hosts):
                raise MongoWriterPolicyError("configured Mongo voting identity malformed")
            declared_ids.add(ident)
            declared_hosts.add(host)
            name_by_id[ident] = host
            if votes == 1 and not arbiter:
                voter_ids.add(ident)
        if len(voter_ids) < 3:
            raise MongoWriterPolicyError("three data-bearing voters required")

        seen_ids: set[int] = set()
        primary_ids: set[int] = set()
        own_ids: set[int] = set()
        healthy: set[int] = set()
        for member in current:
            if not isinstance(member, Mapping):
                raise MongoWriterPolicyError("live Mongo member malformed")
            ident, name = member.get("_id"), member.get("name")
            state, health = member.get("state"), member.get("health")
            own = member.get("self", False)
            if (type(ident) is not int or ident not in declared_ids
                    or ident in seen_ids or name != name_by_id.get(ident)
                    or type(state) is not int or state not in range(0, 11)
                    or type(health) not in (int, float)
                    or not math.isfinite(health) or health not in (0, 1)
                    or type(own) is not bool):
                raise MongoWriterPolicyError("live Mongo voting identity malformed")
            seen_ids.add(ident)
            if state == 1:
                primary_ids.add(ident)
            if own:
                own_ids.add(ident)
            if ident in voter_ids and health == 1 and state in (1, 2):
                healthy.add(ident)
        me = first.get("me")
        if (seen_ids != declared_ids
                or len(primary_ids) != 1 or primary_ids != own_ids
                or not primary_ids.issubset(voter_ids)
                or me != name_by_id[next(iter(primary_ids))]
                or second.get("me") != me
                or first.get("primary") != me
                or second.get("primary") != me
                or len(healthy) < len(voter_ids) // 2 + 1):
            raise MongoWriterPolicyError("current Mongo primary or healthy quorum unverified")

        return {
            "schema": _SCHEMA,
            "primary_fingerprint_sha256": identity_fingerprint,
            "status": "real_readonly_majority_journal_capability_not_writer_registry",
            "configured_members": len(declared),
            "data_bearing_voters": len(voter_ids),
            "healthy_data_bearing_voters": len(healthy),
            "exact_config_and_status_members_verified": True,
            "single_primary_verified": True,
            "primary_identity_stable_across_probe": True,
            "explicit_majority_default": True,
            "explicit_majority_journal_policy": True,
            "database_documents_read": False,
            "database_writes_performed": False,
            "production_writer_registry_complete": False,
            "actor_migration_qualified": False,
            "protected_chat_qualified": False,
            "release_authorized": False,
        }
    except MongoWriterPolicyError:
        raise
    except Exception:
        raise MongoWriterPolicyError("authenticated Mongo writer policy unavailable") from None


async def observe_writer_policy_async(client: Any) -> dict[str, object]:
    """Observe actual policy on an *existing* async Motor/PyMongo client."""
    if not callable(getattr(getattr(client, "admin", None), "command", None)):
        raise MongoWriterPolicyError("Mongo admin client unavailable")
    try:
        # Server-side time limits and a caller-side total bound both apply.
        async with asyncio.timeout(_DEADLINE_S):
            results = []
            for name in ("hello", "replSetGetStatus", "replSetGetConfig",
                         "getDefaultRWConcern", "hello"):
                results.append(await client.admin.command(
                    {name: 1, "maxTimeMS": _COMMAND_MS}
                ))
        return validate_writer_policy(*results)
    except MongoWriterPolicyError:
        raise
    except Exception:
        # Backend admin exceptions may contain Mongo connection credentials.
        raise MongoWriterPolicyError("real Mongo journal policy query failed") from None


def observe_writer_policy_sync(client: Any) -> dict[str, object]:
    """Read exactly five Mongo admin commands via an existing sync client.

    The physical Docker audit uses a fresh authenticated client inside each
    existing service, never a host URI or a connection to the other process.
    """
    if not callable(getattr(getattr(client, "admin", None), "command", None)):
        raise MongoWriterPolicyError("synchronous Mongo admin client unavailable")
    try:
        import time
        end = time.monotonic() + _DEADLINE_S
        results = []
        for name in ("hello", "replSetGetStatus", "replSetGetConfig",
                     "getDefaultRWConcern", "hello"):
            if time.monotonic() >= end:
                raise MongoWriterPolicyError("synchronous Mongo policy deadline expired")
            results.append(client.admin.command(
                {name: 1, "maxTimeMS": _COMMAND_MS}
            ))
        if time.monotonic() >= end:
            raise MongoWriterPolicyError("synchronous Mongo policy deadline expired")
        return validate_writer_policy(*results)
    except MongoWriterPolicyError:
        raise
    except Exception:
        raise MongoWriterPolicyError(
            "synchronous authenticated journal policy unavailable"
        ) from None


_SOURCE_ROLES = {
    "backend": frozenset({
        "conversation_threads", "conversation_messages",
    }),
    "engine": frozenset({
        "canonical_memory_records", "canonical_memory_idempotency",
        "canonical_memory_revisions", "canonical_memory_projection_outbox",
    }),
}


def validate_source_collection_concerns(
    role: str, collections: object,
) -> dict[str, object]:
    """Deny any source handle explicitly weakening verified server defaults.

    Motor/PyMongo WriteConcern() with an empty document inherits the
    independently admitted server w=majority + journal-majority policy.
    Explicit w:1, j:false, unacknowledged or malformed collection overrides
    must never be allowed to publish an even/stable writer epoch.
    """
    if (type(role) is not str or role not in _SOURCE_ROLES
            or not isinstance(collections, Mapping)
            or set(collections) != _SOURCE_ROLES[role]):
        raise MongoWriterPolicyError("canonical source collection inventory invalid")
    try:
        from pymongo.write_concern import WriteConcern
        inherited = 0
        for name in sorted(collections):
            collection = collections[name]
            concern = getattr(collection, "write_concern", None)
            if not isinstance(concern, WriteConcern):
                raise MongoWriterPolicyError("canonical source write concern unavailable")
            document = concern.document
            if (type(document) is not dict
                    or set(document) - {"w", "j", "wtimeout"}
                    or ("w" in document and document["w"] != "majority")
                    or ("j" in document and document["j"] is not True)
                    or ("wtimeout" in document
                        and (type(document["wtimeout"]) is not int
                             or document["wtimeout"] < 0))):
                raise MongoWriterPolicyError(
                    "canonical source weakens majority journal policy"
                )
            if not document:
                inherited += 1
        return {
            "schema": "skeleton.local-ai.mongo-source-write-handles.v1",
            "source_role": role,
            "collection_count": len(collections),
            "server_default_inheriting_collections": inherited,
            "weak_write_concern_overrides_detected": False,
            "database_documents_read": False,
            "database_writes_performed": False,
            "production_writer_registry_complete": False,
            "actor_migration_qualified": False,
        }
    except MongoWriterPolicyError:
        raise
    except Exception:
        raise MongoWriterPolicyError(
            "canonical source write-concern admission unavailable"
        ) from None


__all__ = [
    "MongoWriterPolicyError", "validate_writer_policy",
    "observe_writer_policy_async", "observe_writer_policy_sync",
    "validate_source_collection_concerns",
]

