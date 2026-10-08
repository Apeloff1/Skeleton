"""Dragon Game Studio operational audit and bounded job state.

Every video-analysis job has explicit ownership, consent, retention and
status. The coordinator does not execute external models or retain video.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
import sqlite3


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.AWAITING_REVIEW, JobStatus.FAILED, JobStatus.CANCELLED,
    },
    JobStatus.AWAITING_REVIEW: {
        JobStatus.APPROVED, JobStatus.REJECTED, JobStatus.CANCELLED,
    },
}


@dataclass(frozen=True)
class AnalysisJob:
    owner: str
    job_id: str
    recording_digest: str
    game_label: str
    created_at: float
    updated_at: float
    status: JobStatus
    error_code: str = ""


class DragonAnalysisQueue:
    def __init__(self, db: sqlite3.Connection, max_jobs: int = 1000):
        if not 1 <= max_jobs <= 100000:
            raise ValueError("invalid job budget")
        self.db = db
        self.max_jobs = max_jobs
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_analysis_jobs(
                owner TEXT NOT NULL, job_id TEXT NOT NULL,
                recording_digest TEXT NOT NULL, game_label TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                status TEXT NOT NULL, error_code TEXT NOT NULL,
                PRIMARY KEY(owner, job_id)
            )
        """)
        db.commit()

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ValueError("invalid owner")
        return owner

    def submit(self, owner: str, *, recording_digest: str,
               game_label: str, now: float,
               capture_consent: bool, analysis_consent: bool,
               authorized: bool) -> AnalysisJob:
        if not authorized or not capture_consent or not analysis_consent:
            raise PermissionError("analysis queue requires recording and analysis consent")
        owner = self._owner(owner)
        if not isinstance(recording_digest, str) or len(recording_digest) != 64 or any(
            c not in "0123456789abcdef" for c in recording_digest
        ):
            raise ValueError("invalid recording digest")
        if not isinstance(game_label, str) or not 1 <= len(game_label) <= 200:
            raise ValueError("invalid game label")
        if not math.isfinite(now) or now < 0:
            raise ValueError("invalid job timestamp")
        job_id = sha256(json.dumps(
            [owner, recording_digest, game_label], separators=(",", ":"),
        ).encode()).hexdigest()
        with self.db:
            existing = self.get(owner, job_id, authorized=True)
            if existing:
                return existing
            count = self.db.execute(
                "SELECT COUNT(*) FROM dragon_analysis_jobs WHERE owner=?",
                (owner,),
            ).fetchone()[0]
            if count >= self.max_jobs:
                raise ValueError("analysis queue capacity exceeded")
            self.db.execute("""
                INSERT INTO dragon_analysis_jobs VALUES (?,?,?,?,?,?,?,?)
            """, (owner, job_id, recording_digest, game_label,
                  now, now, JobStatus.QUEUED.value, ""))
        return self.get(owner, job_id, authorized=True)

    def get(self, owner: str, job_id: str, *, authorized: bool) -> AnalysisJob | None:
        if not authorized:
            raise PermissionError("job lookup requires authorization")
        owner = self._owner(owner)
        row = self.db.execute("""
            SELECT recording_digest,game_label,created_at,updated_at,status,error_code
            FROM dragon_analysis_jobs WHERE owner=? AND job_id=?
        """, (owner, job_id)).fetchone()
        return (AnalysisJob(owner, job_id, row[0], row[1], row[2], row[3],
                            JobStatus(row[4]), row[5]) if row else None)

    def advance(self, owner: str, job_id: str, status: JobStatus, *,
                now: float, authorized: bool, error_code: str = "",
                human_approved: bool = False) -> AnalysisJob:
        if not authorized:
            raise PermissionError("job updates require authorization")
        if not isinstance(status, JobStatus):
            raise ValueError("invalid job status")
        if not math.isfinite(now) or now < 0:
            raise ValueError("invalid job timestamp")
        if not isinstance(error_code, str) or len(error_code) > 80:
            raise ValueError("invalid error code")
        with self.db:
            current = self.get(owner, job_id, authorized=True)
            if current is None:
                raise KeyError("analysis job not found")
            if status not in _ALLOWED.get(current.status, set()):
                raise ValueError("invalid job state transition")
            if now < current.updated_at:
                raise ValueError("job time cannot move backwards")
            if status is JobStatus.APPROVED and not human_approved:
                raise PermissionError("approval requires explicit human review")
            self.db.execute("""
                UPDATE dragon_analysis_jobs SET status=?, updated_at=?,error_code=?
                WHERE owner=? AND job_id=? AND status=?
            """, (status.value, now, error_code, owner, job_id,
                  current.status.value))
        return self.get(owner, job_id, authorized=True)

    def pending(self, owner: str, *, authorized: bool, limit: int = 100
                ) -> tuple[AnalysisJob, ...]:
        if not authorized:
            raise PermissionError("job listing requires authorization")
        owner = self._owner(owner)
        if not 1 <= limit <= 1000:
            raise ValueError("invalid job query limit")
        rows = self.db.execute("""
            SELECT job_id FROM dragon_analysis_jobs
            WHERE owner=? AND status IN ('queued','running','awaiting_review')
            ORDER BY created_at,job_id LIMIT ?
        """, (owner, limit)).fetchall()
        return tuple(self.get(owner, row[0], authorized=True) for row in rows)

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("job erasure requires authorization")
        owner = self._owner(owner)
        with self.db:
            return self.db.execute(
                "DELETE FROM dragon_analysis_jobs WHERE owner=?", (owner,)
            ).rowcount
