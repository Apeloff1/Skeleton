"""Explicit state machine preventing unqualified native SFT promotion."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import require_id,require_int
from .errors import reject

STAGES={
    "created":frozenset({"source_verified","held"}),
    "source_verified":frozenset({"bootstrapped","held"}),
    "bootstrapped":frozenset({"genesis_published","training","held"}),
    "genesis_published":frozenset({"training","held"}),
    "training":frozenset({"candidate_published","uncertain","held"}),
    "uncertain":frozenset({"held"}),
    "candidate_published":frozenset({"evaluating","held"}),
    "evaluating":frozenset({"review_pending","uncertain","held"}),
    "review_pending":frozenset({"held"}),
    "held":frozenset(),
}


@dataclass(frozen=True,slots=True)
class RunState:
    run_id:str
    stage:str="created"
    revision:int=0

    def __post_init__(self):
        require_id(self.run_id,"run")
        if self.stage not in STAGES:
            reject("run-stage")
        require_int(self.revision,"revision",0,1000000)

    def advance(self,next_stage:str)->"RunState":
        if next_stage not in STAGES[self.stage]:
            reject("run-transition")
        return RunState(self.run_id,next_stage,self.revision+1)

    def report(self)->dict:
        return {
            "run_id":self.run_id,"stage":self.stage,
            "revision":self.revision,
            "recover_uncertain_automatically":False,
            "automatic_model_activation":False,
        }
