"""Durable Jeeves batch conveyor on one canonical native SQLite authority.

This is an operator-driven bridge from typed approved batch jobs into
durable claim/reservation records and the existing native batch inference
adapter. A crash cannot dequeue another copy of a claimed native request.
Missing receipts remain held; cold recovery is an explicit, replay-only
operator action and never a speculative model retry.

All scheduling and testimony remain source-only until exercised with a
real source-approved installed GGUF on an actual operator device.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Any, Callable, Sequence

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase

from skeleton.jeeves.agent.native_batch_runtime import (
    NativeBatchConveyor, NativeBatchTask, NativeBatchPolicy, NativeBatchHold,
    batch_identity,
)
from skeleton.jeeves.agent.native_fabric_supervisor import (
    FabricJob, FabricRunPolicy,
)
from skeleton.jeeves.native_fabric.contracts import (
    ContractHold, Scope, digest, exact_integer, fingerprint, identifier,
)
from skeleton.jeeves.native_fabric.durable_queue import (
    DurableNativeQueue, DurableQueueHold, WorkOrder,
)
from skeleton.jeeves.native_fabric.telemetry_store import (
    NativeTelemetryStore,
)


class NativeDurableBatchHold(NativeBatchHold):
    """A batch, queue or canonical native receipt is not safe to promote."""


_BATCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_native_durable_batches (
  batch_id TEXT PRIMARY KEY,
  scope_sha256 TEXT NOT NULL,
  tenant TEXT NOT NULL,
  subject TEXT NOT NULL,
  model_sha256 TEXT NOT NULL,
  tokenizer_sha256 TEXT NOT NULL,
  batch_sha256 TEXT NOT NULL,
  job_count INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('admitting','ready')),
  created_ns INTEGER NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class DurableBatchResult:
    batch_id: str
    batch_sha256: str
    ready: int
    claimed: int
    committed: int
    held: int
    cancelled: int
    total: int
    orders: tuple[dict[str, object], ...]

    def __post_init__(self):
        identifier(self.batch_id)
        digest(self.batch_sha256)
        for number in (
            self.ready,self.claimed,self.committed,self.held,
            self.cancelled,self.total,
        ):
            exact_integer(number,maximum=100000)
        if sum((self.ready,self.claimed,self.committed,
                self.held,self.cancelled))!=self.total:
            raise NativeDurableBatchHold("durable order accounting mismatch")

    @property
    def complete(self)->bool:
        return self.committed==self.total

    def to_public_record(self):
        return {
            "schema":"jeeves.native_durable_batch.v1",
            "batch_id":self.batch_id,
            "batch_sha256":self.batch_sha256,
            "queued":self.ready,
            "claimed":self.claimed,
            "committed":self.committed,
            "held":self.held,
            "cancelled":self.cancelled,
            "total":self.total,
            "fully_native_committed":self.complete,
            "orders":list(self.orders),
            "automatic_native_retry":False,
            "model_rights_independently_verified":False,
            "actual_device_qualified":False,
            "release_certified":False,
        }


class NativeDurableBatchConveyor:
    """Serial approved laptop batch with restart-fenced request ownership."""

    def __init__(
        self,worker:Any,*,approved:bool,
        policy:NativeBatchPolicy|None=None,
        maximum_orders:int=10000,
        clock_ns:Callable[[],int]=time.time_ns,
    ):
        if approved is not True:
            raise NativeDurableBatchHold("operator approval required")
        if worker is None or not hasattr(worker,"spine") or not isinstance(
            worker.spine.db,SpineDatabase
        ):
            raise NativeDurableBatchHold("canonical protected native SQLite required")
        if not callable(clock_ns):
            raise NativeDurableBatchHold("trusted wall-time clock required")
        self.worker=worker
        self.db=worker.spine.db
        self.identity=ActiveModel.from_supervisor(worker)
        self.policy=policy or NativeBatchPolicy()
        self.native=NativeBatchConveyor(
            worker,approved=True,policy=self.policy,
        )
        self.scope=Scope(
            self.identity.tenant,self.identity.subject,
            self.identity.model_sha256,self.identity.tokenizer_sha256,
        )
        self.queue=DurableNativeQueue(
            worker,scope_sha256=self.scope.binding,
            maximum_orders=maximum_orders,clock_ns=clock_ns,
        )
        self.telemetry=NativeTelemetryStore(worker,clock_ns=clock_ns)
        self.clock_ns=clock_ns
        self.db.inspect()
        with self.db.transaction() as conn:
            conn.execute(_BATCH_SCHEMA)

    def _live(self):
        if ActiveModel.from_supervisor(self.worker)!=self.identity:
            raise NativeDurableBatchHold("native model changed during durable batch")
        self.db.inspect()

    def _scope(self):
        i=self.identity
        return i.tenant,i.subject,i.model_sha256,i.tokenizer_sha256

    @staticmethod
    def _order_key(batch_id,task_id):
        return "dbo_"+sha256(
            json.dumps(
                {"batch":batch_id,"task":task_id},
                sort_keys=True,separators=(",",":"),
            ).encode("ascii")
        ).hexdigest()[:48]

    def _batch(self,batch_id,conn):
        identifier(batch_id,"batch")
        row=conn.execute(
            "SELECT scope_sha256,tenant,subject,model_sha256,"
            "tokenizer_sha256,batch_sha256,job_count,state,created_ns "
            "FROM jeeves_native_durable_batches WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise NativeDurableBatchHold("batch not admitted")
        if row[0]!=self.scope.binding or tuple(row[1:5])!=self._scope():
            raise NativeDurableBatchHold("foreign batch principal/model identity")
        digest(row[5])
        exact_integer(row[6],minimum=1,maximum=1000)
        if row[7] not in ("admitting","ready"):
            raise NativeDurableBatchHold("invalid durable batch state")
        return row

    def _preflight(self,batch_id:str,jobs:Sequence[FabricJob]):
        self._live()
        identifier(batch_id,"batch")
        if type(jobs) not in (tuple,list):
            raise NativeDurableBatchHold("finite typed batch jobs required")
        jobs=tuple(jobs)
        if not 1<=len(jobs)<=self.policy.maximum_jobs:
            raise NativeDurableBatchHold("batch size exceeds GGUF resource admission")
        if any(not isinstance(x,FabricJob) for x in jobs):
            raise NativeDurableBatchHold("typed approved jobs required")
        tasks=tuple(j.task for j in jobs)
        _,native_digest=self.native._check(batch_id,tasks)
        if len({x.task_id for x in tasks})!=len(tasks):
            raise NativeDurableBatchHold("duplicate task ID")
        # Priority and cohort are part of the durable operator decision,
        # not advisory post-admission fields that can change during resume.
        bound=fingerprint({
            "schema":"jeeves.native_durable_batch_binding.v1",
            "native_batch_sha256":native_digest,
            "jobs":[
                {"task_id":job.task.task_id,"cohort":job.cohort,
                 "priority":job.priority,"prompt_sha256":job.task.prompt_sha256}
                for job in jobs
            ],
        })
        return jobs,bound

    def admit(self,batch_id:str,jobs:Sequence[FabricJob]):
        """Atomically admit the entire approved batch, without inference.

        The header and ALL queued work orders commit in one canonical
        SQLite transaction. A crash before COMMIT leaves neither a header
        nor any task, avoiding partial source catalog ambiguity. Existing
        historical 'admitting' rows remain held for manual investigation.
        """
        jobs,batch_sha=self._preflight(batch_id,jobs)
        now=exact_integer(self.clock_ns(),maximum=10**30)
        orders=[]
        for job in jobs:
            session,request=self.native._session_key(
                batch_id,job.task.task_id,
            )
            orders.append(WorkOrder(
                order_id=self._order_key(batch_id,job.task.task_id),
                scope_sha256=self.scope.binding,
                tenant=self.identity.tenant,
                subject=self.identity.subject,
                model_sha256=self.identity.model_sha256,
                tokenizer_sha256=self.identity.tokenizer_sha256,
                session_id=session,
                request_id=request,
                prompt_sha256=job.task.prompt_sha256,
                seed=0,temperature=0.8,cohort=job.cohort,
                priority=job.priority,admitted_ns=now,
                expires_ns=now+self.policy.maximum_single_job_ms*1_000_000*len(jobs),
            ))
        with self.db.transaction() as conn:
            if conn.execute(
                "SELECT 1 FROM jeeves_native_durable_batches WHERE batch_id=?",
                (batch_id,),
            ).fetchone() is not None:
                raise NativeDurableBatchHold("batch ID previously consumed")
            conn.execute(
                "INSERT INTO jeeves_native_durable_batches VALUES "
                "(?,?,?,?,?,?,?,?,'admitting',?)",
                (batch_id,self.scope.binding,*self._scope(),
                 batch_sha,len(jobs),now),
            )
            # _insert_many reuses this exact private transaction; any
            # unique-ID collision or capacity hold rolls back header too.
            self.queue._insert_many(conn,tuple(orders))
            conn.execute(
                "UPDATE jeeves_native_durable_batches SET state='ready' "
                "WHERE batch_id=? AND state='admitting'",
                (batch_id,),
            )
            if conn.execute("SELECT changes()").fetchone()[0]!=1:
                raise NativeDurableBatchHold("batch could not finish admission")
        return self.inspect(batch_id,jobs)

    def _verify_jobs(self,batch_id,jobs):
        typed,expected=self._preflight(batch_id,jobs)
        with self.db.snapshot() as conn:
            row=self._batch(batch_id,conn)
            if row[5]!=expected or row[6]!=len(typed):
                raise NativeDurableBatchHold("batch input or budget changed after binding")
        return typed,expected

    def inspect(self,batch_id:str,jobs:Sequence[FabricJob]):
        typed,expected=self._verify_jobs(batch_id,jobs)
        counts={state:0 for state in (
            "queued","claimed","committed","held","cancelled",
        )}
        result=[]
        for job in typed:
            order=self.queue.inspect(
                self._order_key(batch_id,job.task.task_id),
            )
            if order["prompt_sha256"]!=job.task.prompt_sha256:
                raise NativeDurableBatchHold("order prompt differs from committed batch")
            counts[order["state"]]+=1
            result.append(order)
        return DurableBatchResult(
            batch_id,expected,counts["queued"],counts["claimed"],
            counts["committed"],counts["held"],counts["cancelled"],
            len(typed),tuple(result),
        )

    def execute_one(self,batch_id:str,job:FabricJob):
        """Exactly one owned native effect; no hidden retries or model fallback."""
        jobs,expected=self._verify_jobs(batch_id,(job,))
        # A single-member call cannot prove the complete original batch hash,
        # therefore execute_one cannot be used to bypass full batch approval.
        raise NativeDurableBatchHold(
            "execute via execute_admitted with complete approved batch inventory"
        )

    def execute_admitted(self,batch_id:str,jobs:Sequence[FabricJob],*,
                         maximum_new_calls:int=1):
        """Bounded wave from approved durable queue into canonical native model."""
        typed,_=self._verify_jobs(batch_id,jobs)
        exact_integer(maximum_new_calls,minimum=1,maximum=64)
        with self.db.snapshot() as conn:
            if self._batch(batch_id,conn)[7]!="ready":
                raise NativeDurableBatchHold("partial batch cannot start inference")
        todo=tuple(
            job for job in typed
            if self.queue.inspect(
                self._order_key(batch_id,job.task.task_id),
            )["state"]=="queued"
        )
        # Order strictly deterministic and bounded; no hidden auto-retry of
        # claimed, held, committed or cancelled prior work.
        todo=sorted(todo,key=lambda j:(-j.priority,j.task.task_id))
        receipts=[]
        for job in todo[:maximum_new_calls]:
            order_id=self._order_key(batch_id,job.task.task_id)
            claim=self.queue.claim(order_id)
            # Stable request and session identity must agree with the existing
            # native batch key before a single model effect is possible.
            session,request=self.native._session_key(batch_id,job.task.task_id)
            if claim.order.session_id!=session or claim.order.request_id!=request:
                raise NativeDurableBatchHold("native batch request key differs")
            native=self.native.run(batch_id,(job.task,))
            if len(native.receipts)!=1:
                raise NativeDurableBatchHold("missing authoritative native batch receipt")
            received=native.receipts[0]
            if (received.session_id!=session or received.request_id!=request
                or received.prompt_sha256!=job.task.prompt_sha256
                or received.task_id!=job.task.task_id):
                raise NativeDurableBatchHold("native output differs from operator work order")
            committed=self.queue.reconcile(
                claim,prompt=job.task.prompt,
            )
            if committed["native_output_sha256"]!=received.output_sha256:
                raise NativeDurableBatchHold("queue replay differs from native batch receipt")
            # Observational receipt only. A failure after native commit leaves
            # the native and queue as authoritative; telemetry may be recovered
            # separately without any new model generation.
            self.telemetry.record_committed(
                observation_id="nobs_"+sha256(order_id.encode("ascii")).hexdigest()[:40],
                session_id=session,request_id=request,prompt=job.task.prompt,
                seed=0,temperature=0.8,duration_ms=received.duration_ms,
            )
            receipts.append(received.to_public_record())
        return {
            "schema":"jeeves.native_durable_batch_wave.v1",
            "batch_id":batch_id,"processed":len(receipts),
            "observed_native_receipts":receipts,
            "status":self.inspect(batch_id,typed).to_public_record(),
            "automatic_native_retry":False,
            "release_certified":False,
        }

    def reconcile_orphans(
        self,batch_id:str,jobs:Sequence[FabricJob],*,
        operator_approved:bool,
    ):
        """Cold process read-only reconciliation; absolutely no inference."""
        if operator_approved is not True:
            raise NativeDurableBatchHold("operator must approve orphan review")
        typed,_=self._verify_jobs(batch_id,jobs)
        reconciled=[]
        for job in typed:
            order_id=self._order_key(batch_id,job.task.task_id)
            state=self.queue.inspect(order_id)["state"]
            if state in ("claimed","held"):
                record=self.queue.reconcile_orphaned(
                    order_id,prompt=job.task.prompt,operator_approved=True,
                )
                reconciled.append(record)
        return {
            "schema":"jeeves.native_durable_batch_reconciliation.v1",
            "batch_id":batch_id,
            "reconciled":len(reconciled),
            "observed_receipts":reconciled,
            "model_calls_started":0,
            "status":self.inspect(batch_id,typed).to_public_record(),
            "release_certified":False,
        }


__all__=["NativeDurableBatchHold","DurableBatchResult","NativeDurableBatchConveyor"]
