"""Reconcile authoritative chat receipts with optional journal after restart."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..authority.canonical import ContractViolation
from .service import OfflineAIService


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    session:str
    turns:int
    journal_events:int
    audit_head:str
    missing_audits:int
    status:str


def inspect(service:OfflineAIService,session:str)->RecoveryReport:
    saved=service.store.load(session,service.actor.model_digest,service.actor.tokenizer_digest)
    journal=service.journal.replay(session)
    committed={event.payload["request_id"]:event for event in journal
               if event.kind=="ai.turn.committed"}
    # Validate all canonical turn receipts without inference. This remains
    # read-only; the caller decides whether to reconcile missing audit entries.
    with service.store.read_snapshot():
        rows=service.store._db.execute(
            "SELECT request_id,output_digest,revision FROM offline_turns WHERE session_id=? ORDER BY revision",
            (session,)).fetchall()
    if len(rows)!=saved.revision:
        raise ContractViolation("authoritative turn receipt loss")
    missing=0
    for rid,output_digest,revision in rows:
        entry=committed.get(rid)
        if entry is None:
            missing+=1
        elif entry.payload["output_digest"]!=output_digest or entry.payload["revision"]!=revision:
            raise ContractViolation("audit and conversation authority disagree")
    head=service.journal.head(session)
    return RecoveryReport(session,saved.revision,len(journal),head[1],missing,
                          "audit-incomplete" if missing else "verified")
