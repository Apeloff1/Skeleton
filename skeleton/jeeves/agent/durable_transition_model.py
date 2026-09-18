"""Write-ahead durable transition learning for Jeeves.

A periodic model snapshot still has a fatal crash window: an audit can say that a
transition was learned while the process dies before the snapshot reaches disk.
On restart the runtime would possess valid evidence of learning but an older
model, potentially reopening cold-start authority.

``DurableLearnedTransitionModel`` journals every mutation *before* applying it to
memory. Each row binds the exact predecessor model fingerprint. Replay starts
from the deterministic empty model, requires each predecessor root in sequence,
applies the mutation through the normal ``LearnedTransitionModel`` methods, and
validates the resulting root when one was recorded. A crash after journal commit
but before memory mutation is therefore recovered by replay rather than lost.

The journal also fences concurrent writers. A new mutation may follow only the
last durably applied model root; an unapplied predecessor blocks new writes until
recovery replay resolves it. Cross-run workers therefore fail closed instead of
silently forking one global learned model.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .model_based_control import (
    AbstractAction,
    CompactState,
    LearnedTransitionModel,
    TransitionExperience,
    TransitionOutcome,
)
from .types import RiskTier, json_safe, positive_int, require_id, stable_fingerprint, stable_id


_TRANSITION_JOURNAL_SCHEMA = 1
_SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")
_GENESIS_HASH = "0" * 64


class DurableTransitionError(RuntimeError):
    """Raised when durable model history cannot be proven or replayed."""


@dataclass(frozen=True, slots=True)
class TransitionJournalEntry:
    model_id: str
    sequence: int
    event_id: str
    kind: str
    at: float
    previous_hash: str
    payload: Mapping[str, Any]
    event_hash: str
    model_fingerprint_after: str | None

    @property
    def expected_hash(self) -> str:
        return stable_fingerprint(
            {
                "model_id": self.model_id,
                "sequence": self.sequence,
                "event_id": self.event_id,
                "kind": self.kind,
                "at": self.at,
                "previous_hash": self.previous_hash,
                "payload": self.payload,
            }
        )


class SQLiteTransitionJournal:
    """Transactional write-ahead journal for one or more learned models."""

    def __init__(
        self,
        path: str | Path,
        *,
        maximum_payload_bytes: int = 8 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise ValueError("SQLiteTransitionJournal requires durable path")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.maximum_payload_bytes = positive_int(
            "maximum_payload_bytes",
            maximum_payload_bytes,
            maximum=128 * 1024 * 1024,
        )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._init_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _initialize(self) -> None:
        with self._init_lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jeeves_transition_journal (
                        model_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        event_id TEXT NOT NULL UNIQUE,
                        kind TEXT NOT NULL,
                        at REAL NOT NULL,
                        previous_hash TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        event_hash TEXT NOT NULL UNIQUE,
                        model_fingerprint_after TEXT,
                        PRIMARY KEY(model_id, sequence),
                        CHECK(sequence >= 1),
                        CHECK(kind IN ('experience','prediction_error'))
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jeeves_transition_journal_meta (
                        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                        schema_version INTEGER NOT NULL
                    )
                    """
                )
                row = conn.execute(
                    "SELECT schema_version FROM jeeves_transition_journal_meta WHERE singleton=1"
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO jeeves_transition_journal_meta(singleton,schema_version) VALUES(1,?)",
                        (_TRANSITION_JOURNAL_SCHEMA,),
                    )
                elif int(row[0]) != _TRANSITION_JOURNAL_SCHEMA:
                    raise DurableTransitionError(
                        "unsupported transition-journal schema version"
                    )
            finally:
                conn.close()

    def append_pending(
        self,
        model_id: str,
        kind: str,
        payload: Mapping[str, Any],
    ) -> TransitionJournalEntry:
        model_id = self._model_id(model_id)
        if kind not in {"experience", "prediction_error"}:
            raise ValueError("unsupported transition journal event kind")
        clean = json_safe(dict(payload))
        declared_before = self._fingerprint(
            str(clean.get("model_fingerprint_before", ""))
        )
        payload_json = self._encode(clean)
        at = float(self._clock())
        if not math.isfinite(at) or at < 0:
            raise DurableTransitionError("clock returned invalid journal timestamp")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                last = conn.execute(
                    """
                    SELECT sequence,event_hash,at,model_fingerprint_after
                    FROM jeeves_transition_journal
                    WHERE model_id=? ORDER BY sequence DESC LIMIT 1
                    """,
                    (model_id,),
                ).fetchone()
                if last is None:
                    sequence = 1
                    previous_hash = _GENESIS_HASH
                else:
                    if last["model_fingerprint_after"] is None:
                        raise DurableTransitionError(
                            "transition journal has unapplied predecessor; replay recovery required"
                        )
                    durable_before = self._fingerprint(
                        str(last["model_fingerprint_after"])
                    )
                    if declared_before != durable_before:
                        raise DurableTransitionError(
                            "transition journal predecessor model root conflict"
                        )
                    sequence = int(last["sequence"]) + 1
                    previous_hash = str(last["event_hash"])
                    if at + 1e-12 < float(last["at"]):
                        raise DurableTransitionError(
                            "transition journal wall clock moved backwards"
                        )
                event_id = stable_id(
                    "model_event",
                    {
                        "model": model_id,
                        "sequence": sequence,
                        "kind": kind,
                        "previous": previous_hash,
                        "payload": clean,
                    },
                )
                envelope = {
                    "model_id": model_id,
                    "sequence": sequence,
                    "event_id": event_id,
                    "kind": kind,
                    "at": at,
                    "previous_hash": previous_hash,
                    "payload": clean,
                }
                event_hash = stable_fingerprint(envelope)
                conn.execute(
                    """
                    INSERT INTO jeeves_transition_journal(
                        model_id,sequence,event_id,kind,at,previous_hash,
                        payload_json,event_hash,model_fingerprint_after
                    ) VALUES(?,?,?,?,?,?,?,?,NULL)
                    """,
                    (
                        model_id,
                        sequence,
                        event_id,
                        kind,
                        at,
                        previous_hash,
                        payload_json,
                        event_hash,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return TransitionJournalEntry(
            model_id=model_id,
            sequence=sequence,
            event_id=event_id,
            kind=kind,
            at=at,
            previous_hash=previous_hash,
            payload=clean,
            event_hash=event_hash,
            model_fingerprint_after=None,
        )

    def mark_applied(
        self,
        model_id: str,
        sequence: int,
        model_fingerprint_after: str,
    ) -> None:
        model_id = self._model_id(model_id)
        fingerprint = self._fingerprint(model_fingerprint_after)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT model_fingerprint_after FROM jeeves_transition_journal
                    WHERE model_id=? AND sequence=?
                    """,
                    (model_id, sequence),
                ).fetchone()
                if row is None:
                    raise DurableTransitionError("unknown transition journal sequence")
                prior = row[0]
                if prior is not None and str(prior) != fingerprint:
                    raise DurableTransitionError(
                        "transition journal sequence already committed to different model root"
                    )
                conn.execute(
                    """
                    UPDATE jeeves_transition_journal
                    SET model_fingerprint_after=?
                    WHERE model_id=? AND sequence=?
                    """,
                    (fingerprint, model_id, sequence),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def entries(self, model_id: str) -> tuple[TransitionJournalEntry, ...]:
        model_id = self._model_id(model_id)
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM jeeves_transition_journal
                WHERE model_id=? ORDER BY sequence ASC
                """,
                (model_id,),
            ).fetchall()
        finally:
            conn.close()
        return tuple(self._entry(row) for row in rows)

    def verify(self, model_id: str) -> tuple[TransitionJournalEntry, ...]:
        entries = self.entries(model_id)
        previous = _GENESIS_HASH
        last_at = -1.0
        for expected_sequence, entry in enumerate(entries, start=1):
            if entry.sequence != expected_sequence:
                raise DurableTransitionError("transition journal sequence gap")
            if entry.previous_hash != previous:
                raise DurableTransitionError("transition journal previous hash mismatch")
            if entry.expected_hash != entry.event_hash:
                raise DurableTransitionError("transition journal event hash mismatch")
            if entry.at + 1e-12 < last_at:
                raise DurableTransitionError("transition journal time regression")
            previous = entry.event_hash
            last_at = entry.at
        return entries

    def _encode(self, payload: Any) -> str:
        text = json.dumps(
            json_safe(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(text.encode("utf-8")) > self.maximum_payload_bytes:
            raise DurableTransitionError("transition journal payload exceeds bound")
        return text

    @staticmethod
    def _entry(row: sqlite3.Row) -> TransitionJournalEntry:
        return TransitionJournalEntry(
            model_id=str(row["model_id"]),
            sequence=int(row["sequence"]),
            event_id=str(row["event_id"]),
            kind=str(row["kind"]),
            at=float(row["at"]),
            previous_hash=str(row["previous_hash"]),
            payload=json.loads(str(row["payload_json"])),
            event_hash=str(row["event_hash"]),
            model_fingerprint_after=(
                None
                if row["model_fingerprint_after"] is None
                else str(row["model_fingerprint_after"])
            ),
        )

    @staticmethod
    def _model_id(value: str) -> str:
        value = require_id("model_id", value)
        if not _SAFE_MODEL_ID.fullmatch(value):
            raise ValueError("model_id must contain safe identifier characters")
        return value

    @staticmethod
    def _fingerprint(value: str) -> str:
        normalized = str(value).strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise DurableTransitionError("model fingerprint must be sha256 hex")
        return normalized


class DurableLearnedTransitionModel(LearnedTransitionModel):
    """Learned transition model reconstructed entirely from a durable WAL."""

    def __init__(
        self,
        journal: SQLiteTransitionJournal,
        *,
        model_id: str = "jeeves-frontier-global",
        max_experiences: int = 1_000_000,
        restore: bool = True,
    ) -> None:
        if not isinstance(journal, SQLiteTransitionJournal):
            raise TypeError("journal must be SQLiteTransitionJournal")
        super().__init__(max_experiences=max_experiences)
        self.journal = journal
        self.model_id = journal._model_id(model_id)
        self._journal_lock = threading.RLock()
        if restore:
            self.replay_journal()

    def observe(self, experience: TransitionExperience) -> None:
        if not isinstance(experience, TransitionExperience):
            raise TypeError("experience must be TransitionExperience")
        with self._journal_lock:
            before = self.fingerprint
            entry = self.journal.append_pending(
                self.model_id,
                "experience",
                {
                    "model_fingerprint_before": before,
                    "experience": self._experience_to_dict(experience),
                },
            )
            super().observe(experience)
            after = self.fingerprint
            self.journal.mark_applied(self.model_id, entry.sequence, after)

    def record_prediction_error(
        self,
        state_id: str,
        action_id: str,
        *,
        predicted_next: str,
        actual_next: str,
    ) -> None:
        with self._journal_lock:
            before = self.fingerprint
            entry = self.journal.append_pending(
                self.model_id,
                "prediction_error",
                {
                    "model_fingerprint_before": before,
                    "state_id": state_id,
                    "action_id": action_id,
                    "predicted_next": predicted_next,
                    "actual_next": actual_next,
                },
            )
            super().record_prediction_error(
                state_id,
                action_id,
                predicted_next=predicted_next,
                actual_next=actual_next,
            )
            after = self.fingerprint
            self.journal.mark_applied(self.model_id, entry.sequence, after)

    def replay_journal(self) -> int:
        """Rebuild this model from genesis and durable events.

        Replay is intentionally only valid on an empty model. A caller that
        wants a fresh reconstruction creates a new instance; replaying over
        live state would duplicate observations.
        """

        with self._journal_lock:
            if self._cells or self._states or self._actions:
                raise DurableTransitionError("journal replay requires empty model")
            entries = self.journal.verify(self.model_id)
            applied = 0
            for entry in entries:
                before = entry.payload.get("model_fingerprint_before")
                if before != self.fingerprint:
                    raise DurableTransitionError(
                        f"transition predecessor model root mismatch at sequence {entry.sequence}"
                    )
                if entry.kind == "experience":
                    experience = self._experience_from_dict(entry.payload["experience"])
                    super().observe(experience)
                elif entry.kind == "prediction_error":
                    super().record_prediction_error(
                        str(entry.payload["state_id"]),
                        str(entry.payload["action_id"]),
                        predicted_next=str(entry.payload["predicted_next"]),
                        actual_next=str(entry.payload["actual_next"]),
                    )
                else:  # pragma: no cover - table CHECK plus parser protects this.
                    raise DurableTransitionError("unknown transition journal event")
                after = self.fingerprint
                if (
                    entry.model_fingerprint_after is not None
                    and entry.model_fingerprint_after != after
                ):
                    raise DurableTransitionError(
                        f"transition resulting model root mismatch at sequence {entry.sequence}"
                    )
                if entry.model_fingerprint_after is None:
                    self.journal.mark_applied(self.model_id, entry.sequence, after)
                applied += 1
            return applied

    @staticmethod
    def _state_to_dict(state: CompactState) -> Mapping[str, Any]:
        return {
            "state_id": state.state_id,
            "features": dict(state.features),
            "progress_bucket": state.progress_bucket,
            "uncertainty_bucket": state.uncertainty_bucket,
            "budget_bucket": state.budget_bucket,
            "failure_bucket": state.failure_bucket,
            "risk": state.risk.value,
            "terminal": state.terminal,
            "metadata": dict(state.metadata),
        }

    @staticmethod
    def _state_from_dict(raw: Mapping[str, Any]) -> CompactState:
        return CompactState(
            state_id=str(raw["state_id"]),
            features=dict(raw["features"]),
            progress_bucket=int(raw["progress_bucket"]),
            uncertainty_bucket=int(raw["uncertainty_bucket"]),
            budget_bucket=int(raw["budget_bucket"]),
            failure_bucket=int(raw["failure_bucket"]),
            risk=RiskTier(str(raw["risk"])),
            terminal=bool(raw["terminal"]),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _action_to_dict(action: AbstractAction) -> Mapping[str, Any]:
        return {
            "action_id": action.action_id,
            "name": action.name,
            "capability": action.capability,
            "risk": action.risk.value,
            "option_id": action.option_id,
            "estimated_external_cost": action.estimated_external_cost,
            "reversible": action.reversible,
            "metadata": dict(action.metadata),
        }

    @staticmethod
    def _action_from_dict(raw: Mapping[str, Any]) -> AbstractAction:
        return AbstractAction(
            action_id=str(raw["action_id"]),
            name=str(raw["name"]),
            capability=str(raw["capability"]),
            risk=RiskTier(str(raw["risk"])),
            option_id=raw.get("option_id"),
            estimated_external_cost=float(raw.get("estimated_external_cost", 0.0)),
            reversible=bool(raw.get("reversible", True)),
            metadata=dict(raw.get("metadata", {})),
        )

    @classmethod
    def _experience_to_dict(cls, experience: TransitionExperience) -> Mapping[str, Any]:
        return {
            "experience_id": experience.experience_id,
            "run_id": experience.run_id,
            "state": cls._state_to_dict(experience.state),
            "action": cls._action_to_dict(experience.action),
            "next_state": cls._state_to_dict(experience.next_state),
            "outcome": experience.outcome.value,
            "reward": experience.reward,
            "verification_score": experience.verification_score,
            "cost": experience.cost,
            "latency_ms": experience.latency_ms,
            "observed_at": experience.observed_at,
            "evidence_ids": list(experience.evidence_ids),
            "metadata": dict(experience.metadata),
        }

    @classmethod
    def _experience_from_dict(cls, raw: Mapping[str, Any]) -> TransitionExperience:
        return TransitionExperience(
            experience_id=str(raw["experience_id"]),
            run_id=str(raw["run_id"]),
            state=cls._state_from_dict(raw["state"]),
            action=cls._action_from_dict(raw["action"]),
            next_state=cls._state_from_dict(raw["next_state"]),
            outcome=TransitionOutcome(str(raw["outcome"])),
            reward=float(raw["reward"]),
            verification_score=float(raw["verification_score"]),
            cost=float(raw.get("cost", 0.0)),
            latency_ms=float(raw.get("latency_ms", 0.0)),
            observed_at=float(raw["observed_at"]),
            evidence_ids=tuple(raw.get("evidence_ids", ())),
            metadata=dict(raw.get("metadata", {})),
        )