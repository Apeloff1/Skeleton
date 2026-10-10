"""Continuous consent custody for queued/running Dragon analysis jobs.

This companion store avoids an unsafe in-place SQLite schema migration of the
legacy queue while making durable-consent jobs auditable and revocable.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3

from .dragon_analysis_queue import AnalysisJob, DragonAnalysisQueue, JobStatus
from .dragon_consent_ledger import DragonConsentLedger


@dataclass(frozen=True)
class JobConsentBinding:
    owner: str
    job_id: str
    consent_id: str
    scope_digest: str


class ConsentBoundAnalysisQueue:
    def __init__(self, queue: DragonAnalysisQueue,
                 consent: DragonConsentLedger):
        self.queue=queue; self.consent=consent; self.db=queue.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_job_consent(
          owner TEXT NOT NULL,job_id TEXT NOT NULL,consent_id TEXT NOT NULL,
          scope_digest TEXT NOT NULL,PRIMARY KEY(owner,job_id))""")
        self.db.commit()

    def submit(self, owner: str, *, recording_digest: str, game_label: str,
               now: float, consent_id: str, scope_digest: str,
               authorized: bool) -> AnalysisJob:
        self.consent.require_active(owner,consent_id,now=now,
            scope_digest=scope_digest,authorized=authorized)
        job=self.queue.submit_with_consent(
            owner,recording_digest=recording_digest,game_label=game_label,
            now=now,consent_id=consent_id,consent_scope_digest=scope_digest,
            consent_ledger=self.consent,authorized=authorized)
        with self.db:
            row=self.db.execute("""SELECT consent_id,scope_digest
              FROM dragon_job_consent WHERE owner=? AND job_id=?""",
              (owner,job.job_id)).fetchone()
            if row and row != (consent_id,scope_digest):
                raise ValueError("immutable job consent binding conflict")
            self.db.execute("""INSERT OR IGNORE INTO dragon_job_consent
              VALUES(?,?,?,?)""",(owner,job.job_id,consent_id,scope_digest))
        return job

    def binding(self, owner: str, job_id: str, *,
                authorized: bool) -> JobConsentBinding:
        if not authorized:
            raise PermissionError("job consent lookup requires authorization")
        row=self.db.execute("""SELECT consent_id,scope_digest
          FROM dragon_job_consent WHERE owner=? AND job_id=?""",
          (owner,job_id)).fetchone()
        if not row:
            raise PermissionError("job has no durable consent binding")
        return JobConsentBinding(owner,job_id,row[0],row[1])

    def require_active(self, owner: str, job_id: str, *, now: float,
                       authorized: bool) -> AnalysisJob:
        binding=self.binding(owner,job_id,authorized=authorized)
        self.consent.require_active(owner,binding.consent_id,now=now,
            scope_digest=binding.scope_digest,authorized=True)
        job=self.queue.get(owner,job_id,authorized=True)
        if job is None:
            raise KeyError("analysis job not found")
        if job.status in {JobStatus.CANCELLED,JobStatus.FAILED,
                          JobStatus.REJECTED}:
            raise PermissionError("analysis job is not executable")
        return job

    def advance(self, owner: str, job_id: str, status: JobStatus, *,
                now: float, authorized: bool, error_code: str="",
                human_approved: bool=False) -> AnalysisJob:
        self.require_active(owner,job_id,now=now,authorized=authorized)
        return self.queue.advance(owner,job_id,status,now=now,
            authorized=True,error_code=error_code,
            human_approved=human_approved)

    def cancel_revoked(self, owner: str, *, now: float,
                       authorized: bool) -> tuple[str,...]:
        if not authorized:
            raise PermissionError("revocation sweep requires authorization")
        cancelled=[]
        for job in self.queue.pending(owner,authorized=True,limit=1000):
            try:
                self.require_active(owner,job.job_id,now=now,authorized=True)
            except PermissionError:
                if job.status in {JobStatus.QUEUED,JobStatus.RUNNING,
                                  JobStatus.AWAITING_REVIEW}:
                    self.queue.advance(owner,job.job_id,JobStatus.CANCELLED,
                        now=now,authorized=True,error_code="CONSENT_REVOKED")
                    cancelled.append(job.job_id)
        return tuple(cancelled)
