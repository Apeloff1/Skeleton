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
from skeleton.automation.agents.swarm_dispatch_archive import SQLiteDispatcherArchive
from skeleton.automation.agents.swarm_dispatch_bindings import (
    BindingDeferred, BindingError, InputBinding, MAX_BINDING_WAIT_MS, materialize, parse_bindings,
)
from skeleton.automation.agents.swarm_dispatch_workflow import (
    MAX_WORKFLOW_BYTES, WorkflowError, WorkflowPlan, compile_workflow, parse_prerequisites,
)
from skeleton.automation.agents.swarm_dispatch_gguf import (
    GGUF_OPERATION, GGUF_CAPABILITY, PinnedGGUFPolicy, PinnedGGUFTransport,
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


def _json_object(data: bytes, *, limit: int = _MAX_COMMAND_BYTES) -> dict:
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
    _canonical(value, limit=limit)
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
    gguf: PinnedGGUFPolicy | None = None
    history_jobs: int = 0
    history_bytes: int = 0
    inbox_bytes: int = _MAX_INBOX_BYTES

    @classmethod
    def parse(cls, raw: bytes) -> DispatcherPolicy:
        config = _json_object(raw)
        fields = {
            "version", "tenants", "operations", "workers", "max_jobs",
            "timeout_seconds", "lease_seconds", "worker_storage_bytes",
            "outer_history", "worker_keys", "inspector_key", "event_keys",
        }
        if (set(config) - {"gguf", "history"} != fields
                or config["version"] != _VERSION or type(config["version"]) is not int):
            raise DurableSwarmError("unsupported dispatcher configuration")
        tenants, operations = config["tenants"], config["operations"]
        if (type(tenants) is not list or not 1 <= len(tenants) <= 32
                or any(type(value) is not str for value in tenants)
                or len(set(tenants)) != len(tenants)
                or type(operations) is not list or not operations
                or any(type(value) is not str for value in operations)
                or len(set(operations)) != len(operations)
                or not set(operations).issubset(_LOCAL_OPERATIONS | {GGUF_OPERATION})):
            raise DurableSwarmError("invalid dispatcher tenant or operation inventory")
        for tenant in tenants:
            _identifier(tenant)
        workers = _uint(config["workers"], 1, 32, "worker count")
        max_jobs = _uint(config["max_jobs"], 1, 512, "job retention")
        timeout = _uint(config["timeout_seconds"], 1, 60, "worker timeout")
        gguf = PinnedGGUFPolicy.parse(config["gguf"]) if "gguf" in config else None
        if (gguf is None) != (GGUF_OPERATION not in operations):
            raise DurableSwarmError("GGUF operation and pinned policy must be provisioned together")
        maximum_timeout = max(timeout, gguf.timeout_seconds if gguf is not None else 0)
        lease = _uint(config["lease_seconds"], maximum_timeout + 15, 3600, "writer lease")
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
        history_jobs, history_bytes, inbox_bytes = max_jobs, 0, _MAX_INBOX_BYTES
        if "history" in config:
            retention = config["history"]
            if type(retention) is not dict or set(retention) != {"jobs", "bytes", "inbox_bytes"}:
                raise DurableSwarmError("invalid history retention policy")
            history_jobs = _uint(retention["jobs"], max_jobs + 1, 100000, "history identities")
            history_bytes = _uint(retention["bytes"], 1024**2, 32 * 1024**3, "history bytes")
            inbox_bytes = _uint(retention["inbox_bytes"], _MAX_INBOX_BYTES, 16 * 1024**3, "inbox bytes")
        all_keys = (*worker_keys, inspector_key, *event_keys)
        if len(set(all_keys)) != len(all_keys) or raw != _canonical(config):
            raise DurableSwarmError("noncanonical or reused dispatcher credentials")
        return cls(tuple(tenants), frozenset(operations), workers, max_jobs, timeout,
                   lease, storage, history, worker_keys, inspector_key, event_keys,
                   sha256(raw).hexdigest(), gguf, history_jobs, history_bytes, inbox_bytes)

    def public(self) -> dict:
        return {
            "version": _VERSION, "tenants": self.tenants,
            "operations": sorted(self.operations), "workers": self.workers,
            "max_jobs": self.max_jobs, "timeout_seconds": self.timeout_seconds,
            "lease_seconds": self.lease_seconds, "worker_storage_bytes": self.worker_storage_bytes,
            "outer_history": self.outer_history, "policy_sha256": self.digest,
            "gguf": None if self.gguf is None else self.gguf.public(),
            "max_resident_jobs": self.max_jobs, "max_history_jobs": self.history_jobs,
            "history_bytes": self.history_bytes, "inbox_bytes": self.inbox_bytes,
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
        self.max_commands = min(1_200_000, max(64, policy.history_jobs * 12))
        self.max_bytes = policy.inbox_bytes
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
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hyperdispatcher_workflows (
                        run_id TEXT NOT NULL REFERENCES runs(run_id),
                        tenant TEXT NOT NULL, workflow_id TEXT NOT NULL,
                        manifest BLOB NOT NULL, manifest_sha256 TEXT NOT NULL,
                        seal TEXT NOT NULL, submitted_ms INTEGER NOT NULL,
                        charge INTEGER NOT NULL CHECK(charge>0),
                        PRIMARY KEY(run_id,tenant,workflow_id)
                    ) WITHOUT ROWID
                """)
                self._install_workflow_control(conn)
                self._install_ingress_ledger(conn)
                conn.execute(
                    "INSERT OR IGNORE INTO hyperdispatcher_inbox_policy VALUES (?,?,?,?,?)",
                    (_RUN_ID, _VERSION, policy.digest, self.max_commands, self.max_bytes),
                )
                row = conn.execute(
                    "SELECT version,policy_sha256,max_commands,max_bytes "
                    "FROM hyperdispatcher_inbox_policy WHERE run_id=?", (_RUN_ID,),
                ).fetchone()
                if tuple(row) != (_VERSION, policy.digest, self.max_commands, self.max_bytes):
                    raise DurableSwarmError("inbox policy differs from durable configuration")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _install_workflow_control(self, conn) -> None:
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='hyperdispatcher_workflow_members'"
        ).fetchone() is not None
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hyperdispatcher_workflow_members (
                run_id TEXT NOT NULL, tenant TEXT NOT NULL, workflow_id TEXT NOT NULL,
                request_id TEXT NOT NULL, task_id TEXT NOT NULL,
                PRIMARY KEY(run_id,request_id),
                UNIQUE(run_id,task_id),
                FOREIGN KEY(run_id,tenant,workflow_id)
                    REFERENCES hyperdispatcher_workflows(run_id,tenant,workflow_id),
                FOREIGN KEY(run_id,request_id) REFERENCES hyperdispatcher_inbox(run_id,request_id)
            ) WITHOUT ROWID
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS hyperdispatcher_member_graph "
                     "ON hyperdispatcher_workflow_members(run_id,tenant,workflow_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hyperdispatcher_workflow_cancellations (
                run_id TEXT NOT NULL, tenant TEXT NOT NULL, workflow_id TEXT NOT NULL,
                request_id TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
                command_sha256 TEXT NOT NULL, seal TEXT NOT NULL,
                PRIMARY KEY(run_id,tenant,workflow_id),
                UNIQUE(run_id,request_id),
                FOREIGN KEY(run_id,tenant,workflow_id)
                    REFERENCES hyperdispatcher_workflows(run_id,tenant,workflow_id),
                FOREIGN KEY(run_id,request_id) REFERENCES hyperdispatcher_inbox(run_id,request_id)
            ) WITHOUT ROWID
        """)
        # Existing A25 databases are migrated once, atomically, from their
        # exact HMAC-sealed manifests. Duplicate task identities fail closed.
        if not existed:
            for row in conn.execute("SELECT * FROM hyperdispatcher_workflows WHERE run_id=?",
                                    (_RUN_ID,)):
                manifest = self._workflow_row(conn, row, verify_members=False)
                for node in manifest["jobs"]:
                    conn.execute("INSERT INTO hyperdispatcher_workflow_members VALUES (?,?,?,?,?)",
                                 (_RUN_ID, manifest["tenant"], manifest["workflow_id"],
                                  node["request_id"], node["task_id"]))

    @staticmethod
    def _indexable_task(body: dict) -> str | None:
        task = body.get("task_id")
        if body.get("kind") != "submit" or type(task) is not str:
            return None
        try:
            return _identifier(task)
        except DispatcherRequestError:
            # Preserve invalid historical submissions for normal rejection;
            # they cannot reserve a valid canonical scheduler identity.
            return None

    def _install_ingress_ledger(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hyperdispatcher_ingress_totals (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                version INTEGER NOT NULL,
                commands INTEGER NOT NULL CHECK(commands>=0),
                workflows INTEGER NOT NULL CHECK(workflows>=0),
                reserved_bytes INTEGER NOT NULL CHECK(reserved_bytes>=0)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hyperdispatcher_submit_index (
                run_id TEXT NOT NULL, request_id TEXT NOT NULL,
                task_id TEXT NOT NULL, command_sha256 TEXT NOT NULL,
                PRIMARY KEY(run_id,request_id),
                FOREIGN KEY(run_id,request_id) REFERENCES hyperdispatcher_inbox(run_id,request_id)
            ) WITHOUT ROWID
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS hyperdispatcher_submit_task "
                     "ON hyperdispatcher_submit_index(run_id,task_id)")
        if conn.execute("SELECT 1 FROM hyperdispatcher_ingress_totals WHERE run_id=?",
                        (_RUN_ID,)).fetchone() is not None:
            self._ledger(conn)
            return
        # One transactional migration scans historical commands exactly once.
        # Future publishers perform only bounded indexed lookups and increments.
        commands = reserved = workflows = 0
        for row in conn.execute("SELECT * FROM hyperdispatcher_inbox WHERE run_id=? ORDER BY sequence",
                                (_RUN_ID,)):
            command = self._decode(row)
            if row["charge"] != len(row["body"]) + _MAX_RESULT_BYTES + 512:
                raise DurableSwarmError("historical inbox charge mismatch")
            task = self._indexable_task(command.body)
            if task is not None:
                conn.execute("INSERT INTO hyperdispatcher_submit_index VALUES (?,?,?,?)",
                             (_RUN_ID, command.request_id, task, command.request_sha256))
            commands += 1
            reserved += row["charge"]
            if commands > self.max_commands or reserved > self.max_bytes:
                raise DurableSwarmError("historical inbox exceeds provisioned capacity")
        for row in conn.execute("SELECT * FROM hyperdispatcher_workflows WHERE run_id=?", (_RUN_ID,)):
            self._workflow_row(conn, row)
            workflows += 1
            reserved += row["charge"]
            if reserved > self.max_bytes or workflows > commands:
                raise DurableSwarmError("historical workflows exceed provisioned capacity")
        conn.execute("INSERT INTO hyperdispatcher_ingress_totals VALUES (?,1,?,?,?)",
                     (_RUN_ID, commands, workflows, reserved))

    def _ledger(self, conn) -> tuple[int, int, int]:
        row = conn.execute(
            "SELECT version,commands,workflows,reserved_bytes FROM hyperdispatcher_ingress_totals WHERE run_id=?",
            (_RUN_ID,),
        ).fetchone()
        if (row is None or row["version"] != 1
                or not 0 <= row["workflows"] <= row["commands"] <= self.max_commands
                or not 0 <= row["reserved_bytes"] <= self.max_bytes):
            raise DurableSwarmError("ingress ledger missing or outside sealed capacity")
        return row["commands"], row["workflows"], row["reserved_bytes"]

    def _reserve(self, conn, *, commands: int, workflows: int, charge: int) -> None:
        before_commands, before_workflows, occupied = self._ledger(conn)
        if before_commands + commands > self.max_commands or occupied + charge > self.max_bytes:
            raise DispatcherRequestError("durable ingress capacity exhausted")
        updated = conn.execute(
            "UPDATE hyperdispatcher_ingress_totals SET commands=?,workflows=?,reserved_bytes=? "
            "WHERE run_id=? AND commands=? AND workflows=? AND reserved_bytes=?",
            (before_commands+commands, before_workflows+workflows, occupied+charge,
             _RUN_ID, before_commands, before_workflows, occupied),
        ).rowcount
        if updated != 1:
            raise DurableSwarmError("ingress capacity ledger changed during transaction")

    def _index_submit(self, conn, request_id: str, body: dict, digest: str) -> None:
        task = self._indexable_task(body)
        if task is not None:
            conn.execute("INSERT INTO hyperdispatcher_submit_index VALUES (?,?,?,?)",
                         (_RUN_ID, request_id, task, digest))

    def _verify_submit_index(self, conn, command: InboxCommand) -> None:
        expected = self._indexable_task(command.body)
        row = conn.execute(
            "SELECT task_id,command_sha256 FROM hyperdispatcher_submit_index WHERE run_id=? AND request_id=?",
            (_RUN_ID, command.request_id),
        ).fetchone()
        if expected is None:
            if row is not None:
                raise DurableSwarmError("non-submit command has an indexed task")
        elif row is None or tuple(row) != (expected, command.request_sha256):
            raise DurableSwarmError("durable submit identity index mismatch")

    def audit(self) -> dict[str, int]:
        """Stream the full immutable ingress, manifests, indexes and totals."""
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN")
            try:
                expected = self._ledger(conn)
                commands = workflows = reserved = indexed = members = cancellations = 0
                for row in conn.execute("SELECT * FROM hyperdispatcher_inbox WHERE run_id=? ORDER BY sequence",
                                        (_RUN_ID,)):
                    command = self._decode(row)
                    self._verify_submit_index(conn, command)
                    self._public_row(row)
                    if row["charge"] != len(row["body"]) + _MAX_RESULT_BYTES + 512:
                        raise DurableSwarmError("inbox byte accounting mismatch")
                    if row["result"] is not None and len(row["result"]) > _MAX_RESULT_BYTES:
                        raise DurableSwarmError("inbox acknowledgement exceeds charge")
                    commands += 1
                    reserved += row["charge"]
                    indexed += int(self._indexable_task(command.body) is not None)
                    if commands > self.max_commands or reserved > self.max_bytes:
                        raise DurableSwarmError("inbox audit exceeded configured limits")
                for row in conn.execute("SELECT * FROM hyperdispatcher_workflows WHERE run_id=?", (_RUN_ID,)):
                    graph = self._workflow_row(conn, row)
                    reserved += row["charge"]
                    workflows += 1
                    members += len(graph["jobs"])
                    cancellation = conn.execute(
                        "SELECT * FROM hyperdispatcher_workflow_cancellations "
                        "WHERE run_id=? AND tenant=? AND workflow_id=?",
                        (_RUN_ID, graph["tenant"], graph["workflow_id"]),
                    ).fetchone()
                    if cancellation is not None:
                        self._cancel_record(conn, cancellation, graph)
                        cancellations += 1
                actual = (
                    conn.execute("SELECT count(*) FROM hyperdispatcher_submit_index WHERE run_id=?", (_RUN_ID,)).fetchone()[0],
                    conn.execute("SELECT count(*) FROM hyperdispatcher_workflow_members WHERE run_id=?", (_RUN_ID,)).fetchone()[0],
                    conn.execute("SELECT count(*) FROM hyperdispatcher_workflow_cancellations WHERE run_id=?", (_RUN_ID,)).fetchone()[0],
                )
                if (commands, workflows, reserved) != expected or actual != (indexed, members, cancellations):
                    raise DurableSwarmError("ingress audit totals or index mismatch")
                conn.commit()
                return {"verified_commands": commands, "verified_workflows": workflows,
                        "verified_members": members, "verified_indexed_tasks": indexed,
                        "verified_cancellations": cancellations, "reserved_bytes": reserved}
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
                if body.get("kind") == "submit" and type(body.get("task_id")) is str:
                    claim = conn.execute(
                        "SELECT request_id FROM hyperdispatcher_workflow_members "
                        "WHERE run_id=? AND task_id=?", (_RUN_ID, body["task_id"]),
                    ).fetchone()
                    if claim is not None:
                        raise DispatcherRequestError("task identity reserved by workflow")
                self._reserve(conn, commands=1, workflows=0, charge=charge)
                stamp = _wait_time(self.clock_ms())
                conn.execute(
                    "INSERT INTO hyperdispatcher_inbox "
                    "(run_id,request_id,request_sha256,submitted_ms,body,charge,status) "
                    "VALUES (?,?,?,?,?,?,'pending')",
                    (_RUN_ID, request_id, digest, stamp, encoded, charge),
                )
                self._index_submit(conn, request_id, body, digest)
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                    (_RUN_ID, request_id),
                ).fetchone()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return self._public_row(row)

    def _workflow_seal(self, manifest: bytes, stamp: int) -> str:
        import hmac
        key = hmac.digest(self.policy.inspector_key, b"skeleton.dispatch.workflow.seal.v1", "sha256")
        return hmac.digest(key, _wait_bytes([self.policy.digest, stamp, sha256(manifest).hexdigest()]),
                           "sha256").hex()

    def _workflow_row(self, conn, row, *, verify_members: bool = True) -> dict:
        import hmac
        raw, stamp = row["manifest"], row["submitted_ms"]
        if (type(raw) is not bytes or not 1 <= len(raw) <= MAX_WORKFLOW_BYTES
                or row["charge"] != len(raw) + 512
                or not hmac.compare_digest(sha256(raw).hexdigest(), row["manifest_sha256"])
                or not hmac.compare_digest(self._workflow_seal(raw, stamp), row["seal"])):
            raise DurableSwarmError("durable workflow manifest seal mismatch")
        try:
            manifest = json.loads(raw)
            if (_wait_bytes(manifest) != raw or type(manifest) is not dict
                    or set(manifest) != {"version", "workflow_id", "tenant", "deadline_ms", "commands"}
                    or manifest["version"] != 1
                    or manifest["workflow_id"] != row["workflow_id"]
                    or manifest["tenant"] != row["tenant"]
                    or type(manifest["commands"]) is not list
                    or not 1 <= len(manifest["commands"]) <= 32):
                raise DurableSwarmError("durable workflow manifest shape mismatch")
            members = {}
            if verify_members:
                members = dict(conn.execute(
                    "SELECT request_id,task_id FROM hyperdispatcher_workflow_members "
                    "WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, row["tenant"], row["workflow_id"]),
                ))
                if len(members) != len(manifest["commands"]):
                    raise DurableSwarmError("workflow membership inventory missing or changed")
            jobs = []
            previous_sequence = 0
            for item in manifest["commands"]:
                if type(item) is not dict or set(item) != {"request_id", "body"}:
                    raise DurableSwarmError("durable workflow command shape mismatch")
                row_command = conn.execute(
                    "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                    (_RUN_ID, item["request_id"]),
                ).fetchone()
                if row_command is None:
                    raise DurableSwarmError("durable workflow command missing")
                command = self._decode(row_command)
                if (command.sequence <= previous_sequence or command.submitted_ms != stamp
                        or _wait_bytes(command.body) != _wait_bytes(item["body"])
                        or command.body.get("tenant") != row["tenant"]
                        or command.body.get("kind") != "submit"):
                    raise DurableSwarmError("durable workflow command identity changed")
                if verify_members and members.get(command.request_id) != command.body["task_id"]:
                    raise DurableSwarmError("workflow membership identity changed")
                previous_sequence = command.sequence
                jobs.append({**self._public_row(row_command), "task_id": command.body["task_id"]})
            return {"workflow_id": row["workflow_id"], "tenant": row["tenant"],
                    "workflow_sha256": row["manifest_sha256"], "submitted_ms": stamp,
                    "deadline_ms": manifest["deadline_ms"], "jobs": jobs}
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
            raise DurableSwarmError("durable workflow manifest invalid") from exc

    def workflow(self, tenant: str, workflow_id: str) -> dict | None:
        _identifier(tenant)
        _identifier(workflow_id)
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN")
            try:
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflows WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, tenant, workflow_id),
                ).fetchone()
                result = None if row is None else self._workflow_row(conn, row)
                conn.commit()
                return result
            except BaseException:
                conn.rollback()
                raise

    def enqueue_workflow(self, plan: WorkflowPlan) -> dict:
        """Publish every graph command and its immutable manifest in one SQL transaction."""
        if not isinstance(plan, WorkflowPlan) or plan.tenant not in self.policy.tenants:
            raise DispatcherRequestError("workflow plan outside configured tenant")
        raw = plan.manifest
        if len(raw) > MAX_WORKFLOW_BYTES or not 1 <= len(plan.commands) <= 32:
            raise DispatcherRequestError("workflow manifest exceeds bound")
        digest = plan.digest
        prepared = [(item.request_id, item.digest, item.body_json,
                     len(item.body_json)+_MAX_RESULT_BYTES+512) for item in plan.commands]
        if len({item[0] for item in prepared}) != len(prepared):
            raise DispatcherRequestError("duplicate workflow request identity")
        total = len(raw)+512 + sum(item[3] for item in prepared)
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                previous = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflows WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, plan.tenant, plan.workflow_id),
                ).fetchone()
                if previous is not None:
                    if previous["manifest_sha256"] != digest or previous["manifest"] != raw:
                        raise DispatcherRequestError("workflow identity already binds another graph")
                    result = self._workflow_row(conn, previous)
                    conn.commit()
                    return result
                stamp = _wait_time(self.clock_ms())
                if not stamp < plan.deadline_ms <= stamp + MAX_BINDING_WAIT_MS:
                    raise DispatcherRequestError("workflow deadline outside admission interval")
                self._reserve(conn, commands=len(prepared), workflows=1, charge=total)
                # Refuse all overlapping standalone or other workflow
                # requests. Never adopt a partial prior publication.
                for request_id, _, _, _ in prepared:
                    if conn.execute(
                            "SELECT 1 FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                            (_RUN_ID, request_id)).fetchone() is not None:
                        raise DispatcherRequestError("workflow request identity already exists")
                # The migration indexed every valid historical submit.
                # Check only the up-to-32 new task identities under this
                # publication transaction, not the entire command history.
                for item in plan.commands:
                    task_id = item.body["task_id"]
                    existing = conn.execute(
                        "SELECT i.* FROM hyperdispatcher_submit_index s "
                        "JOIN hyperdispatcher_inbox i ON i.run_id=s.run_id AND i.request_id=s.request_id "
                        "WHERE s.run_id=? AND s.task_id=? LIMIT 1",
                        (_RUN_ID, task_id),
                    ).fetchone()
                    if existing is not None:
                        prior = self._decode(existing)
                        self._verify_submit_index(conn, prior)
                        raise DispatcherRequestError("workflow task identity already exists")
                for request_id, command_digest, data, charge in prepared:
                    conn.execute(
                        "INSERT INTO hyperdispatcher_inbox "
                        "(run_id,request_id,request_sha256,submitted_ms,body,charge,status) "
                        "VALUES (?,?,?,?,?,?,'pending')",
                        (_RUN_ID, request_id, command_digest, stamp, data, charge),
                    )
                conn.execute(
                    "INSERT INTO hyperdispatcher_workflows VALUES (?,?,?,?,?,?,?,?)",
                    (_RUN_ID, plan.tenant, plan.workflow_id, raw, digest,
                     self._workflow_seal(raw, stamp), stamp, len(raw)+512),
                )
                for item in plan.commands:
                    self._index_submit(conn, item.request_id, item.body, item.digest)
                    conn.execute("INSERT INTO hyperdispatcher_workflow_members VALUES (?,?,?,?,?)",
                                 (_RUN_ID, plan.tenant, plan.workflow_id, item.request_id,
                                  item.body["task_id"]))
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflows WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, plan.tenant, plan.workflow_id),
                ).fetchone()
                result = self._workflow_row(conn, row)
                conn.commit()
                return result
            except BaseException:
                conn.rollback()
                raise

    def workflow_member(self, command: InboxCommand) -> dict | None:
        """Resolve an exact command and its graph before task admission."""
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN")
            try:
                claim = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflow_members WHERE run_id=? AND (task_id=? OR request_id=?)",
                    (_RUN_ID, command.body["task_id"], command.request_id),
                ).fetchone()
                if claim is None:
                    conn.commit()
                    return None
                if claim["request_id"] != command.request_id:
                    raise DispatcherRequestError("task identity reserved by another workflow request")
                if claim["task_id"] != command.body["task_id"]:
                    raise DurableSwarmError("workflow member task identity changed")
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflows WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, claim["tenant"], claim["workflow_id"]),
                ).fetchone()
                if row is None:
                    raise DurableSwarmError("workflow member has no sealed manifest")
                graph = self._workflow_row(conn, row)
                node = next((item for item in graph["jobs"] if item["request_id"] == command.request_id), None)
                if (node is None or node["request_sha256"] != command.request_sha256
                        or node["sequence"] != command.sequence
                        or graph["tenant"] != command.body["tenant"]):
                    raise DurableSwarmError("workflow command differs from sealed membership")
                conn.commit()
                return graph
            except BaseException:
                conn.rollback()
                raise

    def _cancel_seal(self, graph: dict, command: InboxCommand) -> str:
        import hmac
        key = hmac.digest(self.policy.inspector_key, b"skeleton.dispatch.workflow.cancel.v1", "sha256")
        return hmac.digest(key, _wait_bytes([
            self.policy.digest, graph["tenant"], graph["workflow_id"], graph["workflow_sha256"],
            command.request_id, command.request_sha256, command.sequence,
        ]), "sha256").hex()

    def _cancel_record(self, conn, row, graph: dict) -> tuple[InboxCommand, str, dict | None]:
        import hmac
        target = conn.execute(
            "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
            (_RUN_ID, row["request_id"]),
        ).fetchone()
        if target is None:
            raise DurableSwarmError("workflow cancellation command missing")
        command = self._decode(target)
        if (row["manifest_sha256"] != graph["workflow_sha256"]
                or row["command_sha256"] != command.request_sha256
                or command.body != {"kind": "workflow-cancel", "tenant": graph["tenant"],
                                    "workflow_id": graph["workflow_id"]}
                or command.sequence <= max(job["sequence"] for job in graph["jobs"])
                or not hmac.compare_digest(row["seal"], self._cancel_seal(graph, command))
                or target["status"] not in ("pending", "accepted")):
            raise DurableSwarmError("workflow cancellation intent identity mismatch")
        return command, target["status"], self._public_row(target)["result"]

    def cancellation(self, tenant: str, workflow_id: str) -> dict | None:
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN")
            try:
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflow_cancellations "
                    "WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, tenant, workflow_id),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                manifest = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflows WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, tenant, workflow_id),
                ).fetchone()
                if manifest is None:
                    raise DurableSwarmError("workflow cancellation manifest missing")
                command, status, receipt = self._cancel_record(conn, row, self._workflow_row(conn, manifest))
                conn.commit()
                return {"request_id": command.request_id, "status": status, "result": receipt}
            except BaseException:
                conn.rollback()
                raise

    def begin_cancellation(self, owner_id: str, command: InboxCommand) -> tuple[dict, InboxCommand, str, dict | None]:
        tenant, workflow_id = command.body["tenant"], command.body["workflow_id"]
        with closing(self.store._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                run = self.store._require_run(conn, _RUN_ID)
                self.store._require_live_owner(run, owner_id, self.store._now())
                row = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflows WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, tenant, workflow_id),
                ).fetchone()
                if row is None:
                    raise DispatcherRequestError("owned workflow not found")
                graph = self._workflow_row(conn, row)
                if command.sequence <= max(job["sequence"] for job in graph["jobs"]):
                    raise DispatcherRequestError("workflow cancellation predates graph")
                previous = conn.execute(
                    "SELECT * FROM hyperdispatcher_workflow_cancellations "
                    "WHERE run_id=? AND tenant=? AND workflow_id=?",
                    (_RUN_ID, tenant, workflow_id),
                ).fetchone()
                if previous is None:
                    conn.execute(
                        "INSERT INTO hyperdispatcher_workflow_cancellations VALUES (?,?,?,?,?,?,?)",
                        (_RUN_ID, tenant, workflow_id, command.request_id, graph["workflow_sha256"],
                         command.request_sha256, self._cancel_seal(graph, command)),
                    )
                    previous = conn.execute(
                        "SELECT * FROM hyperdispatcher_workflow_cancellations "
                        "WHERE run_id=? AND tenant=? AND workflow_id=?",
                        (_RUN_ID, tenant, workflow_id),
                    ).fetchone()
                original, status, result = self._cancel_record(conn, previous, graph)
                conn.commit()
                return graph, original, status, result
            except BaseException:
                conn.rollback()
                raise

    def outstanding_cancellations(self, *, limit: int = 16) -> tuple[InboxCommand, ...]:
        _uint(limit, 1, 128, "workflow cancellation batch")
        with closing(self.store._connect()) as conn:
            rows = conn.execute(
                "SELECT i.* FROM hyperdispatcher_workflow_cancellations c "
                "JOIN hyperdispatcher_inbox i ON i.run_id=c.run_id AND i.request_id=c.request_id "
                "WHERE c.run_id=? AND i.status='pending' ORDER BY i.sequence LIMIT ?",
                (_RUN_ID, limit),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    @staticmethod
    def _decode(row) -> InboxCommand:
        data = row["body"]
        if (type(data) is not bytes or len(data) > _MAX_COMMAND_BYTES
                or sha256(data).hexdigest() != row["request_sha256"]):
            raise DurableSwarmError("durable command integrity failure")
        body = _json_object(data)
        if _canonical(body) != data:
            raise DurableSwarmError("noncanonical durable command")
        return InboxCommand(row["sequence"], row["request_id"],
                            row["request_sha256"], row["submitted_ms"], body)

    def record(self, request_id: str) -> tuple[InboxCommand, str, dict | None] | None:
        _identifier(request_id)
        with closing(self.store._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM hyperdispatcher_inbox WHERE run_id=? AND request_id=?",
                (_RUN_ID, request_id),
            ).fetchone()
        if row is None:
            return None
        public = self._public_row(row)
        return self._decode(row), public["status"], public["result"]

    def pending(self, *, limit: int = 16, after: int = 0) -> tuple[InboxCommand, ...]:
        _uint(limit, 1, 128, "inbox batch")
        _uint(after, 0, 2**63-1, "inbox cursor")
        with closing(self.store._connect()) as conn:
            # A consistent read with two indexed range scans. Deferred work
            # cannot block later signals, cancellations or independent jobs.
            conn.execute("BEGIN")
            try:
                rows = conn.execute(
                    "SELECT sequence,request_id,request_sha256,submitted_ms,body "
                    "FROM hyperdispatcher_inbox WHERE run_id=? AND status='pending' AND sequence>? "
                    "ORDER BY sequence LIMIT ?", (_RUN_ID, after, limit),
                ).fetchall()
                if after and len(rows) < limit:
                    rows += conn.execute(
                        "SELECT sequence,request_id,request_sha256,submitted_ms,body "
                        "FROM hyperdispatcher_inbox WHERE run_id=? AND status='pending' AND sequence<=? "
                        "ORDER BY sequence LIMIT ?", (_RUN_ID, after, limit-len(rows)),
                    ).fetchall()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return tuple(self._decode(row) for row in rows)

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
        with closing(self.store._connect()) as conn:
            workflows, workflow_bytes = conn.execute(
                "SELECT count(*),coalesce(sum(charge),0) FROM hyperdispatcher_workflows WHERE run_id=?",
                (_RUN_ID,),
            ).fetchone()
        out["workflows"] = workflows
        out["reserved_bytes"] += workflow_bytes
        return out


@dataclass(frozen=True, slots=True)
class ApplicationTick:
    commands: int
    cancelled_dependents: tuple[str, ...]
    recovered: tuple[str, ...]
    disposition: str
    task_id: str | None
    stop_requested: bool
    tasks: tuple[str, ...] = ()
    outcomes: tuple[tuple[str, str], ...] = ()
    archived_tasks: tuple[str, ...] = ()
    deferred_commands: tuple[str, ...] = ()


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
            self.directory / "evidence", max_attempts=self.policy.history_jobs,
            max_bytes=self.policy.worker_storage_bytes, max_artifact_bytes=65536,
        )
        self.archive = (None if not self.policy.history_bytes else SQLiteDispatcherArchive(
            self.store, run_id=_RUN_ID, policy_sha256=self.policy.digest,
            archive_key=self.policy.inspector_key, max_jobs=self.policy.history_jobs,
            max_bytes=self.policy.history_bytes,
        ))
        self.managed: ManagedHostDispatcher | None = None
        self._recovery: LocalCommittedRecovery | None = None
        self._stop_requested = False
        self._inbox_cursor = 0

    @classmethod
    def initialize(
        cls, directory: str | Path, *, tenants: tuple[str, ...],
        operations: tuple[str, ...], workers: int = 2, max_jobs: int = 128,
        timeout_seconds: int = 10, lease_seconds: int = 120,
        worker_storage_bytes: int = 128 * 1024 * 1024,
        outer_history: int = 16, clock_ms: Callable[[], int] | None = None,
        store_clock: Callable[[], float] | None = None, gguf_options: dict | None = None,
        history_jobs: int | None = None, history_bytes: int = 512 * 1024**2,
        inbox_bytes: int = 128 * 1024**2,
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
        if history_jobs is not None:
            config["history"] = {"jobs": history_jobs, "bytes": history_bytes, "inbox_bytes": inbox_bytes}
        if gguf_options is not None:
            if GGUF_OPERATION not in operations:
                raise DispatcherRequestError("GGUF provisioning requires explicit operation grant")
            config["gguf"] = PinnedGGUFPolicy.provision(gguf_options).record()
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

    def _authorities(self):
        policy = self.policy
        original_grants = {
            (policy.worker_issuer(index), policy.worker_id(index)): (key, frozenset({"success"}))
            for index, key in enumerate(policy.worker_keys)
        }
        worker_validator = LocalWorkerEvidenceValidator(
            self.custody, additional_validator=None if policy.gguf is None else (
                lambda attempt, raw: attempt.tenant in policy.tenants
                and attempt.worker_id == policy.worker_id(0)
                and policy.gguf.validate_artifact(attempt, raw)
            ),
        )
        original = HostWorkerAuthority(
            _RUN_ID, grants=original_grants, resolve=self.custody.resolve,
            validate_evidence=worker_validator,
        )
        validator = LocalCommittedEvidenceValidator(
            self.custody, original, local_validator=worker_validator,
        )
        grants = dict(original_grants)
        for index in range(policy.workers):
            grants[("local-inspector", policy.worker_id(index))] = (
                policy.inspector_key, frozenset({"reconcile:committed"}))
        authority = HostWorkerAuthority(_RUN_ID, grants=grants, resolve=self.custody.resolve,
                                        validate_evidence=validator)
        return original, validator, authority

    def start(self) -> ManagedHostDispatcher:
        if self.managed is not None:
            raise DurableSwarmError("application service already started")
        policy = self.policy
        # Revalidate all sealed archived identities before admitting new work;
        # a missing/tampered row must fail closed rather than permit reuse.
        if self.archive is not None:
            self.archive.audit()
        self.inbox.audit()
        signers = {policy.worker_id(index): (policy.worker_issuer(index), key)
                   for index, key in enumerate(policy.worker_keys)}
        pure_operations = policy.operations & _LOCAL_OPERATIONS
        transport_grants = {(tenant, worker): pure_operations
                            for tenant in policy.tenants for worker in signers if pure_operations}
        _, validator, authority = self._authorities()
        transport_options = dict(grants=transport_grants, worker_signers=signers,
                                 timeout_seconds=policy.timeout_seconds)
        if policy.gguf is None:
            transport = LocalSubprocessTransport(self.custody, **transport_options)
        else:
            transport = PinnedGGUFTransport(
                self.custody, policy=policy.gguf, workspace_db=self.store.path,
                gguf_worker=policy.worker_id(0), gguf_tenants=frozenset(policy.tenants),
                **transport_options,
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
                default_lease_seconds=transport.max_execution_seconds + 15,
            )
            for worker in signers:
                capabilities = ["local-compute"]
                if policy.gguf is not None and worker == policy.worker_id(0):
                    capabilities.append(GGUF_CAPABILITY)
                initial.register_worker(worker, capacity=1, capabilities=tuple(capabilities))
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

    def enqueue_workflow(self, tenant: str, workflow_id: str, spec: dict) -> dict:
        tenant = self._tenant(tenant)
        try:
            plan = compile_workflow(workflow_id, tenant, spec, operations=self.policy.operations)
        except WorkflowError as exc:
            raise DispatcherRequestError(str(exc)) from exc
        # Reject invalid static operations before publishing any node.
        # Linked templates cannot be evaluated until receipts materialize.
        for command in plan.commands:
            body = command.body
            if "bindings" in body:
                continue
            payload = {"operation": body["operation"], "input": body["input"]}
            try:
                raw = _canonical(payload, limit=32768)
                if body["operation"] == GGUF_OPERATION:
                    self.policy.gguf.request(payload)
                else:
                    result = _local_reference(payload)
                    _canonical({"version": 1, "payload_sha256": sha256(raw).hexdigest(),
                                "result": result}, limit=self.custody.max_artifact_bytes)
            except (ValueError, TypeError, UnicodeError, RecursionError, DurableSwarmError) as exc:
                raise DispatcherRequestError("invalid static workflow operation") from exc
        return self.inbox.enqueue_workflow(plan)

    def workflow_status(self, tenant: str, workflow_id: str) -> dict:
        tenant = self._tenant(tenant)
        record = self.inbox.workflow(tenant, workflow_id)
        if record is None:
            raise DispatcherRequestError("owned workflow not found")
        counts = {"pending": 0, "rejected": 0, "queued": 0, "leased": 0,
                  "succeeded": 0, "failed": 0, "cancelled": 0, "uncertain": 0}
        for row in record["jobs"]:
            if row["status"] != "accepted":
                counts[row["status"]] += 1
                row["task_state"] = None
                continue
            proof = self.result(tenant, row["task_id"])
            state = "uncertain" if proof["uncertain_on_restore"] else proof["state"]
            if state == "dead":
                state = "failed"
            if state not in counts:
                raise DurableSwarmError("unknown canonical workflow task state")
            counts[state] += 1
            row["task_state"] = state
            if "receipt_sha256" in proof:
                row["receipt_sha256"] = proof["receipt_sha256"]
            if "reconciliation_sha256" in proof:
                row["reconciliation_sha256"] = proof["reconciliation_sha256"]
        unfinished = counts["pending"] + counts["queued"] + counts["leased"]
        if counts["succeeded"] == len(record["jobs"]):
            status = "succeeded"
        elif counts["uncertain"]:
            status = "held-uncertain"
        elif unfinished:
            status = "running"
        else:
            status = "terminated"
        cancellation = self.inbox.cancellation(tenant, workflow_id)
        if cancellation is not None and status != "succeeded":
            if counts["uncertain"]:
                status = "cancelled-held-uncertain"
            elif unfinished:
                status = "cancelling"
            else:
                status = "cancelled"
        return {**record, "workflow_state": status, "counts": counts,
                **({"cancellation": cancellation} if cancellation is not None else {})}

    def _resident(self, tenant: str, task_id: str):
        owner = self._owner().owner
        runtime = owner.broker.broker.runtime
        task = runtime.task(task_id)
        if task is None or owner.broker.tenant_for(task_id) != tenant:
            raise DispatcherRequestError("owned task not found")
        return task

    def _binding_input(self, command: InboxCommand, tenant: str, *,
                       historical: bool = False) -> tuple[object, list[dict]]:
        body = command.body
        if "bindings" not in body and "prerequisites" not in body:
            if "binding_deadline_ms" in body:
                raise DispatcherRequestError("binding deadline without bindings")
            return body["input"], []
        try:
            bindings = (() if "bindings" not in body else
                        parse_bindings(body["bindings"], body["input"], task_id=body["task_id"]))
            prerequisites = (() if "prerequisites" not in body else
                             parse_prerequisites(body["prerequisites"], task_id=body["task_id"]))
            deadline = _uint(body.get("binding_deadline_ms"), command.submitted_ms + 1,
                             command.submitted_ms + MAX_BINDING_WAIT_MS, "binding deadline")
            if not historical and _wait_time(self.clock_ms()) >= deadline:
                raise DispatcherRequestError("result binding deadline expired")

            proofs = {}

            def resolve_source(source_request_id: str, source_task_id: str) -> dict:
                identity = (source_request_id, source_task_id)
                if identity in proofs:
                    return proofs[identity]
                found = self.inbox.record(source_request_id)
                if found is None:
                    raise DispatcherRequestError("earlier owned binding request not found")
                source, status, acknowledgement = found
                if (source.sequence >= command.sequence or source.body.get("kind") != "submit"
                        or source.body.get("tenant") != tenant
                        or source.body.get("task_id") != source_task_id):
                    raise DispatcherRequestError("binding requires earlier same-tenant submission")
                if status == "pending":
                    raise BindingDeferred()
                if status != "accepted":
                    raise DispatcherRequestError("binding source submission rejected")
                if (type(acknowledgement) is not dict
                        or acknowledgement.get("task_id") != source_task_id
                        or acknowledgement.get("submission") != "durable"):
                    raise DurableSwarmError("binding source acknowledgement lacks task identity")
                try:
                    proof = self.result(tenant, source_task_id, _verify_lineage=False)
                except DispatcherRequestError as exc:
                    raise DurableSwarmError("accepted binding source lacks durable task custody") from exc
                if proof["state"] in ("queued", "leased") or proof["uncertain_on_restore"]:
                    raise BindingDeferred()
                if proof["state"] != "succeeded":
                    raise DispatcherRequestError("binding source terminated without success")
                proofs[identity] = proof
                return proof

            output, lineage = materialize(
                body["input"], bindings,
                lambda binding: resolve_source(binding.source_request_id, binding.source_task_id),
            )
            for source_request_id, source_task_id in prerequisites:
                proof = resolve_source(source_request_id, source_task_id)
                lineage.append({"dependency_only": True, "source_request_id": source_request_id,
                                "source_task_id": source_task_id,
                                "receipt_sha256": proof["receipt_sha256"],
                                "reconciliation_sha256": proof.get("reconciliation_sha256")})
            return output, lineage
        except BindingError as exc:
            raise DispatcherRequestError(str(exc)) from exc

    def _verify_lineage(self, tenant: str, task: dict) -> list[dict]:
        payload = task["payload"]
        metadata = payload.get(_HOST_SCHEDULE_FIELD)
        if not isinstance(metadata, dict) or "binding_receipts" not in metadata:
            return []
        found = self.inbox.record(metadata.get("request_id"))
        if found is None:
            raise DurableSwarmError("bound task has no exact original inbox command")
        command, status, _ = found
        if (status not in ("pending", "accepted")
                or command.request_sha256 != metadata.get("request_sha256")
                or command.submitted_ms != metadata.get("enqueued_ms")
                or command.body.get("kind") != "submit"
                or command.body.get("tenant") != tenant
                or command.body.get("task_id") != task["id"]
                or command.body.get("operation") != payload.get("operation")
                or not ({"bindings", "prerequisites"} & set(command.body))):
            raise DurableSwarmError("bound task admission identity changed")
        try:
            resolved, lineage = self._binding_input(command, tenant, historical=True)
        except (DispatcherRequestError, BindingDeferred) as exc:
            raise DurableSwarmError("historical result binding cannot be verified") from exc
        if (_wait_bytes(resolved) != _wait_bytes(payload.get("input"))
                or _wait_bytes(lineage) != _wait_bytes(metadata["binding_receipts"])):
            raise DurableSwarmError("bound result lineage changed")
        return lineage

    def _submit(self, command: InboxCommand) -> dict:
        body = command.body
        required = {"kind", "tenant", "task_id", "operation", "input"}
        permitted = required | {"priority", "dependencies", "singleton", "timer_ms", "event",
                                "bindings", "prerequisites", "binding_deadline_ms"}
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
        def same_submission(record: dict) -> bool:
            existing = record["payload"].get(_HOST_SCHEDULE_FIELD)
            if (type(existing) is not dict
                    or any(existing.get(key) != value for key, value in metadata.items())):
                return False
            if bool({"bindings", "prerequisites"} & set(body)) != ("binding_receipts" in existing):
                raise DurableSwarmError("submission replay binding metadata mismatch")
            self._verify_lineage(tenant, record)
            return True

        if prior is not None:
            if owner.broker.tenant_for(task_id) == tenant and same_submission(runtime._task_record(prior)):
                return {"task_id": task_id, "submission": "durable"}
            raise DispatcherRequestError("task identity already bound to another command")
        old = None if self.archive is None else self.archive.get(task_id)
        if old is not None:
            if old.tenant == tenant and same_submission(old.task):
                return {"task_id": task_id, "submission": "durable"}
            raise DispatcherRequestError("task identity already bound to archived command")
        graph = self.inbox.workflow_member(command)
        if graph is not None:
            if self.inbox.cancellation(tenant, graph["workflow_id"]) is not None:
                raise DispatcherRequestError("workflow cancellation already recorded")
            if _wait_time(self.clock_ms()) >= graph["deadline_ms"]:
                raise DispatcherRequestError("workflow admission deadline expired")
        resolved_input, lineage = self._binding_input(command, tenant)
        if lineage:
            metadata["binding_receipts"] = lineage
        live_dependencies = []
        for dep in deps:
            dep = _identifier(dep)
            if runtime.task(dep) is not None:
                self._resident(tenant, dep)
                live_dependencies.append(dep)
                continue
            previous = None if self.archive is None else self.archive.get(dep)
            if previous is None or previous.tenant != tenant:
                raise DispatcherRequestError("owned dependency not found")
            if previous.task["state"] != "succeeded":
                raise DispatcherRequestError("archived dependency did not succeed")
            proof = self._result_for_record(tenant, previous.task, expected_receipt=previous.receipt_sha256)
            if proof.get("receipt_sha256") != previous.receipt_sha256:
                raise DurableSwarmError("archived dependency evidence missing")
        if self.archive is not None and self.archive.unique_count(
                tuple(task.id for task in runtime.tasks())) >= self.policy.history_jobs:
            raise DispatcherRequestError("total task history capacity exhausted")
        payload = {"operation": operation, "input": resolved_input}
        raw = _canonical(payload, limit=32768)
        try:
            if operation == GGUF_OPERATION:
                if self.policy.gguf is None:
                    raise DurableSwarmError("no provisioned GGUF model")
                self.policy.gguf.request(payload)
            else:
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
        if (self.archive is not None
                and (len(runtime.tasks()) >= self.policy.max_jobs
                     or occupied + payload_charge > _MAX_RETAINED_PAYLOAD)):
            self.archive.compact(managed, target_resident=max(0, self.policy.max_jobs // 2),
                                 prove_result=self._result_for_record)
            # A requested live parent must not disappear from the job's
            # dependency inventory during resident compaction.
            kept = []
            for parent in live_dependencies:
                if runtime.task(parent) is not None:
                    kept.append(parent)
                    continue
                saved = self.archive.get(parent)
                if saved is None or saved.tenant != tenant or saved.task["state"] != "succeeded":
                    raise DispatcherRequestError("compacted dependency did not succeed")
                self._result_for_record(tenant, saved.task, expected_receipt=saved.receipt_sha256)
            live_dependencies = kept
            occupied = sum(len(_canonical(dict(task.payload))) for task in runtime.tasks())
        if len(runtime.tasks()) >= self.policy.max_jobs or occupied + payload_charge > _MAX_RETAINED_PAYLOAD:
            if lineage or graph is not None:
                raise BindingDeferred()
            raise DispatcherRequestError("retained task capacity exhausted")
        task = SwarmTask(task_id, payload, priority=priority, max_attempts=1,
                         required_capabilities=frozenset({GGUF_CAPABILITY if operation == GGUF_OPERATION else "local-compute"}),
                         dependencies=tuple(live_dependencies))
        capture = (managed.submit(tenant, task, singleton_key=singleton)
                   if wait is None else managed.submit_wait(wait, task, singleton_key=singleton))
        if capture is None:
            if lineage or graph is not None:
                raise BindingDeferred()
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

    def _cancel_workflow(self, command: InboxCommand) -> dict:
        if set(command.body) != {"kind", "tenant", "workflow_id"}:
            raise DispatcherRequestError("invalid workflow cancellation request")
        tenant = self._tenant(command.body["tenant"])
        _identifier(command.body["workflow_id"])
        managed = self._owner()
        owner = managed.owner
        graph, original, status, prior = self.inbox.begin_cancellation(owner.owner_id, command)
        if status == "accepted":
            return prior
        runtime = owner.broker.broker.runtime
        # The durable cancellation intent is published before touching any
        # task. On takeover, complete it before any new dispatch can occur.
        counts = {"unadmitted": 0, "cancelled": 0, "succeeded": 0,
                  "failed": 0, "held_uncertain": 0, "already_rejected": 0}
        for item in graph["jobs"]:
            managed.renew()
            found = self.inbox.record(item["request_id"])
            if found is None:
                raise DurableSwarmError("workflow cancellation member disappeared")
            node, current_status, acknowledgement = found
            task_id = item["task_id"]
            if node.request_sha256 != item["request_sha256"]:
                raise DurableSwarmError("workflow cancellation member changed")
            marker = {"reason": "workflow cancelled before task admission",
                      "cancelled_by": original.request_id}
            if current_status == "rejected":
                counts["unadmitted" if acknowledgement == marker else "already_rejected"] += 1
                continue
            resident = runtime.task(task_id)
            archived = None if resident is not None or self.archive is None else self.archive.get(task_id)
            if resident is not None:
                record = runtime._task_record(resident)
                actual_tenant = owner.broker.tenant_for(task_id)
            elif archived is not None:
                record, actual_tenant = archived.task, archived.tenant
            else:
                record, actual_tenant = None, None
            if record is None:
                if current_status != "pending":
                    raise DurableSwarmError("accepted workflow cancellation member has no task custody")
                self.inbox.acknowledge(owner.owner_id, node, accepted=False, result=marker)
                counts["unadmitted"] += 1
                continue
            metadata = record["payload"].get(_HOST_SCHEDULE_FIELD)
            if (actual_tenant != tenant or type(metadata) is not dict
                    or metadata.get("request_id") != node.request_id
                    or metadata.get("request_sha256") != node.request_sha256
                    or metadata.get("enqueued_ms") != node.submitted_ms):
                raise DurableSwarmError("workflow cancellation task custody mismatch")
            self._verify_lineage(tenant, record)
            exact_ack = {"task_id": task_id, "submission": "durable"}
            if current_status == "pending":
                # A prior owner captured admission but lost its ack. Preserve
                # that fact before settling a queued task; never call submit.
                self.inbox.acknowledge(owner.owner_id, node, accepted=True, result=exact_ack)
            elif acknowledgement != exact_ack:
                raise DurableSwarmError("workflow cancellation member acknowledgement mismatch")
            state = record["state"]
            if record.get("effect_uncertain") or state == "leased":
                counts["held_uncertain"] += 1
            elif state == "queued":
                managed.cancel_queued(tenant, task_id)
                counts["cancelled"] += 1
            elif state in ("cancelled", "succeeded"):
                counts[state] += 1
            elif state in ("dead", "failed"):
                counts["failed"] += 1
            else:
                raise DurableSwarmError("unexpected workflow member state")
        result = {"workflow_id": graph["workflow_id"], "workflow_sha256": graph["workflow_sha256"],
                  "cancellation_request_id": original.request_id, "counts": counts,
                  "active_effects_terminated": False}
        if original.request_id != command.request_id:
            self.inbox.acknowledge(owner.owner_id, original, accepted=True, result=result)
        return result

    def _apply(self, command: InboxCommand) -> dict:
        kind = command.body.get("kind")
        if kind == "submit":
            return self._submit(command)
        if kind == "signal":
            return self._signal(command)
        if kind == "workflow-cancel":
            return self._cancel_workflow(command)
        if kind == "cancel-pending":
            if set(command.body) != {"kind", "tenant", "request_id"}:
                raise DispatcherRequestError("invalid pending cancellation request")
            tenant = self._tenant(command.body["tenant"])
            target = self.inbox.record(_identifier(command.body["request_id"]))
            if target is None:
                raise DispatcherRequestError("owned pending request not found")
            prior, status, result = target
            if (prior.sequence >= command.sequence or prior.body.get("kind") != "submit"
                    or prior.body.get("tenant") != tenant
                    or not ({"bindings", "prerequisites"} & set(prior.body))):
                raise DispatcherRequestError("owned pending binding request required")
            cancellation = {"reason": "pending result binding cancelled",
                            "cancelled_by": command.request_id}
            if status == "rejected" and result == cancellation:
                return {"request_id": prior.request_id, "status": "cancelled"}
            if status != "pending":
                raise DispatcherRequestError("binding request is already settled")
            runtime = self._owner().owner.broker.broker.runtime
            if (runtime.task(prior.body["task_id"]) is not None
                    or (self.archive is not None and self.archive.get(prior.body["task_id"]) is not None)):
                raise DispatcherRequestError("task already admitted; use task cancellation")
            self.inbox.acknowledge(self._owner().owner.owner_id, prior,
                                   accepted=False, result=cancellation)
            return {"request_id": prior.request_id, "status": "cancelled"}
        if kind == "stop" and set(command.body) == {"kind"}:
            self._stop_requested = True
            return {"stop": "requested"}
        if kind not in ("cancel", "reconcile") or set(command.body) != {"kind", "tenant", "task_id"}:
            raise DispatcherRequestError("unsupported operator command")
        tenant = self._tenant(command.body["tenant"])
        task_id = _identifier(command.body["task_id"])
        runtime = self._owner().owner.broker.broker.runtime
        if runtime.task(task_id) is None and self.archive is not None:
            archived = self.archive.get(task_id)
            if archived is None or archived.tenant != tenant:
                raise DispatcherRequestError("owned task not found")
            if kind == "cancel" and archived.task["state"] == "cancelled":
                return {"task_id": task_id, "state": "cancelled"}
            if kind == "reconcile" and archived.task.get("reconciliation_sha256"):
                proof = self._result_for_record(tenant, archived.task, expected_receipt=archived.receipt_sha256)
                return {"task_id": task_id, "reconciliation_sha256": proof["reconciliation_sha256"]}
            raise DispatcherRequestError("archived task is terminal")
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
            if (type(metadata) is not dict or set(metadata) - {"binding_receipts"} != {
                    "request_id", "request_sha256", "enqueued_ms"}):
                raise DurableSwarmError("queued task has no admitted schedule identity")
            tenant = owner.broker.tenant_for(task.id)
            if tenant not in self.policy.tenants:
                raise DurableSwarmError("queued task outside configured tenant policy")
            created = _wait_time(metadata["enqueued_ms"])
            if created > now_ms:
                raise DurableSwarmError("dispatcher clock moved behind admitted job")
            found = self.inbox.record(metadata["request_id"])
            if found is None:
                raise DurableSwarmError("queued task lacks durable admission command")
            command, status, acknowledgement = found
            body = command.body
            if (command.request_sha256 != metadata["request_sha256"]
                    or command.submitted_ms != created or body.get("kind") != "submit"
                    or body.get("task_id") != task.id or body.get("tenant") != tenant
                    or body.get("operation") != task.payload.get("operation")
                    or body.get("priority", 100) != task.priority):
                raise DurableSwarmError("queued task admission identity changed")
            if bool({"bindings", "prerequisites"} & set(body)) != ("binding_receipts" in metadata):
                raise DurableSwarmError("queued task lineage inventory changed")
            if "binding_receipts" in metadata:
                self._verify_lineage(tenant, runtime._task_record(task))
            elif _wait_bytes(body["input"]) != _wait_bytes(task.payload.get("input")):
                raise DurableSwarmError("queued task input differs from admitted command")
            graph = self.inbox.workflow_member(command)
            if graph is not None and self.inbox.cancellation(tenant, graph["workflow_id"]) is not None:
                raise DurableSwarmError("cancelled workflow retains a dispatchable task")
            if status == "pending":
                # Admission may have been captured just before owner loss.
                # The inbox must acknowledge exact replay before dispatch.
                continue
            if status != "accepted" or acknowledgement != {"task_id": task.id, "submission": "durable"}:
                raise DurableSwarmError("queued task admission acknowledgement invalid")
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
        deferred = []
        # Restore an interrupted cancellation before normal inbox work or
        # physical dispatch. Never skip a durable intent due to cursor order.
        for command in self.inbox.outstanding_cancellations(limit=16):
            managed.renew()
            result = self._cancel_workflow(command)
            managed.renew()
            self.inbox.acknowledge(managed.owner.owner_id, command, accepted=True, result=result)
            count += 1
        if self.inbox.outstanding_cancellations(limit=1):
            return ApplicationTick(count, (), (), "cancelling", None, False)
        for command in self.inbox.pending(limit=command_limit, after=self._inbox_cursor):
            self._inbox_cursor = command.sequence
            managed.renew()
            # A preceding pending cancellation may have settled a later row
            # already fetched in this batch. Never execute a stale snapshot.
            status = self.inbox.command(command.request_id)
            if status is None or status["request_sha256"] != command.request_sha256:
                raise DurableSwarmError("pending command identity disappeared")
            if status["status"] != "pending":
                continue
            try:
                result = self._apply(command)
            except BindingDeferred:
                managed._ensure_active()
                deferred.append(command.request_id)
                continue
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
            return ApplicationTick(count, (), (), "stopping", None, True,
                                   deferred_commands=tuple(deferred))
        recovered = self._recover_committed()
        cancelled = managed.propagate_dependencies()
        now_ms = _wait_time(self.clock_ms())
        batch = managed.tick_batch(
            self._candidates(now_ms), now_ms=now_ms, limit=self.policy.workers, timer_limit=16,
        )
        archived = ()
        if self.archive is not None:
            resident = len(managed.owner.broker.broker.runtime.tasks())
            if resident >= max(1, self.policy.max_jobs * 3 // 4):
                archived = self.archive.compact(
                    managed, target_resident=self.policy.max_jobs // 2,
                    prove_result=self._result_for_record,
                )
        managed.prune_outer_checkpoints(keep=self.policy.outer_history)
        ids = tuple(row.task_id for row in batch.outcomes)
        return ApplicationTick(
            count, cancelled, recovered, batch.disposition, ids[0] if ids else None, False,
            ids, tuple((row.task_id, row.disposition) for row in batch.outcomes), archived, tuple(deferred),
        )

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
                "worker_custody": self.custody.usage(),
                "terminal_history": None if self.archive is None else self.archive.usage()}

    def result(self, tenant: str, task_id: str, *, _verify_lineage: bool = True) -> dict:
        tenant, task_id = self._tenant(tenant), _identifier(task_id)
        loaded = SwarmDurableBridge(self.store).load(_RUN_ID)
        if loaded is None:
            raise DispatcherRequestError("no durable task archive")
        runtime = loaded.restore_runtime()
        task = runtime.task(task_id)
        tenant_checkpoint = loaded.manager.tenant_store.get(loaded.manager.store.latest().sequence)
        if task is None:
            archived = None if self.archive is None else self.archive.get(task_id)
            if archived is None or archived.tenant != tenant:
                raise DispatcherRequestError("owned task not found")
            return self._result_for_record(tenant, archived.task, expected_receipt=archived.receipt_sha256,
                                           verify_lineage=_verify_lineage)
        if tenant_checkpoint is None:
            raise DurableSwarmError("resident task lacks durable tenant sidecar")
        # The tenant sidecar is authoritative, including terminal identity.
        owners = dict(tenant_checkpoint.active)
        owners.update(dict(tenant_checkpoint.terminal))
        if owners.get(task_id) != tenant:
            raise DispatcherRequestError("owned task not found")
        return self._result_for_record(tenant, runtime._task_record(task), verify_lineage=_verify_lineage)

    def _result_for_record(self, tenant: str, task: dict, *,
                           expected_receipt: str | None = None, verify_lineage: bool = True) -> dict:
        task_id = task["id"]
        result = {"task_id": task_id, "tenant": tenant, "state": task["state"],
                  "uncertain_on_restore": task["effect_uncertain"]}
        # Never present an unacknowledged worker result as completed.
        if task["state"] != "succeeded":
            if expected_receipt is not None:
                raise DurableSwarmError("terminal non-success cannot assert worker success")
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
        if expected_receipt is not None and digest != expected_receipt:
            raise DurableSwarmError("archived worker receipt identity changed")
        resolved = self.custody.resolve(digest)
        if resolved is None:
            raise DurableSwarmError("completed worker result missing")
        receipt, raw = resolved
        record = self.custody.lookup(_RUN_ID, rows[0][0])
        payload = dict(task["payload"])
        payload.pop(_HOST_WAIT_FIELD, None)
        payload.pop(_HOST_SCHEDULE_FIELD, None)
        if (record is None or record.attempt.tenant != tenant
                or record.attempt.payload_json != _wait_bytes(payload)):
            raise DurableSwarmError("completed task admission differs from worker result")
        original, _, authority = self._authorities()
        if not original(receipt.worker_id, task_id, rows[0][0], "success", digest):
            raise DurableSwarmError("completed worker result failed evidence verification")
        reconciliation = task.get("reconciliation_sha256")
        if reconciliation is not None:
            if not authority(receipt.worker_id, task_id, rows[0][0], "reconcile:committed",
                             reconciliation):
                raise DurableSwarmError("completed reconciliation evidence refused")
            result["reconciliation_sha256"] = reconciliation
        result["receipt_sha256"] = digest
        result["result"] = _json_object(raw)["result"]
        if verify_lineage:
            lineage = self._verify_lineage(tenant, task)
            if lineage:
                result["input_lineage"] = lineage
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
    init.add_argument("--operation", action="append", choices=sorted(_LOCAL_OPERATIONS | {GGUF_OPERATION}), required=True)
    init.add_argument("--gguf-policy", type=Path, help="private explicit pinned CPU GGUF policy JSON")
    init.add_argument("--workers", type=int, default=2)
    init.add_argument("--max-jobs", type=int, default=128, help="resident scheduler identity capacity")
    init.add_argument("--history-jobs", type=int, help="explicit rolling terminal history identity ceiling")
    init.add_argument("--history-mib", type=int, default=512)
    init.add_argument("--inbox-mib", type=int, default=128)
    init.add_argument("--evidence-mib", type=int, default=128)
    init.add_argument("--timeout", type=int, default=10)
    init.add_argument("--lease", type=int, default=120)
    enqueue = sub.add_parser("enqueue", help="append one exact JSON command from standard input")
    enqueue.add_argument("--id", required=True)
    workflow = sub.add_parser("workflow-submit", help="atomically publish a bounded JSON graph from stdin")
    workflow.add_argument("--tenant", required=True)
    workflow.add_argument("--id", required=True)
    workflow_status = sub.add_parser("workflow-status", help="inspect exact graph and verified job outcomes")
    workflow_status.add_argument("--tenant", required=True)
    workflow_status.add_argument("--id", required=True)
    workflow_cancel = sub.add_parser("workflow-cancel", help="durably request safe graph cancellation")
    workflow_cancel.add_argument("--tenant", required=True)
    workflow_cancel.add_argument("--id", required=True, help="workflow ID")
    workflow_cancel.add_argument("--request-id", required=True)
    command = sub.add_parser("command", help="read the durable command acknowledgement")
    command.add_argument("--id", required=True)
    result = sub.add_parser("result", help="read independently verified task output")
    result.add_argument("--tenant", required=True)
    result.add_argument("--task", required=True)
    sub.add_parser("status")
    sub.add_parser("audit-history", help="stream and verify every retained terminal history row")
    sub.add_parser("audit-ingress", help="stream and verify durable commands, graph seals and capacity ledger")
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
                history_jobs=args.history_jobs, history_bytes=args.history_mib * 1024**2,
                inbox_bytes=args.inbox_mib * 1024**2, worker_storage_bytes=args.evidence_mib * 1024**2,
                gguf_options=None if args.gguf_policy is None else _json_object(
                    _read_private(args.gguf_policy, _MAX_COMMAND_BYTES)),
            )
            _print(app.status())
            return 0
        app = LocalDispatcherApplication(args.directory)
        if args.action == "enqueue":
            data = sys.stdin.buffer.read(_MAX_COMMAND_BYTES + 1)
            if len(data) > _MAX_COMMAND_BYTES:
                raise DispatcherRequestError("command input too large")
            _print(app.enqueue(args.id, _json_object(data)))
        elif args.action == "workflow-submit":
            raw = sys.stdin.buffer.read(MAX_WORKFLOW_BYTES + 1)
            if len(raw) > MAX_WORKFLOW_BYTES:
                raise DispatcherRequestError("workflow input too large")
            # Reuse the exact duplicate-property and finite-JSON parser.
            data = _json_object(raw, limit=MAX_WORKFLOW_BYTES)
            _print(app.enqueue_workflow(args.tenant, args.id, data))
        elif args.action == "workflow-status":
            _print(app.workflow_status(args.tenant, args.id))
        elif args.action == "workflow-cancel":
            _print(app.enqueue(args.request_id, {"kind": "workflow-cancel",
                                                "tenant": args.tenant, "workflow_id": args.id}))
        elif args.action == "command":
            value = app.inbox.command(args.id)
            _print(value)
            return 0 if value is not None else 1
        elif args.action == "result":
            _print(app.result(args.tenant, args.task))
        elif args.action == "status":
            _print(app.status())
        elif args.action == "audit-ingress":
            _print(app.inbox.audit())
        elif args.action == "audit-history":
            if app.archive is None:
                raise DispatcherRequestError("rolling terminal history not provisioned")
            _print(app.archive.audit())
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
