"""Versioned, checksummed, lock-protected MongoDB schema migrations.

The backend historically created indexes ad hoc in the FastAPI lifespan
(``server._kick_index_creation``). That is fine for idempotent index builds,
but it gives operators no answer to "which schema version is this cluster
on?" and no safe place for data migrations. This module adds that layer
without changing the boot path:

* :class:`Migration` - an ordered unit identified by ``NNNN_snake_case``.
  It declares :class:`IndexSpec` entries and/or an idempotent async
  ``apply_fn(db)`` for data changes. Its checksum covers the id, the
  description, the index specs and the ``apply_fn`` qualified name, so
  editing an applied migration is detected as drift.
* :class:`MigrationRunner` - applies pending migrations in order, holding a
  TTL lease in ``_schema_migration_lock`` so that two replicas cannot migrate
  at the same time. Each applied migration is recorded in
  ``_schema_migrations`` under ``_id = migration id``. The runner fails closed
  on drift: a changed checksum, or an applied id the code does not know about.
* ``python -m core.mongo_migrations status|apply [--dry-run]`` - an operator
  CLI against ``MONGO_URL`` / ``DB_NAME``, the same env as ``core.databases``.

Index specs use MongoDB's default index naming (``field_1``,
``a_1_b_-1``), so applying the baseline against a database whose indexes the
boot path already created is a no-op rather than an ``IndexOptionsConflict``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

MIGRATIONS_COLLECTION = "_schema_migrations"
LOCK_COLLECTION = "_schema_migration_lock"
LOCK_ID = "global"
DEFAULT_LOCK_TTL_S = 300.0

_MIGRATION_ID = re.compile(r"^\d{4}_[a-z0-9_]+$")
_DUPLICATE_KEY = 11000


class MigrationError(RuntimeError):
    """Base class for migration failures."""


class MigrationDefinitionError(MigrationError):
    """The declared migration list is malformed (ids, order, specs)."""


class MigrationDriftError(MigrationError):
    """The database records migrations that disagree with the code."""


class MigrationLockedError(MigrationError):
    """Another owner holds an unexpired migration lease."""


class _Collection(Protocol):  # pragma: no cover - structural typing only
    async def create_index(self, keys: Any, **kwargs: Any) -> str: ...
    async def find_one_and_update(self, filter: Any, update: Any, **kwargs: Any) -> Any: ...
    async def insert_one(self, document: Any, **kwargs: Any) -> Any: ...
    async def delete_one(self, filter: Any, **kwargs: Any) -> Any: ...
    def find(self, *args: Any, **kwargs: Any) -> Any: ...


class _Database(Protocol):  # pragma: no cover - structural typing only
    def __getitem__(self, name: str) -> _Collection: ...


ApplyFn = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class IndexSpec:
    """One index to ensure on ``collection``; ``keys`` are (field, direction)."""

    collection: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False

    def __post_init__(self) -> None:
        if not self.collection or self.collection.startswith("system."):
            raise MigrationDefinitionError(f"invalid collection name: {self.collection!r}")
        if not self.keys:
            raise MigrationDefinitionError(f"index on {self.collection} has no keys")
        for name, direction in self.keys:
            if not name or direction not in (1, -1):
                raise MigrationDefinitionError(f"index on {self.collection} has invalid key {(name, direction)!r}")

    @classmethod
    def single(cls, collection: str, field_name: str, *, unique: bool = False) -> IndexSpec:
        return cls(collection=collection, keys=((field_name, 1),), unique=unique)

    @property
    def name(self) -> str:
        """MongoDB's default index name for these keys."""
        return "_".join(f"{k}_{d}" for k, d in self.keys)

    def as_json(self) -> dict[str, Any]:
        return {
            "collection": self.collection,
            "keys": [[k, d] for k, d in self.keys],
            "unique": self.unique,
        }


@dataclass(frozen=True)
class Migration:
    id: str
    description: str
    indexes: tuple[IndexSpec, ...] = ()
    apply_fn: ApplyFn | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not _MIGRATION_ID.match(self.id):
            raise MigrationDefinitionError(f"migration id {self.id!r} must match NNNN_snake_case")
        if not self.description.strip():
            raise MigrationDefinitionError(f"migration {self.id} needs a description")
        if not self.indexes and self.apply_fn is None:
            raise MigrationDefinitionError(f"migration {self.id} does nothing")

    @property
    def checksum(self) -> str:
        fn = self.apply_fn
        payload = {
            "id": self.id,
            "description": self.description,
            "indexes": [spec.as_json() for spec in self.indexes],
            "apply_fn": None if fn is None else f"{fn.__module__}.{fn.__qualname__}",
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class MigrationStatus:
    applied: list[dict[str, Any]]
    pending: list[str]
    drift: list[dict[str, str]]
    unknown_applied: list[str]

    @property
    def ok(self) -> bool:
        return not self.drift and not self.unknown_applied

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "applied": [r["_id"] for r in self.applied],
            "pending": list(self.pending),
            "drift": list(self.drift),
            "unknown_applied": list(self.unknown_applied),
        }


@dataclass
class MigrationReport:
    applied: list[str]
    dry_run: bool
    planned_indexes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": list(self.applied),
            "dry_run": self.dry_run,
            "planned_indexes": list(self.planned_indexes),
        }


def validate_migrations(migrations: Sequence[Migration]) -> None:
    seen: set[str] = set()
    previous = ""
    for migration in migrations:
        if migration.id in seen:
            raise MigrationDefinitionError(f"duplicate migration id {migration.id}")
        if migration.id <= previous:
            raise MigrationDefinitionError(f"migration {migration.id} is out of order after {previous}")
        seen.add(migration.id)
        previous = migration.id


def _now() -> datetime:
    return datetime.now(UTC)


def _is_duplicate_key(exc: BaseException) -> bool:
    return getattr(exc, "code", None) == _DUPLICATE_KEY


class MigrationRunner:
    """Apply ``migrations`` to ``db`` in order under a TTL lease."""

    def __init__(
        self,
        db: Any,
        migrations: Sequence[Migration],
        *,
        owner: str | None = None,
        lock_ttl_s: float = DEFAULT_LOCK_TTL_S,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        validate_migrations(migrations)
        if lock_ttl_s <= 0:
            raise MigrationDefinitionError("lock_ttl_s must be positive")
        self._db = db
        self._migrations = tuple(migrations)
        self._owner = owner or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._ttl = timedelta(seconds=lock_ttl_s)
        self._clock = clock

    @property
    def owner(self) -> str:
        return self._owner

    async def _applied_records(self) -> list[dict[str, Any]]:
        cursor = self._db[MIGRATIONS_COLLECTION].find({}).sort("_id", 1)
        return [dict(doc) async for doc in cursor]

    async def status(self) -> MigrationStatus:
        records = await self._applied_records()
        by_id = {m.id: m for m in self._migrations}
        applied_ids = {r["_id"] for r in records}
        drift = [
            {"id": r["_id"], "recorded": str(r.get("checksum")), "expected": by_id[r["_id"]].checksum}
            for r in records
            if r["_id"] in by_id and r.get("checksum") != by_id[r["_id"]].checksum
        ]
        unknown = [r["_id"] for r in records if r["_id"] not in by_id]
        pending = [m.id for m in self._migrations if m.id not in applied_ids]
        return MigrationStatus(applied=records, pending=pending, drift=drift, unknown_applied=unknown)

    async def acquire_lock(self) -> None:
        now = self._clock()
        try:
            await self._db[LOCK_COLLECTION].find_one_and_update(
                {"_id": LOCK_ID, "$or": [{"expires_at": {"$lt": now}}, {"owner": self._owner}]},
                {"$set": {"owner": self._owner, "acquired_at": now, "expires_at": now + self._ttl}},
                upsert=True,
            )
        except Exception as exc:
            if _is_duplicate_key(exc):
                raise MigrationLockedError("another process holds the migration lock") from exc
            raise

    async def release_lock(self) -> None:
        await self._db[LOCK_COLLECTION].delete_one({"_id": LOCK_ID, "owner": self._owner})

    async def apply(self, *, dry_run: bool = False) -> MigrationReport:
        status = await self.status()
        if not status.ok:
            raise MigrationDriftError(json.dumps(status.as_dict(), sort_keys=True))
        pending = [m for m in self._migrations if m.id in set(status.pending)]
        planned = [f"{s.collection}.{s.name}" for m in pending for s in m.indexes]
        if dry_run or not pending:
            return MigrationReport(applied=[], dry_run=dry_run, planned_indexes=planned)

        await self.acquire_lock()
        applied: list[str] = []
        try:
            # Re-read under the lease: another owner may have finished first.
            done = {r["_id"] for r in await self._applied_records()}
            for migration in pending:
                if migration.id in done:
                    continue
                started = time.perf_counter()
                for spec in migration.indexes:
                    await self._db[spec.collection].create_index(list(spec.keys), unique=spec.unique)
                if migration.apply_fn is not None:
                    await migration.apply_fn(self._db)
                record = {
                    "_id": migration.id,
                    "checksum": migration.checksum,
                    "description": migration.description,
                    "applied_at": self._clock(),
                    "applied_by": self._owner,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
                try:
                    await self._db[MIGRATIONS_COLLECTION].insert_one(record)
                except Exception as exc:
                    if not _is_duplicate_key(exc):
                        raise
                    continue
                applied.append(migration.id)
        finally:
            await self.release_lock()
        return MigrationReport(applied=applied, dry_run=False, planned_indexes=planned)


def _single(collection: str, field_name: str, *, unique: bool = False) -> IndexSpec:
    return IndexSpec.single(collection, field_name, unique=unique)


# Baseline: exactly the indexes ``server._kick_index_creation`` ensures on
# core_db at boot. tests/test_mongo_migrations_20261122.py parses server.py and
# fails if the two lists diverge, so boot and the ledger stay in lockstep.
BASELINE_BOOT_INDEXES: tuple[IndexSpec, ...] = (
    _single("code_files", "id", unique=True),
    _single("execution_history", "created_at"),
    _single("language_addons", "language_key", unique=True),
    _single("tutorial_progress", "id", unique=True),
    _single("marketplace_listings", "playable_id", unique=True),
    _single("marketplace_listings", "creator_id"),
    IndexSpec("marketplace_listings", (("active", 1), ("created_at", -1))),
    _single("marketplace_purchases", "session_id", unique=True),
    IndexSpec("marketplace_purchases", (("buyer_id", 1), ("payment_status", 1))),
    _single("payment_transactions", "session_id", unique=True),
    _single("tournaments", "tournament_id", unique=True),
    _single("tournaments", "created_at"),
    _single("tournament_rewards", "playable_id"),
    _single("liveops_progress", "visitor_id", unique=True),
    _single("playable_jobs", "job_id", unique=True),
    _single("content_reports", "report_id", unique=True),
    IndexSpec("content_reports", (("status", 1), ("created_at", -1))),
    _single("content_reports", "playable_id"),
    _single("governance_audit", "at"),
    _single("governance_audit", "target_id"),
    _single("content_appeals", "appeal_id", unique=True),
    IndexSpec("content_appeals", (("status", 1), ("created_at", -1))),
)

CORE_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        id="0001_baseline_boot_indexes",
        description="Record the core_db indexes the lifespan has always ensured at boot.",
        indexes=BASELINE_BOOT_INDEXES,
    ),
)


async def _run_cli(argv: Sequence[str] | None, env: Mapping[str, str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.mongo_migrations")
    parser.add_argument("command", choices=("status", "apply"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lock-ttl", type=float, default=DEFAULT_LOCK_TTL_S)
    args = parser.parse_args(argv)

    from motor.motor_asyncio import AsyncIOMotorClient

    client: Any = AsyncIOMotorClient(env.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=10_000)
    try:
        db = client[env.get("DB_NAME", "galaxy_studio_db")]
        runner = MigrationRunner(db, CORE_MIGRATIONS, lock_ttl_s=args.lock_ttl)
        if args.command == "status":
            status = await runner.status()
            print(json.dumps(status.as_dict(), indent=2, sort_keys=True))
            return 0 if status.ok else 2
        try:
            report = await runner.apply(dry_run=args.dry_run)
        except MigrationDriftError as exc:
            print(f"migration drift: {exc}", file=sys.stderr)
            return 2
        except MigrationLockedError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return 0
    finally:
        client.close()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run_cli(argv, os.environ))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
