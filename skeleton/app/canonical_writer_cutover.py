"""Signed, read-only canonical writer cutover qualification.

This is not a database migration. It compares a quiescent, independently
reviewed inventory against the live primary and actual backend owners.
No actor discovery result grants authorization. No missing epoch is created;
no ambiguous or revoked generation is reset. External writer retirement,
backup truth, and physical cluster identity remain operator-held controls.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, fields
import hashlib
import inspect
import json
import re
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference

from skeleton.app.compose_guarded_preflight import (
    _authenticated_principals, _database_name, _scope, _trusted_topology,
)
from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, _verified_epoch_record,
)

_DOMAIN = b"skeleton.canonical-writer-cutover.v1\0"
_SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z", re.ASCII)
_MAX_PLAN_BYTES = 256 * 1024
_MAX_ACTORS = 65536
_MAX_VALIDITY = 600
_SCAN_TIMEOUT = 120
_SCAN_MS = 15000
_BATCH = 32


class WriterCutoverDenied(RuntimeError):
    pass


def _require(condition):
    if condition is not True:
        raise WriterCutoverDenied("canonical writer cutover not qualified")


def _digest(value):
    return type(value) is str and _HEX.fullmatch(value) is not None and value != "0"*64


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _constant(_):
    raise WriterCutoverDenied("invalid cutover document")


@dataclass(frozen=True, slots=True)
class CanonicalWriterCutover:
    authority_id: str
    deployment_id: str
    source_head: str
    database_name: str
    replica_set: str
    voting_hosts: tuple[str, ...]
    principal_inventory: tuple[tuple[str, str], ...]
    issued_at: int
    expires_at: int
    epoch_count: int
    source_scope_count: int
    inventory_sha256: str
    backup_sha256: str
    quiescence_sha256: str
    external_writer_retirement_sha256: str
    storage_provenance_sha256: str

    def __post_init__(self):
        _require(all(type(v) is str and _ID.fullmatch(v) is not None
                     for v in (self.authority_id, self.deployment_id, self.replica_set)))
        _require(type(self.source_head) is str and _SHA.fullmatch(self.source_head) is not None)
        _require(_database_name(self.database_name))
        hosts = self.voting_hosts
        _require(type(hosts) is tuple and 1 <= len(hosts) <= 64)
        _require(all(type(host) is str and 1 <= len(host) <= 512 and host.isascii()
                     and all(33 <= ord(ch) <= 126 for ch in host) for host in hosts))
        _require(tuple(sorted(set(hosts))) == hosts)
        principals = self.principal_inventory
        _require(type(principals) is tuple and 3 <= len(principals) <= 81)
        _require(all(type(pair) is tuple and len(pair) == 2 and
                     all(type(v) is str for v in pair) for pair in principals))
        _require(principals.count(("ROLE_BOUNDARY", "")) == 1)
        boundary = principals.index(("ROLE_BOUNDARY", ""))
        _require(1 <= boundary <= 16 and 1 <= len(principals)-boundary-1 <= 64)
        for part in (principals[:boundary], principals[boundary+1:]):
            _require(tuple(sorted(set(part))) == part)
            _require(all(_scope(v) and len(v.encode("utf-8")) <= 256 for pair in part for v in pair))
        _require(type(self.issued_at) is int and type(self.expires_at) is int
                 and 0 < self.issued_at < self.expires_at < (1<<63)
                 and self.expires_at-self.issued_at <= _MAX_VALIDITY)
        _require(type(self.epoch_count) is int and type(self.source_scope_count) is int
                 and 0 <= self.source_scope_count <= self.epoch_count <= _MAX_ACTORS)
        _require(all(_digest(v) for v in (self.inventory_sha256, self.backup_sha256,
                 self.quiescence_sha256, self.external_writer_retirement_sha256,
                 self.storage_provenance_sha256)))

    def document(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def canonical_bytes(self):
        raw = _DOMAIN + _canonical(self.document())
        _require(len(raw) <= _MAX_PLAN_BYTES)
        return raw

    def assert_current(self):
        _require(self.issued_at <= int(time.time()) < self.expires_at)

    @classmethod
    def parse(cls, raw):
        _require(type(raw) is bytes and 1 <= len(raw) <= _MAX_PLAN_BYTES)
        try:
            doc = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique,
                             parse_constant=_constant)
            _require(type(doc) is dict and set(doc) == {f.name for f in fields(cls)})
            _require(type(doc["voting_hosts"]) is list and type(doc["principal_inventory"]) is list)
            _require(all(type(v) is list for v in doc["principal_inventory"]))
            doc["voting_hosts"] = tuple(doc["voting_hosts"])
            doc["principal_inventory"] = tuple(tuple(v) for v in doc["principal_inventory"])
            return cls(**doc)
        except WriterCutoverDenied:
            raise
        except Exception:
            raise WriterCutoverDenied("invalid cutover document") from None


@dataclass(frozen=True, slots=True)
class VerifiedWriterCutover:
    plan: CanonicalWriterCutover
    signature: bytes
    authority_id: str
    deployment_id: str
    source_head: str
    public_key: bytes

    def __post_init__(self):
        self.verify()

    def verify(self):
        _require(type(self.plan) is CanonicalWriterCutover
                 and self.plan.authority_id == self.authority_id
                 and self.plan.deployment_id == self.deployment_id
                 and self.plan.source_head == self.source_head
                 and type(self.signature) is bytes and len(self.signature) == 64
                 and type(self.public_key) is bytes and len(self.public_key) == 32)
        self.plan.assert_current()
        try:
            Ed25519PublicKey.from_public_bytes(self.public_key).verify(
                self.signature, self.plan.canonical_bytes())
        except (InvalidSignature, TypeError, ValueError):
            raise WriterCutoverDenied("cutover signature invalid") from None


@dataclass(frozen=True, slots=True)
class CutoverInventory:
    epochs: tuple[tuple[str, int], ...]
    source_scopes: tuple[str, ...]

    def __post_init__(self):
        _require(type(self.epochs) is tuple and type(self.source_scopes) is tuple
                 and len(self.source_scopes) <= len(self.epochs) <= _MAX_ACTORS)
        _require(all(type(row) is tuple and len(row) == 2 and _digest(row[0])
                     and type(row[1]) is int and 2 <= row[1] < (1<<63)
                     and row[1] % 2 == 0 for row in self.epochs))
        keys = tuple(row[0] for row in self.epochs)
        _require(tuple(sorted(set(keys))) == keys)
        _require(all(_digest(v) for v in self.source_scopes)
                 and tuple(sorted(set(self.source_scopes))) == self.source_scopes
                 and set(self.source_scopes).issubset(keys))

    @property
    def digest(self):
        return hashlib.sha256(b"skeleton.canonical-epoch-inventory.v1\0"+_canonical({
            "epochs": self.epochs, "source_scopes": self.source_scopes,
        })).hexdigest()

    def matches(self, plan):
        return (type(plan) is CanonicalWriterCutover
                and self.digest == plan.inventory_sha256
                and len(self.epochs) == plan.epoch_count
                and len(self.source_scopes) == plan.source_scope_count)


async def _observe(database):
    first = _trusted_topology(await database.command("hello"))
    auth = _authenticated_principals(await database.command("connectionStatus"))
    second = _trusted_topology(await database.command("hello"))
    _require(first is not None and first == second and auth is not None
             and ("ROLE_BOUNDARY","") in auth and auth[-1] != ("ROLE_BOUNDARY",""))
    # Unlike a shallow ping, require an actual self-consistent advertised
    # voting topology and election/process generation. No DNS or host alias
    # normalization (same name is not physical cluster identity).
    _require(first[1] is not None and first[2] is not None
             and type(first[3]) is tuple and len(first[3]) >= 1
             and first[6] is not None and first[7] is not None
             and first[8] is not None and first[9] is not None)
    return first, auth


def _match_observation(plan, observed, database):
    topology, auth = observed
    _require(database.name == plan.database_name and topology[0] == plan.replica_set
             and topology[3] == plan.voting_hosts and auth == plan.principal_inventory)


async def _cursor_rows(cursor, bound):
    if inspect.isawaitable(cursor):
        cursor = await cursor
    count = 0
    try:
        async for row in cursor:
            count += 1
            _require(count <= bound and type(row) is dict)
            yield row
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


def _majority(collection):
    return collection.with_options(read_concern=ReadConcern("majority"),
                                   read_preference=ReadPreference.PRIMARY)


async def _scope_inventory(collection, actor_field, maximum):
    # No payload extraction. Group existing canonical owner roots by exact
    # tenant and actor identifiers. Missing/malformed fields deny instead of
    # silently skipping legacy data. Limit unique scopes, not document size.
    cursor = _majority(collection).aggregate([
        {"$group": {"_id": {"tenant": "$tenant_id", "actor": "$"+actor_field}}},
        {"$limit": maximum+1},
    ], allowDiskUse=False, maxTimeMS=_SCAN_MS)
    seen = set()
    async for row in _cursor_rows(cursor, maximum):
        scope = row.get("_id")
        _require(type(scope) is dict and set(scope) == {"tenant","actor"})
        _require(_scope(scope["tenant"]) and _scope(scope["actor"]))
        key = MongoCanonicalSourceEpoch._key(scope["tenant"], scope["actor"])
        _require(key not in seen)
        seen.add(key)
    return seen


async def _inventory(epoch, *, threads, records, maximum, verify_linearizable):
    locations = {}
    cursor = _majority(epoch._collection).find({}, {
        "_id":1, "tenant_id":1, "actor_id":1, "phase":1, "epoch":1, "writer_token":1,
    }).sort("_id", 1).limit(maximum+1).max_time_ms(_SCAN_MS)
    async for row in _cursor_rows(cursor, maximum):
        key, tenant, actor = row.get("_id"), row.get("tenant_id"), row.get("actor_id")
        _require(_scope(tenant) and _scope(actor) and _digest(key)
                 and key == epoch._key(tenant, actor) and key not in locations)
        gen = _verified_epoch_record(row, key=key, tenant_id=tenant, actor_id=actor,
                                     phase="stable", writer_token=None)
        _require(type(gen) is int)
        locations[key] = (tenant, actor, gen)
    scopes = (await _scope_inventory(threads, "owner_id", maximum)
              | await _scope_inventory(records, "subject_id", maximum))
    _require(scopes.issubset(locations))
    if verify_linearizable:
        async def check(row):
            tenant, actor, gen = row
            _require(await epoch.read_epoch(tenant_id=tenant, actor_id=actor, context_id=actor) == gen)
        ordered = list(locations.values())
        for i in range(0, len(ordered), _BATCH):
            async with asyncio.TaskGroup() as group:
                for current in ordered[i:i+_BATCH]:
                    group.create_task(check(current))
    return CutoverInventory(tuple(sorted((k,v[2]) for k,v in locations.items())),
                            tuple(sorted(scopes)))


async def qualify_writer_cutover(approval, *, epoch, threads, records):
    """Validate two identical majority inventories plus per-actor linearizable reads.

    Bound every database observation, deny incomplete inventories, and verify
    the independent signed plan before and after I/O. This only scans thread
    and memory roots, not all message, idempotency, revision, outbox, archive
    or external writer surfaces. Those remain independently reviewed.
    """
    _require(type(approval) is VerifiedWriterCutover and type(epoch) is MongoCanonicalSourceEpoch)
    approval.verify()
    plan, database = approval.plan, epoch._database
    for collection, name in ((threads,"conversation_threads"),(records,"canonical_memory_records"),
                             (epoch._collection,"canonical_source_epochs"),(epoch._reader,"canonical_source_epochs")):
        _require(collection.name == name and collection.database.name == plan.database_name
                 and collection.database.client is database.client)
    try:
        async with asyncio.timeout(_SCAN_TIMEOUT):
            start = await _observe(database)
            _match_observation(plan, start, database)
            first = await _inventory(epoch, threads=threads, records=records,
                                     maximum=plan.epoch_count, verify_linearizable=True)
            _require(first.matches(plan))
            second = await _inventory(epoch, threads=threads, records=records,
                                      maximum=plan.epoch_count, verify_linearizable=False)
            end = await _observe(database)
            _require(first == second and start == end)
            approval.verify()
            return first
    except WriterCutoverDenied:
        raise
    except Exception:
        raise WriterCutoverDenied("live canonical writer inventory unavailable") from None


__all__ = ["CanonicalWriterCutover", "VerifiedWriterCutover", "CutoverInventory",
           "WriterCutoverDenied", "qualify_writer_cutover"]
