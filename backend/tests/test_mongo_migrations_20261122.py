"""Contract tests for core.mongo_migrations.

Runner behaviour is exercised against an in-memory collection double and, when
``MONGO_MIGRATIONS_TEST_URL`` points at a disposable mongod, against a real
server too (each test uses a fresh, dropped database).
"""

from __future__ import annotations

import ast
import asyncio
import copy
import os
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from core import mongo_migrations as mm
from core.mongo_migrations import (
    CORE_MIGRATIONS,
    IndexSpec,
    Migration,
    MigrationDefinitionError,
    MigrationDriftError,
    MigrationLockedError,
    MigrationRunner,
)

BACKEND = Path(__file__).resolve().parents[1]


# ── In-memory double (subset of the motor collection API the runner uses) ──


class _DupKey(Exception):
    code = 11000


def _matches(doc: dict[str, Any], flt: dict[str, Any]) -> bool:
    for key, cond in flt.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
            continue
        value = doc.get(key)
        if isinstance(cond, dict) and "$lt" in cond:
            if value is None or not value < cond["$lt"]:
                return False
        elif value != cond:
            return False
    return True


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def sort(self, key: str, direction: int) -> _Cursor:
        self._docs.sort(key=lambda d: d[key], reverse=direction < 0)
        return self

    def __aiter__(self) -> Iterator[dict[str, Any]]:
        async def gen():  # type: ignore[no-untyped-def]
            for doc in self._docs:
                yield doc

        return gen()  # type: ignore[return-value]


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[Any, dict[str, Any]] = {}
        self.indexes: dict[str, dict[str, Any]] = {}

    async def create_index(self, keys: list[tuple[str, int]], unique: bool = False) -> str:
        name = "_".join(f"{k}_{d}" for k, d in keys)
        existing = self.indexes.get(name)
        if existing is not None and existing["unique"] != unique:
            raise RuntimeError("IndexOptionsConflict")
        self.indexes[name] = {"keys": list(keys), "unique": unique}
        return name

    def find(self, flt: dict[str, Any]) -> _Cursor:
        return _Cursor([copy.deepcopy(d) for d in self.docs.values() if _matches(d, flt)])

    async def insert_one(self, doc: dict[str, Any]) -> None:
        if doc["_id"] in self.docs:
            raise _DupKey("duplicate key")
        self.docs[doc["_id"]] = copy.deepcopy(doc)

    async def find_one_and_update(
        self, flt: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if _matches(doc, flt):
                before = copy.deepcopy(doc)
                doc.update(update["$set"])
                return before
        if not upsert:
            return None
        new = {"_id": flt["_id"], **update["$set"]}
        await self.insert_one(new)
        return None

    async def delete_one(self, flt: dict[str, Any]) -> None:
        for key, doc in list(self.docs.items()):
            if _matches(doc, flt):
                del self.docs[key]
                return


class _FakeDb:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}

    def __getitem__(self, name: str) -> _FakeCollection:
        return self.collections.setdefault(name, _FakeCollection())


# ── Backend fixture: fake always, real mongod when configured ──

_MONGO_URL = os.environ.get("MONGO_MIGRATIONS_TEST_URL", "")
_BACKENDS = ["memory"] + (["mongod"] if _MONGO_URL else [])


class _Env:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.client: Any = None
        self.db_name = f"laneb_mig_{uuid.uuid4().hex[:10]}"

    def make_db(self) -> Any:
        if self.kind == "memory":
            if not hasattr(self, "_fake"):
                self._fake = _FakeDb()
            return self._fake
        from motor.motor_asyncio import AsyncIOMotorClient

        # A fresh client per event loop (each test drives its own asyncio.run).
        self.client = AsyncIOMotorClient(_MONGO_URL, serverSelectionTimeoutMS=5000)
        return self.client[self.db_name]

    async def index_names(self, db: Any, collection: str) -> set[str]:
        if self.kind == "memory":
            return set(db[collection].indexes)
        info = await db[collection].index_information()
        return {name for name in info if name != "_id_"}

    async def drop(self) -> None:
        if self.kind == "mongod":
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(_MONGO_URL, serverSelectionTimeoutMS=5000)
            await client.drop_database(self.db_name)
            client.close()


@pytest.fixture(params=_BACKENDS)
def env(request: pytest.FixtureRequest) -> Iterator[_Env]:
    e = _Env(request.param)
    yield e
    asyncio.run(e.drop())


def _run(coro_fn: Callable[[], Any]) -> Any:
    return asyncio.run(coro_fn())


# ── Definition validation ──


def test_migration_ids_must_be_versioned_snake_case() -> None:
    with pytest.raises(MigrationDefinitionError):
        Migration(id="baseline", description="x", indexes=(IndexSpec.single("c", "f"),))
    with pytest.raises(MigrationDefinitionError):
        Migration(id="0001_noop", description="does nothing")


def test_index_spec_rejects_bad_keys_and_system_collections() -> None:
    with pytest.raises(MigrationDefinitionError):
        IndexSpec("c", (("f", 2),))
    with pytest.raises(MigrationDefinitionError):
        IndexSpec("system.users", (("f", 1),))
    assert IndexSpec("c", (("status", 1), ("created_at", -1))).name == "status_1_created_at_-1"


def test_runner_rejects_out_of_order_and_duplicate_ids() -> None:
    a = Migration("0002_b", "b", (IndexSpec.single("c", "b"),))
    b = Migration("0001_a", "a", (IndexSpec.single("c", "a"),))
    with pytest.raises(MigrationDefinitionError):
        MigrationRunner(_FakeDb(), [a, b])
    with pytest.raises(MigrationDefinitionError):
        MigrationRunner(_FakeDb(), [b, b])


def test_checksum_changes_when_definition_changes() -> None:
    base = Migration("0001_a", "a", (IndexSpec.single("c", "f"),))
    assert base.checksum == Migration("0001_a", "a", (IndexSpec.single("c", "f"),)).checksum
    assert base.checksum != Migration("0001_a", "a", (IndexSpec.single("c", "f", unique=True),)).checksum
    assert base.checksum != Migration("0001_a", "a2", (IndexSpec.single("c", "f"),)).checksum


# ── Baseline stays in lockstep with the boot path ──


def _boot_index_calls() -> list[IndexSpec]:
    tree = ast.parse((BACKEND / "server.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_kick_index_creation")
    specs: list[IndexSpec] = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "create_index":
            continue
        target = node.func.value
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "db"):
            continue
        raw = ast.literal_eval(node.args[0])
        keys = ((raw, 1),) if isinstance(raw, str) else tuple((k, d) for k, d in raw)
        unique = any(kw.arg == "unique" and ast.literal_eval(kw.value) for kw in node.keywords)
        specs.append(IndexSpec(target.attr, keys, unique=unique))
    return sorted(specs, key=lambda s: (s.collection, s.name))


def test_baseline_matches_server_boot_indexes() -> None:
    boot = _boot_index_calls()
    assert len(boot) >= 20
    baseline = sorted(mm.BASELINE_BOOT_INDEXES, key=lambda s: (s.collection, s.name))
    assert baseline == boot
    assert CORE_MIGRATIONS[0].indexes == mm.BASELINE_BOOT_INDEXES


# ── Runner behaviour (memory double + real mongod when configured) ──


def test_apply_creates_indexes_records_ledger_and_is_idempotent(env: _Env) -> None:
    async def scenario() -> None:
        db = env.make_db()
        runner = MigrationRunner(db, CORE_MIGRATIONS)
        before = await runner.status()
        assert before.pending == ["0001_baseline_boot_indexes"] and before.ok

        report = await runner.apply()
        assert report.applied == ["0001_baseline_boot_indexes"]
        assert "marketplace_listings.active_1_created_at_-1" in report.planned_indexes
        names = await env.index_names(db, "marketplace_listings")
        assert {"playable_id_1", "creator_id_1", "active_1_created_at_-1"} <= names

        after = await runner.status()
        assert after.pending == [] and after.ok
        record = after.applied[0]
        assert record["checksum"] == CORE_MIGRATIONS[0].checksum
        assert record["applied_by"] == runner.owner

        again = await MigrationRunner(db, CORE_MIGRATIONS).apply()
        assert again.applied == []
        # lock released after a successful run
        assert [d async for d in db[mm.LOCK_COLLECTION].find({})] == []
        if env.client is not None:
            env.client.close()

    _run(scenario)


def test_baseline_is_a_noop_over_indexes_the_boot_path_already_built(env: _Env) -> None:
    async def scenario() -> None:
        db = env.make_db()
        for spec in mm.BASELINE_BOOT_INDEXES:  # what _kick_index_creation does
            arg: Any = spec.keys[0][0] if len(spec.keys) == 1 else list(spec.keys)
            await db[spec.collection].create_index(
                arg if not isinstance(arg, str) or env.kind == "mongod" else [(arg, 1)],
                unique=spec.unique,
            )
        report = await MigrationRunner(db, CORE_MIGRATIONS).apply()
        assert report.applied == ["0001_baseline_boot_indexes"]
        if env.client is not None:
            env.client.close()

    _run(scenario)


def test_dry_run_plans_without_writing(env: _Env) -> None:
    async def scenario() -> None:
        db = env.make_db()
        report = await MigrationRunner(db, CORE_MIGRATIONS).apply(dry_run=True)
        assert report.dry_run and report.applied == []
        assert len(report.planned_indexes) == len(mm.BASELINE_BOOT_INDEXES)
        assert (await MigrationRunner(db, CORE_MIGRATIONS).status()).pending == ["0001_baseline_boot_indexes"]
        if env.client is not None:
            env.client.close()

    _run(scenario)


def test_data_migration_runs_once_in_order(env: _Env) -> None:
    calls: list[str] = []

    async def backfill(db: Any) -> None:
        calls.append("backfill")
        await db["widgets"].insert_one({"_id": "w1", "v": 2})

    migrations = [
        Migration("0001_idx", "widgets index", (IndexSpec.single("widgets", "v"),)),
        Migration("0002_backfill", "seed widget", apply_fn=backfill),
    ]

    async def scenario() -> None:
        db = env.make_db()
        first = await MigrationRunner(db, migrations).apply()
        second = await MigrationRunner(db, migrations).apply()
        assert first.applied == ["0001_idx", "0002_backfill"]
        assert second.applied == []
        assert calls == ["backfill"]
        if env.client is not None:
            env.client.close()

    _run(scenario)


def test_drift_fails_closed(env: _Env) -> None:
    original = [Migration("0001_idx", "widgets index", (IndexSpec.single("widgets", "v"),))]
    edited = [Migration("0001_idx", "widgets index", (IndexSpec.single("widgets", "v", unique=True),))]
    unknown = [Migration("0002_other", "other", (IndexSpec.single("widgets", "w"),))]

    async def scenario() -> None:
        db = env.make_db()
        await MigrationRunner(db, original).apply()
        status = await MigrationRunner(db, edited).status()
        assert not status.ok and status.drift[0]["id"] == "0001_idx"
        with pytest.raises(MigrationDriftError):
            await MigrationRunner(db, edited).apply()
        with pytest.raises(MigrationDriftError):
            await MigrationRunner(db, unknown).apply()
        assert (await MigrationRunner(db, unknown).status()).unknown_applied == ["0001_idx"]
        if env.client is not None:
            env.client.close()

    _run(scenario)


def test_lock_excludes_concurrent_owner_until_expiry(env: _Env) -> None:
    clock_now = [datetime(2026, 11, 22, 12, 0, tzinfo=UTC)]

    def clock() -> datetime:
        return clock_now[0]

    async def scenario() -> None:
        db = env.make_db()
        holder = MigrationRunner(db, CORE_MIGRATIONS, owner="a", lock_ttl_s=60, clock=clock)
        rival = MigrationRunner(db, CORE_MIGRATIONS, owner="b", lock_ttl_s=60, clock=clock)
        await holder.acquire_lock()
        await holder.acquire_lock()  # re-entrant for the same owner
        with pytest.raises(MigrationLockedError):
            await rival.apply()
        assert (await rival.status()).pending  # nothing applied by the rival
        clock_now[0] += timedelta(seconds=61)  # holder crashed; lease expired
        report = await rival.apply()
        assert report.applied == ["0001_baseline_boot_indexes"]
        # holder's stale lease was taken over, so its release is a no-op
        await holder.release_lock()
        if env.client is not None:
            env.client.close()

    _run(scenario)


def test_cli_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit):
        mm.main(["explode"])
