"""Durable transactional offline AI request queue.

The authoritative NativeChatEngine/OfflineAIService owns inference, original
chat transcript and exactly-once request-ID replay. This queue owns *only*
work scheduling, recovery holds and immutable dispatch receipts.

A stale worker MUST NOT be allowed to overwrite newer SQLite state. Expired
inference is held for operator recovery instead of blindly regenerated.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import secrets
import sqlite3
from typing import Any

from .audit import append_event, verify_audit, events_for_job
from .canonical import decode, encode, fingerprint, require_int, require_sha, sha256
from .errors import JobDenied, deny
from .schema import ensure_schema
from .spec import JobIdentity, JobSpec, WorkLimits, require_id
from .result import JobResult
from .transaction import TransactionGate


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: str
    request_id: str
    owner: JobIdentity
    question: str
    worker_id: str
    token: str
    lease_expires_ms: int
    attempt: int

    def __post_init__(self):
        for name in ("job_id","request_id","worker_id"):
            require_id(getattr(self,name), name)
        if type(self.owner) is not JobIdentity or type(self.token) is not str:
            deny("claim-invalid")
        if not 32 <= len(self.token) <= 128:
            deny("claim-token-size")
        require_int(self.lease_expires_ms,0,2**63-1,"claim-expiry")
        require_int(self.attempt,1,20,"claim-attempt")


class JobStore:
    """One SQLite connection per process, WAL recommended for disk storage.

    Use private, owner-checked directory and SQLite connection: this object
    deliberately does not claim to secure the file descriptor from an attacker.
    """

    def __init__(self, db: sqlite3.Connection, limits: WorkLimits | None = None):
        if not isinstance(db,sqlite3.Connection):
            deny("store-sqlite-required")
        self.db=db
        self.limits=limits or WorkLimits()
        if type(self.limits) is not WorkLimits:
            deny("store-limits")
        db.execute("PRAGMA busy_timeout=5000")
        ensure_schema(db)
        self.tx=TransactionGate(db)

    @staticmethod
    def _now(value: int) -> int:
        return require_int(value,0,2**63-1,"clock")

    def _audit_safe(self,db:sqlite3.Connection) -> None:
        verify_audit(db,max_events=100000)

    def _row(self, db, job_id:str):
        return db.execute("""SELECT job_id,tenant,user_id,session_id,request_id,
          model_sha,tokenizer_sha,payload_json,spec_sha,created_ms,expires_ms,
          next_eligible_ms,priority,state,attempt,lease_token_sha,worker_id,
          lease_expires_ms,terminal_sha,result_json,failure_code,updated_ms
          FROM ai_durable_jobs WHERE job_id=?""",(job_id,)).fetchone()

    def _parse(self,row):
        if row is None:
            deny("job-unknown")
        obj=decode(row[7])
        if fingerprint(obj)!=row[8]:
            deny("job-spec-corrupt")
        if obj.get("job_id")!=row[0] or obj.get("request_id")!=row[4]:
            deny("job-identity-corrupt")
        own=obj.get("owner")
        if (not isinstance(own,dict) or
            (own.get("tenant"),own.get("user"),own.get("session"),
             own.get("model_sha256"),own.get("tokenizer_sha256"))
             !=(row[1],row[2],row[3],row[5],row[6])):
            deny("job-owner-corrupt")
        if obj.get("priority")!=row[12] or obj.get("created_ms")!=row[9] or obj.get("expires_ms")!=row[10]:
            deny("job-metadata-corrupt")
        owner=JobIdentity(**own)
        spec=JobSpec(obj["job_id"],obj["request_id"],owner,obj["question"],
                     obj["created_ms"],obj["expires_ms"],obj["priority"],
                     tuple(obj["dependencies"]))
        if spec.digest!=row[8]:
            deny("job-spec-corrupt")
        return spec

    def _assert_owner(self,row,owner:JobIdentity) -> None:
        if type(owner) is not JobIdentity:
            deny("job-owner")
        if row[1:4]!=(owner.tenant,owner.user,owner.session):
            deny("job-owner-mismatch")
        if (row[5],row[6])!=(owner.model_sha256,owner.tokenizer_sha256):
            deny("job-model-mismatch")

    def _public(self,row) -> dict[str,Any]:
        spec=self._parse(row)
        return {
           "job_id":row[0],"request_id":row[4],"tenant":row[1],
           "state":row[13],"attempt":row[14],"priority":row[12],
           "created_ms":row[9],"expires_ms":row[10],
           "lease_expires_ms":row[17],"terminal_sha":row[18],
           "failure_code":row[20],"updated_ms":row[21],
           "model_sha256":spec.owner.model_sha256,
        }

    def submit(self,spec:JobSpec,*,now_ms:int)->str:
        if type(spec) is not JobSpec:
            deny("submit-contract")
        self._now(now_ms)
        if not spec.created_ms <= now_ms < spec.expires_ms:
            deny("submit-clock")
        if len(spec.question.encode("utf-8")) > self.limits.input_bytes:
            deny("submit-input-budget")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            current=self._row(db,spec.job_id)
            if current is not None:
                if current[8]!=spec.digest:
                    deny("job-id-collision")
                self._parse(current)
                return "replayed"
            duplicate=db.execute("""SELECT job_id,spec_sha FROM ai_durable_jobs
              WHERE tenant=? AND user_id=? AND session_id=? AND request_id=?""",
              (spec.owner.tenant,spec.owner.user,spec.owner.session,spec.request_id)).fetchone()
            if duplicate is not None:
                deny("request-id-collision")
            total=db.execute("""SELECT COUNT(*) FROM ai_durable_jobs
             WHERE state IN ('pending','running','held','cancel_requested')""").fetchone()[0]
            if total>=self.limits.queue_depth:
                deny("queue-global-limit")
            tenant_total=db.execute("""SELECT COUNT(*) FROM ai_durable_jobs
             WHERE tenant=? AND state IN ('pending','running','held','cancel_requested')""",
             (spec.owner.tenant,)).fetchone()[0]
            if tenant_total>=self.limits.tenant_depth:
                deny("queue-tenant-limit")
            for dependency in spec.dependencies:
                row=self._row(db,dependency)
                if row is None:
                    deny("dependency-missing")
                if row[1]!=spec.owner.tenant or row[2]!=spec.owner.user:
                    deny("dependency-cross-principal")
                if row[9]>spec.created_ms:
                    deny("dependency-future")
            payload=encode(spec.to_record())
            db.execute("""INSERT INTO ai_durable_jobs(
             job_id,tenant,user_id,session_id,request_id,model_sha,tokenizer_sha,
             payload_json,spec_sha,created_ms,expires_ms,next_eligible_ms,
             priority,state,attempt,updated_ms)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',0,?)""",
             (spec.job_id,spec.owner.tenant,spec.owner.user,spec.owner.session,
              spec.request_id,spec.owner.model_sha256,spec.owner.tokenizer_sha256,
              payload,spec.digest,spec.created_ms,spec.expires_ms,spec.created_ms,
              spec.priority,now_ms))
            for dependency in spec.dependencies:
                db.execute("INSERT INTO ai_job_deps(job_id,dependency_id) VALUES(?,?)",
                           (spec.job_id,dependency))
            append_event(db,spec.job_id,"submitted",{"spec_sha":spec.digest,"at":now_ms})
            return "admitted"

    def inspect(self,job_id:str,owner:JobIdentity)->dict:
        require_id(job_id,"job")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            return self._public(row)

    def load_spec(self,job_id:str,owner:JobIdentity)->JobSpec:
        """Return the original immutable prompt only to its exact owning principal."""
        require_id(job_id,"job")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            return self._parse(row)

    def dependencies(self,job_id:str,owner:JobIdentity)->list[dict]:
        require_id(job_id,"job")
        with self.tx.exclusive() as db:
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            result=[]
            for dependency_id, in db.execute(
              "SELECT dependency_id FROM ai_job_deps WHERE job_id=? ORDER BY dependency_id",
              (job_id,)):
                child=self._row(db,dependency_id)
                if child is None:
                    deny("dependency-corrupt")
                result.append(self._public(child))
            return result

    def _candidates(self,db,now_ms:int)->list:
        return db.execute("""SELECT job_id,tenant,priority,created_ms FROM ai_durable_jobs j
          WHERE state='pending' AND next_eligible_ms<=? AND expires_ms>?
          AND NOT EXISTS(
            SELECT 1 FROM ai_job_deps d JOIN ai_durable_jobs parent ON
             d.dependency_id=parent.job_id
            WHERE d.job_id=j.job_id AND parent.state!='completed'
          )
          AND (SELECT COUNT(*) FROM ai_durable_jobs active
             WHERE active.tenant=j.tenant AND active.state IN ('running','cancel_requested'))
              < ?
          ORDER BY tenant ASC, priority DESC, created_ms ASC,job_id ASC LIMIT 1024""",
          (now_ms,now_ms,self.limits.active_per_tenant)).fetchall()

    def claim(self,worker_id:str,*,now_ms:int,lease_ms:int|None=None,
              target_job_id:str|None=None)->ClaimedJob|None:
        require_id(worker_id,"worker")
        if target_job_id is not None:
            require_id(target_job_id,"target-job")
        self._now(now_ms)
        window=self.limits.lease_ms if lease_ms is None else require_int(lease_ms,100,self.limits.lease_ms,"lease")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            candidates=self._candidates(db,now_ms)
            if target_job_id is not None:
                candidates=[item for item in candidates if item[0]==target_job_id]
            if not candidates:
                return None
            tenant_names=sorted({row[1] for row in candidates})
            previous=db.execute("SELECT rr_tenant FROM ai_job_state WHERE singleton=1").fetchone()[0]
            tenant=next((name for name in tenant_names if name>previous),tenant_names[0])
            job_id=next(job for job,owner,*_ in candidates if owner==tenant)
            row=self._row(db,job_id)
            spec=self._parse(row)
            token=secrets.token_urlsafe(32)
            token_sha=sha256(token.encode("ascii"))
            until=min(now_ms+window,spec.expires_ms)
            if until<=now_ms:
                deny("lease-expired")
            db.execute("""UPDATE ai_durable_jobs SET state='running',attempt=attempt+1,
              lease_token_sha=?,worker_id=?,lease_expires_ms=?,updated_ms=?
              WHERE job_id=? AND state='pending'""",
              (token_sha,worker_id,until,now_ms,job_id))
            db.execute("UPDATE ai_job_state SET rr_tenant=? WHERE singleton=1",(tenant,))
            append_event(db,job_id,"claimed",{"worker":worker_id,"at":now_ms,
                          "attempt":row[14]+1,"lease_expires_ms":until})
            return ClaimedJob(job_id,spec.request_id,spec.owner,spec.question,
                              worker_id,token,until,row[14]+1)

    def _validate_claim(self,row,claim:ClaimedJob,now_ms:int,*,allow_cancel:bool=False)->None:
        if type(claim) is not ClaimedJob:
            deny("claim-type")
        self._now(now_ms)
        if row is None or row[0]!=claim.job_id:
            deny("claim-job")
        self._assert_owner(row,claim.owner)
        acceptable=("running","cancel_requested") if allow_cancel else ("running",)
        if row[13] not in acceptable:
            deny("claim-not-running")
        if row[16]!=claim.worker_id or row[14]!=claim.attempt:
            deny("claim-worker")
        expected=sha256(claim.token.encode("ascii"))
        if row[15] is None or not hmac.compare_digest(row[15],expected):
            deny("claim-token")
        if row[17] is None or now_ms >= row[17] or now_ms>=row[10]:
            deny("claim-expired")

    def heartbeat(self,claim:ClaimedJob,*,now_ms:int,extend_ms:int)->int:
        self._now(now_ms)
        require_int(extend_ms,100,self.limits.lease_ms,"extend")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,claim.job_id)
            self._validate_claim(row,claim,now_ms)
            until=min(now_ms+extend_ms,row[10])
            if until<=row[17]:
                deny("lease-nonextension")
            db.execute("UPDATE ai_durable_jobs SET lease_expires_ms=?,updated_ms=? WHERE job_id=?",
                       (until,now_ms,claim.job_id))
            append_event(db,claim.job_id,"heartbeat",{"at":now_ms,"until":until})
            return until

    def finish(self,claim:ClaimedJob,result:JobResult,*,now_ms:int)->str:
        if type(result) is not JobResult:
            deny("result-type")
        self._now(now_ms)
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,claim.job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,claim.owner)
            if row[13]=="completed":
                if row[18]==result.digest and row[15]==sha256(claim.token.encode("ascii")):
                    return "replayed"
                deny("result-terminal-conflict")
            self._validate_claim(row,claim,now_ms,allow_cancel=True)
            if (result.original_request_id!=row[4] or result.model_sha256!=row[5]
                or result.tokenizer_sha256!=row[6]):
                deny("result-identity")
            from .result_caps import assess
            spec=self._parse(row)
            assess(result,spec,self.limits)
            payload=encode(result.to_record())
            db.execute("""UPDATE ai_durable_jobs SET state='completed',terminal_sha=?,
                  result_json=?,updated_ms=? WHERE job_id=?""",
                  (result.digest,payload,now_ms,claim.job_id))
            append_event(db,claim.job_id,"completed",{"result_sha":result.digest,
                         "at":now_ms})
            return "committed"

    def fail(self,claim:ClaimedJob,*,now_ms:int,code:str,ambiguous:bool)->str:
        require_id(code,"failure")
        if type(ambiguous) is not bool:
            deny("failure-ambiguity")
        self._now(now_ms)
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,claim.job_id)
            self._validate_claim(row,claim,now_ms,allow_cancel=True)
            state="held" if ambiguous else "failed"
            db.execute("""UPDATE ai_durable_jobs SET state=?,failure_code=?,
              lease_expires_ms=NULL,updated_ms=? WHERE job_id=?""",
              (state,code,now_ms,claim.job_id))
            append_event(db,claim.job_id,"held" if ambiguous else "failed",
                         {"code":code,"at":now_ms})
            return state

    def cancel(self,job_id:str,owner:JobIdentity,*,now_ms:int)->str:
        require_id(job_id,"job")
        self._now(now_ms)
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            state=row[13]
            if state in ("cancelled","cancel_requested"):
                return "replayed"
            if state in ("completed","failed"):
                deny("cancel-terminal")
            if state=="held":
                state="cancelled"
            elif state=="pending":
                state="cancelled"
            else:
                state="cancel_requested"
            db.execute("UPDATE ai_durable_jobs SET state=?,updated_ms=? WHERE job_id=?",
                       (state,now_ms,job_id))
            append_event(db,job_id,"cancelled" if state=="cancelled" else "cancel_requested",
                         {"at":now_ms})
            return state

    def sweep(self,*,now_ms:int,limit:int=128)->dict:
        self._now(now_ms)
        require_int(limit,1,1024,"sweep")
        updated={"expired_pending":0,"held_running":0,"blocked_dependencies":0}
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            candidates=db.execute("""SELECT job_id FROM ai_durable_jobs WHERE
              (state='pending' AND expires_ms<=?) OR
              (state IN ('running','cancel_requested') AND
                (lease_expires_ms<=? OR expires_ms<=?)) OR
              (state='pending' AND EXISTS(
                SELECT 1 FROM ai_job_deps d JOIN ai_durable_jobs parent
                 ON d.dependency_id=parent.job_id
                 WHERE d.job_id=ai_durable_jobs.job_id
                 AND parent.state IN ('failed','cancelled','held')
              ))
              ORDER BY job_id LIMIT ?""",(now_ms,now_ms,now_ms,limit)).fetchall()
            for job_id, in candidates:
                row=self._row(db,job_id)
                if row[13]=="pending" and row[10]<=now_ms:
                    state="cancelled"; kind="expired"; key="expired_pending"
                elif row[13]=="pending":
                    state="held"; kind="dependency_held"; key="blocked_dependencies"
                else:
                    state="held"; kind="lease_held"; key="held_running"
                db.execute("""UPDATE ai_durable_jobs SET state=?,failure_code=?,
                  updated_ms=? WHERE job_id=?""",(state,kind,now_ms,job_id))
                append_event(db,job_id,kind,{"at":now_ms})
                updated[key]+=1
        return updated

    def manual_resume(self,job_id:str,owner:JobIdentity,*,now_ms:int,
                      no_effect_proof_sha256:str,operator_approved:bool,
                      proof_verifier)->str:
        require_id(job_id,"job")
        require_sha(no_effect_proof_sha256)
        self._now(now_ms)
        if operator_approved is not True:
            deny("recovery-needs-approval")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            if row[13]!="held":
                deny("recovery-not-held")
            if now_ms<row[21]:
                deny("recovery-clock-regressed")
            if not callable(proof_verifier):
                deny("recovery-verifier-required")
            original=self._parse(row)
            if proof_verifier(original,no_effect_proof_sha256) is not True:
                deny("recovery-proof-unverified")
            if row[14]>=20 or now_ms>=row[10]:
                deny("recovery-budget")
            # The proof's meaning must be independently verified by the
            # operator using the authoritative OfflineChatStore. A digest
            # string alone does NOT establish absence of inference.
            db.execute("""UPDATE ai_durable_jobs SET state='pending',
                 next_eligible_ms=?,lease_token_sha=NULL,worker_id=NULL,
                 lease_expires_ms=NULL,failure_code=NULL,updated_ms=? WHERE job_id=?""",
                 (now_ms,now_ms,job_id))
            append_event(db,job_id,"manual_resume",
                         {"at":now_ms,"proof_sha":no_effect_proof_sha256,
                          "approved":True})
            return "pending"

    def receipt(self,job_id:str,owner:JobIdentity)->JobResult:
        require_id(job_id,"job")
        with self.tx.exclusive() as db:
            self._audit_safe(db)
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            if row[13]!="completed" or row[19] is None:
                deny("result-not-committed")
            record=decode(row[19])
            result=JobResult(
                record["text"],record["output_sha256"],record["model_sha256"],
                record["tokenizer_sha256"],record["prompt_tokens"],
                record["generated_tokens"],record["original_request_id"]
            )
            if result.digest!=row[18]:
                deny("result-corrupt")
            return result

    def audit(self,job_id:str,owner:JobIdentity)->list[dict]:
        require_id(job_id,"job")
        with self.tx.exclusive() as db:
            row=self._row(db,job_id)
            if row is None:
                deny("job-unknown")
            self._assert_owner(row,owner)
            return events_for_job(db,job_id)
