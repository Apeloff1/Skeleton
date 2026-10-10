"""Durable empirical outcomes for calibration and action-learning."""
from __future__ import annotations
from dataclasses import asdict
import hashlib,json
from .action_learning import ActionEconomics
class ResearchLearningStore:
 def __init__(self,db):self.db=db
 def put_action(self,row:ActionEconomics):
  with self.db:self.db.execute("INSERT INTO action_economics VALUES(?,?,?,?,?) ON CONFLICT(action_type) DO UPDATE SET attempts=excluded.attempts,successes=excluded.successes,mean_cost=excluded.mean_cost,mean_latency=excluded.mean_latency",(row.action_type,row.attempts,row.successes,row.mean_cost,row.mean_latency))
 def get_action(self,kind):
  r=self.db.execute("SELECT attempts,successes,mean_cost,mean_latency FROM action_economics WHERE action_type=?",(kind,)).fetchone()
  return ActionEconomics(kind,*r) if r else None
 def record_outcome(self,*,claim_id,predicted,actual,resolved_at,metadata=None):
  if not 0<=predicted<=1 or actual not in (0,1):raise ValueError("invalid calibration outcome")
  meta=json.dumps(metadata or {},sort_keys=True,separators=(",",":"))
  oid=hashlib.sha256(f"{claim_id}|{predicted:.12g}|{actual}|{resolved_at:.12g}|{meta}".encode()).hexdigest()
  with self.db:self.db.execute("INSERT OR IGNORE INTO calibration_outcomes VALUES(?,?,?,?,?)",(oid,predicted,actual,resolved_at,meta))
  return oid
 def calibration_rows(self):
  return tuple(self.db.execute("SELECT predicted,actual FROM calibration_outcomes ORDER BY resolved_at,outcome_id"))
