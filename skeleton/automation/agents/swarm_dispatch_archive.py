"""Bounded append-only terminal history for the installed Hyperdispatcher.

This is retention of exact committed task identities, not a second scheduler.
An archive row is published and verified before resident state is removed.
A crash can leave both copies; it cannot authorize duplicate execution.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from typing import Callable

from skeleton.automation.agents.swarm_durable import (
    DurableSwarmError, ManagedHostDispatcher, _wait_bytes, _wait_digest, _wait_identifier,
)
from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState

_ARCHIVE_VERSION = 1
_TERMINAL = frozenset({"succeeded", "dead", "cancelled"})
_MAX_ARCHIVE_ROW = 131072


class ArchiveCapacity(DurableSwarmError):
    """History storage is full; no resident task has been discarded."""


@dataclass(frozen=True, slots=True)
class ArchivedDispatcherTask:
    tenant: str
    task_id: str
    task: dict
    receipt_sha256: str | None
    source_checkpoint_id: str
    archive_sha256: str


class SQLiteDispatcherArchive:
    """Exact history and permanent task identities in the live writer database."""

    def __init__(self, store, *, run_id: str, policy_sha256: str, archive_key: bytes,
                 max_jobs: int, max_bytes: int) -> None:
        if (type(max_jobs) is not int or not 1 <= max_jobs <= 100000
                or type(max_bytes) is not int or not 1024**2 <= max_bytes <= 32 * 1024**3
                or type(archive_key) is not bytes or len(archive_key) != 32):
            raise DurableSwarmError("invalid dispatcher archive policy")
        self.store = store
        self.run_id = _wait_identifier(run_id)
        self.policy_sha256 = _wait_digest(policy_sha256)
        # Domain-separate archive sealing from the existing inspector issuer.
        self._seal_key = hmac.digest(archive_key, b"skeleton.dispatch.history.seal.v1", "sha256")
        self.max_jobs, self.max_bytes = max_jobs, max_bytes
        with closing(store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hyperdispatcher_history_policy (
                        run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                        version INTEGER NOT NULL, policy_sha256 TEXT NOT NULL,
                        max_jobs INTEGER NOT NULL, max_bytes INTEGER NOT NULL,
                        jobs INTEGER NOT NULL CHECK(jobs>=0),
                        occupied INTEGER NOT NULL CHECK(occupied>=0)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hyperdispatcher_history (
                        run_id TEXT NOT NULL REFERENCES runs(run_id),
                        task_id TEXT NOT NULL, tenant TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN ('succeeded','dead','cancelled')),
                        body BLOB NOT NULL, body_sha256 TEXT NOT NULL,
                        seal TEXT NOT NULL, charge INTEGER NOT NULL CHECK(charge>0),
                        PRIMARY KEY(run_id,task_id)
                    ) WITHOUT ROWID
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS hyperdispatcher_history_tenant "
                             "ON hyperdispatcher_history(run_id,tenant,state,task_id)")
                conn.execute(
                    "INSERT OR IGNORE INTO hyperdispatcher_history_policy VALUES (?,?,?,?,?,0,0)",
                    (self.run_id, _ARCHIVE_VERSION, self.policy_sha256, max_jobs, max_bytes),
                )
                row = conn.execute(
                    "SELECT version,policy_sha256,max_jobs,max_bytes,jobs,occupied "
                    "FROM hyperdispatcher_history_policy WHERE run_id=?", (self.run_id,),
                ).fetchone()
                if (tuple(row)[:4] != (_ARCHIVE_VERSION, self.policy_sha256, max_jobs, max_bytes)
                        or not 0 <= row["jobs"] <= max_jobs
                        or not 0 <= row["occupied"] <= max_bytes):
                    raise DurableSwarmError("dispatcher archive policy or counters changed")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _seal(self, body: bytes) -> str:
        return hmac.digest(self._seal_key, body, "sha256").hex()

    def _decode(self, row) -> ArchivedDispatcherTask:
        try:
            body = row["body"]
            if (type(body) is not bytes or not 1 <= len(body) <= _MAX_ARCHIVE_ROW
                    or row["charge"] != len(body) + 512
                    or not hmac.compare_digest(sha256(body).hexdigest(), row["body_sha256"])
                    or not hmac.compare_digest(self._seal(body), row["seal"])):
                raise DurableSwarmError("dispatcher history integrity failure")
            item = json.loads(body)
            if (type(item) is not dict or set(item) != {
                    "version", "run_id", "policy_sha256", "tenant", "task_id",
                    "task", "receipt_sha256", "source_checkpoint_id"}
                    or type(item["version"]) is not int or item["version"] != _ARCHIVE_VERSION
                    or item["run_id"] != self.run_id
                    or item["policy_sha256"] != self.policy_sha256
                    or item["tenant"] != row["tenant"] or item["task_id"] != row["task_id"]
                    or _wait_bytes(item) != body):
                raise DurableSwarmError("dispatcher history identity mismatch")
            task = item["task"]
            if (type(task) is not dict or task.get("id") != item["task_id"]
                    or task.get("state") != row["state"] or task["state"] not in _TERMINAL
                    or task.get("effect_uncertain") is not False
                    or type(task.get("payload")) is not dict
                    or task.get("leased_to") is not None or task.get("lease_token") is not None):
                raise DurableSwarmError("dispatcher history contains an active or invalid task")
            receipt = item["receipt_sha256"]
            if task["state"] == "succeeded":
                _wait_digest(receipt)
            elif receipt is not None:
                raise DurableSwarmError("non-success history cannot assert a success receipt")
            return ArchivedDispatcherTask(
                _wait_identifier(item["tenant"]), _wait_identifier(item["task_id"]),
                task, receipt, _wait_identifier(item["source_checkpoint_id"]), row["body_sha256"],
            )
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            raise DurableSwarmError("dispatcher history record invalid") from exc

    def get(self, task_id: str) -> ArchivedDispatcherTask | None:
        _wait_identifier(task_id)
        with closing(self.store._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM hyperdispatcher_history WHERE run_id=? AND task_id=?",
                (self.run_id, task_id),
            ).fetchone()
        return None if row is None else self._decode(row)

    def usage(self) -> dict[str, int]:
        with closing(self.store._connect()) as conn:
            row = conn.execute(
                "SELECT jobs,occupied FROM hyperdispatcher_history_policy WHERE run_id=?",
                (self.run_id,),
            ).fetchone()
        if row is None or not 0 <= row["jobs"] <= self.max_jobs or not 0 <= row["occupied"] <= self.max_bytes:
            raise DurableSwarmError("dispatcher history counters invalid")
        return {"jobs": row["jobs"], "reserved_bytes": row["occupied"],
                "max_jobs": self.max_jobs, "max_bytes": self.max_bytes}

    def unique_count(self, resident_ids: tuple[str, ...]) -> int:
        """Count archival identities plus only residents not prepared in history."""
        if (type(resident_ids) is not tuple or len(resident_ids) > 512
                or len(set(resident_ids)) != len(resident_ids)):
            raise DurableSwarmError("invalid resident history inventory")
        for task_id in resident_ids:
            _wait_identifier(task_id)
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN")
            try:
                row = conn.execute(
                    "SELECT jobs FROM hyperdispatcher_history_policy WHERE run_id=?",
                    (self.run_id,),
                ).fetchone()
                if row is None or not 0 <= row["jobs"] <= self.max_jobs:
                    raise DurableSwarmError("dispatcher history count invalid")
                overlap = 0
                if resident_ids:
                    placeholders = ",".join("?" for _ in resident_ids)
                    overlap = conn.execute(
                        "SELECT count(*) FROM hyperdispatcher_history "
                        "WHERE run_id=? AND task_id IN (" + placeholders + ")",
                        (self.run_id, *resident_ids),
                    ).fetchone()[0]
                count = row["jobs"] + len(resident_ids) - overlap
                conn.commit()
                return count
            except BaseException:
                conn.rollback()
                raise

    def audit(self) -> dict[str, int]:
        """Stream every sealed history row and independently reconcile counters."""
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN")
            count = size = 0
            try:
                for row in conn.execute(
                        "SELECT * FROM hyperdispatcher_history WHERE run_id=? ORDER BY task_id",
                        (self.run_id,)):
                    self._decode(row)
                    count += 1
                    size += row["charge"]
                    if count > self.max_jobs or size > self.max_bytes:
                        raise DurableSwarmError("dispatcher history exceeds sealed capacity")
                expected = conn.execute(
                    "SELECT jobs,occupied FROM hyperdispatcher_history_policy WHERE run_id=?",
                    (self.run_id,),
                ).fetchone()
                if expected is None or tuple(expected) != (count, size):
                    raise DurableSwarmError("dispatcher history count or byte accounting mismatch")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return {"verified_jobs": count, "verified_bytes": size}

    def _publish(
        self, owner_id: str, checkpoint_id: str,
        records: tuple[tuple[str, dict, str | None], ...],
    ) -> None:
        """Seal exact terminal bytes while checking the canonical writer and latest checkpoint."""
        if not 1 <= len(records) <= 32:
            raise DurableSwarmError("invalid dispatcher archive batch")
        prepared = []
        identities = set()
        for tenant, task, receipt in records:
            tenant, task_id = _wait_identifier(tenant), _wait_identifier(task["id"])
            if (task_id in identities or task["state"] not in _TERMINAL
                    or task.get("effect_uncertain") is not False
                    or task.get("leased_to") is not None or task.get("lease_token") is not None):
                raise DurableSwarmError("archive requires distinct settled task identities")
            identities.add(task_id)
            if task["state"] == "succeeded":
                _wait_digest(receipt)
            elif receipt is not None:
                raise DurableSwarmError("no success receipt admitted for terminal failure")
            data = _wait_bytes({
                "version": _ARCHIVE_VERSION, "run_id": self.run_id,
                "policy_sha256": self.policy_sha256, "tenant": tenant, "task_id": task_id,
                "task": task, "receipt_sha256": receipt, "source_checkpoint_id": checkpoint_id,
            })
            if len(data) > _MAX_ARCHIVE_ROW:
                raise ArchiveCapacity("single task history row exceeds bound")
            prepared.append((tenant, task_id, task, receipt, data))
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                run = self.store._require_run(conn, self.run_id)
                self.store._require_live_owner(run, owner_id, self.store._now())
                latest = conn.execute(
                    "SELECT checkpoint_id FROM checkpoints WHERE run_id=? "
                    "ORDER BY revision DESC LIMIT 1", (self.run_id,),
                ).fetchone()
                if latest is None or latest["checkpoint_id"] != checkpoint_id:
                    raise DurableSwarmError("dispatcher history publication checkpoint changed")
                usage = conn.execute(
                    "SELECT jobs,occupied FROM hyperdispatcher_history_policy WHERE run_id=?",
                    (self.run_id,),
                ).fetchone()
                if usage is None:
                    raise DurableSwarmError("dispatcher history policy missing")
                jobs, occupied = usage["jobs"], usage["occupied"]
                if not 0 <= jobs <= self.max_jobs or not 0 <= occupied <= self.max_bytes:
                    raise DurableSwarmError("dispatcher history counters invalid")
                for tenant, task_id, task, receipt, data in prepared:
                    previous = conn.execute(
                        "SELECT * FROM hyperdispatcher_history WHERE run_id=? AND task_id=?",
                        (self.run_id, task_id),
                    ).fetchone()
                    if previous is not None:
                        saved = self._decode(previous)
                        # A crash may have preserved the original source
                        # checkpoint; never replace it with a later receipt.
                        if (saved.tenant != tenant or _wait_bytes(saved.task) != _wait_bytes(task)
                                or saved.receipt_sha256 != receipt):
                            raise DurableSwarmError("immutable terminal history conflict")
                        continue
                    charge = len(data) + 512
                    if jobs >= self.max_jobs or occupied + charge > self.max_bytes:
                        raise ArchiveCapacity("dispatcher history capacity exhausted")
                    conn.execute(
                        "INSERT INTO hyperdispatcher_history VALUES (?,?,?,?,?,?,?,?)",
                        (self.run_id, task_id, tenant, task["state"], data,
                         sha256(data).hexdigest(), self._seal(data), charge),
                    )
                    jobs += 1
                    occupied += charge
                conn.execute(
                    "UPDATE hyperdispatcher_history_policy SET jobs=?,occupied=? WHERE run_id=?",
                    (jobs, occupied, self.run_id),
                )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        for tenant, task_id, task, receipt, _ in prepared:
            saved = self.get(task_id)
            if (saved is None or saved.tenant != tenant or _wait_bytes(saved.task) != _wait_bytes(task)
                    or saved.receipt_sha256 != receipt):
                raise DurableSwarmError("terminal archive readback mismatch")

    def compact(
        self, managed: ManagedHostDispatcher, *, target_resident: int,
        prove_result: Callable[[str, dict], dict], limit: int = 32,
    ) -> tuple[str, ...]:
        """Archive leaf-first terminal tasks, then reclaim live identity and payload capacity."""
        if (not isinstance(managed, ManagedHostDispatcher) or managed.store is not self.store
                or managed.owner.run_id != self.run_id or not callable(prove_result)
                or type(limit) is not int or not 1 <= limit <= 32
                or type(target_resident) is not int or not 0 <= target_resident <= 512):
            raise DurableSwarmError("invalid dispatcher compaction request")
        with managed._lock:
            managed.renew()
            owner = managed.owner
            runtime = owner.broker.broker.runtime
            with owner.broker._lock, runtime._lock, owner.manager._lock:
                owner.broker._assert_verified()
                resident = {task.id: task for task in runtime.tasks()}
                if len(resident) <= target_resident:
                    return ()
                # Dependency references are counted over every live node,
                # including terminal children which have yet to be archived.
                refs = {identity: 0 for identity in resident}
                for task in resident.values():
                    for parent in task.dependencies:
                        if parent not in refs:
                            raise DurableSwarmError("resident dependency identity missing")
                        refs[parent] += 1
                pool = dict(resident)
                selected: list[SwarmTask] = []
                while len(pool) > target_resident and len(selected) < limit:
                    eligible = sorted(
                        (task for task in pool.values() if refs[task.id] == 0
                         and task.state.value in _TERMINAL and not task.effect_uncertain),
                        key=lambda task: task.id,
                    )
                    if not eligible:
                        break
                    leaf = eligible[0]
                    selected.append(leaf)
                    del pool[leaf.id]
                    for parent in leaf.dependencies:
                        refs[parent] -= 1
                if not selected:
                    return ()
                loaded = owner.bridge.load(self.run_id)
                if loaded is None:
                    raise DurableSwarmError("terminal history requires durable checkpoint")
                durable = loaded.restore_runtime()
                sidecar = loaded.manager.tenant_store.get(loaded.manager.store.latest().sequence)
                if sidecar is None:
                    raise DurableSwarmError("terminal history requires durable tenant sidecar")
                durable_owners = dict(sidecar.terminal)
                records = []
                for task in selected:
                    tenant = owner.broker._terminal_tenants.get(task.id)
                    previous = durable.task(task.id)
                    task_record = runtime._task_record(task)
                    if (tenant is None or durable_owners.get(task.id) != tenant
                            or previous is None
                            or _wait_bytes(durable._task_record(previous)) != _wait_bytes(task_record)
                            or owner.broker.ingress.phase(tenant, task.id) is not None):
                        raise DurableSwarmError("terminal archive lacks exact settled task custody")
                    result = prove_result(tenant, task_record)
                    if (result.get("task_id") != task.id or result.get("tenant") != tenant
                            or result.get("state") != task.state.value
                            or result.get("uncertain_on_restore") is not False):
                        raise DurableSwarmError("terminal history proof differs from task")
                    records.append((tenant, task_record, result.get("receipt_sha256")))
                # Publication can fail for a full archive without changing
                # the canonical resident scheduler at all.
                try:
                    self._publish(owner.owner_id, loaded.checkpoint.checkpoint_id, tuple(records))
                except ArchiveCapacity:
                    return ()
                except BaseException:
                    owner.broker.retire()
                    raise
                # The ordinary verified delta codec prohibits disappearing
                # identities within a journal. Publish an explicit new full
                # anchor, not a weakened delta transition. The predecessor
                # remains an independently checksummed outer SQL checkpoint.
                # Every removed identity has been sealed and read back above.
                manager = owner.manager
                with manager.store._lock, manager.tenant_store._lock:
                    prior_runtime = manager.store.history()
                    prior_tenants = manager.tenant_store.history()
                    prior_sequence = manager.store._sequence
                    try:
                        for task in selected:
                            if not runtime.forget(task.id):
                                raise DurableSwarmError("terminal history residency disappeared")
                            del owner.broker._terminal_tenants[task.id]
                        # Keep the existing manager, retention ceiling and
                        # monotonic sequence. Only its old journal segment
                        # is closed; never reset the sequence or rewrite the
                        # previous committed outer checkpoint.
                        manager.store._items.clear()
                        manager.tenant_store._items.clear()
                        capture = owner.bridge._capture_checked(
                            self.run_id, owner.owner_id, manager, owner.broker,
                        )
                        if (capture.swarm_sequence <= prior_sequence
                                or manager.store.sequences() != (capture.swarm_sequence,)
                                or manager.tenant_store.sequences() != (capture.swarm_sequence,)):
                            raise DurableSwarmError("terminal history anchor publication mismatch")
                    except BaseException:
                        # A possibly committed anchor must never be undone
                        # in SQL. Retire the owner; restart verifies the last
                        # actual outer checkpoint and sealed history.
                        manager.store._items.clear()
                        manager.store._items.extend(prior_runtime)
                        manager.tenant_store._items.clear()
                        manager.tenant_store._items.extend(prior_tenants)
                        owner.broker.retire()
                        raise
                return tuple(task.id for task in selected)
