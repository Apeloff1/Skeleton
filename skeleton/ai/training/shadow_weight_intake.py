"""Pre-training shadow knowledge intake, deduplication and idle-only leasing.

Incoming Dragon/crawler knowledge belongs in a *shadow evidence queue*, not
in durable tensor weights. A bounded independent-origin qualification decides
which observations may enter a training batch. No intake decision authorizes
model promotion; every trained candidate must still pass the mirror, rights
and native admission chain.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .flgb_training_runtime import CandidateWeights, digest_json, require_digest, require_id
from .shadow_weights import (
    ShadowWeightError, ShadowWeightPolicy, SourceAttestation,
    independent_evidence_roots, _count, _utc,
)

_MAX_INTAKE_SOURCES = 10_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True, slots=True)
class ShadowKnowledge:
    knowledge_id: str
    content_digest: str
    base_model_digest: str
    topic: str
    relevance_ppm: int
    predicted_gain_ppm: int
    observed_at: str
    sources: tuple[SourceAttestation, ...]

    def __post_init__(self) -> None:
        require_id(self.knowledge_id, "knowledge_id")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.base_model_digest, "base_model_digest")
        require_id(self.topic, "topic")
        _count("relevance_ppm", self.relevance_ppm)
        _count("predicted_gain_ppm", self.predicted_gain_ppm)
        _utc("observed_at", self.observed_at)
        if not self.sources or len(self.sources) > _MAX_INTAKE_SOURCES:
            raise ShadowWeightError("intake source count out of bounds")
        if any(not isinstance(x, SourceAttestation) for x in self.sources):
            raise ShadowWeightError("intake sources must be provenance attestations")
        ids = [x.source_id for x in self.sources]
        if len(set(ids)) != len(ids):
            raise ShadowWeightError("duplicated intake source identity")
        object.__setattr__(self, "sources", tuple(sorted(self.sources, key=lambda x: x.source_id)))

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "knowledge_id": self.knowledge_id,
            "content_digest": self.content_digest,
            "base_model_digest": self.base_model_digest,
            "topic": self.topic,
            "relevance_ppm": self.relevance_ppm,
            "predicted_gain_ppm": self.predicted_gain_ppm,
            "observed_at": self.observed_at,
            "sources": [x.as_dict() for x in self.sources],
        }

    @classmethod
    def from_dict(cls, record: dict[str, object]) -> "ShadowKnowledge":
        fields = dict(record)
        sources = fields.pop("sources")
        return cls(**fields, sources=tuple(SourceAttestation(**x) for x in sources))


@dataclass(frozen=True, slots=True)
class ShadowIntakePolicy:
    evidence: ShadowWeightPolicy = ShadowWeightPolicy()
    minimum_relevance_ppm: int = 650_000
    minimum_predicted_gain_ppm: int = 600_000
    max_pending: int = 50_000

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, ShadowWeightPolicy):
            raise ShadowWeightError("intake must carry a shadow evidence policy")
        _count("minimum_relevance_ppm", self.minimum_relevance_ppm)
        _count("minimum_predicted_gain_ppm", self.minimum_predicted_gain_ppm)
        _count("max_pending", self.max_pending, lower=1, upper=1_000_000)

    @property
    def digest(self) -> str:
        return digest_json({
            "evidence_policy_digest": self.evidence.digest,
            "minimum_relevance_ppm": self.minimum_relevance_ppm,
            "minimum_predicted_gain_ppm": self.minimum_predicted_gain_ppm,
            "max_pending": self.max_pending,
        })


@dataclass(frozen=True, slots=True)
class ShadowIntakeAssessment:
    knowledge_digest: str
    policy_digest: str
    independent_roots: int
    reason_codes: tuple[str, ...]
    disposition: str

    def __post_init__(self) -> None:
        require_digest(self.knowledge_digest, "knowledge_digest")
        require_digest(self.policy_digest, "policy_digest")
        _count("independent_roots", self.independent_roots)
        canonical = tuple(self.reason_codes)
        if tuple(sorted(set(canonical))) != canonical:
            raise ShadowWeightError("intake reason codes must be unique and sorted")
        object.__setattr__(self, "reason_codes", canonical)
        if self.disposition not in {"training-ready", "pending", "quarantined"}:
            raise ShadowWeightError("invalid intake disposition")
        if self.disposition == "training-ready" and self.reason_codes:
            raise ShadowWeightError("training-ready intake cannot have unresolved evidence")

    @property
    def digest(self) -> str:
        return digest_json(asdict(self))


def assess_shadow_intake(
    item: ShadowKnowledge, policy: ShadowIntakePolicy,
) -> ShadowIntakeAssessment:
    if not isinstance(item, ShadowKnowledge) or not isinstance(policy, ShadowIntakePolicy):
        raise ShadowWeightError("intake assessment requires knowledge and policy")
    reasons: set[str] = set()
    if len(item.sources) > policy.evidence.maximum_sources:
        reasons.add("source-budget-exceeded")
    if item.relevance_ppm < policy.minimum_relevance_ppm:
        reasons.add("low-task-relevance")
    if item.predicted_gain_ppm < policy.minimum_predicted_gain_ppm:
        reasons.add("low-predicted-gain")
    if any(source.contradiction for source in item.sources):
        reasons.add("unresolved-contradiction")
    if any(not source.allowed_for_training for source in item.sources):
        reasons.add("training-rights-unresolved")
    credible_sources = [
        source for source in item.sources
        if source.allowed_for_training
        and not source.contradiction
        and source.quality_ppm >= policy.evidence.minimum_quality_ppm
    ]
    independent_roots = independent_evidence_roots(credible_sources)
    if len(independent_roots) < policy.evidence.minimum_independent_roots:
        reasons.add("insufficient-independent-evidence")
    if any(source.quality_ppm < policy.evidence.minimum_quality_ppm for source in item.sources):
        reasons.add("low-source-quality")
    blockers = {"unresolved-contradiction", "training-rights-unresolved"}
    disposition = (
        "quarantined" if reasons.intersection(blockers)
        else "pending" if reasons
        else "training-ready"
    )
    return ShadowIntakeAssessment(
        knowledge_digest=item.digest,
        policy_digest=policy.digest,
        independent_roots=len(independent_roots),
        reason_codes=tuple(sorted(reasons)),
        disposition=disposition,
    )


@dataclass(frozen=True, slots=True)
class ShadowIntakeLease:
    knowledge: ShadowKnowledge
    lease_owner: str
    lease_until: str
    revision: int
    assessment_digest: str

    def __post_init__(self) -> None:
        require_id(self.lease_owner, "lease_owner")
        _utc("lease_until", self.lease_until)
        require_digest(self.assessment_digest, "assessment_digest")


class ShadowKnowledgeQueue:
    """SQLite queue with lease fencing, deduplicated content and idle-only work."""

    def __init__(self, database: str | Path, *, policy: ShadowIntakePolicy | None = None) -> None:
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.policy = policy or ShadowIntakePolicy()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS shadow_intake (
                    knowledge_id TEXT PRIMARY KEY,
                    content_digest TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    priority_gain INTEGER NOT NULL,
                    priority_relevance INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    assessment TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_until TEXT,
                    candidate_digest TEXT,
                    updated_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    retry_after TEXT
                );
                CREATE INDEX IF NOT EXISTS shadow_intake_work
                  ON shadow_intake(state,priority_gain DESC,priority_relevance DESC,observed_at,knowledge_id);
                CREATE TABLE IF NOT EXISTS shadow_intake_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_digest TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
            """)
            # Upgrade SQLite queues created before durable retry scheduling.
            columns = {row[1] for row in db.execute("PRAGMA table_info(shadow_intake)")}
            if "attempts" not in columns:
                db.execute(
                    "ALTER TABLE shadow_intake ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
                )
            if "retry_after" not in columns:
                db.execute("ALTER TABLE shadow_intake ADD COLUMN retry_after TEXT")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _event(db: sqlite3.Connection, item: str, action: str, revision: int, digest: str) -> None:
        db.execute(
            """INSERT INTO shadow_intake_events(
                knowledge_id,action,revision,payload_digest,occurred_at
            ) VALUES (?,?,?,?,?)""",
            (item, action, revision, digest, _now().isoformat().replace("+00:00", "Z")),
        )

    def enqueue(self, item: ShadowKnowledge) -> ShadowIntakeAssessment:
        if not isinstance(item, ShadowKnowledge):
            raise ShadowWeightError("knowledge intake payload required")
        assessment = assess_shadow_intake(item, self.policy)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT payload,assessment FROM shadow_intake WHERE knowledge_id=?",
                (item.knowledge_id,),
            ).fetchone()
            if current is not None:
                if json.loads(current["payload"]) != item.as_dict():
                    raise ShadowWeightError("knowledge ID already bound to other shadow content")
                return ShadowIntakeAssessment(**json.loads(current["assessment"]))
            queued = db.execute(
                "SELECT count(*) FROM shadow_intake WHERE state IN ('pending','training-ready','leased')"
            ).fetchone()[0]
            if queued >= self.policy.max_pending:
                raise ShadowWeightError("bounded shadow knowledge queue at capacity")
            duplicate = db.execute(
                "SELECT knowledge_id FROM shadow_intake WHERE content_digest=?",
                (item.content_digest,),
            ).fetchone()
            if duplicate is not None:
                raise ShadowWeightError("knowledge content was previously acquired")
            db.execute(
                """INSERT INTO shadow_intake(
                    knowledge_id,content_digest,payload,priority_gain,priority_relevance,
                    observed_at,state,revision,assessment,lease_owner,lease_until,
                    candidate_digest,updated_at
                ) VALUES (?,?,?,?,?,?,?,1,?,NULL,NULL,NULL,?)""",
                (
                    item.knowledge_id, item.content_digest, _encode(item.as_dict()),
                    item.predicted_gain_ppm, item.relevance_ppm, item.observed_at,
                    assessment.disposition, _encode(asdict(assessment)),
                    _now().isoformat(timespec="microseconds").replace("+00:00", "Z"),
                ),
            )
            self._event(db, item.knowledge_id, "enqueue", 1, assessment.digest)
        return assessment

    def append_evidence(
        self, item: ShadowKnowledge, *, expected_revision: int,
    ) -> ShadowIntakeAssessment:
        """Add corroborating roots without modifying previous attestation history.

        Intake may mature from pending/quarantined to training-ready. Leased
        and trained records are immutable so queued training cannot see a
        different source manifest from the one it acquired.
        """
        if not isinstance(item, ShadowKnowledge):
            raise ShadowWeightError("shadow evidence update requires knowledge payload")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ShadowWeightError("invalid intake expected revision")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM shadow_intake WHERE knowledge_id=?",
                (item.knowledge_id,),
            ).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise ShadowWeightError("unknown or stale intake candidate")
            if row["state"] not in {"pending", "quarantined", "training-ready"} or row["candidate_digest"] is not None:
                raise ShadowWeightError("leased, reserved or trained knowledge is immutable")
            previous = ShadowKnowledge.from_dict(json.loads(row["payload"]))
            if (
                previous.knowledge_id != item.knowledge_id
                or previous.content_digest != item.content_digest
                or previous.base_model_digest != item.base_model_digest
                or previous.topic != item.topic
                or previous.observed_at != item.observed_at
            ):
                raise ShadowWeightError("intake evidence update changed knowledge identity")
            prior = {x.source_id: x for x in previous.sources}
            updated = {x.source_id: x for x in item.sources}
            if any(key not in updated or updated[key] != source for key, source in prior.items()):
                raise ShadowWeightError("shadow intake source history must be append-only")
            assessment = assess_shadow_intake(item, self.policy)
            revision = row["revision"] + 1
            db.execute(
                """UPDATE shadow_intake SET payload=?,priority_gain=?,
                    priority_relevance=?,state=?,assessment=?,revision=?,updated_at=?,
                    attempts=0,retry_after=NULL
                    WHERE knowledge_id=?""",
                (
                    _encode(item.as_dict()), item.predicted_gain_ppm, item.relevance_ppm,
                    assessment.disposition, _encode(asdict(assessment)), revision,
                    _now().isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    item.knowledge_id,
                ),
            )
            self._event(db, item.knowledge_id, "append-source-evidence", revision, assessment.digest)
            return assessment

    def lease(
        self, worker_id: str, *, idle: bool,
        duration_seconds: int = 900,
    ) -> ShadowIntakeLease | None:
        require_id(worker_id, "worker_id")
        if not isinstance(idle, bool):
            raise ShadowWeightError("idle scheduler state must be boolean")
        if not idle:
            return None
        _count("duration_seconds", duration_seconds, lower=15, upper=86_400)
        now = _now()
        now_text = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
        expiry = (now + timedelta(seconds=duration_seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM shadow_intake
                    WHERE (state='training-ready'
                    OR (state='leased' AND lease_until<=?))
                    AND (retry_after IS NULL OR retry_after<=?)
                    ORDER BY priority_gain DESC, priority_relevance DESC,
                             observed_at ASC, knowledge_id ASC LIMIT 1""",
                (now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            revision = row["revision"] + 1
            db.execute(
                """UPDATE shadow_intake SET state='leased',lease_owner=?,lease_until=?,
                    revision=?,updated_at=?,attempts=attempts+1,retry_after=NULL
                    WHERE knowledge_id=?""",
                (worker_id, expiry, revision, now_text, row["knowledge_id"]),
            )
            item = ShadowKnowledge.from_dict(json.loads(row["payload"]))
            assessment = ShadowIntakeAssessment(**json.loads(row["assessment"]))
            self._event(db, row["knowledge_id"], "lease", revision, assessment.digest)
            return ShadowIntakeLease(item, worker_id, expiry, revision, assessment.digest)

    @staticmethod
    def _bound_lease(db: sqlite3.Connection, lease: ShadowIntakeLease) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM shadow_intake WHERE knowledge_id=?",
            (lease.knowledge.knowledge_id,),
        ).fetchone()
        if row is None or row["state"] != "leased" or row["revision"] != lease.revision:
            raise ShadowWeightError("shadow work lease has been revoked or superseded")
        if row["lease_owner"] != lease.lease_owner or row["lease_until"] != lease.lease_until:
            raise ShadowWeightError("shadow work is leased to another worker")
        if row["lease_until"] <= _now().isoformat(timespec="microseconds").replace("+00:00", "Z"):
            raise ShadowWeightError("shadow work lease expired")
        if json.loads(row["payload"]) != lease.knowledge.as_dict():
            raise ShadowWeightError("leased shadow knowledge was changed")
        if ShadowIntakeAssessment(**json.loads(row["assessment"])).digest != lease.assessment_digest:
            raise ShadowWeightError("lease assessment is not current")
        return row

    def renew(
        self, lease: ShadowIntakeLease, *, idle: bool,
        duration_seconds: int = 900,
    ) -> ShadowIntakeLease:
        """Extend a worker's fenced lease while background capacity remains idle.

        The new revision invalidates the previous lease token. A worker must
        hand the returned lease into any subsequent acknowledgement or release.
        An expired lease is never revived by a heartbeat.
        """
        if not isinstance(idle, bool) or not idle:
            raise ShadowWeightError("shadow lease renewal requires idle capacity")
        _count("duration_seconds", duration_seconds, lower=15, upper=86_400)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._bound_lease(db, lease)
            now = _now()
            now_text = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
            expiry = (now + timedelta(seconds=duration_seconds)).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z")
            revision = row["revision"] + 1
            db.execute(
                """UPDATE shadow_intake SET lease_until=?,revision=?,updated_at=?
                    WHERE knowledge_id=?""",
                (expiry, revision, now_text, lease.knowledge.knowledge_id),
            )
            self._event(
                db, lease.knowledge.knowledge_id, "renew-lease",
                revision, lease.assessment_digest,
            )
            return ShadowIntakeLease(
                knowledge=lease.knowledge, lease_owner=lease.lease_owner,
                lease_until=expiry, revision=revision,
                assessment_digest=lease.assessment_digest,
            )

    def quarantine_lease(
        self, lease: ShadowIntakeLease, *, reason_code: str,
    ) -> ShadowIntakeAssessment:
        """Fence out irrecoverably rejected work without discarding provenance.

        Only the lease owner can quarantine its current revision. A later
        append-only evidence revision can requalify it under the same policy.
        """
        require_id(reason_code, "quarantine reason_code")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._bound_lease(db, lease)
            previous = ShadowIntakeAssessment(**json.loads(row["assessment"]))
            assessment = ShadowIntakeAssessment(
                knowledge_digest=lease.knowledge.digest,
                policy_digest=previous.policy_digest,
                independent_roots=previous.independent_roots,
                reason_codes=tuple(sorted(set(previous.reason_codes) | {reason_code})),
                disposition="quarantined",
            )
            revision = row["revision"] + 1
            db.execute(
                """UPDATE shadow_intake SET state='quarantined',
                    assessment=?,lease_owner=NULL,lease_until=NULL,
                    revision=?,updated_at=?,retry_after=NULL WHERE knowledge_id=?""",
                (
                    _encode(asdict(assessment)), revision,
                    _now().isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    lease.knowledge.knowledge_id,
                ),
            )
            self._event(
                db, lease.knowledge.knowledge_id, "worker-quarantine",
                revision, assessment.digest,
            )
            return assessment

    def reserve_candidate(
        self, lease: ShadowIntakeLease, candidate: CandidateWeights,
    ) -> str:
        """Persist one immutable candidate identity before staging other ledgers.

        A crashed worker may re-lease the same observation, but it cannot
        change the candidate digest after the first reservation. This
        provides replay safety across the queue/ledger transaction boundary.
        The lease revision is unchanged: custody identity is a write-once
        property of the existing fenced lease, not a new knowledge revision.
        """
        if not isinstance(candidate, CandidateWeights) or candidate.status != "candidate":
            raise ShadowWeightError("shadow reservation requires unpromoted weights")
        if candidate.base_model_digest != lease.knowledge.base_model_digest:
            raise ShadowWeightError("reserved candidate baseline differs from intake")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._bound_lease(db, lease)
            existing = row["candidate_digest"]
            if existing is not None:
                if existing != candidate.digest:
                    raise ShadowWeightError("shadow knowledge already reserved for other weights")
                return existing
            db.execute(
                """UPDATE shadow_intake SET candidate_digest=?,updated_at=?
                   WHERE knowledge_id=?""",
                (
                    candidate.digest,
                    _now().isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    lease.knowledge.knowledge_id,
                ),
            )
            self._event(
                db, lease.knowledge.knowledge_id, "reserve-trained-candidate",
                row["revision"], candidate.digest,
            )
            return candidate.digest

    def acknowledge(self, lease: ShadowIntakeLease, candidate: CandidateWeights) -> str:
        """Record resulting *candidate* weights, not unreviewed production weights."""
        if not isinstance(candidate, CandidateWeights) or candidate.status != "candidate":
            raise ShadowWeightError("only unpromoted trained candidates may consume intake")
        if candidate.base_model_digest != lease.knowledge.base_model_digest:
            raise ShadowWeightError("trained candidate baseline differs from intake")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._bound_lease(db, lease)
            if row["candidate_digest"] not in (None, candidate.digest):
                raise ShadowWeightError("acknowledgement differs from reserved candidate")
            revision = row["revision"] + 1
            db.execute(
                """UPDATE shadow_intake SET state='trained',candidate_digest=?,
                    lease_owner=NULL,lease_until=NULL,revision=?,updated_at=?
                    WHERE knowledge_id=?""",
                (
                    candidate.digest, revision, _now().isoformat().replace("+00:00", "Z"),
                    lease.knowledge.knowledge_id,
                ),
            )
            self._event(db, lease.knowledge.knowledge_id, "candidate-trained", revision, candidate.digest)
        return candidate.digest

    def release(
        self, lease: ShadowIntakeLease, *, backoff: bool = False,
    ) -> None:
        """Return work to the queue; failures receive exponential retry delay.

        Backoff is durable across process restarts and capped at one hour.
        Explicit idle preemption uses immediate release. Additional evidence
        resets the retry count to avoid penalizing a revised observation.
        """
        if not isinstance(backoff, bool):
            raise ShadowWeightError("invalid shadow retry policy")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._bound_lease(db, lease)
            revision = row["revision"] + 1
            now = _now()
            retry_after = None
            if backoff:
                delay = min(3600, 30 * (1 << min(row["attempts"] - 1, 7)))
                retry_after = (now + timedelta(seconds=delay)).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")
            db.execute(
                """UPDATE shadow_intake SET state='training-ready',lease_owner=NULL,
                    lease_until=NULL,revision=?,retry_after=?,updated_at=?
                    WHERE knowledge_id=?""",
                (
                    revision, retry_after,
                    now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    lease.knowledge.knowledge_id,
                ),
            )
            self._event(
                db, lease.knowledge.knowledge_id,
                "release-with-backoff" if backoff else "release",
                revision, lease.assessment_digest,
            )

    def backlog(
        self, *, states: tuple[str, ...] = ("pending", "quarantined", "training-ready"),
        limit: int = 200,
    ) -> tuple[dict[str, object], ...]:
        """Return bounded, deterministic, provenance-safe shadow work metadata."""
        allowed = {"pending", "quarantined", "training-ready", "leased", "trained"}
        if (
            not isinstance(states, tuple) or not states
            or len(set(states)) != len(states)
            or any(not isinstance(state, str) or state not in allowed for state in states)
        ):
            raise ShadowWeightError("invalid shadow backlog state selection")
        _count("backlog limit", limit, lower=1, upper=10_000)
        placeholders = ",".join("?" for _ in states)
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT knowledge_id,state,revision,priority_gain,priority_relevance,
                           observed_at,attempts,retry_after,candidate_digest,assessment
                    FROM shadow_intake WHERE state IN ({placeholders})
                    ORDER BY priority_gain DESC,priority_relevance DESC,
                             observed_at ASC,knowledge_id ASC LIMIT ?""",
                (*states, limit),
            ).fetchall()
        return tuple({
            "knowledge_id": row["knowledge_id"],
            "state": row["state"],
            "revision": row["revision"],
            "priority_gain_ppm": row["priority_gain"],
            "priority_relevance_ppm": row["priority_relevance"],
            "observed_at": row["observed_at"],
            "attempts": row["attempts"],
            "retry_after": row["retry_after"],
            "candidate_digest": row["candidate_digest"],
            "reason_codes": tuple(json.loads(row["assessment"])["reason_codes"]),
        } for row in rows)

    def workload_summary(self) -> dict[str, int]:
        """Counts for idle schedulers and companion/progress interfaces."""
        now_text = _now().isoformat(timespec="microseconds").replace("+00:00", "Z")
        with self._connect() as db:
            counts = db.execute(
                "SELECT state,COUNT(*) AS amount FROM shadow_intake GROUP BY state"
            ).fetchall()
            delayed = db.execute(
                """SELECT COUNT(*) FROM shadow_intake
                   WHERE state='training-ready' AND retry_after>?""",
                (now_text,),
            ).fetchone()[0]
        result = {
            "pending": 0, "quarantined": 0, "training-ready": 0,
            "leased": 0, "trained": 0, "retry-delayed": delayed,
        }
        for row in counts:
            result[row["state"]] = row["amount"]
        return result

    def events(
        self, *, after_event_id: int = 0, limit: int = 500,
    ) -> tuple[dict[str, object], ...]:
        """Replay ordered timestamped intake actions using an event cursor."""
        if isinstance(after_event_id, bool) or not isinstance(after_event_id, int) or after_event_id < 0:
            raise ShadowWeightError("invalid shadow intake event cursor")
        _count("shadow event limit", limit, lower=1, upper=10_000)
        with self._connect() as db:
            rows = db.execute(
                """SELECT event_id,knowledge_id,action,revision,payload_digest,occurred_at
                   FROM shadow_intake_events WHERE event_id>?
                   ORDER BY event_id LIMIT ?""",
                (after_event_id, limit),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def status(self, knowledge_id: str) -> dict[str, object]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM shadow_intake WHERE knowledge_id=?",
                (require_id(knowledge_id, "knowledge_id"),),
            ).fetchone()
            if row is None:
                raise ShadowWeightError("unknown shadow intake record")
            return {
                "knowledge_id": row["knowledge_id"],
                "state": row["state"],
                "revision": row["revision"],
                "assessment": json.loads(row["assessment"]),
                "candidate_digest": row["candidate_digest"],
                "lease_until": row["lease_until"],
                "attempts": row["attempts"],
                "retry_after": row["retry_after"],
            }


__all__ = [
    "ShadowKnowledge", "ShadowIntakePolicy", "ShadowIntakeAssessment",
    "ShadowIntakeLease", "ShadowKnowledgeQueue", "assess_shadow_intake",
]
