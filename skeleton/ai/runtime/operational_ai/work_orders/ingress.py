"""One SQLite transaction consumes a signed operator grant AND creates the job.

This is the only admission facade intended for external authenticated
clients. Direct WorkOrderStore.submit is an internal trusted-operator API.
"""
from __future__ import annotations
import sqlite3
from .authorization import OperatorAuthority
from .store import WorkOrderStore
from .model import WorkOrder
from .contracts import refuse
from . import journal

class SignedIngress:
    def __init__(self,store,authority):
        if not isinstance(store,WorkOrderStore) or not isinstance(authority,OperatorAuthority):
            refuse("signed source ingress requires queue and authenticated operator key")
        self.store=store;self.authority=authority

    def submit(self,order,ticket,*,observed_at):
        if not isinstance(order,WorkOrder):refuse("typed bounded job required")
        valid=self.authority.verify(ticket,order,observed_at=observed_at)
        now=self.store._clock()
        with self.store.db.transaction() as c:
            # A duplicate grant must not be accepted even when a previous
            # identical job was already successfully written.
            if c.execute("SELECT 1 FROM admissions WHERE nonce_sha=?",
                         (valid["nonce_sha256"],)).fetchone():
                refuse("operator admission nonce already consumed")
            old=c.execute("SELECT request_sha FROM jobs WHERE job_id=?",
                          (order.job_id,)).fetchone()
            if old is not None:
                refuse("new HMAC approval cannot overwrite existing work")
            try:
                c.execute("""INSERT INTO jobs(job_id,tenant,subject,model_sha,tokenizer_sha,
                    session_id,request_id,prompt_sha,request_sha,seed,temperature,
                    max_output,status,revision,updated_ns)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (order.job_id,order.tenant,order.subject,order.model_sha256,
                     order.tokenizer_sha256,order.session_id,order.request_id,
                     order.prompt_sha256,order.request_sha256(),order.seed,
                     order.sampler_temperature,order.max_output_tokens,
                     "queued",1,now))
                c.execute("""INSERT INTO admissions(nonce_sha,job_id,request_sha,
                    tenant,subject,consumed_ns) VALUES (?,?,?,?,?,?)""",
                    (valid["nonce_sha256"],order.job_id,order.request_sha256(),
                     order.tenant,order.subject,now))
            except sqlite3.IntegrityError as exc:
                refuse("operator admission collision or missing budget")
            journal.append(c,order.job_id,"signed-submission",
                {"request_sha256":order.request_sha256(),
                 "admission_nonce_sha256":valid["nonce_sha256"]},
                clock=self.store._clock)
            return {"status":"signed-operator-work-admitted",
                "job_id":order.job_id,"request_sha256":order.request_sha256(),
                "nonce_consumed":True,"native_model_started":False}
