"""Principal-bound durable Jeeves checkpoints inside the existing protected spine.

This is NOT a second SQLite owner. It uses the already descriptor-anchored,
WAL/FULL, private execution-spine connection, locking and transaction methods.
The native request/receipt tables remain independently authoritative. A hash
chain catches accidental or isolated record corruption; it is not an HMAC and
does not authenticate against an administrator who rewrites the whole database.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from .durable_runtime import _CheckpointCodec
from .runtime import RunCheckpoint, RunInputs
from .types import require_id


class NativeCheckpointHold(RuntimeError):
    """An agent custody, identity, integrity or sequence boundary was rejected."""


_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_runs (
    run_id TEXT PRIMARY KEY,
    scope_digest TEXT NOT NULL,
    tenant TEXT NOT NULL,
    subject TEXT NOT NULL,
    model_sha256 TEXT NOT NULL,
    tokenizer_sha256 TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    anchor_sequence INTEGER NOT NULL DEFAULT 0,
    anchor_hash TEXT NOT NULL,
    tip_sequence INTEGER NOT NULL DEFAULT 0,
    tip_hash TEXT NOT NULL
)
"""
_CHECKPOINT_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_checkpoints (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    payload BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES jeeves_native_runs(run_id)
)
"""
_ZERO = "0" * 64


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _link(previous_hash: str, sequence: int, payload_hash: str) -> str:
    return _sha(_json_bytes({
        "previous": previous_hash,
        "sequence": sequence,
        "payload_sha256": payload_hash,
        "schema": "jeeves.native_checkpoint_entry.v1",
    }))


def _input_digest(inputs: RunInputs) -> str:
    if not isinstance(inputs, RunInputs) or inputs.run_id is None:
        raise NativeCheckpointHold("explicit typed run identity required")
    # No capability tokens, injected provider objects or synthetic memory
    # are serialized. The durable lane denies tool grants separately.
    if inputs.grants or inputs.confirmed_actions:
        raise NativeCheckpointHold("durable source lane forbids ephemeral capabilities")
    return _sha(_json_bytes({
        "schema": "jeeves.native_run_binding.v1",
        "goal": asdict(inputs.goal),
        "tenant": inputs.tenant_id,
        "subject": inputs.user_id,
        "workspace": inputs.workspace_id,
        "session": inputs.session_id,
        "run": inputs.run_id,
        "budget": asdict(inputs.budget),
        "provider": inputs.preferred_provider,
        "metadata": inputs.metadata,
        "grants": [],
        "confirmed_actions": [],
    }))


class NativeSQLiteCheckpointer:
    """Bounded, append-only, crash-durable checkpoints on the same native DB.

    The caller must hold the existing cross-process SessionGate for the whole
    agent run; a SQLite transaction alone cannot fence external native calls.
    No automatic clear/reset is exposed: such an operation would erase the
    replay/uncertainty evidence needed for safe cold recovery.
    """

    def __init__(
        self, worker: Any, *,
        max_versions_per_run: int = 32,
        max_checkpoint_bytes: int = 262144,
        max_runs: int = 128,
    ) -> None:
        if not all(type(x) is int for x in (
            max_versions_per_run, max_checkpoint_bytes, max_runs,
        )):
            raise NativeCheckpointHold("integer checkpoint limits required")
        if not (1 <= max_versions_per_run <= 64
                and 4096 <= max_checkpoint_bytes <= 1048576
                and 1 <= max_runs <= 1024):
            raise NativeCheckpointHold("checkpoint limits outside protected bounds")
        if not isinstance(worker.spine.db, SpineDatabase):
            raise NativeCheckpointHold("canonical protected SQLite authority required")
        self.db = worker.spine.db
        self.worker = worker
        self.identity = ActiveModel.from_supervisor(worker)
        self.max_versions_per_run = max_versions_per_run
        self.max_checkpoint_bytes = max_checkpoint_bytes
        self.max_runs = max_runs
        self.db.inspect()
        with self.db.transaction() as conn:
            conn.execute(_RUN_SCHEMA)
            conn.execute(_CHECKPOINT_SCHEMA)

    def _live(self) -> None:
        if ActiveModel.from_supervisor(self.worker) != self.identity:
            raise NativeCheckpointHold("native model or principal changed")

    def _scope(self) -> tuple[str, str, str, str]:
        i = self.identity
        return i.tenant, i.subject, i.model_sha256, i.tokenizer_sha256

    def _row(self, conn: Any, run_id: str) -> tuple | None:
        row = conn.execute(
            "SELECT scope_digest,tenant,subject,model_sha256,"
            "tokenizer_sha256,goal_id,anchor_sequence,anchor_hash,"
            "tip_sequence,tip_hash FROM jeeves_native_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is not None and tuple(row[1:5]) != self._scope():
            raise NativeCheckpointHold("foreign principal or model run custody")
        return row

    def create_run(self, inputs: RunInputs) -> None:
        self._live()
        digest = _input_digest(inputs)
        with self.db.transaction() as conn:
            if self._row(conn, inputs.run_id) is not None:
                raise NativeCheckpointHold("run identity already consumed; no automatic replay")
            if conn.execute("SELECT COUNT(*) FROM jeeves_native_runs").fetchone()[0] >= self.max_runs:
                raise NativeCheckpointHold("durable run inventory full")
            conn.execute(
                "INSERT INTO jeeves_native_runs "
                "(run_id,scope_digest,tenant,subject,model_sha256,"
                "tokenizer_sha256,goal_id,anchor_hash,tip_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (inputs.run_id, digest, *self._scope(), inputs.goal.goal_id,
                 _ZERO, _ZERO),
            )

    def bind_existing(self, inputs: RunInputs) -> None:
        self._live()
        digest = _input_digest(inputs)
        with self.db.snapshot() as conn:
            row = self._row(conn, inputs.run_id)
            if row is None:
                raise NativeCheckpointHold("run absent from authoritative journal")
            if row[0] != digest or row[5] != inputs.goal.goal_id:
                raise NativeCheckpointHold("cold restart inputs differ from bound run")

    def _read(self, conn: Any, run_id: str) -> tuple[RunCheckpoint, ...]:
        row = self._row(conn, run_id)
        if row is None:
            return ()
        digest, tenant, subject, model, tokenizer, goal, anchor_seq, anchor_hash, tip_seq, tip_hash = row
        records = conn.execute(
            "SELECT sequence,payload,payload_sha256,previous_hash,entry_hash "
            "FROM jeeves_native_checkpoints WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        if len(records) > self.max_versions_per_run:
            raise NativeCheckpointHold("checkpoint history exceeds retention")
        if not records and (tip_seq != 0 or anchor_seq != 0
                            or tip_hash != _ZERO or anchor_hash != _ZERO):
            raise NativeCheckpointHold("journal tip exists without checkpoints")
        prev_seq = anchor_seq
        prev_hash = anchor_hash
        decoded: list[RunCheckpoint] = []
        for sequence, payload, payload_hash, previous, entry in records:
            if sequence != prev_seq + 1 or previous != prev_hash:
                raise NativeCheckpointHold("checkpoint chain gap or parent mismatch")
            if (type(payload) is not bytes
                    or len(payload) > self.max_checkpoint_bytes
                    or _sha(payload) != payload_hash
                    or _link(previous, sequence, payload_hash) != entry):
                raise NativeCheckpointHold("checkpoint payload or chain hash mismatch")
            try:
                raw = json.loads(payload)
                item = _CheckpointCodec.decode(raw["checkpoint"])
            except (KeyError, ValueError, TypeError, AttributeError) as exc:
                raise NativeCheckpointHold("invalid durable checkpoint encoding") from exc
            if (raw.get("schema") != "jeeves.native_checkpoint.v1"
                    or raw.get("checkpoint_fingerprint") != item.fingerprint
                    or item.run_id != run_id or item.sequence != sequence
                    or item.goal_id != goal
                    or item.metadata.get("tenant_id") != tenant
                    or item.metadata.get("user_id") != subject):
                raise NativeCheckpointHold("checkpoint content or principal mismatch")
            prev_seq, prev_hash = sequence, entry
            decoded.append(item)
        if prev_seq != tip_seq or prev_hash != tip_hash:
            raise NativeCheckpointHold("checkpoint tip fingerprint mismatch")
        return tuple(decoded)

    def save(self, checkpoint: RunCheckpoint) -> RunCheckpoint:
        if not isinstance(checkpoint, RunCheckpoint):
            raise NativeCheckpointHold("typed checkpoint required")
        self._live()
        raw = {
            "schema": "jeeves.native_checkpoint.v1",
            "checkpoint": _CheckpointCodec.encode(checkpoint),
            "checkpoint_fingerprint": checkpoint.fingerprint,
        }
        payload = _json_bytes(raw)
        if len(payload) > self.max_checkpoint_bytes:
            raise NativeCheckpointHold("checkpoint exceeds protected byte ceiling")
        run_id = checkpoint.run_id
        with self.db.transaction() as conn:
            row = self._row(conn, run_id)
            if row is None:
                raise NativeCheckpointHold("checkpoint run never admitted")
            # A full scan is intentional: never append to already-corrupt
            # provenance. The bounded window makes this deterministic.
            self._read(conn, run_id)
            if (checkpoint.goal_id != row[5]
                    or checkpoint.metadata.get("tenant_id") != self.identity.tenant
                    or checkpoint.metadata.get("user_id") != self.identity.subject):
                raise NativeCheckpointHold("checkpoint not owned by admitted principal")
            next_seq = row[8] + 1
            if checkpoint.sequence != next_seq:
                raise NativeCheckpointHold("checkpoint must advance by exactly one")
            previous = row[9]
            payload_hash = _sha(payload)
            entry = _link(previous, next_seq, payload_hash)
            conn.execute(
                "INSERT INTO jeeves_native_checkpoints VALUES (?,?,?,?,?,?)",
                (run_id, next_seq, payload, payload_hash, previous, entry),
            )
            conn.execute(
                "UPDATE jeeves_native_runs SET tip_sequence=?,tip_hash=? "
                "WHERE run_id=? AND tip_sequence=? AND tip_hash=?",
                (next_seq, entry, run_id, row[8], row[9]),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise NativeCheckpointHold("checkpoint CAS lost")
            excess = conn.execute(
                "SELECT COUNT(*) FROM jeeves_native_checkpoints WHERE run_id=?",
                (run_id,),
            ).fetchone()[0] - self.max_versions_per_run
            if excess > 0:
                retired = conn.execute(
                    "SELECT sequence,entry_hash FROM jeeves_native_checkpoints "
                    "WHERE run_id=? ORDER BY sequence LIMIT 1 OFFSET ?",
                    (run_id, excess - 1),
                ).fetchone()
                if retired is None:
                    raise NativeCheckpointHold("missing journal pruning boundary")
                conn.execute(
                    "DELETE FROM jeeves_native_checkpoints WHERE run_id=? AND sequence<=?",
                    (run_id, retired[0]),
                )
                conn.execute(
                    "UPDATE jeeves_native_runs SET anchor_sequence=?,anchor_hash=? "
                    "WHERE run_id=?",
                    (retired[0], retired[1], run_id),
                )
        return checkpoint

    def history(self, run_id: str) -> tuple[RunCheckpoint, ...]:
        require_id("run_id", run_id)
        self._live()
        with self.db.snapshot() as conn:
            return self._read(conn, run_id)

    def latest(self, run_id: str) -> RunCheckpoint | None:
        history = self.history(run_id)
        return history[-1] if history else None

    def inspect(self, run_id: str) -> dict[str, object]:
        self._live()
        history = self.history(run_id)
        with self.db.snapshot() as conn:
            row = self._row(conn, require_id("run_id", run_id))
        if row is None:
            raise NativeCheckpointHold("durable run not found")
        latest = history[-1] if history else None
        return {
            "schema": "jeeves.native_durable_run.v1",
            "run_id": run_id,
            "goal_id": row[5],
            "checkpoint_sequence": row[8],
            "retained_versions": len(history),
            "phase": latest.phase.value if latest else "admitted",
            "model_sha256": self.identity.model_sha256,
            "tokenizer_sha256": self.identity.tokenizer_sha256,
            "source_verified": False,
            "device_qualified": False,
            "release_certified": False,
        }

    def runs(self) -> tuple[str, ...]:
        self._live()
        with self.db.snapshot() as conn:
            return tuple(row[0] for row in conn.execute(
                "SELECT run_id FROM jeeves_native_runs "
                "WHERE tenant=? AND subject=? AND model_sha256=? "
                "AND tokenizer_sha256=? ORDER BY run_id",
                self._scope(),
            ).fetchall())

    def clear(self, run_id: str) -> bool:
        raise NativeCheckpointHold("erasing durable custody requires a separate reviewed protocol")


__all__ = ["NativeCheckpointHold", "NativeSQLiteCheckpointer"]
