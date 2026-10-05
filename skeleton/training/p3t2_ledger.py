"""Governed training control for P3T2-TRAINING-01.

Volumes owned by this candidate, unsigned:

* VOL-143 run identity and admission
* VOL-144 content-addressed checkpoints
* VOL-145 monotonic resume cursor
* VOL-146 independent evaluation binding
* VOL-147 crash recovery of a staged checkpoint intent
* VOL-148 hard step/token budget stop
* VOL-149 lineage receipt that cannot self-sign closure

This module materializes the lane. It does not grant a completion checkbox,
an implementation signature, or a verification signature.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import sqlite3
import threading
from typing import Any, Mapping


MAX_ID = 256
MAX_ACTOR = 128


class TrainingContractError(ValueError):
    """A governed training invariant was violated."""


def _text(value: object, field: str, *, maximum: int = MAX_ID) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TrainingContractError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise TrainingContractError(f"{field} exceeds maximum length")
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        raise TrainingContractError(f"{field} contains unsafe characters")
    return value


def _positive(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TrainingContractError(f"{field} must be a positive integer")
    return value


def _nonnegative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TrainingContractError(f"{field} must be a non-negative integer")
    return value


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TrainingContractError("value is not canonically serializable") from exc


@dataclass(frozen=True, slots=True)
class RunAdmission:
    run_id: str
    tenant_id: str
    dataset_digest: str
    base_checkpoint_digest: str
    trainer_actor: str
    max_steps: int
    max_tokens: int

    def __post_init__(self) -> None:
        _text(self.run_id, "run_id")
        _text(self.tenant_id, "tenant_id")
        _text(self.dataset_digest, "dataset_digest", maximum=64)
        _text(self.base_checkpoint_digest, "base_checkpoint_digest", maximum=64)
        _text(self.trainer_actor, "trainer_actor", maximum=MAX_ACTOR)
        _positive(self.max_steps, "max_steps")
        _positive(self.max_tokens, "max_tokens")
        if len(self.dataset_digest) != 64 or len(self.base_checkpoint_digest) != 64:
            raise TrainingContractError("dataset and base checkpoint digests must be sha256")


@dataclass(frozen=True, slots=True)
class CheckpointReceipt:
    run_id: str
    step: int
    tokens: int
    digest: str
    parent_digest: str
    cursor: int


@dataclass(frozen=True, slots=True)
class EvaluationReceipt:
    run_id: str
    checkpoint_digest: str
    evaluator_actor: str
    metric_digest: str
    passed: bool


@dataclass(frozen=True, slots=True)
class LineageReceipt:
    run_id: str
    head_digest: str
    evaluation_digest: str
    steps: int
    tokens: int
    promotion_authority: bool = False

    def __post_init__(self) -> None:
        if self.promotion_authority is not False:
            raise TrainingContractError("lineage receipt cannot grant promotion authority")


class GovernedTrainingLedger:
    """SQLite training ledger. Cache is absent; the ledger is the authority."""

    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._db:
            self._db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS training_run (
                    run_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    dataset_digest TEXT NOT NULL,
                    base_checkpoint_digest TEXT NOT NULL,
                    trainer_actor TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    max_tokens INTEGER NOT NULL,
                    cursor INTEGER NOT NULL,
                    tokens INTEGER NOT NULL,
                    head_digest TEXT NOT NULL,
                    staged_step INTEGER,
                    staged_tokens INTEGER,
                    staged_payload BLOB,
                    staged_digest TEXT
                );
                CREATE TABLE IF NOT EXISTS checkpoint (
                    run_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    parent_digest TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    tokens INTEGER NOT NULL,
                    PRIMARY KEY (run_id, step),
                    FOREIGN KEY (run_id) REFERENCES training_run(run_id)
                );
                CREATE TABLE IF NOT EXISTS evaluation (
                    run_id TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL,
                    evaluator_actor TEXT NOT NULL,
                    metric_digest TEXT NOT NULL,
                    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                    PRIMARY KEY (run_id, checkpoint_digest, evaluator_actor),
                    FOREIGN KEY (run_id) REFERENCES training_run(run_id)
                );
                """
            )

    def close(self) -> None:
        self._db.close()

    def admit(self, admission: RunAdmission) -> RunAdmission:
        with self._lock, self._db:
            existing = self._db.execute(
                "SELECT * FROM training_run WHERE run_id = ?",
                (admission.run_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["tenant_id"] != admission.tenant_id
                    or existing["dataset_digest"] != admission.dataset_digest
                    or existing["base_checkpoint_digest"] != admission.base_checkpoint_digest
                    or existing["trainer_actor"] != admission.trainer_actor
                    or int(existing["max_steps"]) != admission.max_steps
                    or int(existing["max_tokens"]) != admission.max_tokens
                ):
                    raise TrainingContractError("run identity cannot be rebound")
                return admission
            self._db.execute(
                """
                INSERT INTO training_run(
                    run_id, tenant_id, dataset_digest, base_checkpoint_digest,
                    trainer_actor, max_steps, max_tokens, cursor, tokens, head_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                """,
                (
                    admission.run_id,
                    admission.tenant_id,
                    admission.dataset_digest,
                    admission.base_checkpoint_digest,
                    admission.trainer_actor,
                    admission.max_steps,
                    admission.max_tokens,
                    admission.base_checkpoint_digest,
                ),
            )
        return admission

    def stage_checkpoint(
        self,
        *,
        run_id: str,
        step: int,
        token_delta: int,
        payload: bytes,
    ) -> str:
        run = _text(run_id, "run_id")
        checked_step = _positive(step, "step")
        delta = _nonnegative(token_delta, "token_delta")
        if not isinstance(payload, bytes) or not payload:
            raise TrainingContractError("checkpoint payload must be non-empty bytes")
        digest = _digest(payload)
        with self._lock, self._db:
            row = self._require_run(run)
            if checked_step != int(row["cursor"]) + 1:
                raise TrainingContractError("checkpoint step must advance the cursor by one")
            tokens = int(row["tokens"]) + delta
            if checked_step > int(row["max_steps"]) or tokens > int(row["max_tokens"]):
                raise TrainingContractError("checkpoint exceeds hard budget")
            if row["staged_digest"] is not None:
                raise TrainingContractError("a staged checkpoint intent is already open")
            self._db.execute(
                """
                UPDATE training_run
                SET staged_step = ?, staged_tokens = ?, staged_payload = ?, staged_digest = ?
                WHERE run_id = ?
                """,
                (checked_step, tokens, payload, digest, run),
            )
        return digest

    def finalize_checkpoint(self, *, run_id: str) -> CheckpointReceipt:
        run = _text(run_id, "run_id")
        with self._lock, self._db:
            row = self._require_run(run)
            if row["staged_digest"] is None or row["staged_payload"] is None:
                raise TrainingContractError("no staged checkpoint intent to finalize")
            payload = bytes(row["staged_payload"])
            digest = _digest(payload)
            if digest != row["staged_digest"]:
                raise TrainingContractError("staged checkpoint payload does not match digest")
            parent = str(row["head_digest"])
            step = int(row["staged_step"])
            tokens = int(row["staged_tokens"])
            self._db.execute(
                """
                INSERT INTO checkpoint(run_id, step, digest, parent_digest, payload, tokens)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run, step, digest, parent, payload, tokens),
            )
            self._db.execute(
                """
                UPDATE training_run
                SET cursor = ?, tokens = ?, head_digest = ?,
                    staged_step = NULL, staged_tokens = NULL,
                    staged_payload = NULL, staged_digest = NULL
                WHERE run_id = ?
                """,
                (step, tokens, digest, run),
            )
        return CheckpointReceipt(run, step, tokens, digest, parent, step)

    def resume(self, *, run_id: str) -> CheckpointReceipt:
        run = _text(run_id, "run_id")
        with self._lock:
            row = self._require_run(run)
            if row["staged_digest"] is not None:
                raise TrainingContractError("resume refused while a staged intent is open")
            cursor = int(row["cursor"])
            if cursor == 0:
                raise TrainingContractError("resume refused before the first finalized checkpoint")
            checkpoint = self._db.execute(
                "SELECT * FROM checkpoint WHERE run_id = ? AND step = ?",
                (run, cursor),
            ).fetchone()
            if checkpoint is None:
                raise TrainingContractError("resume cursor has no checkpoint")
            payload = bytes(checkpoint["payload"])
            if _digest(payload) != checkpoint["digest"] or checkpoint["digest"] != row["head_digest"]:
                raise TrainingContractError("resume digest does not match authoritative head")
        return CheckpointReceipt(
            run,
            int(checkpoint["step"]),
            int(checkpoint["tokens"]),
            str(checkpoint["digest"]),
            str(checkpoint["parent_digest"]),
            int(row["cursor"]),
        )

    def evaluate(
        self,
        *,
        run_id: str,
        checkpoint_digest: str,
        evaluator_actor: str,
        metrics: Mapping[str, Any],
        passed: bool,
    ) -> EvaluationReceipt:
        run = _text(run_id, "run_id")
        digest = _text(checkpoint_digest, "checkpoint_digest", maximum=64)
        actor = _text(evaluator_actor, "evaluator_actor", maximum=MAX_ACTOR)
        if not isinstance(passed, bool):
            raise TrainingContractError("evaluation passed flag must be a real boolean")
        metric_digest = _digest(_canonical(dict(metrics)))
        with self._lock, self._db:
            row = self._require_run(run)
            if actor == row["trainer_actor"]:
                raise TrainingContractError("trainer cannot sign its own evaluation")
            known = self._db.execute(
                "SELECT 1 FROM checkpoint WHERE run_id = ? AND digest = ?",
                (run, digest),
            ).fetchone()
            if known is None:
                raise TrainingContractError("evaluation must bind a finalized checkpoint")
            self._db.execute(
                """
                INSERT INTO evaluation(
                    run_id, checkpoint_digest, evaluator_actor, metric_digest, passed
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, checkpoint_digest, evaluator_actor)
                DO UPDATE SET metric_digest = excluded.metric_digest, passed = excluded.passed
                """,
                (run, digest, actor, metric_digest, 1 if passed else 0),
            )
        return EvaluationReceipt(run, digest, actor, metric_digest, passed)

    def lineage(self, *, run_id: str) -> LineageReceipt:
        run = _text(run_id, "run_id")
        with self._lock:
            row = self._require_run(run)
            evaluation = self._db.execute(
                """
                SELECT metric_digest FROM evaluation
                WHERE run_id = ? AND checkpoint_digest = ? AND passed = 1
                ORDER BY evaluator_actor
                LIMIT 1
                """,
                (run, row["head_digest"]),
            ).fetchone()
            if evaluation is None:
                raise TrainingContractError("lineage requires a passing independent evaluation")
        return LineageReceipt(
            run_id=run,
            head_digest=str(row["head_digest"]),
            evaluation_digest=str(evaluation["metric_digest"]),
            steps=int(row["cursor"]),
            tokens=int(row["tokens"]),
            promotion_authority=False,
        )

    def _require_run(self, run_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM training_run WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise TrainingContractError("training run is not admitted")
        return row
