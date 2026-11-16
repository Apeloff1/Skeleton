"""Installed local-first Hyperdispatcher foreground service and durable operator inbox.

The private directory is the administrative trust boundary. No network listener,
shell evaluation, remote model authority or default service activation exists.
All physical work still traverses the canonical verified swarm owner.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import sys
import time
from typing import Callable

from skeleton.automation.agents.swarm_durable import (
    DurableSwarmError, HostEventReceipt, HostWaitIntent, HostWorkerAuthority,
    LocalCommittedEvidenceValidator, LocalCommittedRecovery,
    LocalSubprocessTransport, LocalWorkerEvidenceValidator, ManagedHostDispatcher,
    SQLiteWorkerCustody, SwarmDurableBridge, _HOST_SCHEDULE_FIELD, _HOST_WAIT_FIELD,
    _LOCAL_OPERATIONS, _local_reference, _wait_bytes, _wait_identifier, _wait_time,
)
from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.automation.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.automation.agents.swarm_quota import Quota, SharedQuota
from skeleton.automation.agents.swarm_runtime import SwarmTask, TaskState
from skeleton.intelligence.dispatch_policy import DispatchCandidate
from skeleton.state import SQLiteRunStore, StateConflict

_CONFIG_FILE = "dispatcher-policy.json"
_RUN_DB = "dispatcher.sqlite3"
_RUN_ID = "local-hyperdispatcher-v1"
_MAX_COMMAND_BYTES = 65536
_MAX_RESULT_BYTES = 4096
_MAX_RETAINED_PAYLOAD = 384 * 1024
_MAX_INBOX_BYTES = 32 * 1024 * 1024
_VERSION = 1


class DispatcherRequestError(ValueError):
    """A rejected request has not mutated the verified owner."""


def _uint(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise DispatcherRequestError("invalid " + label)
    return value


def _identifier(value: object) -> str:
    try:
        return _wait_identifier(value)
    except DurableSwarmError as exc:
        raise DispatcherRequestError("invalid request identifier") from exc


def _canonical(value: object, *, limit: int = _MAX_COMMAND_BYTES) -> bytes:
    try:
        data = _wait_bytes(value)
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise DispatcherRequestError("invalid canonical JSON") from exc
    if len(data) > limit:
        raise DispatcherRequestError("canonical JSON exceeds capacity")
    return data


def _json_object(data: bytes) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise DispatcherRequestError("duplicate JSON property")
            out[key] = value
        return out
    try:
        value = json.loads(data, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               DispatcherRequestError("nonfinite JSON value")))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise DispatcherRequestError("invalid JSON request") from exc
    if type(value) is not dict:
        raise DispatcherRequestError("JSON object required")
    _canonical(value)
    return value


def _private_root(path: str | Path) -> Path:
    root = Path(path)
    if os.name != "posix":
        raise DurableSwarmError("private dispatcher storage requires POSIX ownership checks")
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir()
            or root.resolve(strict=True) != root):
        raise DurableSwarmError("dispatcher directory must be an existing absolute real path")
    info = root.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise DurableSwarmError("dispatcher directory must be owner-private")
    return root


def _private_file(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise DurableSwarmError("dispatcher file is not an owner-private regular file")


def _create_private(path: Path, content: bytes = b"") -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _read_private(path: Path, max_bytes: int) -> bytes:
    _private_file(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise DurableSwarmError("dispatcher opened an unsafe file")
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise DurableSwarmError("dispatcher private file exceeds capacity")
    return data


def _key(value: object) -> bytes:
    if (type(value) is not str or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise DurableSwarmError("invalid dispatcher provisioned key")
    return bytes.fromhex(value)


@dataclass(frozen=True, slots=True)
class DispatcherPolicy:
    tenants: tuple[str, ...]
    operations: frozenset[str]
    workers: int
    max_jobs: int
    timeout_seconds: int
    lease_seconds: int
    worker_storage_bytes: int
    outer_history: int
    worker_keys: tuple[bytes, ...]
    inspector_key: bytes
    event_keys: tuple[bytes, ...]
    digest: str

    @classmethod
    def parse(cls, raw: bytes) -> DispatcherPolicy:
        config = _json_object(raw)
        if set(config) != {
            "version", "tenants", "operations", "workers", "max_jobs",
            "timeout_seconds", "lease_seconds", "worker_storage_bytes",
            "outer_history", "worker_keys", "inspector_key", "event_keys",
        } or config["version"] != _VERSION or type(config["version"]) is not int:
            raise DurableSwarmError("unsupported dispatcher configuration")
        tenants, operations = config["tenants"], config["operations"]
        if (type(tenants) is not list or not 1 <= len(tenants) <= 32
                or any(type(value) is not str for value in tenants)
                or len(set(tenants)) != len(tenants)
                or type(operations) is not list or not operations
                or any(type(value) is not str for value in operations)
                or len(set(operations)) != len(operations)
                or not set(operations).issubset(_LOCAL_OPERATIONS)):
            raise DurableSwarmError("invalid dispatcher tenant or operation inventory")
        for tenant in tenants:
            _identifier(tenant)
        workers = _uint(config["workers"], 1, 32, "worker count")
        max_jobs = _uint(config["max_jobs"], 1, 512, "job retention")
        timeout = _uint(config["timeout_seconds"], 1, 60, "worker timeout")
        lease = _uint(config["lease_seconds"], timeout + 15, 3600, "writer lease")
        storage = _uint(config["worker_storage_bytes"], 1024 * 1024, 64 * 1024**3,
                        "evidence storage")
        history = _uint(config["outer_history"], 2, 128, "checkpoint retention")
        if (type(config["worker_keys"]) is not list or len(config["worker_keys"]) != workers
                or type(config["event_keys"]) is not list
                or len(config["event_keys"]) != len(tenants)):
            raise DurableSwarmError("dispatcher key inventory mismatch")
        worker_keys = tuple(_key(value) for value in config["worker_keys"])
        inspector_key = _key(config["inspector_key"])
        event_keys = tuple(_key(value) for value in config["event_keys"])
        all_keys = (*worker_keys, inspector_key, *event_keys)
        if len(set(all_keys)) != len(all_keys) or raw != _canonical(config):
            raise DurableSwarmError("noncanonical or reused dispatcher credentials")
        return cls(tuple(tenants), frozenset(operations), workers, max_jobs, timeout,
                   lease, storage, history, worker_keys, inspector_key, event_keys,
                   sha256(raw).hexdigest())

    def public(self) -> dict:
        return {
            "version": _VERSION, "tenants": self.tenants,
            "operations": sorted(self.operations), "workers": self.workers,
            "max_jobs": self.max_jobs, "timeout_seconds": self.timeout_seconds,
            "lease_seconds": self.lease_seconds, "worker_storage_bytes": self.worker_storage_bytes,
            "outer_history": self.outer_history, "policy_sha256": self.digest,
        }

    def worker_id(self, index: int) -> str:
        return f"local-worker-{index:02d}"

    def worker_issuer(self, index: int) -> str:
        return f"local-producer-{index:02d}"


@dataclass(frozen=True, slots=True)
class InboxCommand:
    sequence: int
    request_id: str
    request_sha256: str
    submitted_ms: int
    body: dict


class DispatcherInbox:
    """Durable commands in the same SQLite database as the actual writer lease.

    Commands are append-only identities. Publication of their terminal
    acknowledgement checks the current live writer in the same transaction.
    A crash between effect checkpoint and acknowledgement replays the command
    against exact durable task/receipt identity instead of launching again.
    """

    def __init__(self, store: SQLiteRunStore, *, policy: DispatcherPolicy,
                 clock_ms: Callable[[], int]) -> None:
        self.store = store
        self.policy = policy
        self.clock_ms = clock_ms
        self.max_commands = min(8192, max(64, policy.max_jobs * 12))
        with closing(store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hyperdispatcher_inbox_policy (
                        run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                        version INTEGER NOT NULL, policy_sha256 TEXT NOT NULL,
                        max_commands INTEGER NOT NULL, max_bytes INTEGER NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hyperdispatcher_inbox (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL REFERENCES runs(run_id),
                        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                        submitted_ms INTEGER NOT NULL, body BLOB NOT NULL,
                        charge INTEGER NOT NULL CHECK(charge>0),
                        status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected')),
                        result BLOB,
                        CHECK ((status='pending' AND result IS NULL)
                            OR (status!='pending' AND result IS NOT NULL)),
                        UNIQUE(run_id,request_id)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS hyperdispatcher_pending "
                             "ON hyperdispatcher_inbox(run_id,status,sequence)")
                conn.execute(
                    "INSERT OR IGNORE INTO hyperdispatcher_inbox_policy VALUES (?,?,?,?,?)",
                    (_RUN_ID, _VERSION, policy.digest, self.max_commands, _MAX_INBOX_BYTES),
                )
                row = conn.execute(
                    "SELECT version,policy_sha256,max_commands,max_bytes "
                    "FROM hyperdispatcher_inbox_policy WHERE run_id=?", (_RUN_ID,),
                ).fetchone()
                if tuple(row) != (_VERSION, policy.digest, self.max_commands, _MAX_INBOX_BYTES):
                    raise DurableSwarmError("inbox policy differs from durable configuration")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def _public_row(row) -> dict:
        result = None if row["result"] is None else _json_object(row["result"])
        return {"sequence": row["sequence"], "request_id": row["request_id"],
                "request_sha256": row["request_sha256"], "submitted_ms": row["submitted_ms"],
                "status": row["status"], "result": result}

    def enqueue(self, request_id: str, body: dict) -> dict:
        _identifier(request_id)
        if type(body) is not dict:
            raise DispatcherRequestError("command object required")
        encoded = _canonical(body)
        digest = sha256(encoded).hexdigest()
        charge = len(encoded) + _MAX_RESULT_BYTES + 512
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                previous = conn.execute(
                    "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                    (_RUN_ID, request_id),
                ).fetchone()
                if previous is not None:
                    if previous["request_sha256"] != digest or previous["body"] != encoded:
                        raise DispatcherRequestError("command identity already binds other bytes")
                    conn.commit()
                    return self._public_row(previous)
                count, reserved = conn.execute(
                    "SELECT count(*),coalesce(sum(charge),0) "
                    "FROM hyperdispatcher_inbox WHERE run_id=?", (_RUN_ID,),
                ).fetchone()
                if count >= self.max_commands or reserved + charge > _MAX_INBOX_BYTES:
                    raise DispatcherRequestError("durable command capacity exhausted")
                stamp = _wait_time(self.clock_ms())
                conn.execute(
                    "INSERT INTO hyperdispatcher_inbox "
                    "(run_id,request_id,request_sha256,submitted_ms,body,charge,status) "
                    "VALUES (?,?,?,?,?,?,'pending')",
                    (_RUN_ID, request_id, digest, stamp, encoded, charge),
                )
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                    (_RUN_ID, request_id),
                ).fetchone()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return self._public_row(row)

    def pending(self, *, limit: int = 16) -> tuple[InboxCommand, ...]:
        _uint(limit, 1, 128, "inbox batch")
        with closing(self.store._connect()) as conn:
            rows = conn.execute(
                "SELECT sequence,request_id,request_sha256,submitted_ms,body "
                "FROM hyperdispatcher_inbox WHERE run_id=? AND status='pending' "
                "ORDER BY sequence LIMIT ?", (_RUN_ID, limit),
            ).fetchall()
        commands = []
        for row in rows:
            data = row["body"]
            if (type(data) is not bytes or len(data) > _MAX_COMMAND_BYTES
                    or sha256(data).hexdigest() != row["request_sha256"]):
                raise DurableSwarmError("durable command integrity failure")
            body = _json_object(data)
            if _canonical(body) != data:
                raise DurableSwarmError("noncanonical durable command")
            commands.append(InboxCommand(row["sequence"], row["request_id"],
                                         row["request_sha256"], row["submitted_ms"], body))
        return tuple(commands)

    def acknowledge(self, owner_id: str, command: InboxCommand, *,
                    accepted: bool, result: dict) -> None:
        if type(accepted) is not bool:
            raise DispatcherRequestError("invalid acknowledgement")
        data = _canonical(result, limit=_MAX_RESULT_BYTES)
        status = "accepted" if accepted else "rejected"
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                run = self.store._require_run(conn, _RUN_ID)
                self.store._require_live_owner(run, owner_id, self.store._now())
                row = conn.execute(
                    "SELECT request_id,request_sha256,status,result,body "
                    "FROM hyperdispatcher_inbox WHERE run_id=? AND sequence=?",
                    (_RUN_ID, command.sequence),
                ).fetchone()
                if (row is None or row["request_id"] != command.request_id
                        or row["request_sha256"] != command.request_sha256
                        or row["body"] != _canonical(command.body)):
                    raise DurableSwarmError("durable command changed before acknowledgement")
                if row["status"] == "pending":
                    conn.execute("UPDATE hyperdispatcher_inbox SET status=?,result=? "
                                 "WHERE run_id=? AND sequence=? AND status='pending'",
                                 (status, data, _RUN_ID, command.sequence))
                elif (row["status"], row["result"]) != (status, data):
                    raise DurableSwarmError("durable command acknowledgement conflict")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def command(self, request_id: str) -> dict | None:
        _identifier(request_id)
        with closing(self.store._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                (_RUN_ID, request_id),
            ).fetchone()
        return None if row is None else self._public_row(row)

    def summary(self) -> dict[str, int]:
        with closing(self.store._connect()) as conn:
            rows = conn.execute(
                "SELECT status,count(*),sum(charge) FROM hyperdispatcher_inbox "
                "WHERE run_id=? GROUP BY status", (_RUN_ID,),
            ).fetchall()
        out = {"pending": 0, "accepted": 0, "rejected": 0, "reserved_bytes": 0}
        for status, count, size in rows:
            out[status] = count
            out["reserved_bytes"] += size
        return out


@dataclass(frozen=True, slots=True)
class ApplicationTick:
    commands: int
    cancelled_dependents: tuple[str, ...]
    recovered: tuple[str, ...]
    disposition: str
    task_id: str | None
    stop_requested: bool


class LocalDispatcherApplication:
    """Installed private operator application, backed by the canonical owner."""

    def __init__(self, directory: str | Path, *,
                 clock_ms: Callable[[], int] | None = None,
                 store_clock: Callable[[], float] | None = None) -> None:
        self.directory = _private_root(directory)
        self.policy = DispatcherPolicy.parse(_read_private(self.directory / _CONFIG_FILE, 65536))
        db_path = self.directory / _RUN_DB
        _private_file(db_path)
        options = {"max_payload_bytes": 8 * 1024 * 1024}
        if store_clock is not None:
            options["clock"] = store_clock
        self.store = SQLiteRunStore(db_path, **options)
        run = self.store.get_run(_RUN_ID)
        if run.input != {"dispatcher_version": _VERSION, "policy_sha256": self.policy.digest}:
            raise DurableSwarmError("durable run policy differs from provisioned configuration")
        self.clock_ms = clock_ms if clock_ms is not None else lambda: time.time_ns() // 1_000_000
        self.inbox = DispatcherInbox(self.store, policy=self.policy, clock_ms=self.clock_ms)
        self.custody = SQLiteWorkerCustody(
            self.directory / "evidence", max_attempts=self.policy.max_jobs,
            max_bytes=self.policy.worker_storage_bytes, max_artifact_bytes=65536,
        )
        self.managed: ManagedHostDispatcher | None = None
        self._recovery: LocalCommittedRecovery | None = None
        self._stop_requested = False

    @classmethod
    def initialize(
        cls, directory: str | Path, *, tenants: tuple[str, ...],
        operations: tuple[str, ...], workers: int = 2, max_jobs: int = 128,
        timeout_seconds: int = 10, lease_seconds: int = 120,
        worker_storage_bytes: int = 128 * 1024 * 1024,
        outer_history: int = 16, clock_ms: Callable[[], int] | None = None,
        store_clock: Callable[[], float] | None = None,
    ) -> LocalDispatcherApplication:
        from secrets import token_hex
        if os.name != "posix":
            raise DurableSwarmError("private dispatcher storage requires POSIX ownership checks")
        root = Path(directory)
        if (not root.is_absolute() or root.parent.resolve(strict=True) != root.parent
                or root.name in ("", ".", "..")):
            raise DurableSwarmError("dispatcher initialization requires an absolute real parent")
        _uint(workers, 1, 32, "worker count")
        if type(tenants) is not tuple or not 1 <= len(tenants) <= 32:
            raise DispatcherRequestError("explicit tenant inventory required")
        config = {
            "version": _VERSION, "tenants": list(tenants), "operations": list(operations),
            "workers": workers, "max_jobs": max_jobs, "timeout_seconds": timeout_seconds,
            "lease_seconds": lease_seconds, "worker_storage_bytes": worker_storage_bytes,
            "outer_history": outer_history, "worker_keys": [token_hex(32) for _ in range(workers)],
            "inspector_key": token_hex(32), "event_keys": [token_hex(32) for _ in tenants],
        }
        data = _canonical(config)
        policy = DispatcherPolicy.parse(data)
        # Exclusive root creation prevents replacing an earlier service or
        # silently minting new credentials for an existing evidence journal.
        root.mkdir(mode=0o700, exist_ok=False)
        root = _private_root(root)
        (root / "evidence").mkdir(mode=0o700)
        _create_private(root / _CONFIG_FILE, data)
        _create_private(root / _RUN_DB)
        _create_private(root / "serve.lock")
        options = {"max_payload_bytes": 8 * 1024 * 1024}
        if store_clock is not None:
            options["clock"] = store_clock
        store = SQLiteRunStore(root / _RUN_DB, **options)
        store.create_run(_RUN_ID, {"dispatcher_version": _VERSION, "policy_sha256": policy.digest})
        # Directory entry durability is explicit. Never automatically remove
        # failed initialization data or overwrite a previously created root.
        dir_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return cls(root, clock_ms=clock_ms, store_clock=store_clock)

    @contextmanager
    def exclusive_service(self):
        import fcntl
        lock_path = self.directory / "serve.lock"
        _private_file(lock_path)
        fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DurableSwarmError("another local dispatcher process owns the service") from exc
            yield
        finally:
            os.close(fd)

    def start(self) -> ManagedHostDispatcher:
        if self.managed is not None:
            raise DurableSwarmError("application service already started")
        policy = self.policy
        original_grants = {}
        signers = {}
        transport_grants = {}
        for index, key in enumerate(policy.worker_keys):
            worker, issuer = policy.worker_id(index), policy.worker_issuer(index)
            original_grants[(issuer, worker)] = (key, frozenset({"success"}))
            signers[worker] = (issuer, key)
            for tenant in policy.tenants:
                transport_grants[(tenant, worker)] = policy.operations
        original = HostWorkerAuthority(
            _RUN_ID, grants=original_grants, resolve=self.custody.resolve,
            validate_evidence=LocalWorkerEvidenceValidator(self.custody),
        )
        validator = LocalCommittedEvidenceValidator(self.custody, original)
        grants = dict(original_grants)
        for index in range(policy.workers):
            grants[("local-inspector", policy.worker_id(index))] = (
                policy.inspector_key, frozenset({"reconcile:committed"}))
        authority = HostWorkerAuthority(_RUN_ID, grants=grants, resolve=self.custody.resolve,
                                        validate_evidence=validator)
        transport = LocalSubprocessTransport(
            self.custody, grants=transport_grants, worker_signers=signers,
            timeout_seconds=policy.timeout_seconds,
        )
        ingress = SwarmIngressGovernor(
            rate_capacity=policy.max_jobs, rate_refill_per_second=32.0,
            default_quota=Quota(max_queued=policy.max_jobs, max_leased=policy.workers,
                                max_payload_bytes=_MAX_RETAINED_PAYLOAD),
        )
        ingress.configure_shared(SharedQuota(
            "all-configured-tenants",
            Quota(max_queued=policy.max_jobs, max_leased=policy.workers,
                  max_payload_bytes=_MAX_RETAINED_PAYLOAD),
        ))
        initial = None
        if self.store.resume_state(_RUN_ID).checkpoint is None:
            initial = HardenedSwarmRuntime(
                fenced=True, max_tasks=policy.max_jobs, max_workers=policy.workers,
                default_lease_seconds=policy.timeout_seconds + 15,
            )
            for worker in signers:
                initial.register_worker(worker, capacity=1, capabilities=("local-compute",))
        self.managed = ManagedHostDispatcher.start(
            self.store, _RUN_ID, ingress=ingress, authority=authority, transport=transport,
            initial_runtime=initial,
            source_keys={(tenant, "local-operator"): key
                         for tenant, key in zip(policy.tenants, policy.event_keys)},
            clock_ms=self.clock_ms, lease_seconds=policy.lease_seconds,
            max_checkpoints=2, max_terminal_records=policy.max_jobs,
        )
        self._recovery = LocalCommittedRecovery(
            self.custody, validator, issuer="local-inspector", issuer_key=policy.inspector_key,
        )
        self._stop_requested = False
        return self.managed

    def _owner(self) -> ManagedHostDispatcher:
        if self.managed is None:
            raise DurableSwarmError("application service not started")
        self.managed._ensure_active()
        return self.managed

    def _tenant(self, tenant: object) -> str:
        identity = _identifier(tenant)
        if identity not in self.policy.tenants:
            raise DispatcherRequestError("tenant not in host policy")
        return identity

    def enqueue(self, request_id: str, body: dict) -> dict:
        return self.inbox.enqueue(request_id, body)

    def _resident(self, tenant: str, task_id: str):
        owner = self._owner().owner
        runtime = owner.broker.broker.runtime
        task = runtime.task(task_id)
        if task is None or owner.broker.tenant_for(task_id) != tenant:
            raise DispatcherRequestError("owned task not found")
        return task

    def _submit(self, command: InboxCommand) -> dict:
        body = command.body
        required = {"kind", "tenant", "task_id", "operation", "input"}
        permitted = required | {"priority", "dependencies", "singleton", "timer_ms", "event"}
        if not required.issubset(body) or not set(body).issubset(permitted):
            raise DispatcherRequestError("invalid submission properties")
        tenant, task_id = self._tenant(body["tenant"]), _identifier(body["task_id"])
        operation = body["operation"]
        if type(operation) is not str or operation not in self.policy.operations:
            raise DispatcherRequestError("operation not granted")
        priority = _uint(body.get("priority", 100), 0, 1000, "priority")
        deps = body.get("dependencies", [])
        if type(deps) is not list or len(deps) > 32 or any(type(dep) is not str for dep in deps):
            raise DispatcherRequestError("invalid dependency inventory")
        if len(set(deps)) != len(deps) or task_id in deps:
            raise DispatcherRequestError("duplicate or self dependency")
        singleton = body.get("singleton")
        if singleton is not None:
            _identifier(singleton)
        if "timer_ms" in body and "event" in body:
            raise DispatcherRequestError("one deferred gate permitted")
        managed = self._owner()
        owner = managed.owner
        runtime = owner.broker.broker.runtime
        metadata = {"request_id": command.request_id, "request_sha256": command.request_sha256,
                    "enqueued_ms": command.submitted_ms}
        prior = runtime.task(task_id)
        if prior is not None:
            if (owner.broker.tenant_for(task_id) == tenant
                    and prior.payload.get(_HOST_SCHEDULE_FIELD) == metadata):
                return {"task_id": task_id, "submission": "durable"}
            raise DispatcherRequestError("task identity already bound to another command")
        for dep in deps:
            self._resident(tenant, _identifier(dep))
        payload = {"operation": operation, "input": body["input"]}
        raw = _canonical(payload, limit=32768)
        try:
            result = _local_reference(payload)
            _canonical({"version": 1, "payload_sha256": sha256(raw).hexdigest(),
                        "result": result}, limit=self.custody.max_artifact_bytes)
        except (ValueError, TypeError, RecursionError, UnicodeError, DurableSwarmError) as exc:
            raise DispatcherRequestError("operation input or result exceeds worker contract") from exc
        payload[_HOST_SCHEDULE_FIELD] = metadata
        wait = None
        if "timer_ms" in body:
            deadline = _uint(body["timer_ms"], 0, 10**15, "timer deadline")
            wait = HostWaitIntent(_RUN_ID, tenant, task_id, "timer", "host-clock", "deadline", deadline)
        elif "event" in body:
            event = body["event"]
            if (type(event) is not dict or "selector" not in event
                    or not set(event).issubset({"selector", "not_before_ms", "expires_ms"})):
                raise DispatcherRequestError("invalid event gate")
            start = _uint(event.get("not_before_ms", command.submitted_ms),
                          0, 10**15, "event opening")
            expiry = event.get("expires_ms")
            if expiry is not None:
                expiry = _uint(expiry, start, 10**15, "event expiry")
            wait = HostWaitIntent(_RUN_ID, tenant, task_id, "event", "local-operator",
                                  _identifier(event["selector"]), start, expiry)
        payload_charge = len(_canonical(payload))
        if wait is not None:
            payload_charge += len(_canonical(wait.record())) + 128
        occupied = sum(len(_canonical(dict(task.payload))) for task in runtime.tasks())
        if len(runtime.tasks()) >= self.policy.max_jobs or occupied + payload_charge > _MAX_RETAINED_PAYLOAD:
            raise DispatcherRequestError("retained task capacity exhausted")
        task = SwarmTask(task_id, payload, priority=priority, max_attempts=1,
                         required_capabilities=frozenset({"local-compute"}),
                         dependencies=tuple(deps))
        capture = (managed.submit(tenant, task, singleton_key=singleton)
                   if wait is None else managed.submit_wait(wait, task, singleton_key=singleton))
        if capture is None:
            raise DispatcherRequestError("admission quota refused")
        return {"task_id": task_id, "submission": "durable"}

    def _signal(self, command: InboxCommand) -> dict:
        body = command.body
        if set(body) != {"kind", "tenant", "task_id", "event_id", "selector", "evidence"}:
            raise DispatcherRequestError("invalid operator event request")
        tenant, task_id = self._tenant(body["tenant"]), _identifier(body["task_id"])
        resident = self._resident(tenant, task_id)
        try:
            intent = HostWaitIntent.from_record(resident.payload.get(_HOST_WAIT_FIELD))
        except DurableSwarmError as exc:
            raise DispatcherRequestError("task has no valid operator event gate") from exc
        if (intent.kind != "event" or intent.source != "local-operator"
                or intent.run_id != _RUN_ID or intent.tenant != tenant
                or intent.task_id != task_id or intent.digest != resident.wait_intent_sha256
                or intent.selector != _identifier(body["selector"])
                or command.submitted_ms < intent.not_before_ms
                or (intent.expires_ms is not None and command.submitted_ms > intent.expires_ms)):
            raise DispatcherRequestError("event does not match registered gate")
        if command.submitted_ms > self.clock_ms():
            raise DurableSwarmError("operator clock moved behind durable event timestamp")
        key = self.policy.event_keys[self.policy.tenants.index(tenant)]
        receipt = HostEventReceipt.issue(
            intent, event_id=_identifier(body["event_id"]),
            evidence_sha256=sha256(_canonical(body["evidence"])).hexdigest(),
            observed_ms=command.submitted_ms, source_key=key,
        )
        if resident.wake_receipt_sha256 == receipt.digest:
            return {"task_id": task_id, "wake_receipt_sha256": receipt.digest}
        if resident.wake_receipt_sha256 is not None or resident.state is not TaskState.QUEUED:
            raise DispatcherRequestError("event gate is no longer eligible")
        self._owner().deliver_event(tenant, task_id, receipt)
        return {"task_id": task_id, "wake_receipt_sha256": receipt.digest}

    def _apply(self, command: InboxCommand) -> dict:
        kind = command.body.get("kind")
        if kind == "submit":
            return self._submit(command)
        if kind == "signal":
            return self._signal(command)
        if kind == "stop" and set(command.body) == {"kind"}:
            self._stop_requested = True
            return {"stop": "requested"}
        if kind not in ("cancel", "reconcile") or set(command.body) != {"kind", "tenant", "task_id"}:
            raise DispatcherRequestError("unsupported operator command")
        tenant = self._tenant(command.body["tenant"])
        task_id = _identifier(command.body["task_id"])
        task = self._resident(tenant, task_id)
        if kind == "cancel":
            if task.state not in (TaskState.QUEUED, TaskState.CANCELLED) or task.effect_uncertain:
                raise DispatcherRequestError("active or terminal effect cannot be cancelled")
            if task.state is not TaskState.CANCELLED:
                self._owner().cancel_queued(tenant, task_id)
            return {"task_id": task_id, "state": "cancelled"}
        if task.state is TaskState.SUCCEEDED and task.reconciliation_sha256:
            return {"task_id": task_id, "reconciliation_sha256": task.reconciliation_sha256}
        if not task.effect_uncertain or self._recovery is None or task.lease_token is None:
            raise DispatcherRequestError("no uncertain committed local effect")
        record = self.custody.lookup(_RUN_ID, task.lease_token)
        if record is None or record.receipt_sha256 is None:
            raise DispatcherRequestError("no committed worker result available")
        recovered, _ = self._owner().reconcile_committed(self._recovery, tenant, task_id)
        return {"task_id": task_id, "reconciliation_sha256": recovered.reconciliation_sha256}

    def _candidates(self, now_ms: int) -> tuple[DispatchCandidate, ...]:
        owner = self._owner().owner
        runtime = owner.broker.broker.runtime
        rows = []
        for task in runtime.tasks():
            if task.state is not TaskState.QUEUED:
                continue
            metadata = task.payload.get(_HOST_SCHEDULE_FIELD)
            if (type(metadata) is not dict or set(metadata) != {
                    "request_id", "request_sha256", "enqueued_ms"}):
                raise DurableSwarmError("queued task has no admitted schedule identity")
            tenant = owner.broker.tenant_for(task.id)
            if tenant not in self.policy.tenants:
                raise DurableSwarmError("queued task outside configured tenant policy")
            created = _wait_time(metadata["enqueued_ms"])
            if created > now_ms:
                raise DurableSwarmError("dispatcher clock moved behind admitted job")
            rows.append(DispatchCandidate(task.id, tenant, task.priority, created))
        return tuple(rows)

    def _recover_committed(self, limit: int = 8) -> tuple[str, ...]:
        owner = self._owner().owner
        runtime = owner.broker.broker.runtime
        recovered = []
        for task in runtime.tasks():
            if len(recovered) >= limit:
                break
            if not task.effect_uncertain or task.lease_token is None:
                continue
            record = self.custody.lookup(_RUN_ID, task.lease_token)
            if record is None or record.receipt_sha256 is None:
                continue
            tenant = owner.broker.tenant_for(task.id)
            self._owner().reconcile_committed(self._recovery, tenant, task.id)
            recovered.append(task.id)
        return tuple(recovered)

    def tick(self, *, command_limit: int = 16) -> ApplicationTick:
        managed = self._owner()
        managed.renew()
        count = 0
        for command in self.inbox.pending(limit=command_limit):
            managed.renew()
            try:
                result = self._apply(command)
            except DispatcherRequestError as exc:
                managed._ensure_active()
                # Only request errors known to precede mutation are rejected.
                accepted, result = False, {"reason": str(exc)}
            else:
                accepted = True
            managed.renew()
            self.inbox.acknowledge(managed.owner.owner_id, command,
                                   accepted=accepted, result=result)
            count += 1
            if self._stop_requested:
                break
        if self._stop_requested:
            return ApplicationTick(count, (), (), "stopping", None, True)
        recovered = self._recover_committed()
        cancelled = managed.propagate_dependencies()
        now_ms = _wait_time(self.clock_ms())
        result = managed.tick(self._candidates(now_ms), now_ms=now_ms, timer_limit=16)
        managed.prune_outer_checkpoints(keep=self.policy.outer_history)
        return ApplicationTick(count, cancelled, recovered, result.disposition, result.task_id, False)

    def close(self) -> None:
        if self.managed is not None:
            self.managed.close()
            self.managed = None

    def status(self) -> dict:
        resume = self.store.resume_state(_RUN_ID)
        snapshot = None
        if resume.checkpoint is not None:
            archived = SwarmDurableBridge(self.store).load(_RUN_ID)
            # A read-only snapshot must not present a recovered uncertainty as
            # an observed physical stop. Report only the serialized counts.
            runtime = archived.restore_runtime()
            snapshot = {state.value: 0 for state in TaskState}
            snapshot["uncertain_on_restore"] = 0
            for task in runtime.tasks():
                snapshot[task.state.value] += 1
                snapshot["uncertain_on_restore"] += int(task.effect_uncertain)
        return {"policy": self.policy.public(), "run_revision": resume.run.revision,
                "writer_present": resume.run.worker_id is not None,
                "checkpoint_revision": None if resume.checkpoint is None else resume.checkpoint.revision,
                "restored_task_counts": snapshot, "inbox": self.inbox.summary(),
                "worker_custody": self.custody.usage()}

    def result(self, tenant: str, task_id: str) -> dict:
        tenant, task_id = self._tenant(tenant), _identifier(task_id)
        loaded = SwarmDurableBridge(self.store).load(_RUN_ID)
        if loaded is None:
            raise DispatcherRequestError("no durable task archive")
        runtime = loaded.restore_runtime()
        task = runtime.task(task_id)
        tenant_checkpoint = loaded.manager.tenant_store.get(loaded.manager.store.latest().sequence)
        if task is None or tenant_checkpoint is None:
            raise DispatcherRequestError("owned task not found")
        # The tenant sidecar is authoritative, including terminal identity.
        owners = dict(tenant_checkpoint.active)
        owners.update(dict(tenant_checkpoint.terminal))
        if owners.get(task_id) != tenant:
            raise DispatcherRequestError("owned task not found")
        result = {"task_id": task_id, "tenant": tenant, "state": task.state.value,
                  "uncertain_on_restore": task.effect_uncertain}
        # Never present an unacknowledged worker result as completed.
        if task.state is not TaskState.SUCCEEDED:
            return result
        with closing(self.custody._connect()) as conn:
            rows = conn.execute(
                "SELECT lease_token,receipt_digest FROM attempts "
                "WHERE run_id=? AND tenant=? AND task_id=? AND receipt_digest IS NOT NULL "
                "ORDER BY lease_token LIMIT 2", (_RUN_ID, tenant, task_id),
            ).fetchall()
        if len(rows) != 1:
            raise DurableSwarmError("completed task does not have one exact worker result")
        digest = rows[0][1]
        resolved = self.custody.resolve(digest)
        if resolved is None:
            raise DurableSwarmError("completed worker result missing")
        receipt, raw = resolved
        index = next((i for i in range(self.policy.workers)
                      if self.policy.worker_id(i) == receipt.worker_id), None)
        if index is None:
            raise DurableSwarmError("completed worker outside provisioned policy")
        authority = HostWorkerAuthority(
            _RUN_ID, grants={(self.policy.worker_issuer(index), receipt.worker_id):
                             (self.policy.worker_keys[index], frozenset({"success"}))},
            resolve=self.custody.resolve, validate_evidence=LocalWorkerEvidenceValidator(self.custody),
        )
        if not authority(receipt.worker_id, task_id, rows[0][0], "success", digest):
            raise DurableSwarmError("completed worker result failed evidence verification")
        result["receipt_sha256"] = digest
        result["result"] = _json_object(raw)["result"]
        return result

    def serve(self, *, poll_seconds: float = 0.25, max_cycles: int | None = None,
              should_stop: Callable[[], bool] | None = None) -> int:
        if type(poll_seconds) not in (int, float) or not 0.05 <= poll_seconds <= 5:
            raise DispatcherRequestError("invalid service poll period")
        if max_cycles is not None:
            _uint(max_cycles, 1, 1_000_000, "service cycle bound")
        cycles = 0
        with self.exclusive_service():
            managed = self.start()
            try:
                while should_stop is None or not should_stop():
                    tick = self.tick()
                    cycles += 1
                    if tick.stop_requested or (max_cycles is not None and cycles >= max_cycles):
                        break
                    if tick.disposition == "idle" and tick.commands == 0:
                        time.sleep(poll_seconds)
            except BaseException:
                # Unknown acknowledgement requires real lease expiry/recovery,
                # never an optimistic successful shutdown.
                managed.stop()
                self.managed = None
                raise
            else:
                self.close()
        return cycles


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skeleton-jeeves-dispatch",
        description="Private durable local Hyperdispatcher (explicit opt-in, POSIX).",
    )
    parser.add_argument("--directory", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="create exclusive private service state and credentials")
    init.add_argument("--tenant", action="append", required=True)
    init.add_argument("--operation", action="append", choices=sorted(_LOCAL_OPERATIONS), required=True)
    init.add_argument("--workers", type=int, default=2)
    init.add_argument("--max-jobs", type=int, default=128)
    init.add_argument("--timeout", type=int, default=10)
    init.add_argument("--lease", type=int, default=120)
    enqueue = sub.add_parser("enqueue", help="append one exact JSON command from standard input")
    enqueue.add_argument("--id", required=True)
    command = sub.add_parser("command", help="read the durable command acknowledgement")
    command.add_argument("--id", required=True)
    result = sub.add_parser("result", help="read independently verified task output")
    result.add_argument("--tenant", required=True)
    result.add_argument("--task", required=True)
    sub.add_parser("status")
    serve = sub.add_parser("serve", help="run the actual foreground dispatcher")
    serve.add_argument("--poll", type=float, default=0.25)
    serve.add_argument("--max-cycles", type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            app = LocalDispatcherApplication.initialize(
                args.directory, tenants=tuple(args.tenant), operations=tuple(args.operation),
                workers=args.workers, max_jobs=args.max_jobs, timeout_seconds=args.timeout,
                lease_seconds=args.lease,
            )
            _print(app.status())
            return 0
        app = LocalDispatcherApplication(args.directory)
        if args.action == "enqueue":
            data = sys.stdin.buffer.read(_MAX_COMMAND_BYTES + 1)
            if len(data) > _MAX_COMMAND_BYTES:
                raise DispatcherRequestError("command input too large")
            _print(app.enqueue(args.id, _json_object(data)))
        elif args.action == "command":
            value = app.inbox.command(args.id)
            _print(value)
            return 0 if value is not None else 1
        elif args.action == "result":
            _print(app.result(args.tenant, args.task))
        elif args.action == "status":
            _print(app.status())
        elif args.action == "serve":
            from threading import Event
            stopped = Event()
            old = {}
            for signum in (signal.SIGINT, signal.SIGTERM):
                old[signum] = signal.signal(signum, lambda *_: stopped.set())
            try:
                count = app.serve(poll_seconds=args.poll, max_cycles=args.max_cycles,
                                  should_stop=stopped.is_set)
            finally:
                for signum, handler in old.items():
                    signal.signal(signum, handler)
            _print({"cycles": count, "stopped": True})
        return 0
    except (DispatcherRequestError, DurableSwarmError, StateConflict, OSError,
            sqlite3.DatabaseError, ValueError) as exc:
        # Avoid reflecting filesystem paths, credentials or raw task contents.
        print("dispatcher refused request or lost custody: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
