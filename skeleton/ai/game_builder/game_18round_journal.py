"""Persistent, replay-validated round-3..18 competitive game AI journal.

Transactions are compare-and-append; no skipped stages, optimistic stale
branch overwrites, doctored JSON, signature substitutions, or unsigned
model-promotion flags. SQLite WAL gives crash-consistent local custody;
the file is NOT an external tamper-proof ledger. Reopen validates every
entry against configured reviewer keys without storing secrets.
"""
from __future__ import annotations
from pathlib import Path
import sqlite3
import json
import hmac

from .contracts import canonical_digest,canonical_json
from .competitive_title_radar import ThreatRadarError
from .competitive_delivery_gate import TrustedCompetitionJudge,_mac
from .game_18round_relevance import OriginalTaskFocus
from .game_18round_evolution import (
    EvolutionRun,EvolutionRoundReceipt,begin_18round_evolution,
)
from .game_project_workspace import GameWorkspace

MAX_ROWS=16

def _pairs(values):
    body={}
    for k,v in values:
        if k in body:raise ThreatRadarError("duplicate keys in original-game evolution ledger")
        body[k]=v
    return body

class GameEvolutionJournal:
    def __init__(self,root: str|Path,*,task:OriginalTaskFocus):
        if not isinstance(task,OriginalTaskFocus):
            raise ThreatRadarError("exact current user task required for durable history")
        workspace=GameWorkspace(root)
        folder=workspace.root/"training"
        if folder.is_symlink() or not folder.is_dir():
            raise ThreatRadarError("unsafe game evolution ledger directory")
        location=folder/("18round_"+task.task_digest+".sqlite3")
        if location.is_symlink():
            raise ThreatRadarError("symlinked AI weight journal forbidden")
        self.location=location
        self.task=task
        self.db=sqlite3.connect(location,timeout=30,isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS ai_evolution_rounds(
                sequence INTEGER PRIMARY KEY,
                parent_digest TEXT NOT NULL,
                entry_digest TEXT NOT NULL UNIQUE,
                receipt_json TEXT NOT NULL,
                state_digest TEXT NOT NULL,
                shadow_approved INTEGER NOT NULL CHECK(shadow_approved IN (0,1))
            )
        """)

    def __enter__(self):return self
    def __exit__(self,*a):self.close()
    def close(self):self.db.close()

    def _load(self,signers:tuple[TrustedCompetitionJudge,...]):
        if (type(signers) is not tuple
                or any(not isinstance(s,TrustedCompetitionJudge) for s in signers)
                or len({s.judge_id for s in signers})!=len(signers)):
            raise ThreatRadarError("independent configured journal validation keys required")
        keys={s.judge_id:s for s in signers}
        state=begin_18round_evolution(self.task,authorized=True)
        rows=self.db.execute(
            "SELECT sequence,parent_digest,entry_digest,receipt_json,"
            "state_digest,shadow_approved FROM ai_evolution_rounds ORDER BY sequence"
        ).fetchall()
        if len(rows)>MAX_ROWS:raise ThreatRadarError("unexpected round history overflow")
        for i,(seq,parent,entry,serialized,state_hash,approved) in enumerate(rows):
            if seq!=i+1 or parent!=state.digest:
                raise ThreatRadarError("broken or missing chronological AI development link")
            try:
                obj=json.loads(serialized,object_pairs_hook=_pairs,
                               parse_constant=lambda v:(_ for _ in ()).throw(
                                   ThreatRadarError("nonfinite journal input")))
                receipt=EvolutionRoundReceipt(
                    obj["round_number"],obj["action_type"],
                    obj["project_task_digest"],obj["input_chain_digest"],
                    obj["report_digest"],tuple(obj["external_evidence_roots"]),
                    obj["status"],obj["research_reference_only"],
                    obj["reviewer_id"],obj["observed_at"],obj["signature"])
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                raise ThreatRadarError("invalid recorded game AI transition") from exc
            reviewer=keys.get(receipt.reviewer_id)
            if (reviewer is None
                    or not hmac.compare_digest(
                        receipt.signature,_mac(receipt.body(),reviewer.key))
                    or receipt.payload()!=obj
                    or serialized!=canonical_json(obj)
                    or receipt.digest!=entry
                    or receipt.round_number!=i+3
                    or receipt.project_task_digest!=self.task.task_digest
                    or receipt.input_chain_digest!=(
                        self.task.task_digest if not state.rounds
                        else state.rounds[-1].digest)):
                raise ThreatRadarError("source- and credential-bound campaign history corrupted")
            if (state.rounds and
                    receipt.observed_at<=state.rounds[-1].observed_at):
                raise ThreatRadarError("time-reversed game AI journal")
            if bool(approved)!=(state.shadow_approved_for_stage or
                                receipt.status=="verified_sandbox"):
                raise ThreatRadarError("staged shadow authority cannot appear or disappear without a verified round")
            # Signed per-round review was separately qualified by
            # accept_round before append. Replayed receipt integrity
            # guarantees it cannot change retroactively.
            state=EvolutionRun(
                self.task,state.rounds+(receipt,),bool(approved),False)
            if state.digest!=state_hash:
                raise ThreatRadarError("historic world and shadow queue state was changed")
        return state

    def read(self,*,signers:tuple[TrustedCompetitionJudge,...],
             authorized:bool)->EvolutionRun:
        if not authorized:raise PermissionError("journal reader needs operator approval")
        return self._load(signers)

    def append(
        self,before:EvolutionRun,after:EvolutionRun,*,
        signers:tuple[TrustedCompetitionJudge,...],
        authorized:bool,
    )->str:
        if not authorized:raise PermissionError("journal changes need explicit operator approval")
        if (not isinstance(before,EvolutionRun) or
                not isinstance(after,EvolutionRun) or
                before.task!=self.task or after.task!=self.task or
                len(after.rounds)!=len(before.rounds)+1 or
                after.rounds[:-1]!=before.rounds or
                after.user_model_activation_granted or
                len(after.rounds)>MAX_ROWS or
                (before.shadow_approved_for_stage and
                 not after.shadow_approved_for_stage)):
            raise ThreatRadarError("invalid original game staged progress append")
        receipt=after.rounds[-1]
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actual=self._load(signers)
            if actual.digest!=before.digest:
                raise ThreatRadarError("stale game evolution branch cannot overwrite current tip")
            if receipt.reviewer_id not in {x.judge_id for x in signers}:
                raise ThreatRadarError("unknown original-game AI review signer")
            payload=canonical_json(receipt.payload())
            self.db.execute(
                "INSERT INTO ai_evolution_rounds("
                "sequence,parent_digest,entry_digest,receipt_json,state_digest,shadow_approved)"
                "VALUES (?,?,?,?,?,?)",
                (len(after.rounds),before.digest,receipt.digest,payload,
                 after.digest,int(after.shadow_approved_for_stage)))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return after.digest

__all__=["GameEvolutionJournal"]
