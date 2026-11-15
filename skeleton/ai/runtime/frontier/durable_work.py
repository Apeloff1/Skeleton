"""Transactional authenticated work-order custody for app-owned SQLite.

This is an admission/receipt adapter, NOT an executor or authorization service.
The caller supplies an exclusively owned, private, durable connection and a
separate custody key. No default path, credentials, threads, or network.
A claimed order is never automatically reissued after a crash. MACs authenticate
individual records; whole-database rollback needs an external trusted anchor.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
import secrets
import sqlite3
import threading
from typing import Any, Iterable

from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle
from skeleton.frontier.payloads import json_snapshot

_MAX_ROWS = 16_384
_MAX_BYTES = 128 << 20
_MAX_BODY = 256 << 10
_MAX_BATCH = 1024
_MAX_DEPS = 1024
_STATES = frozenset({"pending", "claimed", "succeeded", "failed", "cancelled", "uncertain"})
_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "uncertain"})
_RECOVERY_DOMAIN = b"frontier.work.recovery.v1\0"
_TABLE = "frontier_work_orders_v1"
_FIELDS = ("scope", "work_id", "kind", "body", "dependencies", "state",
           "owner", "token_digest", "receipt", "mac")


class WorkConflict(RuntimeError):
    """Conflicting request or invalid state transition."""


class WorkIntegrityError(RuntimeError):
    """Stored custody was malformed or unauthenticated."""


class WorkCapacity(RuntimeError):
    """Admission refused before work was scheduled."""


def _text(value: object, *, maximum: int = 128) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("invalid work identity")
    return value


def _hex(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA-256 identity")
    return value


def _encode(value: Any, maximum: int = _MAX_BODY) -> bytes:
    raw = json.dumps(json_snapshot(value, max_bytes=maximum), sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(raw) > maximum:
        raise ValueError("encoded work payload exceeds budget")
    return raw


def work_identity(scope: str, kind: str, identity: object) -> str:
    return sha256(_encode([_text(scope), _text(kind), identity])).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkOrder:
    work_id: str
    kind: str
    payload: Any
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkStatus:
    work_id: str
    kind: str
    state: str
    dependencies: tuple[str, ...]
    owner: str
    receipt: str


@dataclass(frozen=True, slots=True, repr=False)
class WorkClaim:
    scope: str
    work_id: str
    owner: str
    token: str
    payload: Any

    def __repr__(self):
        return f"WorkClaim(scope={self.scope!r}, work_id={self.work_id!r}, owner={self.owner!r})"


@dataclass(frozen=True, slots=True)
class RecoveryChallenge:
    scope: str
    work_id: str
    owner: str
    record_mac: str


@dataclass(frozen=True, slots=True)
class RecoveryAuthorization:
    challenge: RecoveryChallenge
    state: str
    receipt_digest: str
    signature: str


def _recovery_payload(challenge: RecoveryChallenge, state: str, receipt: str) -> bytes:
    if type(challenge) is not RecoveryChallenge:
        raise ValueError("canonical recovery challenge required")
    if state not in {"succeeded", "failed", "uncertain"}:
        raise ValueError("recovery cannot requeue execution")
    return _RECOVERY_DOMAIN + _encode([
        _text(challenge.scope), _hex(challenge.work_id), _text(challenge.owner),
        _hex(challenge.record_mac), state, _hex(receipt),
    ])


def sign_recovery(challenge: RecoveryChallenge, *, state: str,
                  receipt_digest: str, recovery_key: bytes) -> RecoveryAuthorization:
    """Operator-only helper: call after independent evidence and quiescence review."""
    if type(recovery_key) is not bytes or len(recovery_key) != 32:
        raise ValueError("independent 256-bit recovery key required")
    payload = _recovery_payload(challenge, state, receipt_digest)
    return RecoveryAuthorization(challenge, state, receipt_digest,
                                 hmac.new(recovery_key, payload, sha256).hexdigest())


@dataclass(frozen=True, slots=True)
class WorkInventory:
    scope: str
    count: int
    digest: str
    states: tuple[tuple[str, int], ...]
    ready: tuple[str, ...]
    blocked: tuple[str, ...]
    unresolved: tuple[str, ...]


class DurableWorkJournal:
    """Source-neutral, bounded transaction owner; admission is explicit.

    Use an independent database from unrelated transaction owners. Connection
    sharing, schema manipulation, backup/restore and authorization are outside
    this contract. Payloads may contain user data: private storage is mandatory.
    """

    def __init__(self, connection: sqlite3.Connection, *, scope: str,
                 custody_key: bytes, max_rows: int = 4096,
                 max_bytes: int = 64 << 20,
                 recovery_key: bytes | None = None,
                 private_handle: PrivateSQLiteHandle | None = None,
                 initialize: bool = True):
        if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
            raise ValueError("exclusive idle SQLite connection required")
        if type(custody_key) is not bytes or len(custody_key) != 32:
            raise ValueError("independent 256-bit custody key required")
        if type(max_rows) is not int or not 1 <= max_rows <= _MAX_ROWS:
            raise ValueError("invalid work row budget")
        if type(max_bytes) is not int or not 4096 <= max_bytes <= _MAX_BYTES:
            raise ValueError("invalid work byte budget")
        if type(initialize) is not bool:
            raise ValueError("explicit initialization policy required")
        if private_handle is not None:
            if type(private_handle) is not PrivateSQLiteHandle or private_handle.connection is not connection:
                raise ValueError("private SQLite handle must own the exact connection")
            private_handle.assert_current()
        self._private_handle = private_handle
        self._db = connection
        self._scope = _text(scope)
        if recovery_key is not None and (type(recovery_key) is not bytes
                or len(recovery_key) != 32 or hmac.compare_digest(recovery_key, custody_key)):
            raise ValueError("recovery must use a separate 256-bit key")
        self._key = custody_key
        self._recovery_key = recovery_key
        self._max_rows = max_rows
        self._max_bytes = max_bytes
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._closed = False
        # Set no persistent connection mode silently. The app owns the DB.
        with self._tx(check_schema=False):
            if initialize:
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                    "scope TEXT NOT NULL, work_id TEXT NOT NULL, kind TEXT NOT NULL,"
                    "body BLOB NOT NULL, dependencies BLOB NOT NULL,"
                    "state TEXT NOT NULL CHECK(state IN "
                    "('pending','claimed','succeeded','failed','cancelled','uncertain')),"
                    "owner TEXT NOT NULL, token_digest TEXT NOT NULL, receipt TEXT NOT NULL,"
                    "mac TEXT NOT NULL, PRIMARY KEY(scope,work_id)) WITHOUT ROWID"
                )
            self._schema()
            self._capacity()

    @property
    def scope(self) -> str:
        return self._scope

    def _owner(self) -> None:
        if self._closed or os.getpid() != self._pid or threading.get_ident() != self._thread:
            raise RuntimeError("work journal owner is closed or changed")
        if self._private_handle is not None:
            self._private_handle.assert_current()
        if self._db.in_transaction:
            raise RuntimeError("work journal requires exclusive transaction authority")

    def _schema(self) -> None:
        rows = self._db.execute(f"PRAGMA table_info({_TABLE})").fetchall()
        types = ("TEXT", "TEXT", "TEXT", "BLOB", "BLOB", "TEXT", "TEXT", "TEXT", "TEXT", "TEXT")
        if (tuple(row[1] for row in rows) != _FIELDS
                or tuple(row[2].upper() for row in rows) != types
                or tuple(row[3] for row in rows) != (1,) * len(_FIELDS)
                or tuple(row[5] for row in rows) != (1, 2) + (0,) * 8):
            raise WorkIntegrityError("unexpected work schema")
        if self._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                            (_TABLE,)).fetchone():
            raise WorkIntegrityError("work journal triggers forbidden")

    @contextmanager
    def _tx(self, *, check_schema: bool = True):
        self._owner()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if self._private_handle is not None:
                self._private_handle.assert_current()
            if check_schema:
                self._schema()
            yield
            if self._private_handle is not None:
                self._private_handle.assert_current()
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _capacity(self, additional_rows: int = 0, additional_bytes: int = 0) -> None:
        count, total = self._db.execute(
            f"SELECT COUNT(*), COALESCE(SUM(length(body)+length(dependencies)+"
            f"length(scope)+length(work_id)+length(kind)+512),0) FROM {_TABLE}"
        ).fetchone()
        if count + additional_rows > self._max_rows or total + additional_bytes > self._max_bytes:
            raise WorkCapacity("work journal capacity exhausted")

    def _mac(self, row: tuple) -> str:
        scope, work_id, kind, body, deps, state, owner, token_digest, receipt = row
        metadata = _encode([scope, work_id, kind, sha256(body).hexdigest(),
                            sha256(deps).hexdigest(), state, owner, token_digest, receipt])
        return hmac.new(self._key, b"frontier.work.v1\0" + metadata, sha256).hexdigest()

    def _valid(self, row: tuple) -> tuple:
        try:
            scope, wid, kind, body, dep_raw, state, owner, token, receipt, mac = row
            if scope != self._scope:
                raise ValueError("wrong scope")
            _hex(wid)
            _text(kind)
            if (type(body) is not bytes or not 0 < len(body) <= _MAX_BODY
                    or type(dep_raw) is not bytes or not 0 < len(dep_raw) <= _MAX_BODY
                    or state not in _STATES or type(owner) is not str
                    or type(token) is not str or type(receipt) is not str):
                raise ValueError("invalid row fields")
            _hex(mac)
            if not hmac.compare_digest(mac, self._mac(row[:-1])):
                raise ValueError("work authentication failed")
            payload = json.loads(body)
            deps = json.loads(dep_raw)
            if _encode(payload) != body or _encode(deps) != dep_raw:
                raise ValueError("noncanonical work record")
            if type(deps) is not list or len(deps) > _MAX_DEPS or len(set(deps)) != len(deps):
                raise ValueError("invalid dependency inventory")
            for dep in deps:
                _hex(dep)
            if wid in deps:
                raise ValueError("self dependency")
            if state == "pending":
                if owner or token or receipt:
                    raise ValueError("invalid pending work")
            elif state == "claimed":
                _text(owner)
                _hex(token)
                if receipt:
                    raise ValueError("invalid claim receipt")
            elif state == "cancelled":
                if owner or token:
                    raise ValueError("cancelled pending work has owner")
                _hex(receipt)
            else:
                _text(owner)
                _hex(token)
                _hex(receipt)
            return row
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise WorkIntegrityError("invalid authenticated work record") from exc

    def _row(self, wid: str) -> tuple | None:
        oversized = self._db.execute(
            f"SELECT 1 FROM {_TABLE} WHERE scope=? AND work_id=? AND "
            "(length(body)>? OR length(dependencies)>? OR length(owner)>128 "
            "OR length(kind)>128 OR length(mac)<>64 OR length(token_digest)>64 "
            "OR length(receipt)>64)",
            (self._scope, _hex(wid), _MAX_BODY, _MAX_BODY),
        ).fetchone()
        if oversized:
            raise WorkIntegrityError("stored work row exceeds validation budget")
        row = self._db.execute(
            f"SELECT {','.join(_FIELDS)} FROM {_TABLE} WHERE scope=? AND work_id=?",
            (self._scope, _hex(wid)),
        ).fetchone()
        return None if row is None else self._valid(tuple(row))

    def _require(self, wid: str) -> tuple:
        row = self._row(wid)
        if row is None:
            raise KeyError("work order not found")
        return row

    def _status(self, row: tuple) -> WorkStatus:
        return WorkStatus(row[1], row[2], row[5], tuple(json.loads(row[4])), row[6], row[8])

    def _prepare(self, order: WorkOrder) -> tuple:
        if type(order) is not WorkOrder:
            raise TypeError("canonical WorkOrder required")
        wid, kind = _hex(order.work_id), _text(order.kind)
        if type(order.dependencies) is not tuple or len(order.dependencies) > _MAX_DEPS:
            raise ValueError("bounded tuple of dependencies required")
        deps = tuple(_hex(dep) for dep in order.dependencies)
        if wid in deps or len(set(deps)) != len(deps):
            raise ValueError("duplicate or self dependency")
        row = (self._scope, wid, kind, _encode(order.payload), _encode(list(deps)),
               "pending", "", "", "")
        return row + (self._mac(row),)

    def submit(self, orders: Iterable[WorkOrder]) -> tuple[WorkStatus, ...]:
        """Atomically admit a topologically ordered batch; no work executes."""
        prepared = []
        prepared_bytes = 0
        ids = set()
        for index, item in enumerate(orders):
            if index >= _MAX_BATCH:
                raise WorkCapacity("work batch exceeds limit")
            row = self._prepare(item)
            if row[1] in ids:
                raise WorkConflict("duplicate identity inside batch")
            prepared_bytes += len(row[3]) + len(row[4]) + 1024
            if prepared_bytes > self._max_bytes:
                raise WorkCapacity("work batch exceeds preparation byte budget")
            ids.add(row[1])
            prepared.append(row)
        with self._tx():
            staged = []
            statuses = []
            available = set()
            for row in prepared:
                existing = self._row(row[1])
                if existing is not None:
                    if existing[:5] != row[:5]:
                        raise WorkConflict("work order identity conflict")
                    statuses.append(self._status(existing))
                else:
                    for dep in json.loads(row[4]):
                        if dep not in available and self._row(dep) is None:
                            raise WorkConflict("dependency absent or batch not topologically ordered")
                    staged.append(row)
                    statuses.append(self._status(row))
                available.add(row[1])
            size = sum(len(row[3])+len(row[4])+len(row[0])+len(row[1])+len(row[2])+512
                       for row in staged)
            self._capacity(len(staged), size)
            self._db.executemany(
                f"INSERT INTO {_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?)", staged
            )
            return tuple(statuses)

    def status(self, work_id: str) -> WorkStatus:
        with self._tx():
            return self._status(self._require(work_id))

    def list_status(self, *, state: str | None = None, limit: int = 256) -> tuple[WorkStatus, ...]:
        if state is not None and state not in _STATES:
            raise ValueError("invalid work state")
        if type(limit) is not int or not 1 <= limit <= _MAX_ROWS:
            raise ValueError("invalid status limit")
        with self._tx():
            self._capacity()
            oversized = self._db.execute(
                f"SELECT 1 FROM {_TABLE} WHERE scope=? AND "
                "(length(body)>? OR length(dependencies)>? OR length(owner)>128 "
                "OR length(kind)>128 OR length(mac)<>64 OR length(token_digest)>64 "
                "OR length(receipt)>64) LIMIT 1",
                (self._scope, _MAX_BODY, _MAX_BODY),
            ).fetchone()
            if oversized:
                raise WorkIntegrityError("stored work row exceeds validation budget")
            # Validate all scope rows before filtering. A forged state cannot hide
            # an unauthenticated record from a recovery/ready scan.
            raw = self._db.execute(
                f"SELECT {','.join(_FIELDS)} FROM {_TABLE} WHERE scope=? ORDER BY work_id",
                (self._scope,),
            )
            result = []
            for item in raw:
                row = self._valid(tuple(item))
                if (state is None or row[5] == state) and len(result) < limit:
                    result.append(self._status(row))
            return tuple(result)

    def pending_payload(self, work_id: str, *, kind: str) -> object:
        """Inspect authenticated pending input solely for pre-claim admission."""
        with self._tx():
            row = self._require(work_id)
            if row[2] != _text(kind) or row[5] != "pending":
                raise WorkConflict("pending work kind or state is not authorized")
            return json.loads(row[3])

    def ready(self, *, kind: str | None = None, limit: int = 64) -> tuple[WorkStatus, ...]:
        """Return authenticated dependency-ready candidates, not actual admission permits."""
        if kind is not None:
            _text(kind)
        if type(limit) is not int or not 1 <= limit <= 1024:
            raise ValueError("invalid ready-work limit")
        # list_status verifies every row and releases its snapshot before
        # claim; claim always rereads prerequisites transactionally.
        rows = self.list_status(limit=_MAX_ROWS)
        by_id = {row.work_id: row for row in rows}
        ready = []
        for row in rows:
            if row.state != "pending" or (kind is not None and row.kind != kind):
                continue
            if any(dep not in by_id for dep in row.dependencies):
                raise WorkIntegrityError("authenticated work has missing dependency")
            if all(by_id[dep].state == "succeeded" for dep in row.dependencies):
                ready.append(row)
                if len(ready) == limit:
                    break
        return tuple(ready)

    def inventory(self, *, expected_digest: str | None = None) -> WorkInventory:
        """Audit every authenticated row and dependency in a single snapshot.

        An independently retained digest detects rollback or deletion relative
        to that exact checkpoint. It is not a remotely anchored history or
        an authorization to execute, and must never be auto-refreshed on open.
        """
        if expected_digest is not None:
            _hex(expected_digest)
        with self._tx():
            self._capacity()
            raw_ids = self._db.execute(
                f"SELECT work_id FROM {_TABLE} WHERE scope=? ORDER BY work_id",
                (self._scope,),
            )
            ids = tuple(item[0] for item in raw_ids)
            rows = {}
            digest = sha256(b"frontier.inventory.v1\\0" + _encode(self._scope))
            for wid in ids:
                row = self._require(wid)
                rows[wid] = self._status(row)
                digest.update(bytes.fromhex(wid))
                digest.update(bytes.fromhex(row[-1]))
            observed = digest.hexdigest()
            if expected_digest is not None and not hmac.compare_digest(expected_digest, observed):
                raise WorkIntegrityError("independent work inventory checkpoint differs")
            children = {wid: [] for wid in rows}
            indegree = {}
            for wid, row in rows.items():
                indegree[wid] = len(row.dependencies)
                for dep in row.dependencies:
                    if dep not in rows:
                        raise WorkIntegrityError("authenticated work has missing dependency")
                    children[dep].append(wid)
                    if row.state in {"claimed", "succeeded", "failed", "uncertain"} and rows[dep].state != "succeeded":
                        raise WorkIntegrityError("executed work has an unfulfilled dependency")
            # Iterative traversal avoids Python recursion on a long DAG.
            from collections import deque
            queue = deque(wid for wid in ids if indegree[wid] == 0)
            visited = 0
            while queue:
                wid = queue.popleft()
                visited += 1
                for child in children[wid]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        queue.append(child)
            if visited != len(rows):
                raise WorkIntegrityError("authenticated work dependency cycle")
            counts = {state: 0 for state in _STATES}
            ready, blocked, unresolved = [], [], []
            for wid, row in rows.items():
                counts[row.state] += 1
                if row.state == "pending":
                    (ready if all(rows[dep].state == "succeeded" for dep in row.dependencies)
                     else blocked).append(wid)
                elif row.state in {"claimed", "uncertain"}:
                    unresolved.append(wid)
            return WorkInventory(self._scope, len(rows), observed, tuple(sorted(counts.items())),
                                 tuple(ready), tuple(blocked), tuple(unresolved))

    def recovery_challenge(self, work_id: str) -> RecoveryChallenge:
        """Expose only the authenticated record identity for external reconciliation."""
        with self._tx():
            row = self._require(work_id)
            if row[5] != "claimed":
                raise WorkConflict("only a claimed order requires reconciliation")
            return RecoveryChallenge(self._scope, row[1], row[6], row[-1])

    def recovery_input(self, challenge: RecoveryChallenge, *, kind: str) -> object:
        """Inspect the exact current authenticated claim, not a stale challenge."""
        if type(challenge) is not RecoveryChallenge or challenge.scope != self._scope:
            raise WorkConflict("foreign recovery challenge")
        with self._tx():
            row = self._require(challenge.work_id)
            if (row[2] != _text(kind) or row[5] != "claimed" or row[6] != challenge.owner
                    or not hmac.compare_digest(row[-1], challenge.record_mac)):
                raise WorkConflict("stale recovery input")
            return json.loads(row[3])

    def reconcile_claimed(self, authorization: RecoveryAuthorization) -> WorkStatus:
        """Resolve a lost claim using independent operator proof; never replay."""
        if self._recovery_key is None:
            raise WorkConflict("independent recovery authority not configured")
        if type(authorization) is not RecoveryAuthorization:
            raise TypeError("canonical recovery authorization required")
        challenge = authorization.challenge
        payload = _recovery_payload(challenge, authorization.state, authorization.receipt_digest)
        expected = hmac.new(self._recovery_key, payload, sha256).hexdigest()
        if not hmac.compare_digest(_hex(authorization.signature), expected):
            raise WorkConflict("invalid independent recovery proof")
        if challenge.scope != self._scope:
            raise WorkConflict("foreign recovery scope")
        with self._tx():
            prior = self._require(challenge.work_id)
            if (prior[5] != "claimed" or prior[6] != challenge.owner
                    or not hmac.compare_digest(prior[-1], challenge.record_mac)):
                raise WorkConflict("stale recovery challenge")
            result = self._replace(prior, state=authorization.state, owner=prior[6],
                                   token_digest=prior[7], receipt=authorization.receipt_digest)
            return self._status(result)

    def _replace(self, prior: tuple, *, state: str, owner: str,
                 token_digest: str, receipt: str) -> tuple:
        row = prior[:5] + (state, owner, token_digest, receipt)
        mac = self._mac(row)
        changed = self._db.execute(
            f"UPDATE {_TABLE} SET state=?,owner=?,token_digest=?,receipt=?,mac=? "
            "WHERE scope=? AND work_id=? AND mac=?",
            (state, owner, token_digest, receipt, mac, self._scope, prior[1], prior[-1]),
        )
        if changed.rowcount != 1:
            raise WorkIntegrityError("work row changed before transition")
        return self._valid(row + (mac,))

    def claim(self, work_id: str, *, owner: str) -> WorkClaim:
        """Call only after live resource and policy admission by the app owner."""
        owner = _text(owner)
        with self._tx():
            prior = self._require(work_id)
            if prior[5] != "pending":
                raise WorkConflict("work is not pending")
            for dep in json.loads(prior[4]):
                if self._require(dep)[5] != "succeeded":
                    raise WorkConflict("dependency has not completed successfully")
            token = secrets.token_hex(32)
            self._replace(prior, state="claimed", owner=owner,
                          token_digest=sha256(token.encode("ascii")).hexdigest(), receipt="")
            return WorkClaim(self._scope, prior[1], owner, token, json.loads(prior[3]))

    def finish(self, claim: WorkClaim, *, succeeded: bool, receipt_digest: str) -> WorkStatus:
        """Only the current claimant can record an independently produced receipt."""
        if type(succeeded) is not bool:
            raise ValueError("explicit execution outcome required")
        return self._finish(claim, "succeeded" if succeeded else "failed", receipt_digest)

    def mark_uncertain(self, claim: WorkClaim, *, receipt_digest: str) -> WorkStatus:
        """Fence an ambiguous outcome permanently; never requeue automatically."""
        return self._finish(claim, "uncertain", receipt_digest)

    def _authenticate_claim(self, claim: WorkClaim) -> tuple:
        if type(claim) is not WorkClaim or claim.scope != self._scope:
            raise WorkConflict("invalid claim scope")
        token_digest = sha256(_hex(claim.token).encode("ascii")).hexdigest()
        prior = self._require(claim.work_id)
        if (prior[6] != claim.owner or not hmac.compare_digest(prior[7], token_digest)
                or not hmac.compare_digest(prior[3], _encode(claim.payload))):
            raise WorkConflict("stale, foreign or modified work claim")
        return prior

    def verify_claim(self, claim: WorkClaim, *, kind: str) -> object:
        """Authenticate the claim and return the independent persisted payload."""
        with self._tx():
            prior = self._authenticate_claim(claim)
            if prior[2] != _text(kind) or prior[5] != "claimed":
                raise WorkConflict("claim kind or state is not authorized")
            return json.loads(prior[3])

    def _finish(self, claim: WorkClaim, state: str, receipt_digest: str) -> WorkStatus:
        receipt_digest = _hex(receipt_digest)
        with self._tx():
            prior = self._authenticate_claim(claim)
            token_digest = prior[7]
            if prior[5] == state and prior[8] == receipt_digest:
                return self._status(prior)
            if prior[5] != "claimed":
                raise WorkConflict("terminal work cannot be changed")
            result = self._replace(prior, state=state, owner=prior[6],
                                   token_digest=token_digest, receipt=receipt_digest)
            return self._status(result)

    def cancel_pending(self, work_id: str, *, receipt_digest: str) -> WorkStatus:
        receipt_digest = _hex(receipt_digest)
        with self._tx():
            prior = self._require(work_id)
            if prior[5] == "cancelled" and prior[8] == receipt_digest:
                return self._status(prior)
            if prior[5] != "pending":
                raise WorkConflict("only never-claimed work can be cancelled")
            return self._status(self._replace(prior, state="cancelled", owner="",
                                              token_digest="", receipt=receipt_digest))

    def close(self) -> None:
        self._owner()
        self._closed = True
