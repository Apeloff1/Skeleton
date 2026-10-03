"""Enumerate and verify recovery expectations for every mutation boundary."""
from __future__ import annotations
from dataclasses import dataclass
PHASES=("before_prepare","prepared","applied","validating","validated","committed","published")
@dataclass(frozen=True)
class CrashExpectation:
 phase:str;action:str;accepted_survives:bool
def expectation(phase:str)->CrashExpectation:
 if phase not in PHASES:raise ValueError("unknown crash phase")
 if phase in {"before_prepare"}:return CrashExpectation(phase,"restart",False)
 if phase in {"prepared","applied","validating"}:return CrashExpectation(phase,"rollback",False)
 if phase=="validated":return CrashExpectation(phase,"reconcile_receipt",True)
 if phase=="committed":return CrashExpectation(phase,"retire_journal",True)
 return CrashExpectation(phase,"verify_publication",True)
def matrix()->tuple[CrashExpectation,...]:return tuple(expectation(p) for p in PHASES)
