"""Durable production control for 6/12 month Jeeves, Builder, Dragon work.

This is an authority-fenced SQLite *control plane*, not a fake daemon or a
substitute for each subsystem's canonical checkpoints. A host worker claims
one short lease, performs one authorized bounded quantum in its own runtime,
then commits an externally verified checkpoint/evidence digest atomically.

Safety:
- no work on expired grants; never automatically renew authority
- fencing token + monotonic epoch reject stale workers after host restarts
- checkpoint hash chain is append-only and committed with the progress cursor
- completed requires verified terminal evidence; disconnected is not failure
- work can be recovered 183/366+ days later without age-based eviction
- receipts contain hashes/identifiers only, never content or credentials
- bounded due scans and streaming audit, no unbounded in-RAM history.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Callable, Iterator

SCHEMA = "skeleton.annual-production.v1"
SYSTEMS = frozenset({"jeeves", "builder", "dragon"})
TERMINAL = frozenset({"completed", "failed", "cancelled"})
MAX_LEASE_SECONDS = 3600
MAX_READ = 100
_TOKEN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ProductionConflict(RuntimeError):
    """Persisted authority, work identity or worker lease is stale."""


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"invalid {label} digest")
    return value


def _clock(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid production clock")
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > 253402300799:
        raise ValueError("invalid production clock")
    return result


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 2**63 - 1:
        raise ValueError(f"invalid {label}")
    return value


def _hash(data: dict) -> str:
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Claim:
    production_id: str
    system: str
    worker: str
    epoch: int
    token: str
    expires_at: float
    authority_digest: str


@dataclass(frozen=True)
class ProductionState:
    production_id: str
    system: str
    horizon_days: int
    status: str
    sequence: int
    checkpoint_digest: str | None
    last_receipt_digest: str | None
    lease_epoch: int
    lease_expires_at: float | None
    next_run_at: float
    authority_expires_at: float
    created_at: float
    updated_at: float


class AnnualProductionStore:
    """One SQLite connection per operation; transactions coordinate processes.

    The host supplies an existing absolute directory on persistent storage.
    Never use a temporary or container-only path for actual year-long work.
    SQLite WAL supports concurrent readers, not a networked multi-host DB.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if (not self.path.is_absolute() or not self.path.parent.is_dir() or
                self.path.is_symlink() or self.path.is_dir()):
            raise ValueError("existing trusted absolute persistence directory required")
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS annual_productions (
                  production_id TEXT PRIMARY KEY,
                  system TEXT NOT NULL,
                  horizon_days INTEGER NOT NULL,
                  objective_digest TEXT NOT NULL,
                  authority_digest TEXT NOT NULL,
                  authority_expires_at REAL NOT NULL,
                  status TEXT NOT NULL,
                  sequence INTEGER NOT NULL,
                  checkpoint_digest TEXT,
                  last_receipt_digest TEXT,
                  lease_epoch INTEGER NOT NULL,
                  lease_token_digest TEXT,
                  lease_worker TEXT,
                  lease_expires_at REAL,
                  next_run_at REAL NOT NULL,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  terminal_evidence_digest TEXT
                );
                CREATE TABLE IF NOT EXISTS annual_checkpoint_receipts (
                  production_id TEXT NOT NULL,
                  sequence INTEGER NOT NULL,
                  epoch INTEGER NOT NULL,
                  state_digest TEXT NOT NULL,
                  evidence_digest TEXT NOT NULL,
                  previous_receipt_digest TEXT,
                  receipt_digest TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  PRIMARY KEY (production_id, sequence),
                  FOREIGN KEY (production_id) REFERENCES annual_productions(production_id)
                );
                CREATE INDEX IF NOT EXISTS annual_due_idx
                  ON annual_productions(status, next_run_at, production_id);
                CREATE TABLE IF NOT EXISTS annual_authority_rotations (
                  production_id TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  old_authority_digest TEXT NOT NULL,
                  new_authority_digest TEXT NOT NULL,
                  approval_digest TEXT NOT NULL,
                  expires_at REAL NOT NULL,
                  approved_at REAL NOT NULL,
                  previous_rotation_digest TEXT,
                  rotation_digest TEXT NOT NULL,
                  PRIMARY KEY (production_id, revision),
                  FOREIGN KEY (production_id) REFERENCES annual_productions(production_id)
                );
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self.path.is_symlink() or not self.path.parent.is_dir():
            raise ProductionConflict("production storage path changed")
        with closing(sqlite3.connect(str(self.path), timeout=5, isolation_level=None)) as db:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _row(db: sqlite3.Connection, production_id: str) -> sqlite3.Row:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM annual_productions WHERE production_id=?",
                         (production_id,)).fetchone()
        if row is None:
            raise ProductionConflict("unknown production")
        return row

    @staticmethod
    def _state(row: sqlite3.Row) -> ProductionState:
        return ProductionState(
            row["production_id"], row["system"], row["horizon_days"],
            row["status"], row["sequence"], row["checkpoint_digest"],
            row["last_receipt_digest"], row["lease_epoch"],
            row["lease_expires_at"], row["next_run_at"],
            row["authority_expires_at"], row["created_at"], row["updated_at"],
        )

    def enroll(self, *, production_id: str, system: str, objective_digest: str,
               authority_digest: str, authority_expires_at: float,
               horizon_days: int, now: float | None = None) -> ProductionState:
        production_id = _name(production_id, "production id")
        if system not in SYSTEMS:
            raise ValueError("invalid production subsystem")
        objective_digest = _digest(objective_digest, "objective")
        authority_digest = _digest(authority_digest, "authority")
        at = _clock(time.time() if now is None else now)
        expiry = _clock(authority_expires_at)
        if horizon_days not in {183, 366}:
            raise ValueError("select a six-month or one-year production horizon")
        if expiry <= at:
            raise PermissionError("active production authorization required")
        with self._tx() as db:
            existing = db.execute(
                "SELECT * FROM annual_productions WHERE production_id=?", (production_id,),
            ).fetchone()
            if existing:
                row = self._row(db, production_id)
                if (row["system"], row["objective_digest"], row["authority_digest"],
                    row["horizon_days"]) != (
                    system, objective_digest, authority_digest, horizon_days
                ):
                    raise ProductionConflict("production identity or authority changed")
                return self._state(row)
            db.execute("""INSERT INTO annual_productions VALUES
                (?, ?, ?, ?, ?, ?, 'queued', 0, NULL, NULL, 0,
                 NULL, NULL, NULL, ?, ?, ?, NULL)""",
                (production_id, system, horizon_days, objective_digest,
                 authority_digest, expiry, at, at, at))
            return self._state(self._row(db, production_id))

    def read(self, production_id: str) -> ProductionState:
        production_id = _name(production_id, "production id")
        with self._connect() as db:
            return self._state(self._row(db, production_id))

    def due(self, *, now: float | None = None, limit: int = 32,
            system: str | None = None) -> tuple[ProductionState, ...]:
        at = _clock(time.time() if now is None else now)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_READ:
            raise ValueError("invalid due scan limit")
        if system is not None and system not in SYSTEMS:
            raise ValueError("invalid production subsystem")
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            sql = """SELECT * FROM annual_productions
                WHERE status IN ('queued','waiting','running')
                  AND next_run_at<=? AND authority_expires_at>?
                  AND (lease_expires_at IS NULL OR lease_expires_at<=?)"""
            args: list = [at, at, at]
            if system is not None:
                sql += " AND system=?"
                args.append(system)
            sql += " ORDER BY next_run_at, production_id LIMIT ?"
            args.append(limit)
            return tuple(self._state(row) for row in db.execute(sql, args))

    @staticmethod
    def _require(db: sqlite3.Connection, claim: Claim, at: float) -> sqlite3.Row:
        row = AnnualProductionStore._row(db, claim.production_id)
        if row["system"] != claim.system or row["authority_digest"] != claim.authority_digest:
            raise ProductionConflict("wrong production or grant authority")
        if row["status"] != "running":
            raise ProductionConflict("production not running")
        if at < row["updated_at"]:
            raise ProductionConflict("production clock moved backward")
        if row["authority_expires_at"] <= at:
            raise PermissionError("authorization expired; reapproval required")
        if (row["lease_epoch"] != claim.epoch or row["lease_worker"] != claim.worker or
                row["lease_expires_at"] is None or row["lease_expires_at"] <= at or
                not hmac.compare_digest(row["lease_token_digest"] or "",
                                        sha256(claim.token.encode()).hexdigest())):
            raise ProductionConflict("worker lease expired or was fenced")
        return row

    def claim(self, production_id: str, *, worker: str, authority_digest: str,
              now: float | None = None, lease_seconds: int = 120) -> Claim:
        production_id = _name(production_id, "production id")
        worker = _name(worker, "worker")
        authority_digest = _digest(authority_digest, "authority")
        at = _clock(time.time() if now is None else now)
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= MAX_LEASE_SECONDS:
            raise ValueError("invalid lease duration")
        with self._tx() as db:
            row = self._row(db, production_id)
            if row["authority_digest"] != authority_digest:
                raise PermissionError("authorization identity differs")
            if at >= row["authority_expires_at"]:
                raise PermissionError("authorization expired; operator reapproval required")
            if row["status"] in TERMINAL or row["status"] == "paused":
                raise ProductionConflict("production not claimable")
            if row["next_run_at"] > at:
                raise ProductionConflict("production not due")
            if row["lease_expires_at"] is not None and row["lease_expires_at"] > at:
                raise ProductionConflict("worker lease still active")
            epoch = row["lease_epoch"] + 1
            token = secrets.token_hex(32)
            expiry = min(at + lease_seconds, row["authority_expires_at"])
            db.execute("""UPDATE annual_productions
                SET status='running', lease_epoch=?, lease_token_digest=?,
                    lease_worker=?, lease_expires_at=?, updated_at=?
                WHERE production_id=?""",
                (epoch, sha256(token.encode()).hexdigest(), worker, expiry, at, production_id))
            return Claim(production_id, row["system"], worker, epoch,
                         token, expiry, authority_digest)

    def heartbeat(self, claim: Claim, *, now: float | None = None,
                  lease_seconds: int = 120) -> Claim:
        at = _clock(time.time() if now is None else now)
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= MAX_LEASE_SECONDS:
            raise ValueError("invalid lease duration")
        with self._tx() as db:
            row = self._require(db, claim, at)
            if at < row["updated_at"]:
                raise ProductionConflict("lease heartbeat clock regression")
            expiry = min(at + lease_seconds, row["authority_expires_at"])
            db.execute("""UPDATE annual_productions SET lease_expires_at=?,
                updated_at=? WHERE production_id=?""",
                (expiry, at, claim.production_id))
            return Claim(claim.production_id, claim.system, claim.worker, claim.epoch,
                         claim.token, expiry, claim.authority_digest)

    def checkpoint(self, claim: Claim, *, sequence: int, state_digest: str,
                   evidence_digest: str, now: float | None = None) -> str:
        at = _clock(time.time() if now is None else now)
        sequence = _positive(sequence, "checkpoint sequence")
        state_digest = _digest(state_digest, "checkpoint state")
        evidence_digest = _digest(evidence_digest, "checkpoint evidence")
        with self._tx() as db:
            row = self._require(db, claim, at)
            if sequence != row["sequence"] + 1:
                raise ProductionConflict("checkpoint cursor gap or replay")
            payload = {"schema": SCHEMA, "production_id": claim.production_id,
                       "system": claim.system, "sequence": sequence,
                       "lease_epoch": claim.epoch, "state_digest": state_digest,
                       "evidence_digest": evidence_digest,
                       "previous_receipt_digest": row["last_receipt_digest"]}
            receipt = _hash(payload)
            db.execute("""INSERT INTO annual_checkpoint_receipts VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)""",
                (claim.production_id, sequence, claim.epoch, state_digest, evidence_digest,
                 row["last_receipt_digest"], receipt, at))
            db.execute("""UPDATE annual_productions
                SET sequence=?, checkpoint_digest=?, last_receipt_digest=?, updated_at=?
                WHERE production_id=?""",
                (sequence, state_digest, receipt, at, claim.production_id))
            return receipt

    def release(self, claim: Claim, *, now: float | None = None,
                retry_seconds: int = 300) -> ProductionState:
        at = _clock(time.time() if now is None else now)
        if type(retry_seconds) is not int or not 0 <= retry_seconds <= 7 * 86400:
            raise ValueError("invalid retry cadence")
        with self._tx() as db:
            self._require(db, claim, at)
            db.execute("""UPDATE annual_productions SET status='waiting',
                next_run_at=?, lease_token_digest=NULL, lease_worker=NULL,
                lease_expires_at=NULL, updated_at=? WHERE production_id=?""",
                (at + retry_seconds, at, claim.production_id))
            return self._state(self._row(db, claim.production_id))

    def terminal(self, claim: Claim, *, state: str, verified_evidence_digest: str,
                 now: float | None = None) -> ProductionState:
        if state not in TERMINAL:
            raise ValueError("terminal requires explicit verified status")
        evidence = _digest(verified_evidence_digest, "terminal evidence")
        at = _clock(time.time() if now is None else now)
        with self._tx() as db:
            row = self._require(db, claim, at)
            if state == "completed" and (row["sequence"] == 0 or
                                         row["checkpoint_digest"] is None):
                raise ProductionConflict("cannot declare completion without durable checkpoint")
            # The caller must verify evidence with the subsystem's canonical
            # owner. Digest format validation does not prove the artifact.
            db.execute("""UPDATE annual_productions SET status=?,
                terminal_evidence_digest=?, lease_token_digest=NULL, lease_worker=NULL,
                lease_expires_at=NULL, updated_at=? WHERE production_id=?""",
                (state, evidence, at, claim.production_id))
            return self._state(self._row(db, claim.production_id))

    def renew_authority(
        self, production_id: str, *, expected_authority_digest: str,
        new_authority_digest: str, approval_digest: str, new_expires_at: float,
        verify_approval: Callable[[str, str, str, str, float], bool],
        now: float | None = None,
    ) -> ProductionState:
        """Operator-approved grant rotation; old lease generations are fenced.

        The trusted host must authenticate and validate the original approval
        (signature, issuer, purpose and project scope) in verify_approval.
        Passing a digest alone does not grant permission and is never enough.
        """
        production_id = _name(production_id, "production id")
        prior = _digest(expected_authority_digest, "previous authority")
        updated = _digest(new_authority_digest, "new authority")
        receipt = _digest(approval_digest, "approval")
        at = _clock(time.time() if now is None else now)
        expiry = _clock(new_expires_at)
        if prior == updated or expiry <= at or not callable(verify_approval):
            raise ValueError("invalid renewed approval or grant")
        if verify_approval(production_id, prior, updated, receipt, expiry) is not True:
            raise PermissionError("independent operator approval was not verified")
        with self._tx() as db:
            row = self._row(db, production_id)
            if row["status"] in TERMINAL:
                raise ProductionConflict("terminal production cannot be revived by grant rotation")
            if row["authority_digest"] != prior:
                raise ProductionConflict("stale authority renewal")
            if expiry <= row["authority_expires_at"]:
                raise ProductionConflict("renewed authority must extend expiry")
            prior_rotation = db.execute("""SELECT revision,rotation_digest
                FROM annual_authority_rotations WHERE production_id=?
                ORDER BY revision DESC LIMIT 1""", (production_id,)).fetchone()
            revision = 1 if prior_rotation is None else prior_rotation[0] + 1
            previous = None if prior_rotation is None else prior_rotation[1]
            body = {"schema": SCHEMA, "production_id": production_id,
                    "revision": revision, "old_authority_digest": prior,
                    "new_authority_digest": updated, "approval_digest": receipt,
                    "expires_at": expiry, "approved_at": at,
                    "previous_rotation_digest": previous}
            rotation_digest = _hash(body)
            db.execute("""INSERT INTO annual_authority_rotations VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (production_id, revision, prior, updated, receipt, expiry, at,
                 previous, rotation_digest))
            # Reauthorization invalidates any prior grant's worker token.
            db.execute("""UPDATE annual_productions
                SET authority_digest=?, authority_expires_at=?,
                    lease_epoch=lease_epoch+1, lease_token_digest=NULL,
                    lease_worker=NULL, lease_expires_at=NULL,
                    status='waiting', next_run_at=?, updated_at=?
                WHERE production_id=?""", (updated, expiry, at, at, production_id))
            return self._state(self._row(db, production_id))

    def verify_authority_chain(self, production_id: str) -> int:
        """Streaming integrity verification of every explicit grant rotation."""
        production_id = _name(production_id, "production id")
        with self._connect() as db:
            row = self._row(db, production_id)
            cursor = db.execute("""SELECT revision,old_authority_digest,
                new_authority_digest,approval_digest,expires_at,approved_at,
                previous_rotation_digest,rotation_digest
                FROM annual_authority_rotations WHERE production_id=?
                ORDER BY revision""", (production_id,))
            prev_digest = None
            prev_grant = None
            revisions = 0
            for record in cursor:
                (rev, old, new, receipt, expiry, approved, link, digest) = record
                revisions += 1
                data = {"schema": SCHEMA, "production_id": production_id,
                        "revision": rev, "old_authority_digest": old,
                        "new_authority_digest": new, "approval_digest": receipt,
                        "expires_at": expiry, "approved_at": approved,
                        "previous_rotation_digest": link}
                if (rev != revisions or link != prev_digest or
                    (prev_grant is not None and old != prev_grant) or
                    _hash(data) != digest):
                    raise ProductionConflict("production grant history integrity failure")
                prev_digest, prev_grant = digest, new
            if prev_grant is not None and row["authority_digest"] != prev_grant:
                raise ProductionConflict("production grant head differs from verified history")
            return revisions

    def verify_chain(self, production_id: str) -> int:
        production_id = _name(production_id, "production id")
        with self._connect() as db:
            row = self._row(db, production_id)
            previous = None
            sequence = 0
            cursor = db.execute("""SELECT sequence,epoch,state_digest,evidence_digest,
                previous_receipt_digest,receipt_digest
                FROM annual_checkpoint_receipts WHERE production_id=?
                ORDER BY sequence""", (production_id,))
            for item in cursor:
                sequence += 1
                seq, epoch, state, evidence, prev, receipt = item
                data = {"schema": SCHEMA, "production_id": production_id,
                        "system": row["system"], "sequence": seq,
                        "lease_epoch": epoch, "state_digest": state,
                        "evidence_digest": evidence,
                        "previous_receipt_digest": prev}
                if seq != sequence or prev != previous or _hash(data) != receipt:
                    raise ProductionConflict("production checkpoint chain corrupted")
                previous = receipt
            if (sequence != row["sequence"] or previous != row["last_receipt_digest"]):
                raise ProductionConflict("production checkpoint head differs")
            return sequence
