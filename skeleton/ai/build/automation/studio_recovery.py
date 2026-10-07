"""Recovery policy helpers for interrupted Studio transactions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Any

PHASES=("prepared","applied","validating","validated","committed")
@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str

def decide_recovery(journal: Mapping[str,Any], *, current_head: str) -> RecoveryDecision:
    phase=str(journal.get("phase",""))
    if phase not in PHASES: return RecoveryDecision("fail_closed","unknown transaction phase")
    if phase=="committed": return RecoveryDecision("retire_journal","transaction committed")
    base=str(journal.get("base_commit_sha",""))
    if not base or current_head != base: return RecoveryDecision("fail_closed","repository head changed")
    return RecoveryDecision("rollback","interrupted uncommitted transaction")
