"""Durable SQLite lifecycle for candidate/shadow/active model weights.

Writes are single-transaction, revision-checked and append audit-chain events.
No background worker or silent promotion: a separately authenticated native
runtime admission must consume an eligible promotion permit explicitly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .flgb_training_runtime import CandidateWeights, MirrorEvaluation, PromotionEvidence, digest_json, require_digest, require_id
from .shadow_weights import (
    ShadowAssessment, ShadowPromotionPermit, ShadowWeightBatch,
    ShadowWeightError, ShadowWeightPolicy, SourceAttestation,
    authorize_shadow_promotion,
)

_SCHEMA_VERSION = 1
_STATES = frozenset({"shadow", "eligible", "active", "retired", "quarantined", "rejected"})
_GENESIS = "0" * 64


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _encode(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ShadowWeightError("shadow ledger payload is not canonical JSON") from exc


def _batch_data(batch: ShadowWeightBatch) -> dict[str, object]:
    return {
        "candidate": asdict(batch.candidate),
        "sources": [source.as_dict() for source in batch.sources],
    }


def _decode_batch(raw: str) -> ShadowWeightBatch:
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"candidate", "sources"}:
        raise ShadowWeightError("invalid persisted shadow batch")
    return ShadowWeightBatch(
        CandidateWeights(**data["candidate"]),
        tuple(SourceAttestation(**row) for row in data["sources"]),
    )


@dataclass(frozen=True, slots=True)
class ShadowWeightSnapshot:
    batch: ShadowWeightBatch
    state: str
    revision: int
    assessment: ShadowAssessment | None
    permit: ShadowPromotionPermit | None
    updated_at: str

    def __post_init__(self) -> None:
        if self.state not in _STATES:
            raise ShadowWeightError("invalid persisted shadow state")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ShadowWeightError("invalid shadow revision")
        if self.permit is not None and self.permit.candidate_digest != self.batch.candidate.digest:
            raise ShadowWeightError("persisted permit candidate mismatch")
        if self.assessment is not None and self.assessment.source_manifest_digest != self.batch.source_manifest_digest:
            raise ShadowWeightError("stale source assessment in ledger")
        if self.state in {"eligible", "active"} and self.permit is None:
            raise ShadowWeightError("eligible/active weights require a promotion permit")


class ShadowWeightLedger:
    """Persistent workflow: shadow -> eligible -> active -> retired / rollback.

    One SQLite writer owns each transaction; optimistic revisions prevent stale
    reviewers or simultaneous jobs from overwriting another promotion.
    """

    def __init__(self, path: str | Path, *, initial_model_digest: str) -> None:
        require_digest(initial_model_digest, "initial_model_digest")
        self.path = Path(path)
        if not self.path.parent.is_dir():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS shadow_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shadow_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    batch_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    assessment_json TEXT,
                    permit_json TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shadow_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    previous_state TEXT,
                    state TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    prev_digest TEXT NOT NULL,
                    event_digest TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS shadow_events_candidate
                    ON shadow_events(candidate_id, seq);
            """)
            row = db.execute("SELECT value FROM shadow_meta WHERE key='schema_version'").fetchone()
            if row is None:
                db.execute("INSERT INTO shadow_meta(key,value) VALUES('schema_version',?)", (str(_SCHEMA_VERSION),))
                db.execute("INSERT INTO shadow_meta(key,value) VALUES('root_model_digest',?)", (initial_model_digest,))
                db.execute("INSERT INTO shadow_meta(key,value) VALUES('active_model_digest',?)", (initial_model_digest,))
            elif row[0] != str(_SCHEMA_VERSION):
                raise ShadowWeightError("unsupported shadow ledger schema")

    def _connection(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _atomic(db: sqlite3.Connection) -> None:
        db.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _active(db: sqlite3.Connection) -> str:
        row = db.execute("SELECT value FROM shadow_meta WHERE key='active_model_digest'").fetchone()
        if row is None:
            raise ShadowWeightError("shadow ledger missing active model pointer")
        return require_digest(row[0], "active_model_digest")

    @staticmethod
    def _require_revision(row: sqlite3.Row, revision: int | None) -> None:
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int) or revision != row["revision"]
        ):
            raise ShadowWeightError("stale shadow revision")

    @staticmethod
    def _row(db: sqlite3.Connection, candidate_id: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM shadow_candidates WHERE candidate_id=?", (require_id(candidate_id, "candidate_id"),)
        ).fetchone()
        if row is None:
            raise ShadowWeightError("unknown shadow candidate")
        return row

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> ShadowWeightSnapshot:
        assessment = json.loads(row["assessment_json"]) if row["assessment_json"] else None
        permit = json.loads(row["permit_json"]) if row["permit_json"] else None
        return ShadowWeightSnapshot(
            batch=_decode_batch(row["batch_json"]),
            state=row["state"],
            revision=row["revision"],
            assessment=ShadowAssessment(**assessment) if assessment is not None else None,
            permit=ShadowPromotionPermit(**permit) if permit is not None else None,
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _record_event(
        db: sqlite3.Connection,
        *,
        candidate_id: str,
        action: str,
        revision: int,
        previous_state: str | None,
        state: str,
        payload_digest: str,
        occurred_at: str,
    ) -> str:
        require_id(candidate_id, "candidate_id")
        require_id(action, "event action")
        require_digest(payload_digest, "payload digest")
        prev = db.execute("SELECT event_digest FROM shadow_events ORDER BY seq DESC LIMIT 1").fetchone()
        previous_digest = prev[0] if prev else _GENESIS
        event = {
            "candidate_id": candidate_id,
            "action": action,
            "revision": revision,
            "previous_state": previous_state,
            "state": state,
            "payload_digest": payload_digest,
            "prev_digest": previous_digest,
            "occurred_at": occurred_at,
        }
        digest = digest_json(event)
        db.execute(
            """INSERT INTO shadow_events(
                candidate_id,action,revision,previous_state,state,
                payload_digest,prev_digest,event_digest,occurred_at
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (candidate_id, action, revision, previous_state, state,
             payload_digest, previous_digest, digest, occurred_at),
        )
        return digest

    @property
    def active_model_digest(self) -> str:
        with self._connection() as db:
            return self._active(db)

    def snapshot(self, candidate_id: str) -> ShadowWeightSnapshot:
        with self._connection() as db:
            return self._snapshot(self._row(db, candidate_id))

    def stage(self, batch: ShadowWeightBatch, *, expected_revision: int | None = None) -> ShadowWeightSnapshot:
        if not isinstance(batch, ShadowWeightBatch):
            raise ShadowWeightError("shadow staging requires batch and source attestations")
        now = _utc_now()
        with self._connection() as db:
            self._atomic(db)
            row = db.execute(
                "SELECT * FROM shadow_candidates WHERE candidate_id=?", (batch.candidate.candidate_id,)
            ).fetchone()
            if row is None:
                if expected_revision is not None:
                    raise ShadowWeightError("new candidate cannot carry an expected revision")
                db.execute(
                    """INSERT INTO shadow_candidates(
                        candidate_id,batch_json,state,revision,assessment_json,permit_json,updated_at
                    ) VALUES (?,?, 'shadow',1,NULL,NULL,?)""",
                    (batch.candidate.candidate_id, _encode(_batch_data(batch)), now),
                )
                self._record_event(
                    db, candidate_id=batch.candidate.candidate_id, action="stage", revision=1,
                    previous_state=None, state="shadow", payload_digest=batch.digest, occurred_at=now,
                )
            else:
                self._require_revision(row, expected_revision)
                existing = self._snapshot(row)
                if existing.batch.digest == batch.digest:
                    return existing
                if existing.state not in {"shadow", "quarantined"}:
                    raise ShadowWeightError("reviewed, active or rejected candidate is immutable")
                if existing.batch.candidate.digest != batch.candidate.digest:
                    raise ShadowWeightError("candidate ID is already bound to other weights")
                before = {source.source_id: source for source in existing.batch.sources}
                incoming = {source.source_id: source for source in batch.sources}
                if any(source_id not in incoming or source != incoming[source_id]
                       for source_id, source in before.items()):
                    raise ShadowWeightError("shadow source revisions must be append-only")
                revision = row["revision"] + 1
                db.execute(
                    """UPDATE shadow_candidates SET batch_json=?,state='shadow',revision=?,
                    assessment_json=NULL,permit_json=NULL,updated_at=? WHERE candidate_id=?""",
                    (_encode(_batch_data(batch)), revision, now, batch.candidate.candidate_id),
                )
                self._record_event(
                    db, candidate_id=batch.candidate.candidate_id, action="append-evidence",
                    revision=revision, previous_state=existing.state,
                    state="shadow", payload_digest=batch.digest, occurred_at=now,
                )
            return self._snapshot(self._row(db, batch.candidate.candidate_id))

    def assess(
        self, candidate_id: str, policy: ShadowWeightPolicy, *,
        expected_revision: int | None = None,
    ) -> ShadowAssessment:
        """Persist pre-mirror disposition; review can proceed only on eligible evidence."""
        with self._connection() as db:
            self._atomic(db)
            row = self._row(db, candidate_id)
            self._require_revision(row, expected_revision)
            if row["state"] not in {"shadow", "quarantined"}:
                raise ShadowWeightError("shadow candidate cannot be re-assessed in this state")
            batch = _decode_batch(row["batch_json"])
            assessment = batch.assess(policy)
            state = "shadow" if assessment.eligible_for_mirror else "quarantined"
            revision = row["revision"] + 1
            now = _utc_now()
            db.execute(
                """UPDATE shadow_candidates SET assessment_json=?,permit_json=NULL,
                state=?,revision=?,updated_at=? WHERE candidate_id=?""",
                (_encode(asdict(assessment)), state, revision, now, candidate_id),
            )
            self._record_event(
                db, candidate_id=candidate_id, action="assess", revision=revision,
                previous_state=row["state"], state=state,
                payload_digest=assessment.digest, occurred_at=now,
            )
            return assessment

    def qualify(
        self, candidate_id: str, evaluation: MirrorEvaluation,
        promotion: PromotionEvidence, *, admission_authority: str,
        expected_revision: int,
    ) -> ShadowPromotionPermit:
        with self._connection() as db:
            self._atomic(db)
            row = self._row(db, candidate_id)
            self._require_revision(row, expected_revision)
            if row["state"] != "shadow" or not row["assessment_json"]:
                raise ShadowWeightError("candidate must have qualifying source assessment")
            batch = _decode_batch(row["batch_json"])
            assessment = ShadowAssessment(**json.loads(row["assessment_json"]))
            permit = authorize_shadow_promotion(
                batch, assessment, evaluation, promotion,
                admission_authority=admission_authority,
            )
            revision = row["revision"] + 1
            now = _utc_now()
            db.execute(
                """UPDATE shadow_candidates SET permit_json=?,state='eligible',
                revision=?,updated_at=? WHERE candidate_id=?""",
                (_encode(asdict(permit)), revision, now, candidate_id),
            )
            self._record_event(
                db, candidate_id=candidate_id, action="qualified-mirror-promotion",
                revision=revision, previous_state="shadow", state="eligible",
                payload_digest=permit.digest, occurred_at=now,
            )
            return permit

    def commit_activation(
        self, candidate_id: str, *,
        permit_digest: str, admitted_model_digest: str,
        activation_receipt_digest: str, expected_revision: int,
    ) -> ShadowWeightSnapshot:
        """CAS the active pointer after native runtime has independently loaded weights."""
        for name, value in (
            ("permit_digest", permit_digest), ("admitted_model_digest", admitted_model_digest),
            ("activation_receipt_digest", activation_receipt_digest),
        ):
            require_digest(value, name)
        with self._connection() as db:
            self._atomic(db)
            row = self._row(db, candidate_id)
            self._require_revision(row, expected_revision)
            current = self._active(db)
            snapshot = self._snapshot(row)
            permit = snapshot.permit
            if snapshot.state != "eligible" or permit is None or permit.digest != permit_digest:
                raise ShadowWeightError("candidate lacks current promotion permit")
            if current != permit.base_model_digest:
                raise ShadowWeightError("active weight baseline changed before activation")
            if admitted_model_digest != permit.weights_digest:
                raise ShadowWeightError("actual runtime weights do not match candidate")
            revision = row["revision"] + 1
            now = _utc_now()
            db.execute(
                "UPDATE shadow_meta SET value=? WHERE key='active_model_digest'",
                (admitted_model_digest,),
            )
            db.execute(
                """UPDATE shadow_candidates SET state='retired',revision=revision+1,
                   updated_at=? WHERE state='active' AND candidate_id!=?""",
                (now, candidate_id),
            )
            db.execute(
                """UPDATE shadow_candidates SET state='active',revision=?,updated_at=?
                   WHERE candidate_id=?""",
                (revision, now, candidate_id),
            )
            self._record_event(
                db, candidate_id=candidate_id, action="native-activation",
                revision=revision, previous_state="eligible", state="active",
                payload_digest=activation_receipt_digest, occurred_at=now,
            )
            return self._snapshot(self._row(db, candidate_id))

    def commit_rollback(
        self, candidate_id: str, *, restored_model_digest: str,
        rollback_receipt_digest: str, expected_revision: int,
    ) -> ShadowWeightSnapshot:
        require_digest(restored_model_digest, "restored_model_digest")
        require_digest(rollback_receipt_digest, "rollback_receipt_digest")
        with self._connection() as db:
            self._atomic(db)
            row = self._row(db, candidate_id)
            self._require_revision(row, expected_revision)
            snapshot = self._snapshot(row)
            if snapshot.state != "active" or snapshot.permit is None:
                raise ShadowWeightError("only the active candidate can be rolled back")
            if self._active(db) != snapshot.permit.weights_digest:
                raise ShadowWeightError("active pointer no longer matches candidate")
            if restored_model_digest != snapshot.permit.base_model_digest:
                raise ShadowWeightError("rollback must restore the exact previous model")
            revision = row["revision"] + 1
            now = _utc_now()
            db.execute(
                "UPDATE shadow_meta SET value=? WHERE key='active_model_digest'",
                (restored_model_digest,),
            )
            db.execute(
                """UPDATE shadow_candidates SET state='retired',revision=?,updated_at=?
                    WHERE candidate_id=?""",
                (revision, now, candidate_id),
            )
            self._record_event(
                db, candidate_id=candidate_id, action="native-rollback",
                revision=revision, previous_state="active", state="retired",
                payload_digest=rollback_receipt_digest, occurred_at=now,
            )
            return self._snapshot(self._row(db, candidate_id))

    def events(self, *, after_sequence: int = 0, limit: int = 1000) -> tuple[dict[str, object], ...]:
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
            raise ShadowWeightError("invalid event cursor")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise ShadowWeightError("invalid event page size")
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM shadow_events WHERE seq>? ORDER BY seq LIMIT ?",
                (after_sequence, limit),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def pending(self, *, limit: int = 200) -> tuple[ShadowWeightSnapshot, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise ShadowWeightError("invalid pending page size")
        with self._connection() as db:
            rows = db.execute(
                """SELECT * FROM shadow_candidates WHERE state IN ('shadow','quarantined','eligible')
                   ORDER BY updated_at,candidate_id LIMIT ?""", (limit,),
            ).fetchall()
        return tuple(self._snapshot(row) for row in rows)


__all__ = ["ShadowWeightLedger", "ShadowWeightSnapshot"]
