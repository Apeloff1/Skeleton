"""Fail-closed decision for resuming an interrupted autonomous build."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ResumeDecision:
 action:str;reason:str
def decide(*,saved_head:str,current_head:str,journal_phase:str|None,receipt_present:bool,baseline_matches:bool)->ResumeDecision:
 if saved_head!=current_head:return ResumeDecision("quarantine","repository head changed while build suspended")
 if not baseline_matches:return ResumeDecision("quarantine","accepted baseline identity changed")
 if journal_phase in {"prepared","applied","validating"}:return ResumeDecision("rollback_task","interrupted mutable transaction")
 if journal_phase=="validated" and not receipt_present:return ResumeDecision("reconcile_receipt","validated work lacks receipt")
 if journal_phase=="committed":return ResumeDecision("retire_journal","committed transaction survived")
 return ResumeDecision("continue","safe durable boundary")
