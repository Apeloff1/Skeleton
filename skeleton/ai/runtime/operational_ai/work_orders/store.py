"""Durable native AI work custody with actor-scoped reads and SQLite token CAS.

Caller authority must come from trusted owner/operator code; a model, prompt
or retrieved document is never allowed to call this store directly.
"""
from __future__ import annotations
import secrets
import sqlite3
import time
from .contracts import identifier,digest_id,uint,hash_bytes,refuse
from .model import WorkOrder
from .database import WorkDatabase
from . import journal
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt

class WorkOrderStore:
    def __init__(self,root,*,clock=time.monotonic_ns,readonly=False):
        if not callable(clock):refuse("trusted monotonic clock required")
        self.db=WorkDatabase(root,readonly=readonly)
        self._clock=clock
    def close(self):self.db.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

    def configure_budget(self,tenant,*,ceiling,operator_approved,expected_revision=None):
        identifier(tenant,"tenant")
        uint(ceiling,maximum=1000000000000)
        if ceiling<1 or operator_approved is not True:
            refuse("positive operator-approved local token ceiling required")
        with self.db.transaction() as c:
            prev=c.execute("SELECT ceiling,reserved,consumed,revision FROM budgets WHERE tenant=?",
                           (tenant,)).fetchone()
            if prev is None:
                if expected_revision is not None:refuse("new budget must have no previous revision")
                c.execute("INSERT INTO budgets(tenant,ceiling) VALUES (?,?)",(tenant,ceiling))
                return {"tenant":tenant,"revision":1,"ceiling":ceiling}
            old,reserved,consumed,revision=prev
            if type(expected_revision) is not int or revision!=expected_revision:
                refuse("budget revision compare-and-set conflict")
            if ceiling<reserved+consumed:refuse("cannot lower budget below committed/pending consumption")
            if c.execute("UPDATE budgets SET ceiling=?,revision=revision+1 WHERE tenant=? AND revision=?",
                         (ceiling,tenant,revision)).rowcount!=1:
                refuse("budget update lost revision")
            return {"tenant":tenant,"revision":revision+1,"ceiling":ceiling}

    def submit(self,order):
        if not isinstance(order,WorkOrder):refuse("typed work order required")
        request_sha=order.request_sha256()
        now=self._clock()
        with self.db.transaction() as c:
            old=c.execute("SELECT request_sha FROM jobs WHERE job_id=?",(order.job_id,)).fetchone()
            if old is not None:
                if old[0]!=request_sha:refuse("job ID collision with changed request")
                return {"job_id":order.job_id,"created":False,"request_sha256":request_sha}
            try:
                c.execute("""INSERT INTO jobs(job_id,tenant,subject,model_sha,tokenizer_sha,
                    session_id,request_id,prompt_sha,request_sha,seed,temperature,
                    max_output,status,revision,updated_ns)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (order.job_id,order.tenant,order.subject,order.model_sha256,
                     order.tokenizer_sha256,order.session_id,order.request_id,
                     order.prompt_sha256,request_sha,order.seed,
                     order.sampler_temperature,order.max_output_tokens,
                     "queued",1,now))
            except sqlite3.IntegrityError as exc:
                raise type(exc)("work order collision, missing budget, or invalid state") from exc
            journal.append(c,order.job_id,"submitted",
                           {"request_sha256":request_sha},clock=self._clock)
            return {"job_id":order.job_id,"created":True,"request_sha256":request_sha}

    def _scoped(self,c,order):
        if not isinstance(order,WorkOrder):refuse("typed owner record required")
        row=journal.job(c,order.job_id)
        if (row["tenant"],row["subject"],row["model_sha"],
            row["tokenizer_sha"],row["session_id"],row["request_id"],
            row["request_sha"])!=(
             order.tenant,order.subject,order.model_sha256,
             order.tokenizer_sha256,order.session_id,order.request_id,
             order.request_sha256()):
            refuse("cross-principal or mutated durable request")
        return row

    def inspect(self,order):
        with self.db.snapshot() as c:
            row=self._scoped(c,order)
            return {k:v for k,v in row.items() if k!="lease_sha"}

    def list_jobs(self,*,tenant,subject,model_sha256,limit=100,status=None):
        identifier(tenant);identifier(subject);digest_id(model_sha256)
        if type(limit) is not int or not 1<=limit<=100:
            refuse("job listing ceiling exceeded")
        if status is not None and status not in (
             "queued","leased","dispatch-unknown","held","committed","cancelled"):
            refuse("unknown job status")
        with self.db.snapshot() as c:
            args=[tenant,subject,model_sha256]
            where="tenant=? AND subject=? AND model_sha=?"
            if status is not None:where+=" AND status=?";args.append(status)
            rows=c.execute("SELECT job_id,status,revision,output_sha FROM jobs WHERE "
                           +where+" ORDER BY updated_ns,job_id LIMIT ?",(*args,limit)).fetchall()
            return tuple({"job_id":j,"status":s,"revision":r,"output_sha256":d}
                         for j,s,r,d in rows)

    def claim(self,order,*,expected_revision,reservation_tokens):
        uint(expected_revision,maximum=1000000000)
        uint(reservation_tokens,maximum=1000000000)
        if reservation_tokens<order.max_output_tokens:refuse("insufficient generation reservation")
        lease=secrets.token_hex(32)
        lease_sha=hash_bytes(bytes.fromhex(lease))
        now=self._clock()
        with self.db.transaction() as c:
            row=self._scoped(c,order)
            if row["status"]!="queued" or row["revision"]!=expected_revision:
                refuse("work not queued at expected revision")
            budget=c.execute("SELECT ceiling,reserved,consumed FROM budgets WHERE tenant=?",
                             (order.tenant,)).fetchone()
            if budget is None:refuse("no operator-configured tenant token budget")
            ceiling,reserved,consumed=budget
            if consumed+reserved+reservation_tokens>ceiling:
                refuse("durable quota capacity exhausted")
            if c.execute("UPDATE budgets SET reserved=reserved+? WHERE tenant=?",
                         (reservation_tokens,order.tenant)).rowcount!=1:
                refuse("budget reservation lost")
            if c.execute("""UPDATE jobs SET status='leased',revision=revision+1,
                    lease_sha=?,token_reservation=?,updated_ns=?
                    WHERE job_id=? AND status='queued' AND revision=?""",
                    (lease_sha,reservation_tokens,now,order.job_id,expected_revision)).rowcount!=1:
                refuse("work-order lease CAS lost")
            journal.append(c,order.job_id,"leased",
                {"reservation":reservation_tokens,"revision":expected_revision+1},
                clock=self._clock)
            return {"job_id":order.job_id,"lease":lease,"revision":expected_revision+1}

    def dispatch(self,order,lease,*,expected_revision):
        uint(expected_revision,maximum=1000000000)
        if type(lease) is not str or len(lease)!=64:
            refuse("cryptographically random lease required")
        try:lease_sha=hash_bytes(bytes.fromhex(lease))
        except ValueError:refuse("malformed lease token")
        now=self._clock()
        with self.db.transaction() as c:
            row=self._scoped(c,order)
            if (row["status"]!="leased" or row["revision"]!=expected_revision
                or row["lease_sha"]!=lease_sha):
                refuse("missing or expired native dispatch authority")
            if c.execute("""UPDATE jobs SET status='dispatch-unknown',
                    revision=revision+1,lease_sha=NULL,updated_ns=?
                    WHERE job_id=? AND status='leased' AND revision=? AND lease_sha=?""",
                    (now,order.job_id,expected_revision,lease_sha)).rowcount!=1:
                refuse("native dispatch CAS lost")
            journal.append(c,order.job_id,"dispatch-fenced",
                {"revision":expected_revision+1,"request_sha256":row["request_sha"]},
                clock=self._clock)
            return {"job_id":order.job_id,"status":"dispatch-unknown",
                    "revision":expected_revision+1}

    def reconcile(self,order,worker,prompt_text):
        """Only canonical replay may move dispatch-unknown/held to committed."""
        order.confirm_prompt(prompt_text)
        order.confirm_worker(worker)
        with self.db.snapshot() as c:
            before=self._scoped(c,order)
            if before["status"] not in ("dispatch-unknown","held"):
                refuse("work has no unresolved native dispatch")
        result=worker.spine.replay(order.session_id,order.request_id,prompt_text,
                     seed=order.seed,temperature=order.sampler_temperature)
        if result is None:
            return {"job_id":order.job_id,"status":before["status"],
                    "committed":False,"auto_retry":False}
        receipt=verify_turn_receipt(result,model_sha256=order.model_sha256,
                                    tokenizer_sha256=order.tokenizer_sha256)
        if receipt["replayed"] is not True:
            refuse("uncommitted or fake replay cannot close durable work")
        used=receipt["prompt_tokens"]+receipt["generated_tokens"]
        now=self._clock()
        with self.db.transaction() as c:
            row=self._scoped(c,order)
            if row["revision"]!=before["revision"] or row["status"]!=before["status"]:
                refuse("work changed while independently verifying canonical replay")
            if used>row["token_reservation"]:
                refuse("committed result exceeded durable token reservation")
            budget=c.execute("SELECT reserved,consumed FROM budgets WHERE tenant=?",
                             (order.tenant,)).fetchone()
            if budget is None or budget[0]<row["token_reservation"]:
                refuse("durable quota ledger and job reservation diverged")
            c.execute("""UPDATE budgets SET reserved=reserved-?,
                    consumed=consumed+? WHERE tenant=?""",
                    (row["token_reservation"],used,order.tenant))
            if c.execute("""UPDATE jobs SET status='committed',revision=revision+1,
                 output_sha=?,tokens_charged=?,token_reservation=0,updated_ns=?
                 WHERE job_id=? AND revision=? AND status=?""",
                 (receipt["output_sha256"],used,now,order.job_id,
                  before["revision"],before["status"])).rowcount!=1:
                refuse("native reconciliation CAS conflict")
            journal.append(c,order.job_id,"committed",
                {"output_sha256":receipt["output_sha256"],"tokens_charged":used,
                 "revision":before["revision"]+1},clock=self._clock)
            return {"job_id":order.job_id,"status":"committed",
                    "revision":before["revision"]+1,
                    "output_sha256":receipt["output_sha256"],
                    "tokens_charged":used,"recovered_from_spine":True}

    def hold_unknown(self,order,*,expected_revision):
        uint(expected_revision,maximum=1000000000)
        with self.db.transaction() as c:
            row=self._scoped(c,order)
            if row["status"]!="dispatch-unknown" or row["revision"]!=expected_revision:
                refuse("only uncertain native effects may become held")
            now=self._clock()
            c.execute("""UPDATE jobs SET status='held',revision=revision+1,updated_ns=?
                    WHERE job_id=? AND revision=? AND status='dispatch-unknown'""",
                    (now,order.job_id,expected_revision))
            journal.append(c,order.job_id,"held",
                {"reason":"unknown-native-effect","revision":expected_revision+1},
                clock=self._clock)
            return {"status":"held","revision":expected_revision+1,
                    "reservation_released":False}

    def abandon_before_dispatch(self,order,lease,*,expected_revision,operator_approved):
        if operator_approved is not True:refuse("explicit operator stop approval required")
        uint(expected_revision,maximum=1000000000)
        if type(lease) is not str or len(lease)!=64:refuse("original lease token required")
        try:lease_sha=hash_bytes(bytes.fromhex(lease))
        except ValueError:refuse("malformed lease")
        with self.db.transaction() as c:
            row=self._scoped(c,order)
            if (row["status"]!="leased" or row["revision"]!=expected_revision
                or row["lease_sha"]!=lease_sha):
                refuse("dispatch already occurred or lease mismatch")
            budget=c.execute("SELECT reserved FROM budgets WHERE tenant=?",
                             (order.tenant,)).fetchone()
            if budget is None or budget[0]<row["token_reservation"]:
                refuse("token budget custody mismatch")
            c.execute("UPDATE budgets SET reserved=reserved-? WHERE tenant=?",
                      (row["token_reservation"],order.tenant))
            now=self._clock()
            c.execute("""UPDATE jobs SET status='cancelled',revision=revision+1,
                        lease_sha=NULL,token_reservation=0,updated_ns=?
                        WHERE job_id=? AND revision=? AND status='leased'""",
                        (now,order.job_id,expected_revision))
            journal.append(c,order.job_id,"cancelled",
                           {"reason":"leased-but-never-dispatched",
                            "revision":expected_revision+1},clock=self._clock)
            return {"status":"cancelled","reservation_released":True}

    def budget(self,tenant):
        identifier(tenant)
        with self.db.snapshot() as c:
            row=c.execute("SELECT ceiling,reserved,consumed,revision FROM budgets WHERE tenant=?",
                          (tenant,)).fetchone()
            if row is None:refuse("unknown tenant budget")
            return dict(zip(("ceiling","reserved","consumed","revision"),row))

    def pending_events(self,*,tenant,subject,model_sha256,limit=32):
        identifier(tenant);identifier(subject);digest_id(model_sha256)
        if type(limit) is not int or not 1<=limit<=128:refuse("outbox bounds")
        with self.db.snapshot() as c:
            rows=c.execute("""SELECT o.event_sha,o.job_id FROM outbox o
                 JOIN jobs j ON j.job_id=o.job_id WHERE j.tenant=? AND j.subject=?
                 AND j.model_sha=? AND o.acknowledged=0 ORDER BY o.rowid LIMIT ?""",
                 (tenant,subject,model_sha256,limit)).fetchall()
            return tuple({"event_sha256":sha,"job_id":job} for sha,job in rows)

    def ack_event(self,event_sha256,*,tenant,subject,model_sha256):
        digest_id(event_sha256);identifier(tenant);identifier(subject);digest_id(model_sha256)
        with self.db.transaction() as c:
            row=c.execute("""SELECT o.acknowledged FROM outbox o
                JOIN jobs j ON j.job_id=o.job_id WHERE o.event_sha=?
                AND j.tenant=? AND j.subject=? AND j.model_sha=?""",
                (event_sha256,tenant,subject,model_sha256)).fetchone()
            if row is None:refuse("unknown or cross-principal outbox event")
            if row[0]==1:return False
            now=self._clock()
            if c.execute("""UPDATE outbox SET acknowledged=1,acknowledged_ns=?
                 WHERE event_sha=? AND acknowledged=0""",
                 (now,event_sha256)).rowcount!=1:
                refuse("outbox event ack lost")
            return True

    def audit(self,*,maximum_events=1000000):
        self.db.inspect()
        with self.db.snapshot() as c:
            chain=journal.inspect(c,maximum=maximum_events)
            totals=c.execute("""SELECT b.tenant,b.reserved,b.consumed,
                COALESCE(SUM(j.token_reservation),0),
                COALESCE(SUM(j.tokens_charged),0)
                FROM budgets b LEFT JOIN jobs j ON j.tenant=b.tenant
                GROUP BY b.tenant""").fetchall()
            for tenant,reserved,consumed,job_res,job_spent in totals:
                if reserved!=job_res or consumed!=job_spent:
                    refuse("tenant-wide durable quota and work orders diverged")
            # The admission nonce and job must be mutually bound to the exact
            # append-only signed-submission event, not merely present.
            from .contracts import parse,digest_id
            signed_events=c.execute("""SELECT job_id,body FROM events
                              WHERE kind='signed-submission'""").fetchall()
            for event_job,raw in signed_events:
                payload=parse(raw)
                if type(payload) is not dict or set(payload)!={
                    "request_sha256","admission_nonce_sha256"}:
                    refuse("signed admission audit payload malformed")
                nonce=digest_id(payload["admission_nonce_sha256"])
                row=c.execute("""SELECT a.job_id,a.request_sha,a.tenant,
                    a.subject,j.request_sha,j.tenant,j.subject
                    FROM admissions a JOIN jobs j ON j.job_id=a.job_id
                    WHERE a.nonce_sha=?""",(nonce,)).fetchone()
                if (row is None or row[0]!=event_job or
                    row[1]!=row[4] or row[2]!=row[5] or row[3]!=row[6]
                    or row[1]!=payload["request_sha256"]):
                    refuse("durable signed approval does not match event/job")
            count=c.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]
            if count!=len(signed_events):
                refuse("signed operator admission nonce/event count diverged")
            return {**chain,"budgets_checked":len(totals),
                    "admissions_checked":count,
                    "native_inference_proved":False,
                    "release_certified":False}
