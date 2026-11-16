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

_DOMAIN = b"skeleton.canonical-writer-cutover.v2\0"
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
    graph_sha256: str
    collection_counts: tuple[tuple[str, int], ...]

    def __post_init__(self):
        _require(type(self.epochs) is tuple and type(self.source_scopes) is tuple
                 and len(self.source_scopes) <= len(self.epochs) <= _MAX_ACTORS)
        _require(all(type(row) is tuple and len(row) == 2 and _digest(row[0])
                     and type(row[1]) is int and 2 <= row[1] < (1<<63)
                     and row[1] % 2 == 0 for row in self.epochs))
        _require(_digest(self.graph_sha256) and type(self.collection_counts) is tuple
                 and all(type(row) is tuple and len(row) == 2 for row in self.collection_counts)
                 and tuple(name for name, _ in self.collection_counts) == tuple(_GRAPH_FIELDS)
                 and all(type(count) is int and 0 <= count <= _GRAPH_LIMIT
                         for _, count in self.collection_counts))
        keys = tuple(row[0] for row in self.epochs)
        _require(tuple(sorted(set(keys))) == keys)
        _require(all(_digest(v) for v in self.source_scopes)
                 and tuple(sorted(set(self.source_scopes))) == self.source_scopes
                 and set(self.source_scopes).issubset(keys))

    @property
    def digest(self):
        return hashlib.sha256(b"skeleton.canonical-epoch-inventory.v2\0"+_canonical({
            "epochs": self.epochs, "source_scopes": self.source_scopes,
            "graph_sha256": self.graph_sha256, "collection_counts": self.collection_counts,
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


# Bounded metadata-only graph of the six known canonical source collections.
_GRAPH_LIMIT = 250_000
_GRAPH_FIELDS = {
    "threads": ("_id", "thread_id", "tenant_id", "owner_id", "version", "message_sequence"),
    "messages": ("_id", "message_id", "thread_id", "sequence", "_commit_state"),
    "records": ("repository_namespace", "memory_id", "tenant_id", "namespace",
                "subject_id", "version"),
    "revisions": ("repository_namespace", "memory_id", "tenant_id", "namespace",
                  "version", "record.memory_id", "record.tenant_id", "record.namespace",
                  "record.subject_id", "record.version"),
    "projection_outbox": ("repository_namespace", "event_id", "memory_id", "tenant_id",
                          "namespace", "memory_version", "action", "record.memory_id",
                          "record.tenant_id", "record.namespace", "record.subject_id",
                          "record.version", "published_at"),
    "idempotency": ("repository_namespace", "memory_id", "tenant_id", "namespace",
                    "idempotency_key", "request_digest", "status", "result.memory_id",
                    "result.tenant_id", "result.namespace", "result.subject_id",
                    "result.version"),
}
_GRAPH_NAMES = {
    "threads": "conversation_threads", "messages": "conversation_messages",
    "records": "canonical_memory_records", "revisions": "canonical_memory_revisions",
    "projection_outbox": "canonical_memory_projection_outbox",
    "idempotency": "canonical_memory_idempotency",
}


def _identity(value):
    _require(_scope(value))
    return value


def _number(value, minimum=1):
    from bson.int64 import Int64
    _require(type(value) in (int, Int64) and minimum <= value < (1 << 63))
    return int(value)


class _OwnerGraph:
    """Structural metadata evidence, not payload or historical completeness."""

    def __init__(self, repository_namespace):
        self.namespace = _identity(repository_namespace)
        self.threads = {}
        self.records = {}
        self.scopes = set()
        self.counts = {}
        self.unique = set()
        self.lane = None
        self.hash = hashlib.sha256(b"skeleton.canonical-local-owner-graph.v1\0")
        self.hash.update(_canonical(self.namespace))

    def begin(self, lane):
        _require(lane in _GRAPH_FIELDS and lane not in self.counts)
        if self.lane is not None:
            self.hash.update(_canonical(("end", self.lane, self.counts[self.lane])))
        self.unique.clear()
        self.lane = lane
        self.counts[lane] = 0
        self.hash.update(_canonical(("begin", lane)))

    def _key(self, row):
        _require(row.get("repository_namespace") == self.namespace)
        return tuple(_identity(row.get(key)) for key in ("tenant_id", "namespace", "memory_id"))

    def _snapshot(self, row, root, field, version_field):
        snap = row.get(field)
        _require(type(snap) is dict)
        tenant, namespace, memory_id = self._key(row)
        subject, version = root
        _require(snap.get("memory_id") == memory_id and snap.get("tenant_id") == tenant
                 and snap.get("namespace") == namespace and snap.get("subject_id") == subject)
        observed = _number(snap.get("version"))
        _require(observed <= version)
        if version_field is not None:
            _require(observed == _number(row.get(version_field)))
        return observed

    def feed(self, row):
        lane = self.lane
        _require(type(row) is dict and lane is not None)
        self.counts[lane] += 1
        _require(self.counts[lane] <= _GRAPH_LIMIT)
        if lane == "threads":
            key = _identity(row.get("thread_id"))
            _require(row.get("_id") == key and key not in self.threads)
            tenant, actor = (_identity(row.get(k)) for k in ("tenant_id", "owner_id"))
            version = _number(row.get("version"))
            sequence = _number(row.get("message_sequence"), 0)
            self.threads[key] = (tenant, actor, version, sequence)
            self.scopes.add(MongoCanonicalSourceEpoch._key(tenant, actor))
            normalized = (key, tenant, actor, version, sequence)
        elif lane == "messages":
            key = _identity(row.get("message_id"))
            thread = _identity(row.get("thread_id"))
            _require(row.get("_id") == key and thread in self.threads)
            sequence = _number(row.get("sequence"))
            _require(row.get("_commit_state") == "committed"
                     and sequence <= self.threads[thread][3])
            _require(("message", key) not in self.unique
                     and ("sequence", thread, sequence) not in self.unique)
            self.unique.update((("message", key), ("sequence", thread, sequence)))
            normalized = (key, thread, sequence, "committed")
        elif lane == "records":
            key = self._key(row)
            _require(key not in self.records and ("memory", key[2]) not in self.unique)
            self.unique.add(("memory", key[2]))
            subject = _identity(row.get("subject_id"))
            version = _number(row.get("version"))
            self.records[key] = (subject, version)
            self.scopes.add(MongoCanonicalSourceEpoch._key(key[0], subject))
            normalized = (key, subject, version)
        else:
            key = self._key(row)
            _require(key in self.records)
            root = self.records[key]
            if lane == "revisions":
                version = self._snapshot(row, root, "record", "version")
                identity = (key, version)
                normalized = (identity, root[0])
            elif lane == "projection_outbox":
                version = self._snapshot(row, root, "record", "memory_version")
                identity = _identity(row.get("event_id"))
                action = _identity(row.get("action"))
                published = row.get("published_at")
                _require(published is None or _scope(published))
                normalized = (identity, key, root[0], version, action, published)
            else:
                _require(lane == "idempotency" and row.get("status") == "committed")
                version = self._snapshot(row, root, "result", None)
                identity = (key[0], key[1], _identity(row.get("idempotency_key")))
                digest = row.get("request_digest")
                _require(_digest(digest))
                normalized = (identity, key, root[0], version, digest, "committed")
            _require(identity not in self.unique)
            self.unique.add(identity)
        self.hash.update(_canonical(normalized))
        self.hash.update(b"\n")

    def finish(self):
        _require(tuple(self.counts) == tuple(_GRAPH_FIELDS))
        self.hash.update(_canonical(("end", self.lane, self.counts[self.lane])))
        return self.hash.hexdigest(), tuple(sorted(self.scopes)), tuple(self.counts.items())


async def _owner_graph(database, collections, repository_namespace):
    _require(type(collections) is dict and set(collections) == set(_GRAPH_FIELDS))
    graph = _OwnerGraph(repository_namespace)
    for lane, fields in _GRAPH_FIELDS.items():
        collection = collections[lane]
        _require(collection.name == _GRAPH_NAMES[lane]
                 and collection.database.name == database.name
                 and collection.database.client is database.client)
        graph.begin(lane)
        projection = {key: 1 for key in fields}
        if "_id" not in projection:
            projection["_id"] = 0
        cursor = (_majority(collection).find({}, projection, collation={"locale": "simple"})
                  .sort("_id", 1).limit(_GRAPH_LIMIT+1).max_time_ms(_SCAN_MS))
        async for row in _cursor_rows(cursor, _GRAPH_LIMIT):
            graph.feed(row)
    return graph.finish()


async def _inventory(epoch, *, collections, repository_namespace, maximum, verify_linearizable):
    threads, records = collections["threads"], collections["records"]
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
    graph_digest, graph_scopes, counts = await _owner_graph(epoch._database, collections, repository_namespace)
    _require(scopes == set(graph_scopes) and scopes.issubset(locations))
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
                            tuple(sorted(scopes)), graph_digest, counts)


async def qualify_writer_cutover(approval, *, epoch, collections, repository_namespace):
    """Validate two identical majority inventories plus per-actor linearizable reads.

    Bound every database observation, deny incomplete inventories, and verify
    the independent signed plan before and after I/O. Scan every known local
    conversation/memory owner collection. Archives, external writers, payload
    custody and historical completeness remain independently reviewed.
    """
    _require(type(approval) is VerifiedWriterCutover and type(epoch) is MongoCanonicalSourceEpoch)
    approval.verify()
    plan, database = approval.plan, epoch._database
    for collection, name in ((epoch._collection,"canonical_source_epochs"),(epoch._reader,"canonical_source_epochs")):
        _require(collection.name == name and collection.database.name == plan.database_name
                 and collection.database.client is database.client)
    try:
        async with asyncio.timeout(_SCAN_TIMEOUT):
            start = await _observe(database)
            _match_observation(plan, start, database)
            first = await _inventory(epoch, collections=collections, repository_namespace=repository_namespace,
                                     maximum=plan.epoch_count, verify_linearizable=True)
            _require(first.matches(plan))
            second = await _inventory(epoch, collections=collections, repository_namespace=repository_namespace,
                                      maximum=plan.epoch_count, verify_linearizable=False)
            end = await _observe(database)
            _require(first == second and start == end)
            approval.verify()
            return first
    except WriterCutoverDenied:
        raise
    except Exception:
        raise WriterCutoverDenied("live canonical writer inventory unavailable") from None


async def inspect_writer_inventory(*, epoch, collections, repository_namespace):
    """Read-only operator inventory evidence; never creates an approval."""
    _require(type(epoch) is MongoCanonicalSourceEpoch)
    db = epoch._database
    for collection, name in ((epoch._collection,"canonical_source_epochs"),(epoch._reader,"canonical_source_epochs")):
        _require(collection.name == name and collection.database.name == db.name
                 and collection.database.client is db.client)
    try:
        async with asyncio.timeout(_SCAN_TIMEOUT):
            first_topology = await _observe(db)
            first = await _inventory(epoch, collections=collections, repository_namespace=repository_namespace,
                                     maximum=_MAX_ACTORS, verify_linearizable=True)
            second = await _inventory(epoch, collections=collections, repository_namespace=repository_namespace,
                                      maximum=_MAX_ACTORS, verify_linearizable=False)
            _require(first == second and first_topology == await _observe(db))
            return {"schema":"skeleton.canonical-writer-observation.v2",
                    "epoch_count":len(first.epochs), "source_scope_count":len(first.source_scopes),
                    "inventory_sha256":first.digest, "local_owner_graph_sha256":first.graph_sha256,
                    "local_collection_counts":dict(first.collection_counts), "stable_primary_observed":True,
                    "writes_performed":False, "writer_cutover_authorized":False,
                    "guarded_local_ai_ready":False}
    except WriterCutoverDenied:
        raise
    except Exception:
        raise WriterCutoverDenied("canonical writer inventory unavailable") from None


__all__ = ["CanonicalWriterCutover", "VerifiedWriterCutover", "CutoverInventory",
           "WriterCutoverDenied", "qualify_writer_cutover", "inspect_writer_inventory"]
