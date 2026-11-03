"""Native genesis is never a runtime-serving admission authority."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import refuse

STAGES = {
    "requested": ("source_admitted","held"),
    "source_admitted": ("vocab_built","held"),
    "vocab_built": ("initialized","held"),
    "initialized": ("published_genesis","held"),
    "published_genesis": ("training","held"),
    "training": ("candidate_published","uncertain","held"),
    "candidate_published": ("candidate_review","held"),
    "candidate_review": ("held",),
    "uncertain": ("held",),
    "held": (),
}


@dataclass(frozen=True, slots=True)
class GenesisState:
    run_id: str
    stage: str = "requested"
    revision: int = 0

    def __post_init__(self) -> None:
        from .canonical import required_id
        required_id(self.run_id,"run")
        if self.stage not in STAGES or type(self.revision) is not int or self.revision < 0:
            refuse("genesis-state-invalid")

    def advance(self, next_stage: str) -> "GenesisState":
        if next_stage not in STAGES[self.stage]:
            refuse("genesis-transition-denied")
        return GenesisState(self.run_id,next_stage,self.revision+1)

    def report(self) -> dict:
        return {
            "run_id":self.run_id,"stage":self.stage,"revision":self.revision,
            "automatic_resume":False,"automatic_promotion":False,
            "production_authorized":False,
        }
