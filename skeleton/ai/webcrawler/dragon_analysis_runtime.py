"""Durable fail-closed orchestration state for the Dragon analysis chain."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,sqlite3,math

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt,DEFAULT_CHAIN,validate_chain
from .dragon_analysis_execution import WorkerCapability,LayerDispatch,plan_analysis_execution


@dataclass(frozen=True)
class RunCheckpoint:
    owner:str
    run_id:str
    state:str
    revision:int
    chain_fingerprint:str
    cancelled:bool


class DragonAnalysisRuntime:
    """Persists receipts and leases one dependency-valid stage at a time."""

    def __init__(self,db:sqlite3.Connection):
        self.db=db
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_analysis_runs(
          owner TEXT NOT NULL,run_id TEXT NOT NULL,state TEXT NOT NULL,
          revision INTEGER NOT NULL,cancelled INTEGER NOT NULL DEFAULT 0,
          created_at REAL NOT NULL,updated_at REAL NOT NULL,
          PRIMARY KEY(owner,run_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_analysis_run_receipts(
          owner TEXT NOT NULL,run_id TEXT NOT NULL,layer TEXT NOT NULL,
          input_json TEXT NOT NULL,output_fingerprint TEXT NOT NULL,
          independent_sources INTEGER NOT NULL,passed INTEGER NOT NULL,
          human_approved INTEGER NOT NULL,
          PRIMARY KEY(owner,run_id,layer))""")
        db.commit()

    def create(self,owner:str,run_id:str,*,now:float,authorized:bool)->RunCheckpoint:
        if not authorized: raise PermissionError("analysis runtime requires authorization")
        if not owner or not run_id or not math.isfinite(now): raise ValueError("invalid run identity")
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO dragon_analysis_runs
              VALUES(?,?,?,0,0,?,?)""",(owner,run_id,"running",now,now))
        return self.checkpoint(owner,run_id,authorized=True)

    def _receipts(self,owner,run_id):
        rows=self.db.execute("""SELECT layer,input_json,output_fingerprint,
          independent_sources,passed,human_approved FROM dragon_analysis_run_receipts
          WHERE owner=? AND run_id=?""",(owner,run_id)).fetchall()
        return tuple(LayerReceipt(AnalysisLayer(x[0]),tuple(json.loads(x[1])),x[2],
            x[3],bool(x[4]),bool(x[5])) for x in rows)

    def checkpoint(self,owner:str,run_id:str,*,authorized:bool)->RunCheckpoint:
        if not authorized: raise PermissionError("checkpoint read requires authorization")
        row=self.db.execute("""SELECT state,revision,cancelled FROM dragon_analysis_runs
          WHERE owner=? AND run_id=?""",(owner,run_id)).fetchone()
        if not row: raise KeyError("analysis run not found")
        verdict=validate_chain(self._receipts(owner,run_id),authorized=True)
        return RunCheckpoint(owner,run_id,row[0],row[1],verdict.fingerprint,bool(row[2]))

    def cancel(self,owner:str,run_id:str,*,now:float,authorized:bool)->RunCheckpoint:
        if not authorized: raise PermissionError("cancellation requires authorization")
        with self.db:
            n=self.db.execute("""UPDATE dragon_analysis_runs SET cancelled=1,state='cancelled',
              revision=revision+1,updated_at=? WHERE owner=? AND run_id=? AND cancelled=0""",
              (now,owner,run_id)).rowcount
        if not n and not self.db.execute("SELECT 1 FROM dragon_analysis_runs WHERE owner=? AND run_id=?",
            (owner,run_id)).fetchone(): raise KeyError("analysis run not found")
        return self.checkpoint(owner,run_id,authorized=True)

    def next_dispatch(self,owner:str,run_id:str,capabilities:tuple[WorkerCapability,...],*,
                      authorized:bool)->LayerDispatch|None:
        cp=self.checkpoint(owner,run_id,authorized=authorized)
        if cp.cancelled or cp.state!="running": return None
        plan=plan_analysis_execution(self._receipts(owner,run_id),capabilities,
            authorized=True,max_dispatch=1)
        return plan.ready[0] if plan.ready else None

    def _commit_receipt_uncommitted(self,owner:str,run_id:str,receipt:LayerReceipt,*,now:float,
                                    expected_revision:int,authorized:bool)->RunCheckpoint:
        if not authorized: raise PermissionError("receipt commit requires authorization")
        row=self.db.execute("""SELECT state,revision,cancelled FROM dragon_analysis_runs
          WHERE owner=? AND run_id=?""",(owner,run_id)).fetchone()
        if not row: raise KeyError("analysis run not found")
        if row[2] or row[0]!="running": raise PermissionError("analysis run is not active")
        if row[1]!=expected_revision: raise RuntimeError("stale analysis checkpoint")
        current=self._receipts(owner,run_id)
        existing=next((x for x in current if x.layer is receipt.layer),None)
        if existing:
            if existing!=receipt: raise ValueError("receipt replay conflict")
            verdict=validate_chain(current,authorized=True)
            return RunCheckpoint(owner,run_id,row[0],row[1],verdict.fingerprint,bool(row[2]))
        candidate=current+(receipt,)
        verdict=validate_chain(candidate,authorized=True)
        if receipt.layer in verdict.rejected_layers:
            raise ValueError("receipt violates chain dependencies or acceptance policy")
        self.db.execute("""INSERT INTO dragon_analysis_run_receipts VALUES(?,?,?,?,?,?,?,?)""",
            (owner,run_id,receipt.layer.value,json.dumps(receipt.input_fingerprints),
             receipt.output_fingerprint,receipt.independent_sources,int(receipt.passed),
             int(receipt.human_approved)))
        state="complete" if verdict.complete else "running"
        self.db.execute("""UPDATE dragon_analysis_runs SET state=?,revision=revision+1,
          updated_at=? WHERE owner=? AND run_id=?""",(state,now,owner,run_id))
        return RunCheckpoint(owner,run_id,state,row[1]+1,verdict.fingerprint,False)

    def commit_receipt(self,owner:str,run_id:str,receipt:LayerReceipt,*,now:float,
                       expected_revision:int,authorized:bool)->RunCheckpoint:
        with self.db:
            return self._commit_receipt_uncommitted(owner,run_id,receipt,now=now,
                expected_revision=expected_revision,authorized=authorized)
