"""SQLite-backed, optimistic-CAS persistence for the 100-milestone work queue.

This is a genuine durable adapter for the active Jeeves milestone scheduler.
A checkpoint is first validated by the scheduler, then atomically written
with a monotone version and a digest of its canonical bytes. Restored data
is reconstructed as typed records and independently rechecked.

A hash detects accidental corruption or mismatches. It is not a cryptographic
signature against an attacker able to rewrite the database and its hashes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, TypeVar

from .delivery_assurance_milestones import (
    MilestoneAttestation, MilestoneBoard, MilestoneReceipt,
)
from .delivery_milestone_queue import (
    MilestoneQueue, QueueEvent, WorkItem, restore_queue, verify_queue,
)

SCHEMA = "skeleton.jeeves.milestone_durable_queue.v1"
_MAX_DOCUMENT = 4 * 1024 * 1024
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class MilestoneCheckpointError(ValueError):
    """The durable checkpoint is stale, corrupt, or outside its source scope."""


class MilestoneCheckpointConflict(MilestoneCheckpointError):
    """Another writer advanced a checkpoint after it was read."""


@dataclass(frozen=True, slots=True)
class StoredMilestoneQueue:
    run_id: str
    generation: int
    queue: MilestoneQueue
    payload_sha256: str

    @property
    def fingerprint(self) -> str:
        return self.queue.fingerprint


@dataclass(frozen=True, slots=True)
class StoredMilestoneControl:
    run_id: str
    source_commit: str
    artifact_digest: str
    mode: str
    generation: int
    actor_ref: str
    reason_ref: str
    receipt: str


T = TypeVar("T")


def _record(typ: type[T], raw: object) -> T:
    if not isinstance(raw, dict) or set(raw) != {item.name for item in fields(typ)}:
        raise MilestoneCheckpointError("invalid or unknown milestone snapshot fields")
    try:
        return typ(**raw)
    except (TypeError, ValueError, KeyError) as exc:
        raise MilestoneCheckpointError("malformed milestone snapshot record") from exc


def _encode(queue: MilestoneQueue) -> bytes:
    verify_queue(queue)
    raw = {
        "schema": SCHEMA,
        "queue": asdict(queue),
    }
    try:
        value = json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise MilestoneCheckpointError("cannot canonically serialize milestone queue") from exc
    if len(value) > _MAX_DOCUMENT:
        raise MilestoneCheckpointError("milestone checkpoint exceeds durable size budget")
    return value


def _decode(payload: bytes) -> MilestoneQueue:
    if not isinstance(payload, bytes) or len(payload) > _MAX_DOCUMENT:
        raise MilestoneCheckpointError("oversized or malformed milestone checkpoint")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        data = {}
        for key, value in pairs:
            if key in data:
                raise MilestoneCheckpointError("duplicate serialized milestone field")
            data[key] = value
        return data
    try:
        raw = json.loads(
            payload.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=lambda value: (_ for _ in ()).throw(
                MilestoneCheckpointError("nonfinite checkpoint number")
            ),
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise MilestoneCheckpointError("invalid serialized milestone queue") from exc
    if (not isinstance(raw, dict) or set(raw) != {"schema", "queue"}
            or raw["schema"] != SCHEMA or not isinstance(raw["queue"], dict)):
        raise MilestoneCheckpointError("unknown milestone checkpoint schema")
    q = raw["queue"]
    if set(q) != {x.name for x in fields(MilestoneQueue)}:
        raise MilestoneCheckpointError("queue checkpoint fields changed")
    br = q["board"]
    if not isinstance(br, dict) or set(br) != {x.name for x in fields(MilestoneBoard)}:
        raise MilestoneCheckpointError("board checkpoint fields changed")
    if not isinstance(br["receipts"], list):
        raise MilestoneCheckpointError("board receipts require a list")
    receipts = []
    for row in br["receipts"]:
        if not isinstance(row, dict):
            raise MilestoneCheckpointError("invalid approval receipt")
        entry = dict(row)
        entry["attestation"] = _record(MilestoneAttestation, entry.get("attestation"))
        receipts.append(_record(MilestoneReceipt, entry))
    board = _record(MilestoneBoard, {
        "source_commit": br["source_commit"],
        "receipts": tuple(receipts),
    })
    if not isinstance(q["work"], list) or not isinstance(q["events"], list):
        raise MilestoneCheckpointError("work and event journal must be lists")
    work = tuple(_record(WorkItem, item) for item in q["work"])
    events = tuple(_record(QueueEvent, item) for item in q["events"])
    queue = _record(MilestoneQueue, {
        "source_commit": q["source_commit"],
        "artifact_digest": q["artifact_digest"],
        "max_attempts": q["max_attempts"],
        "lease_seconds": q["lease_seconds"],
        "board": board,
        "work": work,
        "events": events,
    })
    verify_queue(queue)
    if _encode(queue) != payload:
        raise MilestoneCheckpointError("checkpoint is not canonical or exact-replay stable")
    return queue


class SQLiteMilestoneQueueStore:
    """Durable source-scoped queue snapshots with compare-and-swap generation."""

    def __init__(self, path: str | Path, *, namespace: str = "default") -> None:
        if not isinstance(namespace, str) or not _KEY.fullmatch(namespace):
            raise MilestoneCheckpointError("invalid checkpoint namespace")
        self.namespace = namespace
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            self.path, timeout=15, check_same_thread=False, isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout=15000")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS milestone_queue_checkpoint (
                namespace TEXT NOT NULL,
                run_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                source_commit TEXT NOT NULL,
                artifact_digest TEXT NOT NULL,
                queue_fingerprint TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                payload BLOB NOT NULL,
                PRIMARY KEY(namespace, run_id)
            );
            CREATE TABLE IF NOT EXISTS milestone_queue_history (
                namespace TEXT NOT NULL,
                run_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                source_commit TEXT NOT NULL,
                artifact_digest TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                queue_fingerprint TEXT NOT NULL,
                previous_digest TEXT NOT NULL,
                receipt_digest TEXT NOT NULL,
                PRIMARY KEY(namespace, run_id, generation)
            );
            CREATE TABLE IF NOT EXISTS milestone_queue_control (
                namespace TEXT NOT NULL,
                run_id TEXT NOT NULL,
                source_commit TEXT NOT NULL,
                artifact_digest TEXT NOT NULL,
                mode TEXT NOT NULL,
                generation INTEGER NOT NULL,
                actor_ref TEXT NOT NULL,
                reason_ref TEXT NOT NULL,
                receipt_digest TEXT NOT NULL,
                PRIMARY KEY(namespace, run_id)
            );
        """)

    def _open(self) -> None:
        if self._closed:
            raise MilestoneCheckpointError("checkpoint store is closed")

    @staticmethod
    def _key(run_id: str) -> str:
        if not isinstance(run_id, str) or not _KEY.fullmatch(run_id):
            raise MilestoneCheckpointError("invalid checkpoint run identity")
        return run_id

    @staticmethod
    def _history_digest(
        namespace: str, run_id: str, generation: int,
        source_commit: str, artifact_digest: str,
        payload_sha256: str, queue_fingerprint: str,
        previous_digest: str,
    ) -> str:
        return hashlib.sha256(json.dumps({
            "namespace": namespace, "run": run_id, "generation": generation,
            "source": source_commit, "artifact": artifact_digest,
            "payload": payload_sha256, "queue": queue_fingerprint,
            "previous": previous_digest,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _verify_history(self, key: str, latest: sqlite3.Row | None) -> str:
        """Replay every generation and ensure the head matches current state.

        Must be called under an active SQLite transaction to prevent
        cross-process torn reads between history and checkpoint snapshots.
        """
        rows = self._connection.execute(
            """
            SELECT * FROM milestone_queue_history
            WHERE namespace=? AND run_id=?
            ORDER BY generation ASC
            """, (self.namespace, key),
        ).fetchall()
        if (latest is None) != (not rows):
            raise MilestoneCheckpointError("checkpoint generation history is incomplete")
        previous = "0" * 64
        for sequence, item in enumerate(rows, 1):
            if (type(item["generation"]) is not int
                    or item["generation"] != sequence
                    or item["previous_digest"] != previous):
                raise MilestoneCheckpointError("checkpoint generation history is reordered")
            receipt = self._history_digest(
                self.namespace, key, sequence,
                item["source_commit"], item["artifact_digest"],
                item["payload_sha256"], item["queue_fingerprint"], previous,
            )
            if item["receipt_digest"] != receipt:
                raise MilestoneCheckpointError("checkpoint generation receipt was altered")
            previous = receipt
        if latest is not None:
            last = rows[-1]
            if any(last[column] != latest[column] for column in (
                "generation", "source_commit", "artifact_digest",
                "payload_sha256", "queue_fingerprint",
            )):
                raise MilestoneCheckpointError("checkpoint latest state does not match history")
        return previous

    def _append_history(
        self, key: str, generation: int, queue: MilestoneQueue,
        payload_sha: str, previous: str,
    ) -> None:
        receipt = self._history_digest(
            self.namespace, key, generation,
            queue.source_commit, queue.artifact_digest,
            payload_sha, queue.fingerprint, previous,
        )
        self._connection.execute(
            """
            INSERT INTO milestone_queue_history (
                namespace, run_id, generation, source_commit, artifact_digest,
                payload_sha256, queue_fingerprint, previous_digest, receipt_digest
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                self.namespace, key, generation, queue.source_commit,
                queue.artifact_digest, payload_sha, queue.fingerprint,
                previous, receipt,
            ),
        )

    def _control_receipt(
        self, run_id: str, source: str, artifact: str,
        mode: str, generation: int, actor: str, reason: str,
    ) -> str:
        return hashlib.sha256(json.dumps({
            "namespace": self.namespace, "run": run_id,
            "source": source, "artifact": artifact,
            "mode": mode, "generation": generation,
            "actor": actor, "reason": reason,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _control_from_row(self, row: sqlite3.Row) -> StoredMilestoneControl:
        mode, gen = row["mode"], row["generation"]
        if (mode not in {"running", "paused", "cancelled"}
                or type(gen) is not int or gen <= 0
                or not isinstance(row["actor_ref"], str)
                or not _KEY.fullmatch(row["actor_ref"])
                or not isinstance(row["reason_ref"], str)
                or not _KEY.fullmatch(row["reason_ref"])):
            raise MilestoneCheckpointError("invalid durable operator-control record")
        expected = self._control_receipt(
            row["run_id"], row["source_commit"], row["artifact_digest"],
            mode, gen, row["actor_ref"], row["reason_ref"],
        )
        if expected != row["receipt_digest"]:
            raise MilestoneCheckpointError("durable operator control was altered")
        return StoredMilestoneControl(
            row["run_id"], row["source_commit"], row["artifact_digest"],
            mode, gen, row["actor_ref"], row["reason_ref"], expected,
        )

    def _read_control(self, key: str) -> StoredMilestoneControl | None:
        row = self._connection.execute(
            """
            SELECT * FROM milestone_queue_control
            WHERE namespace=? AND run_id=?
            """, (self.namespace, key),
        ).fetchone()
        return self._control_from_row(row) if row is not None else None

    def operator_control(
        self, run_id: str, *, source_commit: str,
        artifact_digest: str,
    ) -> StoredMilestoneControl | None:
        """Read the source-bound, durable operator override if one exists."""
        key = self._key(run_id)
        with self._lock:
            self._open()
            self._connection.execute("BEGIN")
            try:
                row = self._connection.execute(
                    """
                    SELECT source_commit, artifact_digest
                    FROM milestone_queue_checkpoint
                    WHERE namespace=? AND run_id=?
                    """, (self.namespace, key),
                ).fetchone()
                if row is None:
                    raise MilestoneCheckpointError("operator control requires initialized queue")
                if (row["source_commit"] != source_commit
                        or row["artifact_digest"] != artifact_digest):
                    raise MilestoneCheckpointError("operator control source mismatch")
                record = self._read_control(key)
                if record is not None and (
                    record.source_commit != source_commit
                    or record.artifact_digest != artifact_digest
                ):
                    raise MilestoneCheckpointError("operator control has foreign source")
                self._connection.execute("COMMIT")
                return record
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def set_operator_control(
        self, run_id: str, *, source_commit: str, artifact_digest: str,
        mode: str, actor_ref: str, reason_ref: str,
        expected_generation: int | None = None,
    ) -> StoredMilestoneControl:
        """Explicit host action: pause, resume, or irreversibly cancel a run.

        Authorization of the host operator remains the caller's responsibility.
        All modifications require the pinned source and optimistic generation.
        The cancelled mode is terminal and may not silently resume.
        """
        key = self._key(run_id)
        if not isinstance(mode, str) or mode not in {"running", "paused", "cancelled"}:
            raise MilestoneCheckpointError("unknown operator control mode")
        if (not isinstance(actor_ref, str) or not _KEY.fullmatch(actor_ref)
                or not isinstance(reason_ref, str)
                or not _KEY.fullmatch(reason_ref)):
            raise MilestoneCheckpointError("operator action needs scoped actor and reason refs")
        if expected_generation is not None and (
            type(expected_generation) is not int or expected_generation <= 0
        ):
            raise MilestoneCheckpointError("operator generation must be positive")
        with self._lock:
            self._open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                state = self._connection.execute(
                    """
                    SELECT source_commit, artifact_digest
                    FROM milestone_queue_checkpoint
                    WHERE namespace=? AND run_id=?
                    """, (self.namespace, key),
                ).fetchone()
                if state is None or (
                    state["source_commit"] != source_commit
                    or state["artifact_digest"] != artifact_digest
                ):
                    raise MilestoneCheckpointError("operator control needs exact queue source")
                previous = self._read_control(key)
                if previous is None:
                    if expected_generation is not None:
                        raise MilestoneCheckpointConflict("operator control has no prior generation")
                    generation = 1
                else:
                    if (previous.source_commit != source_commit
                            or previous.artifact_digest != artifact_digest):
                        raise MilestoneCheckpointError("operator control source mismatch")
                    if (previous.mode == mode and previous.actor_ref == actor_ref
                            and previous.reason_ref == reason_ref):
                        self._connection.execute("COMMIT")
                        return previous
                    if previous.mode == "cancelled":
                        raise MilestoneCheckpointError("cancelled work may not resume")
                    if previous.generation != expected_generation:
                        raise MilestoneCheckpointConflict("operator control changed since last read")
                    generation = previous.generation + 1
                receipt = self._control_receipt(
                    key, source_commit, artifact_digest, mode,
                    generation, actor_ref, reason_ref,
                )
                if previous is None:
                    self._connection.execute(
                        """
                        INSERT INTO milestone_queue_control
                        (namespace,run_id,source_commit,artifact_digest,
                         mode,generation,actor_ref,reason_ref,receipt_digest)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (self.namespace,key,source_commit,artifact_digest,
                         mode,generation,actor_ref,reason_ref,receipt),
                    )
                else:
                    self._connection.execute(
                        """
                        UPDATE milestone_queue_control
                        SET mode=?,generation=?,actor_ref=?,reason_ref=?,receipt_digest=?
                        WHERE namespace=? AND run_id=? AND generation=?
                        """,
                        (mode,generation,actor_ref,reason_ref,receipt,
                         self.namespace,key,previous.generation),
                    )
                self._connection.execute("COMMIT")
                return StoredMilestoneControl(
                    key, source_commit, artifact_digest, mode,
                    generation, actor_ref, reason_ref, receipt,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def save(
        self, run_id: str, queue: MilestoneQueue,
        *, expected_fingerprint: str | None = None,
    ) -> StoredMilestoneQueue:
        """Atomically advance a snapshot if its previously-read state matches.

        The first save permits no expected fingerprint. Subsequent changed
        saves require the *exact* old fingerprint or fail without mutation.
        Repeating the exact same payload is idempotent.
        """
        key = self._key(run_id)
        payload = _encode(queue)
        payload_sha = hashlib.sha256(payload).hexdigest()
        digest = queue.fingerprint
        with self._lock:
            self._open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                old = self._connection.execute(
                    """
                    SELECT generation, source_commit, artifact_digest,
                           queue_fingerprint, payload_sha256, payload
                    FROM milestone_queue_checkpoint
                    WHERE namespace=? AND run_id=?
                    """, (self.namespace, key),
                ).fetchone()
                previous_receipt = self._verify_history(key, old)
                operator = self._read_control(key)
                if operator is not None and (
                    operator.source_commit != queue.source_commit
                    or operator.artifact_digest != queue.artifact_digest
                ):
                    raise MilestoneCheckpointError("operator control source has drifted")
                if old is not None and operator is not None:
                    if (old["payload_sha256"] != payload_sha
                            or old["queue_fingerprint"] != digest):
                        if operator.mode == "cancelled":
                            raise MilestoneCheckpointError("cancelled queue cannot advance")
                        if operator.mode == "paused":
                            old_queue = _decode(old["payload"])
                            if any(
                                event.action == "claim"
                                for event in queue.events[len(old_queue.events):]
                            ):
                                raise MilestoneCheckpointError("paused queue cannot claim work")
                if old is not None:
                    # Do not trust a stored fingerprint without authenticating
                    # the actual saved bytes and re-validating the chain.
                    stored_payload = old["payload"]
                    if (not isinstance(stored_payload, bytes)
                            or hashlib.sha256(stored_payload).hexdigest()
                            != old["payload_sha256"]):
                        raise MilestoneCheckpointError("persisted checkpoint was corrupted")
                    if _decode(stored_payload).fingerprint != old["queue_fingerprint"]:
                        raise MilestoneCheckpointError("checkpoint fingerprint was corrupted")
                if old is None:
                    if expected_fingerprint is not None:
                        raise MilestoneCheckpointConflict("checkpoint missing for expected state")
                    generation = 1
                    self._connection.execute(
                        """
                        INSERT INTO milestone_queue_checkpoint
                        (namespace,run_id,generation,source_commit,artifact_digest,
                         queue_fingerprint,payload_sha256,payload)
                        VALUES (?,?,?,?,?,?,?,?)
                        """,
                        (self.namespace, key, generation, queue.source_commit,
                         queue.artifact_digest, digest, payload_sha, payload),
                    )
                    self._append_history(key, generation, queue, payload_sha, previous_receipt)
                else:
                    if (old["source_commit"] != queue.source_commit
                            or old["artifact_digest"] != queue.artifact_digest):
                        raise MilestoneCheckpointConflict("checkpoint source binding changed")
                    if old["queue_fingerprint"] == digest and old["payload_sha256"] == payload_sha:
                        generation = old["generation"]
                    else:
                        if expected_fingerprint != old["queue_fingerprint"]:
                            raise MilestoneCheckpointConflict("checkpoint changed since last read")
                        generation = old["generation"] + 1
                        if generation > 9_000_000_000_000_000_000:
                            raise MilestoneCheckpointError("checkpoint generation overflow")
                        self._connection.execute(
                            """
                            UPDATE milestone_queue_checkpoint
                            SET generation=?, queue_fingerprint=?, payload_sha256=?, payload=?
                            WHERE namespace=? AND run_id=? AND generation=?
                            """,
                            (generation, digest, payload_sha, payload,
                             self.namespace, key, old["generation"]),
                        )
                        self._append_history(
                            key, generation, queue, payload_sha, previous_receipt,
                        )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return StoredMilestoneQueue(key, generation, queue, payload_sha)

    def load(
        self, run_id: str, *, source_commit: str,
        artifact_digest: str,
    ) -> StoredMilestoneQueue | None:
        key = self._key(run_id)
        with self._lock:
            self._open()
            self._connection.execute("BEGIN")
            try:
                row = self._connection.execute(
                    """
                    SELECT *
                    FROM milestone_queue_checkpoint
                    WHERE namespace=? AND run_id=?
                    """, (self.namespace, key),
                ).fetchone()
                self._verify_history(key, row)
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        if row is None:
            return None
        if (row["source_commit"] != source_commit
                or row["artifact_digest"] != artifact_digest):
            raise MilestoneCheckpointError("checkpoint belongs to another source snapshot")
        payload = row["payload"]
        if not isinstance(payload, bytes):
            raise MilestoneCheckpointError("persisted milestone payload is not bytes")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != row["payload_sha256"]:
            raise MilestoneCheckpointError("stored checkpoint content hash mismatch")
        queue = _decode(payload)
        restore_queue(queue, source_commit, artifact_digest)
        if queue.fingerprint != row["queue_fingerprint"]:
            raise MilestoneCheckpointError("stored checkpoint does not match verified queue")
        generation = row["generation"]
        if type(generation) is not int or generation < 1:
            raise MilestoneCheckpointError("invalid persisted checkpoint generation")
        return StoredMilestoneQueue(key, generation, queue, digest)

    def checkpoint_history(self, run_id: str) -> tuple[dict[str, object], ...]:
        """Export content-free, validated generation receipts for audit."""
        key = self._key(run_id)
        with self._lock:
            self._open()
            self._connection.execute("BEGIN")
            try:
                current = self._connection.execute(
                    """
                    SELECT * FROM milestone_queue_checkpoint
                    WHERE namespace=? AND run_id=?
                    """, (self.namespace, key),
                ).fetchone()
                self._verify_history(key, current)
                rows = self._connection.execute(
                    """
                    SELECT generation, payload_sha256, queue_fingerprint,
                           previous_digest, receipt_digest
                    FROM milestone_queue_history
                    WHERE namespace=? AND run_id=? ORDER BY generation
                    """, (self.namespace, key),
                ).fetchall()
                result = tuple({
                    "generation": item["generation"],
                    "payload_sha256": item["payload_sha256"],
                    "queue_fingerprint": item["queue_fingerprint"],
                    "previous_digest": item["previous_digest"],
                    "receipt_digest": item["receipt_digest"],
                } for item in rows)
                self._connection.execute("COMMIT")
                return result
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> "SQLiteMilestoneQueueStore":
        self._open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
