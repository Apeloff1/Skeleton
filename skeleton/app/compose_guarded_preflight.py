"""Read-only Compose Mongo epoch preflight; never claims AI is activated.

Run inside the backend container with authenticated MONGO_URL, DB_NAME and
operator-selected canonical actor scope. No credentials, actor identifiers,
conversation contents or exception strings are emitted. No migrations, index
creation, epoch provisioning, writes, or model execution occur.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch

SCHEMA = "skeleton.app.compose_guarded_mongo_preflight.v1"


def _result(code: str, *, replica_set: bool = False, epoch: bool = False, authenticated: bool = False) -> dict[str, object]:
    return {
        "schema_version": SCHEMA,
        "code": code,
        "mongo_replica_set_primary_observed": replica_set,
        "mongo_authenticated_session_observed": authenticated,
        "canonical_actor_epoch_stable_observed": epoch,
        "canonical_writer_inventory_verified": False,
        "canonical_database_name_aligned_observed": False,
        "shared_epoch_database_selected": False,
        "canonical_cluster_identity_verified": False,
        "independent_reviewer_verified": False,
        "activated_model_tokenizer_verified": False,
        "guarded_local_ai_ready": False,
        "consumer_or_device_qualified": False,
        "writes_performed": False,
    }


def _database_name(value: object) -> bool:
    """Conservative Mongo database identifier; never accept URI/path syntax."""
    return (
        type(value) is str and 1 <= len(value) <= 63
        and value.isascii()
        and value[0].isalnum()
        and all(ch.isalnum() or ch in "_-" for ch in value)
    )


def _scope(value: object) -> bool:
    try:
        return (
            type(value) is str and bool(value)
            and value == value.strip()
            and len(value.encode("utf-8", errors="strict")) <= 512
            and all(ord(ch) >= 32 and ord(ch) != 127 for ch in value)
        )
    except UnicodeError:
        return False


def _plain_document(value: object, *, limit: int = 128) -> bool:
    # Check key types before any lookup: an injected key may implement
    # arbitrary equality or hashing even inside a real dict.
    return (
        type(value) is dict and len(value) <= limit
        and all(type(key) is str and 0 < len(key) <= 128 for key in value)
    )


def _wire_integer(value: object) -> int | None:
    if type(value) is int:
        return value
    try:
        from bson.int64 import Int64
    except ImportError:
        return None
    if type(value) is Int64:
        return int(value)
    return None


def _valid_principal_utf8(value: str) -> bool:
    """Reject unpaired surrogates and oversized identities before comparison."""
    try:
        return len(value) <= 128 and len(value.encode("utf-8", errors="strict")) <= 256
    except UnicodeError:
        return False


def _authenticated_principals(response: object) -> tuple[tuple[str, str], ...] | None:
    """Bound and normalize Mongo identities without logging their values.

    Reject malformed, duplicated or excessively large server responses before
    sorting. This is an authentication observation, not role authorization.
    """
    if not _plain_document(response) or not _plain_document(response.get("authInfo")):
        return None
    users = response["authInfo"].get("authenticatedUsers")
    if type(users) is not list or not 1 <= len(users) <= 16:
        return None
    principals: list[tuple[str, str]] = []
    for user in users:
        if not _plain_document(user, limit=16):
            return None
        identity = []
        for key in ("db", "user"):
            value = user.get(key)
            if (type(value) is not str or not value or value != value.strip()
                    or not _valid_principal_utf8(value)
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
                return None
            identity.append(value)
        principals.append((identity[0], identity[1]))
    if len(set(principals)) != len(principals):
        return None
    # Bind the observation to authenticated role assignments when supplied.
    # Missing role metadata is not authorization evidence; this is strictly
    # an additional fail-closed rotation detector, never a readiness grant.
    auth_info = response["authInfo"]
    # Explicit null is malformed metadata, not an absent optional field.
    # Otherwise a role-custody rotation could disappear into a null response
    # and be treated as an unchanged authenticated identity.
    if "authenticatedUserRoles" not in auth_info:
        return tuple(sorted(principals))
    roles = auth_info["authenticatedUserRoles"]
    if type(roles) is not list or len(roles) > 64:
        return None
    trusted_roles: list[tuple[str, str]] = []
    for role in roles:
        if not _plain_document(role, limit=16):
            return None
        pair: list[str] = []
        for key in ("db", "role"):
            value = role.get(key)
            if (type(value) is not str or not value or value != value.strip()
                    or not _valid_principal_utf8(value)
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
                return None
            pair.append(value)
        trusted_roles.append((pair[0], pair[1]))
    if len(set(trusted_roles)) != len(trusted_roles):
        return None
    return tuple(sorted(principals)) + (("ROLE_BOUNDARY", ""),) + tuple(sorted(trusted_roles))


def _trusted_topology(hello: object) -> tuple[object, ...] | None:
    """Snapshot only inert Mongo hello scalars before cross-await comparisons.

    Never invoke equality, string conversion or hashing on arbitrary driver
    values. Optional fields may be absent on older Mongo versions; malformed
    present fields invalidate the observation.
    """
    if not _plain_document(hello) or hello.get("isWritablePrimary") is not True:
        return None
    # A writable primary must not simultaneously assert a secondary or
    # arbiter role. Reject contradictory and non-boolean role flags before
    # reading the canonical epoch; never coerce arbitrary driver values.
    # Legacy hello fields can coexist with modern primary flags. A server
    # claiming writable-primary while explicitly denying legacy primary
    # status is contradictory; do not use it as an epoch authority.
    # Present-but-null role claims are malformed, not absent. Reject them
    # before canonical epoch custody to prevent ambiguous role transitions.
    if any(field in hello and hello[field] is None
           for field in ("ismaster", "secondary", "arbiterOnly")):
        return None
    legacy_primary = hello.get("ismaster")
    if legacy_primary is not None and legacy_primary is not True:
        return None
    for role in ("secondary", "arbiterOnly"):
        role_value = hello.get(role)
        if role_value is not None and type(role_value) is not bool:
            return None
        if role_value is True:
            return None
    # A mongos router can report writable-primary semantics without being a
    # replica-set primary. A ghost replica-set member is likewise not a
    # canonical writer. Explicit contradictory server roles fail closed.
    # These are topology observations only, never an activation certificate.
    # Explicit null authority flags are malformed rather than absent. A
    # proxy/ghost-role transition must not collapse to an omitted field.
    if any(field in hello and hello[field] is None for field in (
        "msg", "loadBalanced", "isreplicaset",
    )):
        return None
    msg = hello.get("msg")
    if msg is not None and (type(msg) is not str or msg == "isdbgrid"
                            or not 1 <= len(msg) <= 128 or not msg.isascii()
                            or any(ord(ch) < 33 or ord(ch) > 126 for ch in msg)):
        return None
    # A load-balanced proxy is not an independently observed replica-set
    # writer, even if a synthetic hello response includes primary fields.
    # A serviceId denotes a load-balanced service endpoint rather than a
    # stable Mongo election identity. Neither may authorize epoch custody.
    load_balanced = hello.get("loadBalanced")
    if load_balanced is not None and (type(load_balanced) is not bool or load_balanced):
        return None
    if "serviceId" in hello:
        return None
    ghost = hello.get("isreplicaset")
    if ghost is not None and (type(ghost) is not bool or ghost is True):
        return None
    # A present-but-null authority field is not an omitted optional field.
    # In particular, null membership or election identity must not silently
    # collapse into the same snapshot as an older server omitting that field.
    if any(field in hello and hello[field] is None for field in (
        "me", "primary", "hosts", "passives", "arbiters",
        "electionId", "setVersion", "topologyVersion",
    )):
        return None
    name = hello.get("setName")
    if (type(name) is not str or not 1 <= len(name) <= 128
            or not name.isascii()
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in name)):
        return None
    values: list[object] = [name]
    for field in ("me", "primary"):
        value = hello.get(field)
        if value is not None and (type(value) is not str or not value
                                  or len(value) > 512 or not value.isascii()
                                  or "\\" in value or "/" in value
                                  or any(ord(ch) < 33 or ord(ch) > 126 for ch in value)):
            return None
        values.append(value)
    # A primary claiming two distinct endpoints cannot establish a stable
    # writer authority. Reject it before observing an epoch; never normalize
    # or resolve hostnames here because that would introduce network TOCTOU.
    if values[1] is not None and values[2] is not None and values[1] != values[2]:
        return None
    # A claimed primary must not disappear from its own advertised voting
    # topology. Treat membership as an observation only: no DNS resolution,
    # authorization claim or automatic replica-set reconfiguration.
    membership: list[object] = []
    seen_hosts: set[str] = set()
    for field in ("hosts", "passives", "arbiters"):
        hosts = hello.get(field)
        if hosts is None:
            membership.append(None)
            continue
        if (type(hosts) is not list or (field == "hosts" and not hosts)
                or len(hosts) > 64 or len(seen_hosts) + len(hosts) > 64):
            return None
        trusted: list[str] = []
        for host in hosts:
            if (type(host) is not str or not 1 <= len(host) <= 512
                    or not host.isascii() or "\\" in host or "/" in host
                    or any(ord(ch) < 33 or ord(ch) > 126 for ch in host)
                    or host in seen_hosts):
                return None
            seen_hosts.add(host)
            trusted.append(host)
        membership.append(tuple(sorted(trusted)))
    # Both advertised identities of this writable primary must be present in
    # the voting host set when supplied. Checking only `primary` misses a
    # contradictory `me` when `primary` is omitted; never treat that as a
    # trusted stable topology across an epoch read.
    if hello.get("hosts") is not None:
        for endpoint in (values[1], values[2]):
            if endpoint is not None and endpoint not in membership[0]:
                return None
    # A writable primary cannot simultaneously advertise itself as a passive
    # or arbiter. Even when the voting-host list is omitted, these conflicting
    # role claims invalidate the snapshot before any canonical epoch read.
    # This is a consistency check, not a topology discovery or activation grant.
    for endpoint in (values[1], values[2]):
        if endpoint is not None and any(
            endpoint in members for members in membership[1:] if members is not None
        ):
            return None
    values.extend(membership)
    election = hello.get("electionId")
    if election is not None:
        try:
            from bson.objectid import ObjectId
        except ImportError:
            return None
        if type(election) is ObjectId:
            election = election.binary
        elif type(election) is not str or not election or len(election) > 128:
            return None
        elif (not election.isascii() or "\\" in election
              or any(ord(ch) < 33 or ord(ch) > 126 for ch in election)):
            return None
    values.append(election)
    version = hello.get("setVersion")
    if version is not None:
        version = _wire_integer(version)
        if version is None or not 0 <= version < (1 << 63):
            return None
    values.append(version)
    # A primary can retain its election identifier while its topology
    # generation changes. Snapshot the generation as inert exact types.
    topology = hello.get("topologyVersion")
    if topology is not None:
        if (type(topology) is not dict or len(topology) != 2
                or any(type(key) is not str for key in topology)
                or "processId" not in topology or "counter" not in topology):
            return None
        try:
            from bson.objectid import ObjectId
        except ImportError:
            return None
        process = topology["processId"]
        counter = _wire_integer(topology["counter"])
        if type(process) is not ObjectId or counter is None:
            return None
        if not 0 <= counter < (1 << 63):
            return None
        values.extend((process.binary, counter))
    else:
        values.extend((None, None))
    return tuple(values)


async def inspect_compose_mongo_epoch(
    database: Any, *, tenant_id: str, actor_id: str, context_id: str,
) -> dict[str, object]:
    """Inspect only Mongo's read concern and a provisioned actor epoch.

    Even a successful result does not establish cross-process writer coverage,
    independent reviewer trust, native tokenizer binding or release readiness.
    """
    if not all(_scope(x) for x in (tenant_id, actor_id, context_id)):
        return _result("operator_actor_scope_required")
    if not callable(getattr(database, "command", None)):
        return _result("mongo_authority_unavailable")
    try:
        async with asyncio.timeout(3.0):
            hello = await database.command("hello")
    except Exception:
        return _result("mongo_primary_probe_unavailable")
    initial_topology = _trusted_topology(hello)
    if initial_topology is None:
        return _result("mongo_replica_set_primary_required")
    # These fields are the stable parts of a primary observation. A changed
    # election, host or replica-set identity during preflight invalidates
    # the read window. No field here is a cryptographic cluster identity.
    # A healthy unauthenticated replica set is not an acceptable canonical
    # custody authority. Inspect the current connection without publishing
    # usernames, role names, credentials or raw server responses.
    try:
        async with asyncio.timeout(3.0):
            auth = await database.command("connectionStatus")
    except Exception:
        return _result("mongo_authenticated_session_unavailable", replica_set=True)
    initial_users = _authenticated_principals(auth)
    if initial_users is None:
        return _result("mongo_authenticated_session_required", replica_set=True)
    try:
        epoch = MongoCanonicalSourceEpoch(database)
        async with asyncio.timeout(3.0):
            first_epoch = await epoch.read_epoch(
                tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
            )
        # A single successful read can be superseded by an intervening
        # canonical writer or primary election. Recheck both after the first
        # read, never claiming a continuous lock or complete writer inventory.
        async with asyncio.timeout(3.0):
            last_hello = await database.command("hello")
        if _trusted_topology(last_hello) != initial_topology:
            return _result("mongo_primary_changed_during_preflight",
                           replica_set=True, authenticated=True)
        # Authentication may rotate while the epoch read is in flight. A
        # stable primary and epoch do not prove the same authenticated writer.
        async with asyncio.timeout(3.0):
            final_auth = await database.command("connectionStatus")
        if _authenticated_principals(final_auth) != initial_users:
            return _result("mongo_principal_changed_during_preflight",
                           replica_set=True, authenticated=False)
        async with asyncio.timeout(3.0):
            final_epoch = await epoch.read_epoch(
                tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
            )
        if (type(first_epoch) is not int or type(final_epoch) is not int
                or not 2 <= first_epoch < (1 << 63) or first_epoch % 2
                or final_epoch != first_epoch):
            return _result("canonical_actor_epoch_changed_during_preflight",
                           replica_set=True, authenticated=True)
        # The second linearizable read can itself span an election or a
        # credential rotation. Recheck both authorities AFTER that await;
        # a previously matching epoch is not a permit to ignore this race.
        async with asyncio.timeout(3.0):
            post_hello = await database.command("hello")
            post_auth = await database.command("connectionStatus")
        if _trusted_topology(post_hello) != initial_topology:
            return _result("mongo_primary_changed_during_final_epoch_read",
                           replica_set=True, authenticated=False)
        if _authenticated_principals(post_auth) != initial_users:
            return _result("mongo_principal_changed_during_final_epoch_read",
                           replica_set=True, authenticated=False)
        # The final authentication probe is another network await. An
        # election during that probe must not be reported as a stable
        # topology observation. This is still NOT a writer lease.
        async with asyncio.timeout(3.0):
            terminal_hello = await database.command("hello")
        if _trusted_topology(terminal_hello) != initial_topology:
            return _result("mongo_primary_changed_after_final_authentication",
                           replica_set=True, authenticated=False)
    except Exception:
        return _result("canonical_actor_epoch_unavailable", replica_set=True, authenticated=True)
    return _result("mongo_epoch_observed_only", replica_set=True, epoch=True, authenticated=True)


async def _run_from_environment(
    *, source: str = "backend", shared_epoch_database: str | None = None,
    scope: tuple[str, str, str] | None = None,
) -> dict[str, object]:
    """Observe one deployed source principal; never connect using CLI secrets."""
    if source not in ("backend", "engine"):
        return _result("mongo_connection_configuration_required")
    uri = os.environ.get("MONGO_URL" if source == "backend" else "SKL_MONGO_URI", "")
    name = os.environ.get("DB_NAME" if source == "backend" else "SKL_MONGO_DATABASE", "")
    if scope is None:
        scope = (
            os.environ.get("SKL_CANONICAL_TENANT_ID", ""),
            os.environ.get("SKL_CANONICAL_ACTOR_ID", ""),
            os.environ.get("SKL_CANONICAL_CONTEXT_ID", ""),
        )
    if type(scope) is not tuple or len(scope) != 3:
        return _result("operator_actor_scope_required")
    tenant_id, actor_id, context_id = scope
    if not all(_scope(x) for x in (tenant_id, actor_id, context_id)):
        return _result("operator_actor_scope_required")
    if not uri or not _database_name(name) or len(uri) > 8192:
        return _result("mongo_connection_configuration_required")
    # Compose backend and engine use distinct logical Mongo databases by
    # default. An epoch in one database cannot fence writes in the other.
    # This value is a non-secret, explicitly supplied engine configuration,
    # NOT an automatic migration or evidence of matching server identities.
    # Legacy mode observes a same-named database only. Explicit shared
    # mode observes the named witness through this service's own credentials;
    # the backend and engine source databases remain untouched and distinct.
    if shared_epoch_database is None:
        engine_name = os.environ.get("SKL_CANONICAL_MONGO_DATABASE", "")
        if not _database_name(engine_name):
            return _result("canonical_engine_database_identity_required")
        if name != engine_name:
            return _result("canonical_database_identity_mismatch")
        target_name = name
    else:
        if not _database_name(shared_epoch_database):
            return _result("canonical_shared_epoch_database_identity_required")
        target_name = shared_epoch_database
    client = None
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(
            uri, connect=False, maxPoolSize=2, minPoolSize=0,
            serverSelectionTimeoutMS=2000, connectTimeoutMS=2000,
            socketTimeoutMS=2000, retryWrites=False, retryReads=False,
            appname="skeleton-guarded-mongo-readonly-preflight",
        )
        # Bound the complete read-only preflight, not just individual Mongo
        # commands. A slow chain of successful probes must not hang first run.
        observed = await asyncio.wait_for(
            inspect_compose_mongo_epoch(
                client[target_name], tenant_id=tenant_id, actor_id=actor_id,
                context_id=context_id,
            ), timeout=12.0,
        )
        # A matching database NAME alone cannot establish the same cluster,
        # writer role or physical replica set. Never mark those as verified.
        observed["canonical_database_name_aligned_observed"] = shared_epoch_database is None
        observed["shared_epoch_database_selected"] = shared_epoch_database is not None
        return observed
    except TimeoutError:
        # Timeout is an unknown custody outcome, never an activation permit.
        return _result("mongo_preflight_deadline_exceeded")
    except Exception:
        return _result("mongo_primary_probe_unavailable")
    finally:
        if client is not None:
            client.close()


def _read_private_scope(stream: Any) -> tuple[str, str, str]:
    raw = stream.read(4097)
    if type(raw) is not bytes or not 1 <= len(raw) <= 4096:
        raise ValueError("invalid scope input")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("invalid scope input")
            output[key] = value
        return output

    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("invalid scope input") from None
    fields = ("tenant_id", "actor_id", "context_id")
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("invalid scope input")
    scope = tuple(value[field] for field in fields)
    if not all(_scope(part) for part in scope):
        raise ValueError("invalid scope input")
    return scope


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.app.compose_guarded_preflight",
        description="Read-only Mongo epoch observation; never authorizes inference.",
    )
    parser.add_argument("--source", choices=("backend", "engine"), default="backend")
    parser.add_argument("--shared-epoch-database", help="explicit existing epoch database")
    parser.add_argument("--scope-stdin", action="store_true", help="read bounded scope JSON from stdin")
    parser.add_argument("--summary", action="store_true", help="emit redacted first-run observation summary")
    args = parser.parse_args(argv)
    try:
        scope = _read_private_scope(sys.stdin.buffer) if args.scope_stdin else None
    except (OSError, ValueError, TypeError, AttributeError):
        result = _result("operator_actor_scope_required")
    else:
        try:
            if not argv:  # preserve the existing environment-only seam
                result = asyncio.run(_run_from_environment())
            else:
                result = asyncio.run(_run_from_environment(
                    source=args.source, shared_epoch_database=args.shared_epoch_database,
                    scope=scope,
                ))
        except Exception:
            result = _result("mongo_primary_probe_unavailable")
    if args.summary:
        from skeleton.app.compose_mongo_first_run_status import summarize_observation
        result = summarize_observation(result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 2  # Observation-only CLI must never authorize activation.


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
